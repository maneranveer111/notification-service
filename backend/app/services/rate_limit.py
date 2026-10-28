import logging
import time
from uuid import UUID

from app.config import get_settings

logger = logging.getLogger(__name__)

_redis_client = None


def get_redis_client():
    global _redis_client
    if _redis_client is None:
        import redis
        settings = get_settings()
        _redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    return _redis_client


def check_rate_limit(client_id: UUID, limit_per_minute: int) -> bool:
    """
    Check fixed window rate limit in Redis: key rl:{client_id}:{unix_minute}.
    Uses INCR and EXPIRE 60.
    Returns True if allowed (current_count <= limit_per_minute), False if over limit.
    Fails open (returns True) on Redis errors.
    """
    try:
        r = get_redis_client()
        unix_minute = int(time.time() // 60)
        key = f"rl:{client_id}:{unix_minute}"

        pipe = r.pipeline()
        pipe.incr(key)
        pipe.expire(key, 60)
        results = pipe.execute()
        current_count = results[0]

        if current_count > limit_per_minute:
            return False
        return True
    except Exception as exc:
        logger.warning("Redis rate limit check failed for client %s: %s", client_id, exc)
        return True


check_client_rate_limit = check_rate_limit

