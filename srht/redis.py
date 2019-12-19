from redis import Redis
from srht.config import cfg
from urllib.parse import urlparse

url = cfg("sr.ht", "redis-host", "localhost")
url = urlparse(url)

redis = Redis(host=url.hostname,
        port=(url.port or 6379),
        password=url.password,
        db=int(url.path[1:]) if url.path else 0)
