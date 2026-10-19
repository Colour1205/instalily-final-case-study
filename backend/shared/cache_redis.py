"""Redis connection (Memurai on Windows), used by the leads API's cache."""

import redis

from shared.settings import settings

# Short timeouts: if Redis is slow or down, the API gives up on the cache quickly and reads the database.
redis_client = redis.Redis.from_url(
    settings.REDIS_URL, decode_responses=True, socket_timeout=1, socket_connect_timeout=1
)
