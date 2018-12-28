from datetime import datetime
from flask import Blueprint, request, redirect, render_template, current_app
from flask_login import login_user, logout_user
from srht.config import cfg
from srht.oauth.scope import OAuthScope
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
    meta_uri = cfg("meta.sr.ht", "origin")
    r = requests.post(meta_uri + "/oauth/exchange", json={
        "client_id": current_app.login_config.client_id,
        "client_secret": current_app.login_config.client_secret,
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
    from srht.flask import DATE_FORMAT
    expires = datetime.strptime(expires, DATE_FORMAT)

    r = requests.get(meta_uri + "/api/user/profile", headers={
        "Authorization": "token " + token
    })
    if r.status_code != 200:
        return render_template("oauth-error.html",
            details="Error occured retrieving account info. Try again.")
    
    profile = r.json()
    user = current_app.lookup_or_register(exchange, profile, scopes)

    login_user(user, remember=True)
    if not state or not state.startswith("/"):
        return redirect("/")
    else:
        return redirect(urllib.parse.unquote(state))

@oauth_blueprint.route("/logout")
def logout():
    logout_user()
    return redirect(request.headers.get("Referer") or "/")
