from redis import Redis
from srht.config import cfg

redis = Redis(host=cfg("sr.ht", "redis-host", "localhost"))
