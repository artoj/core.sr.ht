from datetime import datetime
from flask import Blueprint, request, redirect, render_template, current_app
from flask_login import login_user, logout_user
from srht.config import cfg, get_origin
from srht.crypto import verify_request_signature
from srht.database import db
from srht.flask import csrf_bypass
from srht.oauth.scope import OAuthScope
from srht.oauth import OAuthError
import base64
import json
import requests
import urllib

oauth_blueprint = Blueprint('srht.oauth', __name__)

@oauth_blueprint.route("/oauth/callback")
def oauth_callback():
    error = request.args.get("error")
    if error:
        details = request.args.get("details")
        return render_template("oauth-error.html", details=details)
    exchange_token = request.args.get("exchange")
    scopes = request.args.get("scopes")
    state = request.args.get("state")
    _scopes = [OAuthScope(s) for s in scopes.split(",")]
    if not OAuthScope("profile:read") in _scopes:
        return render_template("oauth-error.html",
            details=("This application requires profile access at a mininum " +
                "to function correctly. " +
                "Try again and do not untick these permissions."))
    if not exchange_token:
        return render_template("oauth-error.html",
            details=("Expected an exchange token from meta.sr.ht. " +
                "Something odd has happened, try again."))
    meta_uri = get_origin("meta.sr.ht")
    r = requests.post(meta_uri + "/oauth/exchange", json={
        "client_id": current_app.oauth_service.client_id,
        "client_secret": current_app.oauth_service.client_secret,
        "exchange": exchange_token,
    })
    if r.status_code != 200:
        return render_template("oauth-error.html",
            details="Error occured retrieving OAuth token. Try again.")
    exchange = r.json()
    token = exchange.get("token")
    expires = exchange.get("expires")
    if not token or not expires:
        return render_template("oauth-error.html",
            details="Error occured retrieving OAuth token. Try again.")

    try:
        user = current_app.oauth_service.lookup_or_register(
                token, expires, scopes)
    except OAuthError:
        return render_template("oauth-error.html",
            details="Error occured retrieving account info. Try again.")

    db.session.commit()
    login_user(user, remember=True)
    if not state or not state.startswith("/"):
        return redirect("/")
    else:
        return redirect(urllib.parse.unquote(state))

@oauth_blueprint.route("/logout")
def logout():
    logout_user()
    return redirect(request.headers.get("Referer") or "/")

@oauth_blueprint.route("/oauth/revoke/<revocation_token>")
def revoke(revocation_token):
    OAuthToken = current_app.oauth_service.OAuthToken
    User = current_app.oauth_service.User
    user = User.query.filter(
            User.oauth_revocation_token == revocation_token).one_or_none()
    if not user:
        abort(404)
    OAuthToken.query.filter(OAuthToken.user_id == user.id).delete()
    db.session.commit()
    return {}

@oauth_blueprint.route("/oauth/webhook/profile-update", methods=["POST"])
@csrf_bypass
def profile_update():
    verify_request_signature()
    profile = json.loads(payload.decode('utf-8'))
    User = current_app.oauth_service.User
    user = User.query.filter(User.username == profile["name"]).one_or_none()
    if not user:
        return "Unknown user.", 404
    current_app.oauth_service.profile_update_hook(user, profile)
    return f"Profile updated for {user.username}."
