import sqlalchemy as sa
import sqlalchemy_utils as sau
from enum import Enum
from sqlalchemy.ext.declarative import declared_attr

class UserType(Enum):
    unconfirmed = "unconfirmed"
    active_non_paying = "active_non_paying"
    active_free = "active_free"
    active_paying = "active_paying"
    active_delinquent = "active_delinquent"
    admin = "admin"
    unknown = "unknown"
    suspended = "suspended"

class UserMixin:
    @declared_attr
    def __tablename__(cls):
        return "user"

    id = sa.Column(sa.Integer, primary_key=True)
    created = sa.Column(sa.DateTime, nullable=False)
    updated = sa.Column(sa.DateTime, nullable=False)
    username = sa.Column(sa.Unicode(256), index=True, unique=True)
    email = sa.Column(sa.String(256), nullable=False)
    user_type = sa.Column(
            sau.ChoiceType(UserType, impl=sa.String()),
            nullable=False,
            default=UserType.unconfirmed)
    url = sa.Column(sa.String(256))
    location = sa.Column(sa.Unicode(256))
    bio = sa.Column(sa.Unicode(4096))
    suspension_notice = sa.Column(sa.Unicode(4096))

    @property
    def canonical_name(self):
        return "~" + self.username

    def is_authenticated(self):
        return True

    def is_active(self):
        return True

    def is_anonymous(self):
        return False

    def get_id(self):
        return self.username

    def __repr__(self):
        return '<User {} {}>'.format(self.id, self.username)

    def __str__(self):
        return self.canonical_name

    def to_dict(self, short=False):
        return {
            "canonical_name": self.canonical_name,
            "name": self.username,
            **({
                "email": self.email,
                "url": self.url,
                "location": self.location,
                "bio": self.bio,
            } if not short else {})
        }

class ExternalUserMixin(UserMixin):
    oauth_token = sa.Column(sa.String(256))
    oauth_token_expires = sa.Column(sa.DateTime)
    oauth_token_scopes = sa.Column(sa.String)
    oauth_revocation_token = sa.Column(sa.String(256))
