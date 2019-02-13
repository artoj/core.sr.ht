"""
Import this module only after configuring your database.
"""

from celery import Celery
from srht.database import db
from srht.webhook import Webhook
import requests

worker = Celery('webhooks', broker='redis://')

@worker.task
def _celery_dispatch(delivery_table, delivery_id, url, payload, headers):
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

class CeleryWebhook(Webhook):
    def process_delivery(cls, delivery, headers):
        Delivery = cls.Delivery
        _celery_dispatch.delay(Delivery.__tablename__,
                delivery.id, delivery.url, delivery.payload, headers)
