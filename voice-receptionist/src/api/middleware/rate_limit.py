"""
Rate Limiting Middleware.

Provides configurable rate limiting per endpoint and user.
Uses Redis for distributed rate limiting across multiple instances.
"""

import time
from typing import Optional, Callable
from functools import wraps

from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from src.core.config import settings
from src.core.logging import get_logger

logger = get_logger(__name__)


class RateLimiter:
    """
    Token bucket rate limiter with Redis backend.
    
    Falls back to in-memory storage if Redis is unavailable.
    """
    
    def __init__(self):
        self.local_cache: dict = {}
        self.redis_client = None
        self._init_redis()
    
    def _init_redis(self):
        """Initialize Redis client if available."""
        if settings.redis_url:
            try:
                import redis
                self.redis_client = redis.from_url(settings.redis_url)
                self.redis_client.ping()
                logger.info("Rate limiter using Redis backend")
            except Exception as e:
                logger.warning("Redis unavailable, using in-memory rate limiting", error=str(e))
                self.redis_client = None
    
    def is_allowed(
        self, 
        key: str, 
        limit: int, 
        window_seconds: int
    ) -> tuple[bool, int, int]:
        """
        Check if request is allowed under rate limit.
        
        Args:
            key: Unique identifier (e.g., IP, user_id)
            limit: Maximum requests allowed
            window_seconds: Time window in seconds
        
        Returns:
            (allowed, remaining, reset_time)
        """
        if self.redis_client:
            return self._check_redis(key, limit, window_seconds)
        return self._check_local(key, limit, window_seconds)
    
    def _check_redis(self, key: str, limit: int, window: int) -> tuple[bool, int, int]:
        """Check rate limit using Redis."""
        try:
            pipe = self.redis_client.pipeline()
            now = int(time.time())
            window_key = f"rate:{key}:{now // window}"
            
            pipe.incr(window_key)
            pipe.expire(window_key, window)
            results = pipe.execute()
            
            count = results[0]
            remaining = max(0, limit - count)
            reset_time = (now // window + 1) * window
            
            return count <= limit, remaining, reset_time
        except Exception as e:
            logger.error("Redis rate limit check failed", error=str(e))
            return True, limit, int(time.time()) + window
    
    def _check_local(self, key: str, limit: int, window: int) -> tuple[bool, int, int]:
        """Check rate limit using local memory."""
        now = int(time.time())
        window_start = now // window * window
        cache_key = f"{key}:{window_start}"
        
        # Clean old entries
        self._cleanup_local_cache(now - window * 2)
        
        # Get current count
        count = self.local_cache.get(cache_key, 0) + 1
        self.local_cache[cache_key] = count
        
        remaining = max(0, limit - count)
        reset_time = window_start + window
        
        return count <= limit, remaining, reset_time
    
    def _cleanup_local_cache(self, before: int):
        """Remove old entries from local cache."""
        keys_to_delete = [
            k for k in self.local_cache 
            if int(k.split(':')[-1]) < before
        ]
        for k in keys_to_delete:
            del self.local_cache[k]


# Global rate limiter instance
rate_limiter = RateLimiter()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware for rate limiting.
    
    Applies different limits based on endpoint type:
    - Auth endpoints: 5/minute
    - API endpoints: 100/minute
    - WebSocket: No limit (handled separately)
    """
    
    # Rate limits per endpoint pattern
    LIMITS = {
        "/api/v1/auth/login": (5, 60),      # 5 per minute
        "/api/v1/auth/register": (3, 60),   # 3 per minute
        "/api/v1/bookings": (30, 60),       # 30 per minute
        "/api/v1/voice": (10, 60),          # 10 per minute
        "default": (100, 60),               # 100 per minute
    }
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip rate limiting for health checks
        if request.url.path.startswith("/health"):
            return await call_next(request)
        
        # Skip WebSocket upgrades
        if request.headers.get("upgrade", "").lower() == "websocket":
            return await call_next(request)
        
        # Get client identifier
        client_ip = request.client.host if request.client else "unknown"
        user_id = getattr(request.state, "user_id", None)
        key = f"{user_id or client_ip}"
        
        # Find matching limit
        limit, window = self._get_limit(request.url.path)
        
        # Check rate limit
        allowed, remaining, reset_time = rate_limiter.is_allowed(
            key=f"{key}:{request.url.path.split('/')[1:4]}",
            limit=limit,
            window_seconds=window,
        )
        
        if not allowed:
            logger.warning(
                "Rate limit exceeded",
                client=key,
                path=request.url.path,
            )
            return Response(
                content='{"detail": "Too many requests"}',
                status_code=429,
                media_type="application/json",
                headers={
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_time),
                    "Retry-After": str(reset_time - int(time.time())),
                }
            )
        
        # Process request
        response = await call_next(request)
        
        # Add rate limit headers
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_time)
        
        return response
    
    def _get_limit(self, path: str) -> tuple[int, int]:
        """Get rate limit for path."""
        for pattern, limit in self.LIMITS.items():
            if pattern != "default" and path.startswith(pattern):
                return limit
        return self.LIMITS["default"]


def rate_limit(limit: int = 10, window: int = 60):
    """
    Decorator for endpoint-specific rate limiting.
    
    Usage:
        @router.get("/expensive")
        @rate_limit(limit=5, window=60)
        async def expensive_endpoint():
            ...
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(request: Request, *args, **kwargs):
            client_ip = request.client.host if request.client else "unknown"
            key = f"decorator:{func.__name__}:{client_ip}"
            
            allowed, remaining, reset = rate_limiter.is_allowed(key, limit, window)
            
            if not allowed:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded",
                    headers={"Retry-After": str(reset - int(time.time()))},
                )
            
            return await func(request, *args, **kwargs)
        return wrapper
    return decorator
