from __future__ import annotations

import hashlib
import json
from typing import Any

from fastapi import Request, Response, status
from fastapi.encoders import jsonable_encoder

PUBLIC_STABLE_CACHE = "public, max-age=60, stale-while-revalidate=300"
PUBLIC_REVALIDATE_CACHE = "no-cache"
PRIVATE_NO_STORE_CACHE = "private, no-store"


def stable_etag(value: Any) -> str:
    payload = json.dumps(
        jsonable_encoder(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f'"{hashlib.sha256(payload).hexdigest()}"'


def is_not_modified(request: Request, etag: str) -> bool:
    header = request.headers.get("if-none-match")
    if not header:
        return False
    normalized_etag = _normalize_etag_token(etag)
    candidates = {_normalize_etag_token(item) for item in header.split(",")}
    return "*" in candidates or normalized_etag in candidates


def set_cache_headers(response: Response, *, etag: str, cache_control: str) -> None:
    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = cache_control


def not_modified_response(*, etag: str, cache_control: str) -> Response:
    return Response(
        status_code=status.HTTP_304_NOT_MODIFIED,
        headers={"ETag": etag, "Cache-Control": cache_control},
    )


def _normalize_etag_token(value: str) -> str:
    token = value.strip()
    if token.startswith("W/"):
        token = token[2:].strip()
    return token.strip('"')
