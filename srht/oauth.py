from datetime import datetime
from flask import Blueprint, request, redirect, render_template, current_app, g
from flask_login import login_user, logout_user
from functools import wraps
from werkzeug.local import LocalProxy
import abc
import hashlib
import requests
import urllib

from srht.validation import Validation
from srht.config import cfg

current_token = LocalProxy(lambda:
        g.current_oauth_token if "current_oauth_token" in g else None)

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

class AbstractOAuthService(abc.ABC):
    """
    Implements hooks that sr.ht can use to authorize clients to an
    OAuth-enabled API.
    """

    @abc.abstractmethod
    def get_client_id(self):
        """
        Used to add your client ID to scopes with no client ID set.
        """
        pass

    @abc.abstractmethod
    def get_token(self, token, token_hash, scopes):
        """
        Get or create an OAuthToken object. We don't do anything with it but
        hand it back to you; the type can be anything that you find useful.
        """
        pass

class AbstractOAuthProvider(abc.ABC):
    """
    Implements hooks that sr.ht can use to resolve OAuth tokens issued by a
    provider.
    """

    @abc.abstractmethod
    def resolve_scope(self, scope):
        """
        Given a parsed scope, validate its correctness (possibly against your
        database of valid clients, etc) and add any extra metadata you wish.
        Throw exceptions if anything is wrong.
        """
        pass

    @abc.abstractmethod
    def get_alias(self, client_id):
        """
        Given a client_id alias, return the actual client_id (or None).
        """
        pass

_base_service = None
_base_provider = None

def set_base_service(base_service):
    global _base_service
    _base_service = base_service

def set_base_provider(base_provider):
    global _base_provider
    _base_provider = base_provider

class OAuthScope:
    def __init__(self, scope, resolve=True):
        client_id = None
        access = 'read'
        if scope == "*":
            access = 'write'
        if '/' in scope:
            s = scope.split('/')
            if len(s) != 2:
                raise Exception('Invalid OAuth scope syntax')
            client_id = s[0]
            scope = s[1]
        if ':' in scope:
            s = scope.split(':')
            if len(s) != 2:
                raise Exception('Invalid OAuth scope syntax')
            scope = s[0]
            access = s[1]
        alias = _base_provider and _base_provider.get_alias(client_id)
        if not access in ['read', 'write']:
            raise Exception('Invalid scope access {}'.format(access))
        self.client_id = alias or client_id
        self.scope = scope
        self.access = access
        if resolve:
            _base_provider and _base_provider.resolve_scope(self)

    def __eq__(self, other):
        return self.client_id == other.client_id \
                and self.access == other.access \
                and self.scope == other.scope

    def __repr__(self):
        if self.client_id:
            return '{}/{}:{}'.format(self.client_id, self.scope, self.access)
        return '{}:{}'.format(self.scope, self.access)

    def __hash__(self):
        return hash((self.client_id if self.client_id else None, self.scope, self.access))

    def readver(self):
        if self.client:
            return '{}/{}:{}'.format(self.client_id, self.scope, 'read')
        return '{}:{}'.format(self.scope, 'read')

    def fulfills(self, want):
        if self.scope == "*":
            if want.access == "read":
                return True
            return self.access == "write"
        else:
            return (
                self.scope == want.scope and
                self.client_id == want.client_id and
                self.access == "write" if want.access == "write" else True
            )

    def friendly(self):
        return self.description if hasattr(self, "description") else self.scope

def oauth(scopes):
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
                required = OAuthScope(scopes)
                required.client_id = _base_service.get_client_id()
            except OAuthError as err:
                return err.response

            try:
                oauth_token = _base_service.get_token(token, token_hash, required)
            except OAuthError as err:
                return err.response

            if not oauth_token:
                return valid.error("Invalid or expired OAuth token", status=401)

            g.current_oauth_token = oauth_token

            args = (oauth_token,) + args
            if oauth_token.scopes == "*":
                return f(*args, **kwargs)

            available = [OAuthScope(s) for s in oauth_token.scopes.split(',')]
            applicable = [s for s in available if s.fulfills(required)]
            if not any(applicable):
                return valid.error("Your OAuth token is not permitted to use " +
                    "this endpoint (needs {})".format(required), status=403)

            return f(*args, **kwargs)
        return wrapper
    return wrap

def meta_delegated_exchange(token, client_id, client_secret, revocation_url):
    """
    Validates an OAuth token with meta.sr.ht and returns a tuple of
    meta.sr.ht's responses: token, profile. Raises an OAuthError if anything
    goes wrong.
    """
    meta_uri = cfg("meta.sr.ht", "origin")
    try:
        r = requests.post("{}/oauth/token/{}".format(meta_uri, token), json={
            "client_id": client_id,
            "client_secret": client_secret,
            "revocation_url": revocation_url
        })
        _token = r.json()
    except Exception as ex:
        print(ex)
        raise OAuthError("Temporary authentication failure", status=500)
    if r.status_code != 200:
        raise OAuthError(_token, status=r.status_code)
    try:
        r = requests.get("{}/api/user/profile".format(meta_uri), headers={
            "Authorization": "token {}".format(token)
        })
        profile = r.json()
    except Exception as ex:
        print(ex)
        raise OAuthError("Temporary authentication failure", status=500)
    if r.status_code != 200:
        raise OAuthError(profile, status=r.status_code)
    return _token, profile

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
