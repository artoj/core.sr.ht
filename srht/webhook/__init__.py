from collections import namedtuple
from srht.webhook.webhook import Webhook, verify_payload

Event = namedtuple("Event", ["name", "scope"])
