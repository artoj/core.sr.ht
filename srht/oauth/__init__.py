from flask import g, request, redirect, current_app
from functools import wraps
from srht.crypto import fernet
from srht.validation import Validation
from werkzeug.local import LocalProxy
import json

current_token = LocalProxy(lambda:
        g.current_oauth_token if "current_oauth_token" in g else None)
"""
Proxy for the currently authorized OAuth token. The type is implementation
defined, it's populated from the return value of
AbstractOAuthService.get_token.
"""

current_user = LocalProxy(lambda:
        g.current_user if "current_user" in g else None)
"""
Proxy for the currently authorzied user. The type is implementation defined,
it's populated from the return value of AbstractOAuthService.get_user.
"""

def login_user(user, set_cookie=False):
    g.current_user = user
    g.set_current_user = set_cookie

def logout_user():
    g.current_user = None
    g.set_current_user = True

def freshen_user():
    g.set_current_user = True

def loginrequired(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        from srht.oauth import UserType
        if not current_user:
            return redirect(current_app.oauth_service.oauth_url(request.url))
        elif current_user.user_type == UserType.suspended:
            return "Your account has been suspended. Contact support", 401
        else:
            return f(*args, **kwargs)
    return wrapper

class OAuthError(Exception):
    def __init__(self, err, *args, status=401, **kwargs):
        super().__init__(*args, **kwargs)
        if isinstance(err, dict):
            self.response = err, status
        else:
            valid = Validation(request)
            valid.error(err, status=status)
            self.response = valid.response
        self.status = status

from srht.oauth.client import OAuthClientMixin
from srht.oauth.token import OAuthTokenMixin, ExternalOAuthTokenMixin
from srht.oauth.user import UserMixin, UserType, ExternalUserMixin

from srht.oauth.blueprint import oauth_blueprint
from srht.oauth.decorator import oauth
from srht.oauth.scope import OAuthScope
from srht.oauth.interface import AbstractOAuthService, AbstractOAuthProvider
from srht.oauth.interface import DelegatedScope
