import abc
from functools import wraps
from flask import request
import hashlib
from srht.validation import Validation

class AbstractOAuthService(abc.ABC):
    """
    Implements hooks that sr.ht can use to authorize clients to an
    OAuth-enabled API.
    """

    @abc.abstractmethod
    def get_token(self, token_hash, scopes):
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
    def __init__(self, scope):
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
        return self.description or ""

def oauth(scopes):
    def wrap(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            token = request.headers.get('Authorization')
            valid = Validation(request)
            if not token or not token.startswith('token '):
                return valid.error("No authorization supplied (expected an " +
                    "OAuth token)", status=401)
            token = token.split(' ')
            if len(token) != 2:
                return valid.error("Invalid authorization supplied", status=401)
            token = token[1]
            token_hash = hashlib.sha512(token.encode()).hexdigest()
            try:
                required = OAuthScope(scopes)
            except Exception as ex:
                return valid.error(str(ex))
            oauth_token = _base_service.get_token(token_hash, required)
            if not oauth_token:
                return valid.error("Invalid or expired OAuth token", status=401)
            args = (oauth_token,) + args
            if oauth_token.scopes == "*":
                return f(*args, **kwargs)
            available = [OAuthScope(s) for s in oauth_token.scopes.split(',')]
            applicable = [
                s for s in available
                if s.client_id == required.client_id and s.scope == required.scope
            ]
            if not any(applicable):
                return valid.error("Your OAuth token is not permitted to use " +
                    "this endpoint (needs {})".format(required), status=403)
            if (required.access == 'read'
                    and any([s for s in applicable
                        if s.access == 'read' or s.access == 'write'])):
                return f(*args, **kwargs)
            if (required.access == 'write'
                    and any([s for s in applicable if s.access == 'write'])):
                return f(*args, **kwargs)
            return valid.errors("Your OAuth token is not permitted to use " +
                "this endpoint (needs {})".format(required), status=403)
        return wrapper
    return wrap
