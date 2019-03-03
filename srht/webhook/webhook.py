import json
import requests
from enum import Enum
from flask import request, current_app, abort
from srht.api import paginated_response
from srht.database import db
from srht.flask import date_handler
from srht.oauth import oauth, current_token
from srht.validation import Validation
from srht.webhook.magic import WebhookMeta

class Webhook(metaclass=WebhookMeta):
    """
    Magic webhook base class. Derived classes will automatically have the
    necessary SQL tables rigged up. You must specify:

    events = ["list", "of", "valid", "events"]

    You can also specify any number of SQLAlchemy columns normally, and they'll
    be added to the Subscription class. Your derived class will automatically
    have:
    
    MyClass.Subscription

    Based on the _SubscriptionMixin above, with any of your columns added,
    mapped to the SQL table my_class_subscription. You'll also get:

    MyClass.Delivery

    Based on _DeliveryMixin, with a relationship rigged up to
    MyClass.Subscription.
    """

    def deliver(cls, event: Enum, payload: dict, *filters):
        """
        Delivers the specified event to all subscribers. Filter subscribers down
        to your custom columns if necessary by passing SQLAlchemy filter
        statements into *args.
        """
        Subscription = cls.Subscription 
        subs = Subscription.query
        subs = subs.filter(
            # Coarse SQL-side filter, fine filtering later
            Subscription._events.like("%" + event.value + "%"))
        for f in filters:
            subs = subs.filter(f)
        for sub in subs.all():
            if event in sub.events:
                cls.notify(sub, event, payload)

    def notify(cls, sub, event, payload):
        """Notifies a single subscriber of a webhook event."""
        payload = json.dumps(payload, default=date_handler)
        delivery = cls.Delivery()
        delivery.event = event.value
        delivery.subscription_id = sub.id
        delivery.url = sub.url
        delivery.payload = payload[:65536]
        headers = {
            "Content-Type": "application/json",
            "X-Webhook-Event": event.value,
            "X-Webhook-Delivery": str(delivery.uuid),
        }
        delivery.payload_headers = "\n".join(
                f"{key}: {value}" for key, value in headers.items())
        delivery.response_status = -2
        db.session.add(delivery)
        db.session.commit()
        cls.process_delivery(delivery, headers)

    def process_delivery(cls, delivery, headers):
        try:
            r = requests.post(delivery.url, data=delivery.payload,
                    timeout=5, headers=headers)
            delivery.response = r.text[:65536]
            delivery.response_status = r.status_code
            delivery.response_headers = "\n".join(
                    f"{key}: {value}" for key, value in r.headers.items())
        except requests.exceptions.ReadTimeout:
            delivery.response = "Request timeed out after 5 seconds."
            delivery.response_status = -1
        db.session.commit()

    def api_routes(cls, blueprint, prefix):
        Delivery = cls.Delivery
        Subscription = cls.Subscription 

        @blueprint.route(f"{prefix}/webhooks",
                endpoint=f"{cls.__name__}_webhooks_GET")
        @oauth(None)
        def webhooks_GET():
            query = (Subscription.query
                .filter(Subscription.token_id == current_token.id)
                .filter(Subscription.user_id == current_token.user_id))
            return paginated_response(Subscription.id, query)

        @blueprint.route(f"{prefix}/webhooks", methods=["POST"],
                endpoint=f"{cls.__name__}_webhooks_POST")
        @oauth(None)
        def webhooks_POST():
            valid = Validation(request)
            sub = Subscription(valid, current_token)
            if not valid.ok:
                return valid.response
            db.session.add(sub)
            db.session.commit()
            return sub.to_dict(), 201

        @blueprint.route(f"{prefix}/webhooks/<sub_id>",
                endpoint=f"{cls.__name__}_webhooks_by_id_GET")
        @oauth(None)
        def webhooks_by_id_GET(sub_id):
            valid = Validation(request)
            sub = Subscription.query.filter(
                Subscription.id == sub_id).one_or_none()
            if not sub:
                abort(404)
            if sub.token_id != current_token.id:
                abort(401)
            return sub.to_dict()

        @blueprint.route(f"{prefix}/webhooks/<sub_id>", methods=["DELETE"],
                endpoint=f"{cls.__name__}_webhooks_by_id_DELETE")
        @oauth(None)
        def webhooks_by_id_DELETE(sub_id):
            valid = Validation(request)
            sub = Subscription.query.filter(
                    Subscription.id == sub_id).one_or_none()
            if not sub:
                abort(404)
            if sub.token_id != current_token.id:
                abort(401)
            db.session.delete(sub)
            db.session.commit()
            return {}, 204

        @blueprint.route(f"{prefix}/webhooks/<sub_id>/deliveries",
                endpoint=f"{cls.__name__}_deliveries_GET")
        @oauth(None)
        def deliveries_GET(sub_id):
            valid = Validation(request)
            sub = Subscription.query.filter(
                Subscription.id == sub_id).one_or_none()
            if not sub:
                abort(404)
            if sub.token_id != current_token.id:
                abort(401)
            query = (Delivery.query
                .filter(Delivery.subscription_id == sub.id))
            return paginated_response(Delivery.id, query)

        @blueprint.route(f"{prefix}/webhooks/<sub_id>/deliveries/<delivery_id>",
                endpoint=f"{cls.__name__}_deliveries_by_id_GET")
        @oauth(None)
        def deliveries_by_id_GET(sub_id, delivery_id):
            valid = Validation(request)
            sub = Subscription.query.filter(
                Subscription.id == sub_id).one_or_none()
            if not sub:
                abort(404)
            if sub.token_id != current_token.id:
                abort(401)
            delivery = (Delivery.query
                .filter(Delivery.subscription_id == sub_id)
                .filter(Delivery.id == delivery_id)).one_or_none()
            if not delivery:
                abort(404)
            return delivery.to_dict()
