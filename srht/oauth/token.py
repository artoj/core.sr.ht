from datetime import datetime, timedelta
from sqlalchemy.ext.declarative import declared_attr
from srht.oauth.scope import OAuthScope
import binascii
import hashlib
import sqlalchemy as sa

class BaseOAuthTokenMixin:
    @declared_attr
    def __tablename__(cls):
        return "oauthtoken"

    id = sa.Column(sa.Integer, primary_key=True)
    created = sa.Column(sa.DateTime, nullable=False)
    updated = sa.Column(sa.DateTime, nullable=False)
    expires = sa.Column(sa.DateTime, nullable=False)
    token_hash = sa.Column(sa.String(128), nullable=False)
    token_partial = sa.Column(sa.String(8), nullable=False)
    _scopes = sa.Column(sa.String(512), nullable=False, name="scopes")

    @property
    def scopes(self):
        return [OAuthScope(s) for s in self._scopes.split(",")]

    @scopes.setter
    def scopes(self, value):
        assert all(isinstance(s, OAuthScope) for s in value)
        self._scopes = ",".join(str(s) for s in value)

    @declared_attr
    def user_id(cls):
        return sa.Column(sa.Integer, sa.ForeignKey('user.id'))

    @declared_attr
    def user(cls):
        return sa.orm.relationship('User',
            backref=sa.orm.backref('oauth_tokens'))

    def authorized_for(self, scope):
        return any(s.fulfills(scope) for s in self.scopes)

class ExternalOAuthTokenMixin(BaseOAuthTokenMixin):
    def __init__(self, user, token, expires):
        self.user_id = user.id
        self.expires = datetime.now() + timedelta(days=365)
        self.token_partial = token[:8]
        self.token_hash = hashlib.sha512(token.encode()).hexdigest()

class OAuthTokenMixin(BaseOAuthTokenMixin):
    @declared_attr
    def __table_args__(cls):
        return (sa.UniqueConstraint('client_id', 'user_id',
                name='client_user_unique'),)

    @declared_attr
    def client_id(cls):
        return sa.Column(sa.Integer,
            sa.ForeignKey('oauthclient.id', ondelete="CASCADE"))

    @declared_attr
    def client(cls):
        return sa.orm.relationship('OAuthClient',
            backref=sa.orm.backref('tokens', cascade='all, delete'))
