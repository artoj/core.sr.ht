from flask import g
from srht.validation import Validation
from werkzeug.local import LocalProxy

current_token = LocalProxy(lambda:
        g.current_oauth_token if "current_oauth_token" in g else None)
"""
Proxy for the currently authorized OAuth token. The type is implementation
defined, it's populated from the return value of
AbstractOAuthService.get_token.
"""

class OAuthError(Exception):
    def __init__(self, err, *args, status=401, **kwargs):
        super().__init__(*args, **kwargs)
        if isinstance(err, dict):
            self.response = err
        else:
            valid = Validation(request)
            valid.error(err)
            self.response = valid.response
        self.status = status

from srht.oauth.blueprint import oauth_blueprint
from srht.oauth.decorator import oauth
from srht.oauth.exchange import delegated_exchange
from srht.oauth.scope import OAuthScope
from srht.oauth.interface import AbstractOAuthService, AbstractOAuthProvider
from srht.oauth.interface import set_base_service, set_base_provider

# TEMP (compatibility):
meta_delegated_exchange = delegated_exchange
