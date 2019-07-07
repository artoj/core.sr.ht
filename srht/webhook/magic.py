import re
import sqlalchemy as sa
import sqlalchemy_utils as sau
import uuid
from enum import Enum
from sqlalchemy.ext.declarative import declared_attr
from srht.database import Base
from srht.oauth import OAuthScope
from srht.oauth.scope import client_id
from werkzeug.local import LocalProxy

_webhooks = list()

registered_webhooks = LocalProxy(lambda: _webhooks)

# https://stackoverflow.com/a/1176023
first_cap_re = re.compile('(.)([A-Z][a-z]+)')
all_cap_re = re.compile('([a-z0-9])([A-Z])')
def snake_case(name):
    s1 = first_cap_re.sub(r'\1_\2', name)
    return all_cap_re.sub(r'\1_\2', s1).lower()

event_re = re.compile(r"""
        (?P<resource>[a-z]+):(?P<events>[a-z+]+)
        (\[(?P<ids>[0-9,]+)\])?""", re.X)

class _SubscriptionMixin:
    @declared_attr
    def __tablename__(cls):
        return snake_case(cls.__name__)

    id = sa.Column(sa.Integer, primary_key=True)
    created = sa.Column(sa.DateTime, nullable=False)
    url = sa.Column(sa.Unicode(2048), nullable=False)
    _events = sa.Column(sa.Unicode, nullable=False, name="events")

    def __init__(self, valid, token, *args, **kwargs):
        self.token_id = token.id
        self.user_id = token.user_id
        self.url = valid.require("url")
        events = valid.require("events")
        if not valid.ok:
            return
        try:
            self.events = set(self._Webhook.Events(event)
                    for event in events)
        except ValueError:
            valid.expect(False,
                    f"Unsupported event type", field="events")
        valid.expect(OAuthScope.all in token.scopes or
            all(self._Webhook.event_scope[ev] in token.scopes
                for ev in self.events),
            "Permission denied - does your token have the appropriate scopes?")
        if hasattr(self._Webhook, "__init__"):
            self._Webhook.__init__(self, *args, **kwargs)

    @property
    def events(self):
        return [self._Webhook.Events(e) for e in self._events.split(",")]

    @events.setter
    def events(self, val):
        self._events = ",".join(v.value for v in val)

    @declared_attr
    def user_id(cls):
        return sa.Column(sa.Integer,
                sa.ForeignKey("user.id", ondelete="CASCADE"))

    @declared_attr
    def user(cls):
        return sa.orm.relationship("User")

    @declared_attr
    def token_id(cls):
        return sa.Column(sa.Integer,
                sa.ForeignKey("oauthtoken.id", ondelete="CASCADE"))

    @declared_attr
    def token(cls):
        return sa.orm.relationship("OAuthToken")

    def to_dict(self):
        return {
            "id": self.id,
            "created": self.created,
            "events": [e.value for e in self.events],
            "url": self.url,
        }

class _DeliveryMixin:
    @declared_attr
    def __tablename__(cls):
        return snake_case(cls.__name__)

    id = sa.Column(sa.Integer, primary_key=True)
    uuid = sa.Column(sau.UUIDType, nullable=False)
    created = sa.Column(sa.DateTime, nullable=False)
    event = sa.Column(sa.Unicode(256), nullable=False)
    url = sa.Column(sa.Unicode(2048), nullable=False)
    payload = sa.Column(sa.Unicode(65536), nullable=False)
    payload_headers = sa.Column(sa.Unicode(16384), nullable=False)
    response = sa.Column(sa.Unicode(65536))
    response_status = sa.Column(sa.Integer, nullable=False)
    response_headers = sa.Column(sa.Unicode(16384))

    @declared_attr
    def subscription_id(cls):
        name = snake_case(cls.__name__.replace("Delivery", "Subscription"))
        return sa.Column(sa.Integer,
                sa.ForeignKey(name + '.id', ondelete="CASCADE"),
                nullable=False)

    @declared_attr
    def subscription(cls):
        cls_name = cls.__name__.replace("Delivery", "Subscription")
        return sa.orm.relationship(cls_name,
                backref=sa.orm.backref('deliveries', cascade='all, delete'))

    def __init__(self):
        self.uuid = uuid.uuid4()

    def to_dict(self):
        return {
            "id": str(self.uuid),
            "created": self.created,
            "event": self.event,
            "url": self.url,
            "payload": self.payload,
            "payload_headers": self.payload_headers,
            "response": self.response,
            "response_status": self.response_status,
            "response_headers": self.response_headers,
        }

class WebhookMeta(type):
    def __new__(cls, name, bases, members):
        base_members = dict()
        subs_members = dict()
        for key, value in members.items():
            if isinstance(value, sa.Column):
                subs_members[key] = value
            else:
                base_members[key] = value
        events = base_members.get("events")
        base_members.update({
            "Subscription": type(name + "Subscription",
                (_SubscriptionMixin, Base), subs_members),
            "Delivery": type(name + "Delivery", (_DeliveryMixin, Base), dict()),
        })
        if events is not None:
            norm = lambda name: re.sub('[-:]', '_', name)
            base_members["Events"] = Enum(name + "Events",
                    [(norm(ev.name), ev.name) for ev in events ])
            scopes = {
                getattr(base_members["Events"],
                    norm(ev.name)): OAuthScope(ev.scope) for ev in events
            }
            if client_id:
                for scope in scopes.values():
                    scope.client_id = client_id
            base_members["event_scope"] = scopes
            base_members["Events"]
        cls = super().__new__(cls, name, bases, base_members)
        if events is not None:
            registered_webhooks.append(cls)
            # This is gross
            cls._deliver = cls.deliver
            cls.deliver = lambda *args, **kwargs: cls._deliver(cls, *args, **kwargs)
            cls._notify = cls.notify
            cls.notify = lambda *args, **kwargs: cls._notify(cls, *args, **kwargs)
            cls._prepare_headers = cls.prepare_headers
            cls.prepare_headers = lambda *args, **kwargs: cls._prepare_headers(cls, *args, **kwargs)
            cls._process_delivery = cls.process_delivery
            cls.process_delivery = lambda *args, **kwargs: cls._process_delivery(cls, *args, **kwargs)
            cls._api_routes = cls.api_routes
            cls.api_routes = lambda *args, **kwargs: cls._api_routes(cls, *args, **kwargs)
        cls.Subscription._Webhook = cls
        cls.Delivery._Webhook = cls
        return cls
