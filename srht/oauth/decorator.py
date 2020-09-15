from datetime import datetime, timedelta
from flask import current_app, request, g, abort
from functools import wraps
from srht.config import cfg, get_origin
from srht.crypto import encrypt_request_authorization
from srht.crypto import verify_encrypted_authorization
from srht.database import db
from srht.oauth import OAuthError, UserType
from srht.oauth.scope import OAuthScope
from srht.validation import Validation
import hashlib
import requests

metasrht = get_origin("meta.sr.ht")

def _internal_auth(f, auth, *args, **kwargs):
    # Used for authenticating internal API users, like other sr.ht sites.
    oauth_service = current_app.oauth_service
    OAuthClient = oauth_service.OAuthClient
    OAuthToken = oauth_service.OAuthToken
    User = oauth_service.User

    auth = verify_encrypted_authorization(auth)
    client_id = auth["client_id"]
    username = auth.get("name", auth.get("username"))
    assert username

    # Create a synthetic OAuthToken based on the client ID and username
    token = client_id
    token_hash = hashlib.sha512((token + username).encode()).hexdigest()
    oauth_token = OAuthToken.query.filter(
            OAuthToken.token_hash == token_hash).one_or_none()
    if not oauth_token:
        user = User.query.filter(User.username == username).one_or_none()
        if user == None:
            # The request issuer is asking about a user which doesn't exist
            # XXX: Is this because the service wasn't notified about an
            # account deletion? Should we tell them?
            assert current_app.site != "meta.sr.ht"
            profile = oauth_service.fetch_unknown_user(username)
            user = oauth_service.get_user(profile)
        oauth_token = OAuthToken()
        oauth_token.user = user
        oauth_token.user_id = user.id
        # Note: the expiration is meaningless
        oauth_token.expires = datetime.utcnow() + timedelta(days=9999)
        if hasattr(oauth_token, "client_id"):
            client = OAuthClient.query.filter(
                    OAuthClient.client_id == client_id).one_or_none()
            assert client, f"Client ID {client_id} missing"
            oauth_token.client = client
            oauth_token.client_id = client.id
        oauth_token.token_hash = token_hash
        oauth_token.token_partial = "internal"
        oauth_token._scopes = "*"
        db.session.add(oauth_token)
        db.session.commit()

    g.current_oauth_token = oauth_token
    return f(*args, **kwargs)

def oauth(scopes):
    """
    Validates OAuth authorization for a wrapped function. Scopes should be a
    string-formatted list of required scopes, or None if no particular scopes
    are required.
    """
    def wrap(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            internal = request.headers.get('X-Srht-Authorization')
            if internal:
                return _internal_auth(f, internal, *args, **kwargs)

            token = request.headers.get('Authorization')
            valid = Validation(request)
            if not token or not (token.startswith('token ')
                    or token.startswith('Bearer ')
                    or token.startswith('Internal ')):
                return valid.error("No authorization supplied (expected an "
                    "OAuth token)", status=401)

            token = token.split(' ')
            if len(token) != 2:
                return valid.error("Invalid authorization supplied", status=401)

            if token[0] == "Internal":
                return _internal_auth(f, token[1], *args, **kwargs)

            token = token[1]
            token_hash = hashlib.sha512(token.encode()).hexdigest()

            try:
                if scopes:
                    required = OAuthScope(scopes)
                    required.client_id = current_app.oauth_service.client_id
                else:
                    required = None
            except OAuthError as err:
                return err.response

            try:
                oauth_token = current_app.oauth_service.get_token(
                        token, token_hash, required)
            except OAuthError as err:
                return err.response

            if not oauth_token:
                return valid.error("Invalid or expired OAuth token", status=401)

            g.current_oauth_token = oauth_token

            if oauth_token.scopes == "*" or scopes is None:
                return f(*args, **kwargs)

            applicable = [s for s in oauth_token.scopes if s.fulfills(required)]
            if not any(applicable):
                return valid.error("Your OAuth token is not permitted to use " +
                    "this endpoint (needs {})".format(required), status=403)

            if oauth_token.user.user_type == UserType.suspended:
                return valid.error("The authorized user's account has been " +
                    "suspended with the following notice: \n" +
                    oauth_token.user.suspension_notice + "\n" +
                    "Contact support: " + cfg("sr.ht", "owner-email"),
                    status=403)

            if oauth_token.user.user_type == UserType.unconfirmed:
                return valid.error("The authorized user's account has not " +
                    "been confirmed.", status=403)

            return f(*args, **kwargs)
        return wrapper
    return wrap
