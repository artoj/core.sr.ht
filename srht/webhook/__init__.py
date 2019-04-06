from collections import namedtuple
from srht.webhook.webhook import Webhook, public_key

Event = namedtuple("Event", ["name", "scope"])
