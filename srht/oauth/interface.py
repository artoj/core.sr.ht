import abc
import hashlib
import os
import requests
from collections import namedtuple
from datetime import datetime
from flask import current_app, url_for
from srht.config import cfg
from srht.api import get_results
from srht.database import db
from srht.flask import DATE_FORMAT
from srht.oauth import OAuthError, ExternalUserMixin, UserType, OAuthScope
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
                raise Exception("Unable to ensure delegated scopes are " +
                    f"provisioned. Is {metasrht} reachable?")
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

    def _preauthorized_warning(self):
        print(f"""
Warning: unable to determine user_type from meta.sr.ht.

If you are the admin of {metasrht}, run the following SQL to correct this:

    UPDATE oauthclient
    SET preauthorized = 't'
    WHERE client_id = '{self.client_id}';
""")

    def get_token(self, token, token_hash, scopes):
        """Fetch an OAuth token given the provided token & token_hash."""
        # TODO: rig up webhook(?)
        now = datetime.utcnow()
        oauth_token = (self.OAuthToken.query
            .filter(self.OAuthToken.token_hash == token_hash)
            .filter(self.OAuthToken.expires > now)
        ).one_or_none()
        if oauth_token:
            oauth_token.updated = now
            db.session.commit()
            return oauth_token
        if not self.User or not issubclass(self.User, ExternalUserMixin):
            return oauth_token
        revocation_token = hashlib.sha512(os.urandom(16)).hexdigest()
        origin = cfg(current_app.site, "origin")
        revocation_url = origin + url_for("srht.oauth.revoke",
                revocation_token=revocation_token)
        _token = self.delegated_exchange(token, revocation_url)
        expires = datetime.strptime(_token["expires"], DATE_FORMAT)
        scopes = set(OAuthScope(s) for s in _token["scopes"].split(","))
        user = self.lookup_or_register(token, expires, _token["scopes"])
        db.session.flush()
        user.oauth_revocation_token = revocation_token
        oauth_token = self.OAuthToken()
        oauth_token.user_id = user.id
        oauth_token.expires = expires
        oauth_token.token_partial = token[:8]
        oauth_token.token_hash = hashlib.sha512(token.encode()).hexdigest()
        oauth_token.scopes = scopes
        db.session.add(oauth_token)
        db.session.commit()
        return oauth_token

    def ensure_webhook(self, user):
        origin = cfg(current_app.site, "origin")
        webhook_url = origin + url_for("srht.oauth.profile_update")
        events = ["profile:update"]
        for webhook in get_results(f"{metasrht}/api/user/webhooks",
                user.oauth_token):
            if webhook["url"] != webhook_url:
                continue
            if webhook["events"] == events:
                return # Webhook already configured
            # This webhook is set up incorrectly, delete it
            url = f"{metasrht}/api/user/webhooks/{webhook['id']}"
            r = requests.delete(url, headers={
                "Authorization": f"token {user.oauth_token}",
            })
            if r.status_code != 200:
                print("Warning: failed to remove invalid webhook for "
                    f"{user.username}: {r.text}")
                return
        r = requests.post(f"{metasrht}/api/user/webhooks", headers={
            "Authorization": f"token {user.oauth_token}",
        }, json={
            "events": events,
            "url": webhook_url,
        })
        if r.status_code != 200:
            print(f"Warning: failed to create webhook for {user.username}: "
                    f"{r.text}")

    def lookup_or_register(self, token, token_expires, scopes):
        User = self.User
        try:
            r = requests.get(f"{metasrht}/api/user/profile", headers={
                "Authorization": f"token {token}",
            })
            profile = r.json()
        except Exception as ex:
            print(ex)
            raise OAuthError("Temporary authentication failure", status=500)
        if r.status_code != 200:
            raise OAuthError(profile, status=r.status_code)

        user = User.query.filter(User.username == profile["name"]).one_or_none()
        if not user:
            user = User()
            user.username = profile["name"]
            db.session.add(user)
        if "user_type" in profile:
            user.user_type = UserType(profile["user_type"])
        else:
            self._preauthorized_warning()
            user.user_type = UserType.unknown
        user.email = profile["email"]
        user.bio = profile["bio"]
        user.location = profile["location"]
        user.url = profile["url"]
        user.oauth_token = token
        user.oauth_token_expires = token_expires
        user.oauth_token_scopes = scopes
        try:
            self.ensure_webhook(user)
        except Exception as ex:
            print(f"Error ensuring webhook for {user.username}: {str(ex)}")
        return user

    def delegated_exchange(self, token, revocation_url):
        """
        Validates an OAuth token with meta.sr.ht and returns a tuple of
        meta.sr.ht's responses: token, profile. Raises an OAuthError if anything
        goes wrong.
        """
        try:
            r = requests.post("{}/oauth/token/{}".format(metasrht, token),
                json={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "revocation_url": revocation_url,
                })
            _token = r.json()
        except Exception as ex:
            print(ex)
            raise OAuthError("Temporary authentication failure", status=500)
        if r.status_code != 200:
            raise OAuthError(_token, status=r.status_code)
        return _token

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
