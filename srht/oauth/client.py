import sqlalchemy as sa
from sqlalchemy.ext.declarative import declared_attr

class OAuthClientMixin:
    @declared_attr
    def __tablename__(cls):
        return "oauthclient"

    id = sa.Column(sa.Integer, primary_key=True)
    created = sa.Column(sa.DateTime, nullable=False)
    updated = sa.Column(sa.DateTime, nullable=False)

    @declared_attr
    def user_id(cls):
        return sa.Column(sa.Integer, sa.ForeignKey('user.id'))

    @declared_attr
    def user(cls):
        return sa.orm.relationship('User',
            backref=sa.orm.backref('oauth_clients'))
