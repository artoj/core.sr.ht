"""
Import this module only after configuring your database.
"""

from celery import Celery
from srht.database import db
from srht.webhook import Webhook
from werkzeug.local import LocalProxy
import requests

_async_request = None
async_request = LocalProxy(lambda: _async_request)

def make_worker(broker='redis://'):
    worker = Celery('webhooks', broker=broker)

    @worker.task
    def async_request(url, payload, headers,
            delivery_table=None, delivery_id=None, timeout=5):
        """
        Performs an HTTP POST asyncronously, and updates the delivery row if a
        table & id is specified.
        """
        r = None
        try:
            r = requests.post(url, data=payload, timeout=timeout, headers=headers)
            response = r.text
            response_status = r.status_code
            response_headers = "\n".join(
                    f"{key}: {value}" for key, value in r.headers.items())
        except requests.exceptions.ReadTimeout:
            response = "Request timed out after 5 seconds."
            response_status = -1
            response_headers = None
        if delivery_table and delivery_id:
            db.session.execute(
                f"""
                UPDATE {delivery_table}
                SET response = :response,
                    response_status = :status,
                    response_headers = :headers
                WHERE id = :delivery_id
                """, {
                    "response": response,
                    "status": response_status,
                    "headers": response_headers,
                    "delivery_id": delivery_id
                })
            db.session.commit()
        return r

    global _async_request
    _async_request = async_request
    return worker

class CeleryWebhook(Webhook):
    def process_delivery(cls, delivery, headers, delay=True, timeout=5):
        """
        Delivers the webhook via celery (or immediately if delay=True).
        """
        Delivery = cls.Delivery
        if delay:
            async_request.delay(delivery.url, delivery.payload, headers,
                    timeout=timeout, delivery_table=Delivery.__tablename__,
                    delivery_id=delivery.id)
        else:
            return async_request(delivery.url, delivery.payload, headers,
                    timeout=timeout, delivery_table=Delivery.__tablename__,
                    delivery_id=delivery.id)
