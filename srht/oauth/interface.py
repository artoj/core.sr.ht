import abc
import hashlib
import requests
import requests.exceptions
from collections import namedtuple
from datetime import datetime
from flask import current_app, url_for
from sqlalchemy.sql import text
from srht.api import get_results, ensure_webhooks
from srht.config import cfg, get_origin
from srht.crypto import encrypt_request_authorization
from srht.database import db
from srht.flask import DATE_FORMAT
from srht.oauth import OAuthError, ExternalUserMixin, UserType, OAuthScope
from urllib.parse import quote_plus
from werkzeug.local import LocalProxy

metasrht = get_origin("meta.sr.ht")

DelegatedScope = namedtuple("DelegatedScope",
        ["name", "description", "writable"])

class AbstractOAuthService(abc.ABC):
    """
    Implements hooks that sr.ht can use to authorize clients to an
    OAuth-enabled API.
    """
    def __init__(self, client_id, client_secret,
            required_scopes=["profile"], delegated_scopes=[],
            token_class=None, user_class=None, client_class=None):
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
        self.User = user_class
        self.OAuthToken = token_class
        self.OAuthClient = client_class

        self._get = (lambda *args, **kwargs:
                self._request("GET", *args, **kwargs))
        self._post = (lambda *args, **kwargs:
                self._request("POST", *args, **kwargs))
        self._delete = (lambda *args, **kwargs:
                self._request("DELETE", *args, **kwargs))

        if any(self.delegated_scopes):
            try:
                self._ensure_delegated()
            except requests.exceptions.ConnectionError:
                pass # Not important

    def _ensure_delegated(self):
        current = set()
        desired = set(self.delegated_scopes)
        ids = dict()
        resp = {"next": 1}
        while resp["next"] is not None:
            r = self._get(f"{metasrht}/api/delegate/scopes")
            if r.status_code != 200:
                print("Unable to ensure delegated scopes are " +
                    f"provisioned. Is {metasrht} reachable?")
                print("This may render the API unusable.")
                return
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

        origin = get_origin(current_app.site)
        revocation_url = origin + url_for("srht.oauth.revoke_delegated_token")
        _token = self.delegated_exchange(token, revocation_url)
        expires = datetime.strptime(_token["expires"], DATE_FORMAT)
        scopes = set(OAuthScope(s) for s in _token["scopes"].split(","))
        user = self.lookup_via_oauth(token, expires, _token["scopes"])
        db.session.flush()
        oauth_token = self.OAuthToken()
        oauth_token.user_id = user.id
        oauth_token.expires = expires
        oauth_token.token_partial = token[:8]
        oauth_token.token_hash = hashlib.sha512(token.encode()).hexdigest()
        oauth_token.scopes = scopes
        db.session.add(oauth_token)
        db.session.commit()
        return oauth_token

    def fetch_unknown_user(self, username):
        """Fetch an unknown user profile with internal authorization"""
        r = requests.get(f"{metasrht}/api/user/profile",
                headers=encrypt_request_authorization(user=
                    type("User", tuple(), {"username": username})))
        if r.status_code != 200:
            raise Exception(r.text)
        return r.json()

    def get_user(self, profile):
        """Get a user object from the meta.sr.ht user profile dict"""
        User = self.User
        # I hate SQLAlchemy SO FUCKING MUCH
        results = db.engine.execute(text("""
            INSERT INTO "user" (
                created, updated, username, email, user_type, url, location,
                bio, suspension_notice
            ) VALUES (
                NOW() at time zone 'utc',
                NOW() at time zone 'utc',
                :name, :email, :user_type, :url, :location, :bio, :suspension_notice
            )
            ON CONFLICT (username)
            DO UPDATE SET
                updated = NOW() at time zone 'utc',
                email = :email,
                user_type = :user_type,
                url = :url,
                location = :location,
                bio = :bio,
                suspension_notice = :suspension_notice
            RETURNING id, username, email, user_type, url, location, bio, suspension_notice;
        """), profile)
        row = results.fetchone()
        user = User()
        user.id = row[0]
        user.username = row[1]
        user.email = row[2]
        user.user_type = UserType(row[3])
        user.url = row[4]
        user.location = row[5]
        user.bio = row[6]
        user.suspension_notice = row[7]
        db.session.commit()
        # TODO: Add a version number or something so that we can add new
        # webhooks as necessary
        origin = get_origin(current_app.site)
        webhook_url = origin + url_for("srht.oauth.profile_update")
        self.ensure_meta_webhooks(user, {
            webhook_url: ["profile:update"],
        })
        return user

    def lookup_user(self, username):
        User = self.User
        user = User.query.filter(User.username == username).one_or_none()
        if user:
            return user
        try:
            profile = self.fetch_unknown_user(username)
        except:
            return None
        return self.get_user(profile)

    def ensure_meta_webhooks(self, user, webhooks):
        """
        Ensures that the given webhooks are rigged up with meta.sr.ht for this
        user. Webhooks should be a dict whose key is the webhook URL and whose
        values are the list of events to send to that URL.
        """
        try:
            ensure_webhooks(user, f"{metasrht}/api/user/webhooks", webhooks)
        except Exception as ex:
            print("Warning: failed to ensure meta.sr.ht webhooks:")
            print(ex)

    def lookup_via_oauth(self, token, token_expires, scopes):
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
        user = self.get_user(profile)
        user.oauth_token = token
        user.oauth_token_expires = token_expires
        user.oauth_token_scopes = scopes
        return user

    def delegated_exchange(self, token, revocation_url):
        """
        Validates an OAuth token with meta.sr.ht and returns a tuple of
        meta.sr.ht's responses: token, profile. Raises an OAuthError if anything
        goes wrong.
        """
        try:
            r = requests.post("{}/oauth/token/verify".format(metasrht),
                json={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "revocation_url": revocation_url,
                    "oauth_token": token,
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
            get_origin("meta.sr.ht", external=True), self.client_id,
            ','.join(self.required_scopes + scopes), quote_plus(return_to))

    def profile_update_hook(self, user, payload):
        if "user_type" in payload:
            user.user_type = UserType(payload["user_type"])
            user.suspension_notice = payload["suspension_notice"]
        user.email = payload["email"]
        user.bio = payload["bio"]
        user.location = payload["location"]
        user.url = payload["url"]
        db.session.commit()

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
