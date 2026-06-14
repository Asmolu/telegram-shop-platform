import asyncio
import logging
from datetime import UTC, datetime

from app.core.config import settings
from app.db.session import async_session_factory
from app.modules.manual_payments.repository import ManualPaymentsRepository
from app.modules.manual_payments.service import ManualPaymentsService

logger = logging.getLogger(__name__)


async def run_manual_payment_expiration_worker(stop_event: asyncio.Event) -> None:
    poll_seconds = max(1, settings.manual_payment_expiration_poll_seconds)
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=poll_seconds)
            continue
        except TimeoutError:
            pass

        try:
            await process_due_manual_payments()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error(
                "manual payment expiration worker cycle failed",
                extra={"error_type": type(exc).__name__},
            )


async def process_due_manual_payments(*, limit: int = 100) -> int:
    async with async_session_factory() as session:
        repository = ManualPaymentsRepository(session)
        payment_ids = await repository.list_due_ids(now=datetime.now(UTC), limit=limit)

    expired_count = 0
    for payment_id in payment_ids:
        try:
            async with async_session_factory() as session:
                service = ManualPaymentsService(session)
                if await service.expire_due_payment(payment_id):
                    expired_count += 1
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error(
                "manual payment expiration failed",
                extra={
                    "payment_id": payment_id,
                    "error_type": type(exc).__name__,
                },
            )
    return expired_count
