import time
from prometheus_client.metrics_core import GaugeMetricFamily
from redis import Redis, ResponseError


class RedisQueueCollector:
    def __init__(self, broker, name, documentation, queue_name="celery"):
        self.redis = Redis.from_url(broker)
        self.queue_name = queue_name
        self.name = name
        self.documentation = documentation

    def collect(self):
        start = time.time()
        errors = 0
        try:
            queue_size = self.redis.llen(self.queue_name)
        except ResponseError: # Key is not a list
            queue_size = 0
            errors += 1
        duration = time.time() - start
        yield GaugeMetricFamily(self.name + "_queue_length", self.documentation, value=queue_size)
        yield GaugeMetricFamily(
            self.name + "_queue_length_collection_time_seconds",
            "Time to collect queue metrics",
            value=duration,
        )
        yield GaugeMetricFamily(
            self.name + "_queue_length_collection_error_count",
            "Errors encountered while collecting queue metrics",
            value=errors,
        )
