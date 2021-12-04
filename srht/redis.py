from redis import from_url
from srht.config import cfg

redis = from_url(cfg("sr.ht", "redis-host", "redis://localhost"))
