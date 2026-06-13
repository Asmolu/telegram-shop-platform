import asyncio
import logging
from datetime import UTC, datetime, timedelta

from app.core.config import settings
from app.db.session import async_session_factory
from app.modules.customer_notifications.campaigns.repository import (
    CustomerNotificationCampaignRepository,
)
from app.modules.customer_notifications.campaigns.schemas import (
    BroadcastCampaignProcessBatchRequest,
)
from app.modules.customer_notifications.campaigns.service import (
    CustomerNotificationCampaignService,
)

logger = logging.getLogger(__name__)


async def run_customer_campaign_worker(stop_event: asyncio.Event) -> None:
    poll_seconds = max(1, settings.customer_campaign_worker_poll_seconds)
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=poll_seconds)
            continue
        except TimeoutError:
            pass

        try:
            await process_due_campaign_batches()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error(
                "customer campaign worker cycle failed",
                extra={"error_type": type(exc).__name__},
            )


async def process_due_campaign_batches() -> int:
    now = datetime.now(UTC)
    async with async_session_factory() as session:
        repository = CustomerNotificationCampaignRepository(session)
        campaign_ids = await repository.list_due_campaign_ids(
            now=now,
            stale_before=now
            - timedelta(seconds=max(1, settings.customer_campaign_sending_timeout_seconds)),
            limit=20,
        )

    processed = 0
    for campaign_id in campaign_ids:
        try:
            async with async_session_factory() as session:
                service = CustomerNotificationCampaignService(session)
                result = await service.process_batch(
                    campaign_id=campaign_id,
                    actor=None,
                    payload=BroadcastCampaignProcessBatchRequest(),
                )
                processed += result.processed
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error(
                "customer campaign worker batch failed",
                extra={"campaign_id": campaign_id, "error_type": type(exc).__name__},
            )
    return processed
