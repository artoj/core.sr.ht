import json
import requests
from enum import Enum
from srht.database import db
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
            # TODO: Parse the event list properly and make sure that they're
            # subscribed to the right event
            cls.notify(sub, event, payload)

    def notify(cls, sub, event, payload):
        """Notifies a single subscriber of a webhook event."""
        # TODO: Override this with a CeleryWebhook class
        payload = json.dumps(payload, indent='\t')
        delivery = cls.Delivery()
        delivery.event = event.value
        delivery.subscription_id = sub.id
        delivery.url = sub.url
        delivery.payload = payload
        headers = {
            "Content-Type": "application/json",
            "X-Webhook-Event": event.value,
            "X-Webhook-Delivery": str(delivery.uuid),
        }
        delivery.payload_headers = "\n".join(
                f"{key}: {value}" for key, value in headers.items())
        try:
            r = requests.post(sub.url, data=payload, timeout=5, headers=headers)
            delivery.response = r.text
            delivery.response_status = r.status_code
            delivery.response_headers = "\n".join(
                    f"{key}: {value}" for key, value in r.headers.items())
        except Exception as ex:
            delivery.response = str(ex)
            delivery.response_status = -1
        db.session.add(delivery)
        db.session.commit()
