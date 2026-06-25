from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from fastapi import Request, status
from redis.exceptions import RedisError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from app.core.config import settings
from app.core.redis import get_redis_client

logger = logging.getLogger(__name__)

_memory_buckets: dict[str, tuple[int, float]] = {}
_redis_disabled_until = 0.0
_REDIS_RETRY_SECONDS = 30.0


@dataclass(frozen=True)
class RateLimitRule:
    name: str
    requests: int
    window_seconds: int


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if not settings.rate_limit_enabled:
            return await call_next(request)

        rule = _match_rule(request)
        if rule is None:
            return await call_next(request)

        key = _rate_limit_key(request, rule)
        allowed, retry_after = await _allow_request(key, rule)
        if allowed:
            return await call_next(request)

        if rule.name == "telemetry":
            logger.info(
                "telemetry rate limited",
                extra={
                    "request_id": getattr(request.state, "request_id", None),
                    "path": request.url.path,
                    "retry_after": retry_after,
                },
            )
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"detail": "Rate limit exceeded"},
            headers={"Retry-After": str(max(1, retry_after))},
        )


def reset_in_memory_rate_limiter() -> None:
    _memory_buckets.clear()


def _match_rule(request: Request) -> RateLimitRule | None:
    path = request.url.path
    method = request.method.upper()
    api_prefix = settings.api_v1_prefix.rstrip("/")
    if not path.startswith(f"{api_prefix}/"):
        return None

    seller_auth_paths = {
        f"{api_prefix}/seller-auth/login",
        f"{api_prefix}/seller-auth/register/start",
        f"{api_prefix}/seller-auth/register/confirm",
        f"{api_prefix}/seller-auth/register/resend-code",
        f"{api_prefix}/seller-auth/register/telegram-start",
    }
    if method == "POST" and (
        path == f"{api_prefix}/auth/telegram/login" or path in seller_auth_paths
    ):
        return RateLimitRule(
            "auth",
            settings.rate_limit_auth_requests,
            settings.rate_limit_auth_window_seconds,
        )
    if method == "POST" and path == f"{api_prefix}/analytics/telemetry":
        return RateLimitRule(
            "telemetry",
            settings.rate_limit_telemetry_requests,
            settings.rate_limit_telemetry_window_seconds,
        )
    if method == "POST" and path.startswith(f"{api_prefix}/uploads/"):
        return RateLimitRule(
            "uploads",
            settings.rate_limit_upload_requests,
            settings.rate_limit_upload_window_seconds,
        )
    if method == "POST" and path == f"{api_prefix}/orders/checkout":
        return RateLimitRule(
            "checkout",
            settings.rate_limit_checkout_requests,
            settings.rate_limit_checkout_window_seconds,
        )
    if method == "POST" and path == f"{api_prefix}/promo-codes/validate":
        return RateLimitRule(
            "promo",
            settings.rate_limit_promo_requests,
            settings.rate_limit_promo_window_seconds,
        )
    if method == "POST" and path.startswith(f"{api_prefix}/products/") and path.endswith(
        "/reviews"
    ):
        return RateLimitRule(
            "reviews",
            settings.rate_limit_review_requests,
            settings.rate_limit_review_window_seconds,
        )
    if path.startswith(f"{api_prefix}/customer-notifications/campaigns/") and method in {
        "POST",
        "PATCH",
    }:
        return RateLimitRule(
            "customer-campaigns",
            settings.rate_limit_customer_campaign_requests,
            settings.rate_limit_customer_campaign_window_seconds,
        )
    if path == f"{api_prefix}/customer-notifications/campaigns" and method == "POST":
        return RateLimitRule(
            "customer-campaigns",
            settings.rate_limit_customer_campaign_requests,
            settings.rate_limit_customer_campaign_window_seconds,
        )
    if path == f"{api_prefix}/customer-notifications/templates" and method == "POST":
        return RateLimitRule(
            "customer-campaigns",
            settings.rate_limit_customer_campaign_requests,
            settings.rate_limit_customer_campaign_window_seconds,
        )
    if path.startswith(f"{api_prefix}/customer-notifications/templates/") and method == "PATCH":
        return RateLimitRule(
            "customer-campaigns",
            settings.rate_limit_customer_campaign_requests,
            settings.rate_limit_customer_campaign_window_seconds,
        )

    return RateLimitRule(
        "global",
        settings.rate_limit_global_requests,
        settings.rate_limit_global_window_seconds,
    )


async def _allow_request(key: str, rule: RateLimitRule) -> tuple[bool, int]:
    if settings.rate_limit_redis_enabled:
        redis_result = await _allow_request_redis(key, rule)
        if redis_result is not None:
            return redis_result

    if settings.rate_limit_in_memory_fallback_enabled:
        return _allow_request_memory(key, rule)

    return True, rule.window_seconds


async def _allow_request_redis(key: str, rule: RateLimitRule) -> tuple[bool, int] | None:
    global _redis_disabled_until
    now = time.monotonic()
    if now < _redis_disabled_until:
        return None

    try:
        redis = get_redis_client()
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, rule.window_seconds)
        ttl = await redis.ttl(key)
        retry_after = ttl if isinstance(ttl, int) and ttl > 0 else rule.window_seconds
        return count <= rule.requests, retry_after
    except (OSError, RedisError):
        _redis_disabled_until = now + _REDIS_RETRY_SECONDS
        logger.debug("Redis rate limiting unavailable; using fallback", exc_info=True)
        return None


def _allow_request_memory(key: str, rule: RateLimitRule) -> tuple[bool, int]:
    now = time.monotonic()
    count, expires_at = _memory_buckets.get(key, (0, now + rule.window_seconds))
    if now >= expires_at:
        count = 0
        expires_at = now + rule.window_seconds

    count += 1
    _memory_buckets[key] = (count, expires_at)
    retry_after = max(1, int(expires_at - now))
    return count <= rule.requests, retry_after


def _rate_limit_key(request: Request, rule: RateLimitRule) -> str:
    client_host = _client_host(request)
    return f"rate-limit:{rule.name}:{client_host}"


def _client_host(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    if request.client is not None:
        return request.client.host
    return "unknown"
