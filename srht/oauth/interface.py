import abc
import requests
from collections import namedtuple
from datetime import datetime
from srht.config import cfg
from srht.database import db
from srht.oauth import OAuthError, OAuthTokenMixin
from werkzeug.local import LocalProxy
from urllib.parse import quote_plus

metasrht = cfg("meta.sr.ht", "origin")

DelegatedScope = namedtuple("DelegatedScope",
        ["name", "description", "writable"])

class AbstractOAuthService(abc.ABC):
    """
    Implements hooks that sr.ht can use to authorize clients to an
    OAuth-enabled API.
    """
    def __init__(self, client_id, client_secret,
            required_scopes=["profile"], delegated_scopes=[],
            token_class=None, user_class=None):
        """
        required_scopes: list of scopes (in string form) to request from
        meta.sr.ht when authenticating web users

        delegated_scopes: list of DelegatedScopes for delegated OAuth with
        meta.sr.ht when authenticating API clients
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.required_scopes = required_scopes
        self.delegated_scopes = delegated_scopes
        self.OAuthToken = token_class
        self.User = user_class

        self._get = (lambda *args, **kwargs:
                self._request("GET", *args, **kwargs))
        self._post = (lambda *args, **kwargs:
                self._request("POST", *args, **kwargs))
        self._delete = (lambda *args, **kwargs:
                self._request("DELETE", *args, **kwargs))

        if any(self.delegated_scopes):
            self._ensure_delegated()

    def _ensure_delegated(self):
        current = set()
        desired = set(self.delegated_scopes)
        ids = dict()
        resp = {"next": 1}
        while resp["next"] is not None:
            r = self._get(f"{metasrht}/api/delegate/scopes")
            if r.status_code != 200:
                raise Exception("Unable to ensure delegated scopes are provisioned.")
            resp = r.json()
            for scope in resp["results"]:
                ids[scope["name"]] = scope["id"]
                current.update([DelegatedScope(
                    scope["name"], scope["description"], scope["writable"])])
        to_remove = current - desired
        to_add = desired - current
        for scope in to_remove:
            self._delete(f"{metasrht}/api/delegate/scopes/{ids[scope.name]}")
        for scope in to_add:
            self._post(f"{metasrht}/api/delegate/scopes", json={
                "name": scope.name,
                "description": scope.description,
                "writable": scope.writable,
            })

    def _request(self, *args, **kwargs):
        headers = kwargs.pop("headers", dict())
        headers.update({
            "X-OAuth-ID": self.client_id,
            "X-OAuth-Secret": self.client_secret,
        })
        return requests.request(*args, headers=headers, **kwargs)

    def get_token(self, token, token_hash, scopes):
        """Fetch an OAuth token given the provided token & token_hash."""
        now = datetime.utcnow()
        oauth_token = (self.OAuthToken.query
            .filter(self.OAuthToken.token_hash == token_hash)
            .filter(self.OAuthToken.expires > now)
        ).first()
        if oauth_token:
            oauth_token.updated = now
            db.session.commit()
        return oauth_token

    def lookup_or_register(self, exchange, profile, scopes):
        """
        Used to lookup or register web users authenticating via delegated OAuth.
        Return the user object; it must fulfill flask_login's user class
        contract.
        """
        pass

    def exchange(self, token, revocation_url):
        """
        Validates an OAuth token with meta.sr.ht and returns a tuple of
        meta.sr.ht's responses: token, profile. Raises an OAuthError if anything
        goes wrong.
        """
        try:
            r = requests.post("{}/oauth/token/{}".format(metasrht, token),
                json={
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
            r = requests.get("{}/api/user/profile".format(metasrht), headers={
                "Authorization": "token {}".format(token)
            })
            profile = r.json()
        except Exception as ex:
            print(ex)
            raise OAuthError("Temporary authentication failure", status=500)
        if r.status_code != 200:
            raise OAuthError(profile, status=r.status_code)
        return _token, profile

    def oauth_url(self, return_to, scopes=[]):
        return "{}/oauth/authorize?client_id={}&scopes={}&state={}".format(
            metasrht, self.client_id, ','.join(self.required_scopes + scopes),
            quote_plus(return_to))

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
