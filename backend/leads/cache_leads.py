"""Redis access for the leads API: cache-aside with request coalescing. Redis only.

Redis itself is set to evict with LFU (least frequently used) when it reaches its memory limit,
so popular pages stay cached and rarely viewed ones are dropped first.
"""

import json
import logging
import time

import redis

from shared.cache_redis import redis_client

log = logging.getLogger(__name__)

LOCK_SECONDS = 5
WAIT_SECONDS = 3
CHECK_EVERY_SECONDS = 0.05


class LeadCache:
    """Keeps recent API answers in Redis, and lets only one request at a time rebuild a missing answer."""

    def __init__(self, seconds: int) -> None:
        """Set how long each saved answer lives before Redis deletes it."""
        self.seconds = seconds

    def get(self, key: str) -> dict | None:
        """Return the saved answer for this key, or None if it is missing, expired or Redis is down."""
        try:
            saved = redis_client.get(key)
        except redis.RedisError as error:
            log.warning("Redis read failed: %r", error)
            return None
        if saved is None:
            return None
        return json.loads(saved)

    def get_or_build(self, key: str, build) -> dict | None:
        """Cache-aside with request coalescing: return the cached answer, or build it once while others wait.

        build is the function that reads the answer from the database.
        """
        answer = self.get(key)
        if answer is not None:
            return answer

        # Only one request in the whole system can create this lock (NX), so only one rebuilds the answer.
        lock_key = "lock:" + key
        try:
            got_lock = redis_client.set(lock_key, "1", nx=True, ex=LOCK_SECONDS)
        except redis.RedisError as error:
            log.warning("Redis lock failed, reading the database: %r", error)
            return build()

        if got_lock:
            try:
                # Check again: another request may have saved the answer just before this one got the lock.
                answer = self.get(key)
                if answer is None:
                    answer = build()
                    if answer is not None:
                        redis_client.set(key, json.dumps(answer), ex=self.seconds)
            except redis.RedisError as error:
                log.warning("Redis write failed: %r", error)
            finally:
                try:
                    redis_client.delete(lock_key)
                except redis.RedisError:
                    pass  # the lock expires by itself after LOCK_SECONDS
            return answer

        # Another request is rebuilding this answer: wait for it instead of hitting the database as well.
        waited = 0.0
        while waited < WAIT_SECONDS:
            time.sleep(CHECK_EVERY_SECONDS)
            waited += CHECK_EVERY_SECONDS
            answer = self.get(key)
            if answer is not None:
                return answer
            try:
                still_locked = redis_client.exists(lock_key)
            except redis.RedisError:
                still_locked = False
            if not still_locked:
                break  # the builder finished without saving (unknown lead, or it failed)
        return build()
