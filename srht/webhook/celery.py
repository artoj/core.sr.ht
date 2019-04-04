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
    def async_request(url, payload, headers, delivery_table=None, delivery_id=None):
        """
        Performs an HTTP POST asyncronously, and updates the delivery row if a
        table & id is specified.
        """
        try:
            r = requests.post(url, data=payload, timeout=5, headers=headers)
            response = r.text
            response_status = r.status_code
            response_headers = "\n".join(
                    f"{key}: {value}" for key, value in r.headers.items())
        except requests.exceptions.ReadTimeout:
            response = "Request timeed out after 5 seconds."
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

    global _async_request
    _async_request = async_request
    return worker

class CeleryWebhook(Webhook):
    def process_delivery(cls, delivery, headers):
        Delivery = cls.Delivery
        async_request.delay(delivery.url, delivery.payload, headers,
                delivery_table=Delivery.__tablename__, delivery_id=delivery.id)
