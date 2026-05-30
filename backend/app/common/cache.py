from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, TypeVar

from pydantic import BaseModel, TypeAdapter, ValidationError
from redis.exceptions import RedisError

from app.core.config import settings
from app.core.redis import get_redis_client

logger = logging.getLogger(__name__)

TModel = TypeVar("TModel", bound=BaseModel)
TValue = TypeVar("TValue")
CACHE_PREFIX = "cache:v1"


class CacheService:
    async def get_model(self, key: str, model_type: type[TModel]) -> TModel | None:
        raw = await self._get_raw(key)
        if raw is None:
            return None
        try:
            return model_type.model_validate_json(raw)
        except ValidationError:
            logger.debug("Redis cache payload validation failed", exc_info=True)
            return None

    async def set_model(self, key: str, value: BaseModel, ttl_seconds: int) -> None:
        await self._set_raw(key, value.model_dump_json(), ttl_seconds)

    async def get_value(self, key: str, adapter: TypeAdapter[TValue]) -> TValue | None:
        raw = await self._get_raw(key)
        if raw is None:
            return None
        try:
            return adapter.validate_json(raw)
        except ValidationError:
            logger.debug("Redis cache payload validation failed", exc_info=True)
            return None

    async def set_value(
        self,
        key: str,
        value: TValue,
        adapter: TypeAdapter[TValue],
        ttl_seconds: int,
    ) -> None:
        payload = adapter.dump_json(value).decode("utf-8")
        await self._set_raw(key, payload, ttl_seconds)

    async def delete(self, *keys: str) -> None:
        if not settings.cache_enabled or not keys:
            return
        try:
            await get_redis_client().delete(*keys)
        except (OSError, RedisError):
            logger.debug("Redis cache delete failed", exc_info=True)

    async def delete_patterns(self, *patterns: str) -> None:
        if not settings.cache_enabled:
            return
        try:
            redis = get_redis_client()
            keys: list[str] = []
            for pattern in patterns:
                async for key in redis.scan_iter(match=pattern):
                    keys.append(key)
            if keys:
                await redis.delete(*keys)
        except (OSError, RedisError):
            logger.debug("Redis cache pattern delete failed", exc_info=True)

    async def _get_raw(self, key: str) -> str | None:
        if not settings.cache_enabled:
            return None
        try:
            raw = await get_redis_client().get(key)
        except (OSError, RedisError):
            logger.debug("Redis cache get failed", exc_info=True)
            return None
        return raw if isinstance(raw, str) else None

    async def _set_raw(self, key: str, value: str, ttl_seconds: int) -> None:
        if not settings.cache_enabled or ttl_seconds <= 0:
            return
        try:
            await get_redis_client().setex(key, ttl_seconds, value)
        except (OSError, RedisError):
            logger.debug("Redis cache set failed", exc_info=True)


def public_products_list_key(
    *,
    limit: int,
    offset: int,
    category_id: int | None,
    tag_id: int | None,
    status: Any,
    search: str | None,
) -> str:
    return _stable_key(
        "catalog:products:list",
        {
            "limit": limit,
            "offset": offset,
            "category_id": category_id,
            "tag_id": tag_id,
            "status": _enum_value(status),
            "search": search.strip() if isinstance(search, str) else None,
        },
    )


def public_product_detail_key(product_id: int) -> str:
    return f"{CACHE_PREFIX}:catalog:products:detail:{product_id}"


def categories_list_key() -> str:
    return f"{CACHE_PREFIX}:catalog:categories:list"


def tags_list_key() -> str:
    return f"{CACHE_PREFIX}:catalog:tags:list"


def public_banners_list_key(*, limit: int, offset: int) -> str:
    return _stable_key("catalog:banners:list", {"limit": limit, "offset": offset})


def public_product_reviews_key(product_id: int) -> str:
    return f"{CACHE_PREFIX}:catalog:reviews:product:{product_id}"


def product_cache_patterns() -> tuple[str, str]:
    return (
        f"{CACHE_PREFIX}:catalog:products:list:*",
        f"{CACHE_PREFIX}:catalog:products:detail:*",
    )


def taxonomy_cache_patterns() -> tuple[str, str, str, str]:
    return (
        categories_list_key(),
        tags_list_key(),
        *product_cache_patterns(),
    )


def banner_cache_patterns() -> tuple[str]:
    return (f"{CACHE_PREFIX}:catalog:banners:list:*",)


def review_cache_patterns(product_id: int | None = None) -> tuple[str]:
    if product_id is None:
        return (f"{CACHE_PREFIX}:catalog:reviews:product:*",)
    return (public_product_reviews_key(product_id),)


def _stable_key(namespace: str, params: dict[str, object]) -> str:
    payload = json.dumps(params, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"{CACHE_PREFIX}:{namespace}:{digest}"


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)
