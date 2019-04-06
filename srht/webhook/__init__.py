from collections import namedtuple
from srht.webhook.webhook import Webhook

Event = namedtuple("Event", ["name", "scope"])
