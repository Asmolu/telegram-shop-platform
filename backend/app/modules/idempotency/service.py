from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.models import IdempotencyRecord
from app.modules.idempotency.repository import IdempotencyRepository

IDEMPOTENCY_TTL_HOURS = 24
IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")


@dataclass
class IdempotencyClaim:
    record: IdempotencyRecord | None
    replay_response: dict[str, Any] | None = None

    @property
    def is_replay(self) -> bool:
        return self.replay_response is not None


class IdempotencyService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        ttl: timedelta = timedelta(hours=IDEMPOTENCY_TTL_HOURS),
        now_factory=None,
    ) -> None:
        self.session = session
        self.repository = IdempotencyRepository(session)
        self.ttl = ttl
        self.now_factory = now_factory or (lambda: datetime.now(UTC))

    async def begin(
        self,
        *,
        user_id: int,
        scope: str,
        key: str,
        request_hash: str,
    ) -> IdempotencyClaim:
        normalized_key = self._normalize_key(key)
        now = self._now()
        await self.repository.cleanup_expired(now=now, user_id=user_id, scope=scope)
        inserted_id = await self.repository.insert_processing(
            user_id=user_id,
            scope=scope,
            key=normalized_key,
            request_hash=request_hash,
            expires_at=now + self.ttl,
        )
        if inserted_id is not None:
            record = await self.repository.get_by_id_for_update(inserted_id)
            if record is None:
                raise AppError(
                    "Idempotency record could not be created",
                    status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
            return IdempotencyClaim(record=record)

        record = await self.repository.get_by_key_for_update(
            user_id=user_id,
            scope=scope,
            key=normalized_key,
        )
        if record is None:
            raise AppError(
                "Idempotency record could not be loaded",
                status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        if record.request_hash != request_hash:
            raise AppError(
                "Idempotency-Key was already used with different request payload",
                status.HTTP_409_CONFLICT,
            )

        if record.status == "SUCCEEDED" and isinstance(record.response_body, dict):
            return IdempotencyClaim(record=record, replay_response=record.response_body)

        raise AppError(
            "Request with this Idempotency-Key is still processing",
            status.HTTP_409_CONFLICT,
        )

    def complete(
        self,
        claim: IdempotencyClaim | None,
        *,
        response_body: dict[str, Any],
        response_status_code: int,
    ) -> None:
        if claim is None or claim.record is None:
            return
        self.repository.mark_succeeded(
            claim.record,
            response_body=response_body,
            response_status_code=response_status_code,
            completed_at=self._now(),
        )

    @staticmethod
    def hash_payload(payload: Any) -> str:
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _normalize_key(key: str) -> str:
        normalized = key.strip()
        if not IDEMPOTENCY_KEY_PATTERN.fullmatch(normalized):
            raise AppError("Invalid Idempotency-Key", status.HTTP_422_UNPROCESSABLE_CONTENT)
        return normalized

    def _now(self) -> datetime:
        return self.now_factory()
