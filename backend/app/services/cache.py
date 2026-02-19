import json
import os
from typing import Dict, Any, Optional

import redis.asyncio as redis

# NOTE:
# In docker compose, Redis hostname is usually "redis".
# But in your logs redis is NOT running / not reachable (challenge mode).
# So this file must NOT crash if redis is down.
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
_redis: Optional[redis.Redis] = None


def _get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.Redis.from_url(REDIS_URL)
    return _redis


# Simple in-memory fallback cache (used when Redis is unavailable)
_memory_cache: Dict[str, Dict[str, Any]] = {}
_memory_cache_expiry: Dict[str, float] = {}


def _mem_get(key: str) -> Optional[Dict[str, Any]]:
    import time

    exp = _memory_cache_expiry.get(key)
    if exp is not None and exp < time.time():
        _memory_cache.pop(key, None)
        _memory_cache_expiry.pop(key, None)
        return None
    return _memory_cache.get(key)


def _mem_set(key: str, value: Dict[str, Any], ttl_seconds: int) -> None:
    import time

    _memory_cache[key] = value
    _memory_cache_expiry[key] = time.time() + ttl_seconds


async def get_revenue_summary(property_id: str, tenant_id: str) -> Dict[str, Any]:
    """
    Fetches revenue summary, utilizing caching to improve performance.

    Fixes:
    - Cache key MUST include tenant_id (prevents cross-tenant leakage)
    - Must not 500 if Redis is down (fallback to in-memory cache)
    """
    cache_key = f"revenue:{tenant_id}:{property_id}"
    ttl_seconds = 300

    # 1) Try in-memory cache first (fast + always available)
    mem_hit = _mem_get(cache_key)
    if mem_hit is not None:
        return mem_hit

    # 2) Try Redis (if available)
    try:
        r = _get_redis()
        cached = await r.get(cache_key)
        if cached:
            data = json.loads(cached)
            # also populate memory cache for resilience
            _mem_set(cache_key, data, ttl_seconds)
            return data
    except Exception:
        # Redis down/unreachable -> ignore, continue to compute fresh
        pass

    # Revenue calculation is delegated to the reservation service.
    from app.services.reservations import calculate_total_revenue

    result = await calculate_total_revenue(property_id, tenant_id)

    # 3) Write-through cache (best-effort)
    _mem_set(cache_key, result, ttl_seconds)
    try:
        r = _get_redis()
        await r.setex(cache_key, ttl_seconds, json.dumps(result))
    except Exception:
        pass

    return result
