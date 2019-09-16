from flask import current_app, request, g
from functools import wraps
from srht.config import cfg
from srht.oauth import OAuthError, UserType
from srht.oauth.scope import OAuthScope
from srht.validation import Validation
import hashlib
import requests

def oauth(scopes):
    """
    Validates OAuth authorization for a wrapped function. Scopes should be a
    string-formatted list of required scopes, or None if no particular scopes
    are required.
    """
    def wrap(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            token = request.headers.get('Authorization')
            valid = Validation(request)
            if not token or not token.startswith('token '):
                return valid.error("No authorization supplied (expected an "
                    "OAuth token)", status=401)

            token = token.split(' ')
            if len(token) != 2:
                return valid.error("Invalid authorization supplied", status=401)

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
