from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import OutboxDelivery, OutboxEvent, OutboxStatus
from app.modules.outbox.schemas import OutboxClaim


class OutboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, event: OutboxEvent) -> None:
        self.session.add(event)

    async def claim_due(
        self,
        *,
        now: datetime,
        stale_before: datetime,
        worker_id: str,
        limit: int,
    ) -> list[OutboxClaim]:
        statement = (
            select(OutboxEvent)
            .options(selectinload(OutboxEvent.deliveries))
            .where(
                (
                    (OutboxEvent.status == OutboxStatus.PENDING)
                    & (OutboxEvent.next_attempt_at <= now)
                )
                | (
                    (OutboxEvent.status == OutboxStatus.PROCESSING)
                    & (
                        OutboxEvent.locked_at.is_(None)
                        | (OutboxEvent.locked_at < stale_before)
                    )
                )
            )
            .order_by(OutboxEvent.next_attempt_at, OutboxEvent.created_at, OutboxEvent.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        events = list((await self.session.execute(statement)).scalars().unique())
        claims: list[OutboxClaim] = []
        for event in events:
            recovered_stale = event.status == OutboxStatus.PROCESSING
            claim_token = uuid4()
            event.status = OutboxStatus.PROCESSING
            event.attempt_count += 1
            event.locked_at = now
            event.locked_by = worker_id
            event.claim_token = claim_token
            claims.append(
                OutboxClaim.create(
                    database_id=event.id,
                    event_id=event.event_id,
                    claim_token=claim_token,
                    event_name=event.event_name,
                    payload=dict(event.payload),
                    pending_consumers=tuple(
                        delivery.consumer
                        for delivery in event.deliveries
                        if delivery.status.value == "PENDING"
                    ),
                    attempt_count=event.attempt_count,
                    recovered_stale=recovered_stale,
                )
            )
        return claims

    async def get_owned_with_deliveries(
        self,
        *,
        event_database_id: int,
        claim_token: UUID,
        for_update: bool = False,
    ) -> OutboxEvent | None:
        statement = (
            select(OutboxEvent)
            .options(selectinload(OutboxEvent.deliveries))
            .where(
                OutboxEvent.id == event_database_id,
                OutboxEvent.status == OutboxStatus.PROCESSING,
                OutboxEvent.claim_token == claim_token,
            )
        )
        if for_update:
            statement = statement.with_for_update()
        return (await self.session.execute(statement)).scalars().unique().one_or_none()

    async def renew_claim(
        self,
        *,
        event_database_id: int,
        claim_token: UUID,
        now: datetime,
    ) -> bool:
        result = await self.session.execute(
            update(OutboxEvent)
            .where(
                OutboxEvent.id == event_database_id,
                OutboxEvent.status == OutboxStatus.PROCESSING,
                OutboxEvent.claim_token == claim_token,
            )
            .values(locked_at=now)
        )
        return bool(result.rowcount)

    async def get_with_deliveries(
        self, event_id: UUID, *, for_update: bool = False
    ) -> OutboxEvent | None:
        statement = (
            select(OutboxEvent)
            .options(selectinload(OutboxEvent.deliveries))
            .where(OutboxEvent.event_id == event_id)
        )
        if for_update:
            statement = statement.with_for_update()
        return (await self.session.execute(statement)).scalars().unique().one_or_none()

    async def get_delivery(
        self, *, event_id: UUID, consumer: str, for_update: bool = False
    ) -> tuple[OutboxEvent, OutboxDelivery] | None:
        statement = (
            select(OutboxEvent, OutboxDelivery)
            .join(OutboxDelivery, OutboxDelivery.outbox_event_id == OutboxEvent.id)
            .where(OutboxEvent.event_id == event_id, OutboxDelivery.consumer == consumer)
        )
        if for_update:
            statement = statement.with_for_update()
        return (await self.session.execute(statement)).one_or_none()

    async def counts(self) -> dict[str, int]:
        rows = await self.session.execute(
            select(OutboxEvent.status, func.count(OutboxEvent.id)).group_by(OutboxEvent.status)
        )
        return {status.value: count for status, count in rows}

    async def oldest_pending(self) -> OutboxEvent | None:
        return (
            await self.session.execute(
                select(OutboxEvent)
                .where(OutboxEvent.status == OutboxStatus.PENDING)
                .order_by(OutboxEvent.created_at, OutboxEvent.id)
                .limit(1)
            )
        ).scalar_one_or_none()

    async def list_failed(self, *, limit: int) -> list[OutboxEvent]:
        return list(
            (
                await self.session.execute(
                    select(OutboxEvent)
                    .options(selectinload(OutboxEvent.deliveries))
                    .where(OutboxEvent.status == OutboxStatus.FAILED)
                    .order_by(OutboxEvent.updated_at.desc(), OutboxEvent.id.desc())
                    .limit(limit)
                )
            )
            .scalars()
            .unique()
        )
