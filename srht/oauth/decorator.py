from flask import request, g
from functools import wraps
from srht.oauth import OAuthError
from srht.oauth.scope import OAuthScope
from srht.oauth.interface import base_service
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
                    required.client_id = base_service.client_id
                else:
                    required = None
            except OAuthError as err:
                return err.response

            try:
                oauth_token = base_service.get_token(token, token_hash, required)
            except OAuthError as err:
                return err.response

            if not oauth_token:
                return valid.error("Invalid or expired OAuth token", status=401)

            g.current_oauth_token = oauth_token

            if oauth_token.scopes == "*" or scopes is None:
                return f(*args, **kwargs)

            available = [OAuthScope(s) for s in oauth_token.scopes.split(',')]
            applicable = [s for s in available if s.fulfills(required)]
            if not any(applicable):
                return valid.error("Your OAuth token is not permitted to use " +
                    "this endpoint (needs {})".format(required), status=403)

            return f(*args, **kwargs)
        return wrapper
    return wrap
