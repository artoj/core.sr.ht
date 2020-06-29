"""
srht.cache is a simple wrapper around Redis which turns connection errors into
cache misses.
"""
from srht.redis import redis

def get_cache(key):
    try:
        return redis.get(key)
    except:
        return None

def set_cache(key, expr, value):
    try:
        redis.setex(key, expr, value)
    except:
        pass

def expunge_cache(key):
    """Failing to expunge the cache may be a security issue, so this is not
    wrapped in a try/except"""
    redis.delete(key)
