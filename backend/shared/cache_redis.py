"""Redis connection (Memurai on Windows), used by the leads API's cache."""

import redis

from shared.config import settings

# Short timeouts: if Redis is slow or down, the API gives up on the cache quickly and reads the database.
redis_client = redis.Redis.from_url(
    settings.redis_url, decode_responses=True, socket_timeout=1, socket_connect_timeout=1
)
