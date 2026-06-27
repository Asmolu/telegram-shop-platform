from __future__ import annotations

from datetime import UTC, datetime, timedelta
from io import BytesIO

import pytest
from fastapi.testclient import TestClient

from app.common.deps import get_current_user
from app.core.config import settings
from app.core.errors import AppError
from app.db.models import (
    BroadcastCampaign,
    BroadcastCampaignStatus,
    BroadcastCampaignType,
    BroadcastDelivery,
    BroadcastDeliveryStatus,
    CustomerTelegramSubscription,
    NotificationChannel,
    NotificationTemplate,
    NotificationTemplateCategory,
    User,
    UserRole,
)
from app.main import create_app
from app.modules.customer_notifications.campaigns.router import get_customer_campaign_service
from app.modules.customer_notifications.campaigns.schemas import (
    BroadcastCampaignCreate,
    BroadcastCampaignList,
    BroadcastCampaignProcessBatchRequest,
    BroadcastCampaignScheduleRequest,
    BroadcastCampaignTestRequest,
    BroadcastDeliveryList,
    BroadcastDeliverySummary,
    NotificationTemplateCreate,
    NotificationTemplateList,
    NotificationTemplateRead,
    NotificationTemplateUpdate,
)
from app.modules.customer_notifications.campaigns.service import (
    CustomerCampaignTelegramSender,
    CustomerNotificationCampaignService,
)
from app.modules.telegram.service import TelegramDeliveryError
from app.modules.uploads.service import ValidatedImageUpload


class DummySession:
    def __init__(self) -> None:
        self.commits = 0
        self.rolled_back = False
        self.flushed = False

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rolled_back = True

    async def flush(self) -> None:
        self.flushed = True

    async def refresh(self, _: object) -> None:
        return None


class FakeAuditService:
    def __init__(self) -> None:
        self.actions: list[dict[str, object]] = []

    async def record_action(self, **kwargs: object) -> None:
        self.actions.append(kwargs)


class FakeCampaignSender:
    def __init__(self, errors: list[TelegramDeliveryError] | None = None) -> None:
        self.errors = errors or []
        self.messages: list[tuple[int, str, str | None]] = []
        self.photos: list[tuple[int, bytes, str, str, str]] = []

    async def send_message(
        self,
        *,
        chat_id: int,
        message: str,
        parse_mode: str | None = None,
    ) -> int | None:
        self.messages.append((chat_id, message, parse_mode))
        if self.errors:
            raise self.errors.pop(0)
        return 777

    async def send_photo(
        self,
        *,
        chat_id: int,
        photo: bytes,
        filename: str,
        mime_type: str,
        caption: str,
    ) -> int | None:
        self.photos.append((chat_id, photo, filename, mime_type, caption))
        if self.errors:
            raise self.errors.pop(0)
        return 778


class FakeStorage:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.deleted: list[str] = []
        self.next_id = 1

    def save_bytes(self, content: bytes, *, folder: str, suffix: str) -> str:
        path = f"{folder}/image-{self.next_id}{suffix}"
        self.next_id += 1
        self.files[path] = content
        return path

    def delete(self, relative_path: str) -> None:
        self.deleted.append(relative_path)
        self.files.pop(relative_path, None)

    def exists(self, relative_path: str) -> bool:
        return relative_path in self.files

    def read_bytes(self, relative_path: str) -> bytes:
        if relative_path not in self.files:
            raise FileNotFoundError(relative_path)
        return self.files[relative_path]


class FakeUploadsService:
    def __init__(self, storage: FakeStorage) -> None:
        self.storage = storage

    async def validate_and_read_image(
        self,
        file: object,
        *,
        profile: object = None,
    ) -> ValidatedImageUpload:
        del profile
        original_filename = getattr(file, "filename", "") or "upload"
        content_type = getattr(file, "content_type", "") or ""
        content = await file.read(5 * 1024 * 1024 + 1)
        suffix = (
            "." + original_filename.rsplit(".", 1)[-1].lower()
            if "." in original_filename
            else ""
        )
        if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
            raise AppError("Invalid file extension", 400)
        if content_type not in {"image/jpeg", "image/png", "image/webp"}:
            raise AppError("Invalid MIME type", 400)
        if len(content) > 5 * 1024 * 1024:
            raise AppError("File size exceeds limit", 400)
        return ValidatedImageUpload(
            content=content,
            extension=suffix,
            original_filename=original_filename,
            mime_type=content_type,
            size_bytes=len(content),
        )


class FakeUploadFile:
    def __init__(
        self,
        *,
        filename: str = "campaign.png",
        content_type: str = "image/png",
        content: bytes = b"image-bytes",
    ) -> None:
        self.filename = filename
        self.content_type = content_type
        self._file = BytesIO(content)

    async def read(self, _: int = -1) -> bytes:
        return self._file.read()


class FakeCampaignRepository:
    def __init__(self) -> None:
        self.templates: dict[int, NotificationTemplate] = {}
        self.campaigns: dict[int, BroadcastCampaign] = {}
        self.deliveries: list[BroadcastDelivery] = []
        self.subscriptions: dict[int, CustomerTelegramSubscription] = {}
        self.next_template_id = 1
        self.next_campaign_id = 1
        self.next_delivery_id = 1

    def add_template(self, template: NotificationTemplate) -> None:
        template.id = self.next_template_id
        self.next_template_id += 1
        template.created_at = _now()
        template.updated_at = _now()
        self.templates[template.id] = template

    def add_campaign(self, campaign: BroadcastCampaign) -> None:
        campaign.id = self.next_campaign_id
        self.next_campaign_id += 1
        campaign.created_at = _now()
        campaign.updated_at = _now()
        self.campaigns[campaign.id] = campaign

    def add_deliveries(self, deliveries: list[BroadcastDelivery]) -> None:
        for delivery in deliveries:
            delivery.id = self.next_delivery_id
            self.next_delivery_id += 1
            delivery.created_at = _now()
            delivery.updated_at = _now()
            delivery.subscription = self.subscriptions[delivery.subscription_id]
            self.deliveries.append(delivery)

    async def get_template_by_id(self, template_id: int) -> NotificationTemplate | None:
        return self.templates.get(template_id)

    async def list_templates(self, **_: object) -> tuple[list[NotificationTemplate], int]:
        return list(self.templates.values()), len(self.templates)

    async def get_campaign_by_id(self, campaign_id: int) -> BroadcastCampaign | None:
        return self.campaigns.get(campaign_id)

    async def get_campaign_by_id_for_update(self, campaign_id: int) -> BroadcastCampaign | None:
        return self.campaigns.get(campaign_id)

    async def list_campaigns(self, **_: object) -> tuple[list[BroadcastCampaign], int]:
        return list(self.campaigns.values()), len(self.campaigns)

    async def count_eligible_recipients(
        self,
        *,
        campaign_type: BroadcastCampaignType,
        audience_filter: object,
    ) -> int:
        return len(
            [
                subscription
                for subscription in self.subscriptions.values()
                if self._eligible(
                    subscription,
                    campaign_type,
                    require_user=getattr(audience_filter, "scope", "all") != "connected",
                )
                and getattr(audience_filter, "scope", "all") in {"all", "connected"}
            ]
        )

    async def list_eligible_recipients(
        self,
        *,
        campaign_type: BroadcastCampaignType,
        audience_filter: object,
    ) -> list[CustomerTelegramSubscription]:
        return [
            subscription
            for subscription in self.subscriptions.values()
            if self._eligible(
                subscription,
                campaign_type,
                require_user=getattr(audience_filter, "scope", "all") != "connected",
            )
            and getattr(audience_filter, "scope", "all") in {"all", "connected"}
        ]

    async def count_campaign_deliveries(self, campaign_id: int) -> int:
        return len(
            [delivery for delivery in self.deliveries if delivery.campaign_id == campaign_id]
        )

    async def delivery_summary(self, campaign_id: int) -> dict[BroadcastDeliveryStatus, int]:
        summary: dict[BroadcastDeliveryStatus, int] = {}
        for delivery in self.deliveries:
            if delivery.campaign_id != campaign_id:
                continue
            summary[delivery.status] = summary.get(delivery.status, 0) + 1
        return summary

    async def list_deliveries(
        self,
        *,
        campaign_id: int,
        status: BroadcastDeliveryStatus | None = None,
        **_: object,
    ) -> tuple[list[BroadcastDelivery], int]:
        deliveries = [
            delivery
            for delivery in self.deliveries
            if delivery.campaign_id == campaign_id and (status is None or delivery.status == status)
        ]
        return deliveries, len(deliveries)

    async def deliveries_for_processing(
        self,
        *,
        campaign_id: int,
        now: datetime,
        limit: int,
    ) -> list[BroadcastDelivery]:
        processable = []
        for delivery in self.deliveries:
            if delivery.campaign_id != campaign_id:
                continue
            if delivery.status not in {
                BroadcastDeliveryStatus.PENDING,
                BroadcastDeliveryStatus.RATE_LIMITED,
            }:
                continue
            if delivery.next_attempt_at is not None and delivery.next_attempt_at > now:
                continue
            processable.append(delivery)
        return processable[:limit]

    async def recover_stale_sending_deliveries(self, **_: object) -> int:
        return 0

    async def count_unfinished_deliveries(self, *, campaign_id: int) -> int:
        return len(
            [
                delivery
                for delivery in self.deliveries
                if delivery.campaign_id == campaign_id
                and delivery.status
                in {
                    BroadcastDeliveryStatus.PENDING,
                    BroadcastDeliveryStatus.SENDING,
                    BroadcastDeliveryStatus.RATE_LIMITED,
                }
            ]
        )

    async def count_remaining_processable(self, **_: object) -> int:
        return 0

    async def skip_remaining_deliveries(
        self,
        *,
        campaign_id: int,
        now: datetime,
        error_code: str,
        error_message: str,
    ) -> int:
        skipped = 0
        for delivery in self.deliveries:
            if delivery.campaign_id != campaign_id:
                continue
            if delivery.status in {
                BroadcastDeliveryStatus.PENDING,
                BroadcastDeliveryStatus.SENDING,
                BroadcastDeliveryStatus.RATE_LIMITED,
            }:
                skipped += 1
                delivery.status = BroadcastDeliveryStatus.SKIPPED
                delivery.next_attempt_at = None
                delivery.error_code = error_code
                delivery.error_message = error_message
                delivery.updated_at = now
        return skipped

    async def get_test_subscription_for_user(
        self,
        *,
        user_id: int,
        telegram_user_id: int,
    ) -> CustomerTelegramSubscription | None:
        for subscription in self.subscriptions.values():
            if subscription.user_id == user_id or subscription.telegram_user_id == telegram_user_id:
                return subscription
        return None

    def _eligible(
        self,
        subscription: CustomerTelegramSubscription,
        campaign_type: BroadcastCampaignType,
        *,
        require_user: bool = True,
    ) -> bool:
        if require_user and subscription.user_id is None:
            return False
        if not subscription.has_chat or subscription.telegram_chat_id is None:
            return False
        if subscription.chat_type != "private" or subscription.blocked_at is not None:
            return False
        if campaign_type == BroadcastCampaignType.MARKETING:
            return subscription.marketing_opt_in
        return subscription.service_opt_in


@pytest.mark.asyncio
async def test_template_create_update_disable_create_audit_logs() -> None:
    service, repository, _, audit = _service()

    template = await service.create_template(
        actor=_user(role=UserRole.SELLER),
        payload=NotificationTemplateCreate(
            key="marketing.drop",
            name="Drop",
            category=NotificationTemplateCategory.MARKETING,
            body_template="Hi {name}",
            allowed_variables=["name"],
        ),
    )
    updated = await service.update_template(
        template_id=template.id,
        actor=_user(role=UserRole.SELLER),
        payload=NotificationTemplateUpdate(name="Drop v2"),
    )
    disabled = await service.disable_template(
        template_id=template.id,
        actor=_user(role=UserRole.SELLER),
    )

    assert template.id in repository.templates
    assert updated.name == "Drop v2"
    assert disabled.is_active is False
    assert [action["action"] for action in audit.actions] == [
        "customer_notifications.template_created",
        "customer_notifications.template_updated",
        "customer_notifications.template_disabled",
    ]


@pytest.mark.asyncio
async def test_campaign_draft_creation_works_for_seller() -> None:
    service, _, _, audit = _service()

    campaign = await service.create_campaign(
        actor=_user(role=UserRole.SELLER),
        payload=_campaign_payload(campaign_type=BroadcastCampaignType.MARKETING),
    )

    assert campaign.status == BroadcastCampaignStatus.DRAFT
    assert campaign.created_by_user_id == 1
    assert audit.actions[-1]["action"] == "customer_notifications.campaign_created"


def test_user_cannot_manage_customer_campaigns() -> None:
    app = _app_with_current_user(_user(role=UserRole.USER))
    app.dependency_overrides[get_customer_campaign_service] = lambda: FakeApiService()
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/customer-notifications/campaigns")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_unauthenticated_campaign_management_is_rejected() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/customer-notifications/campaigns")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_campaign_preview_estimates_only_eligible_recipients() -> None:
    service, repository, _, _ = _service()
    repository.subscriptions = {
        1: _subscription(marketing_opt_in=True),
        2: _subscription(id=2, user_id=2, telegram_user_id=43, marketing_opt_in=False),
        3: _subscription(id=3, user_id=3, telegram_user_id=44, has_chat=False),
        4: _subscription(id=4, user_id=4, telegram_user_id=45, blocked_at=_now()),
    }
    campaign = await service.create_campaign(
        actor=_user(role=UserRole.SELLER),
        payload=_campaign_payload(campaign_type=BroadcastCampaignType.MARKETING),
    )

    preview = await service.preview_campaign(campaign.id)

    assert preview.recipient_count_estimate == 1
    assert "Marketing estimate excludes" in " ".join(preview.eligibility_warnings)


@pytest.mark.asyncio
async def test_service_campaign_preview_excludes_service_opt_out_and_missing_chat() -> None:
    service, repository, _, _ = _service()
    repository.subscriptions = {
        1: _subscription(service_opt_in=True),
        2: _subscription(id=2, user_id=2, telegram_user_id=43, service_opt_in=False),
        3: _subscription(id=3, user_id=3, telegram_user_id=44, has_chat=False),
    }
    campaign = await service.create_campaign(
        actor=_user(role=UserRole.SELLER),
        payload=_campaign_payload(campaign_type=BroadcastCampaignType.SERVICE),
    )

    preview = await service.preview_campaign(campaign.id)

    assert preview.recipient_count_estimate == 1


@pytest.mark.asyncio
async def test_connected_audience_includes_unlinked_active_bot1_subscriptions() -> None:
    service, repository, _, _ = _service()
    repository.subscriptions = {
        1: _subscription(marketing_opt_in=True),
        2: _subscription(id=2, user_id=None, telegram_user_id=43, marketing_opt_in=True),
        3: _subscription(id=3, user_id=None, telegram_user_id=44, marketing_opt_in=False),
    }
    campaign = await service.create_campaign(
        actor=_user(role=UserRole.SELLER),
        payload=BroadcastCampaignCreate(
            name="Campaign",
            type=BroadcastCampaignType.MARKETING,
            audience_filter={"scope": "connected"},
            message_body="Campaign body",
        ),
    )

    preview = await service.preview_campaign(campaign.id)
    started = await service.schedule_campaign(
        campaign_id=campaign.id,
        actor=_user(role=UserRole.SELLER),
        payload=BroadcastCampaignScheduleRequest(),
        start_now=True,
    )

    assert preview.recipient_count_estimate == 2
    assert started.recipient_count_final == 2
    assert [delivery.user_id for delivery in repository.deliveries] == [1, None]


def test_customer_campaign_sender_uses_customer_bot_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "telegram_customer_bot_token", "customer-token")
    monkeypatch.setattr(settings, "telegram_bot_token", "seller-token")
    monkeypatch.setattr(settings, "telegram_webapp_bot_token", "webapp-token")

    sender = CustomerCampaignTelegramSender()

    assert sender.telegram_service.bot_token == "customer-token"


@pytest.mark.asyncio
async def test_start_materializes_delivery_rows_without_synchronous_broadcast() -> None:
    service, repository, sender, _ = _service()
    repository.subscriptions = {
        1: _subscription(marketing_opt_in=True),
        2: _subscription(id=2, user_id=2, telegram_user_id=43, marketing_opt_in=True),
    }
    campaign = await service.create_campaign(
        actor=_user(role=UserRole.SELLER),
        payload=_campaign_payload(campaign_type=BroadcastCampaignType.MARKETING),
    )

    started = await service.schedule_campaign(
        campaign_id=campaign.id,
        actor=_user(role=UserRole.SELLER),
        payload=BroadcastCampaignScheduleRequest(),
        start_now=True,
    )

    assert started.status == BroadcastCampaignStatus.SENDING
    assert len(repository.deliveries) == 2
    assert sender.messages == []


@pytest.mark.asyncio
async def test_campaign_image_attach_validates_and_persists_metadata() -> None:
    service, repository, _, audit = _service()
    campaign = await service.create_campaign(
        actor=_user(role=UserRole.SELLER),
        payload=_campaign_payload(campaign_type=BroadcastCampaignType.MARKETING),
    )

    updated = await service.attach_campaign_image(
        campaign_id=campaign.id,
        actor=_user(role=UserRole.SELLER),
        file=FakeUploadFile(filename="sale.webp", content_type="image/webp"),
    )

    assert updated.image_path == "customer_campaigns/image-1.webp"
    assert updated.image_url == "/uploads/customer_campaigns/image-1.webp"
    assert updated.image_original_filename == "sale.webp"
    assert updated.image_mime_type == "image/webp"
    assert updated.image_size_bytes == len(b"image-bytes")
    assert audit.actions[-1]["action"] == "customer_notifications.campaign_image_attached"


@pytest.mark.asyncio
async def test_campaign_image_attach_rejects_invalid_mime_type() -> None:
    service, _, _, _ = _service()
    campaign = await service.create_campaign(
        actor=_user(role=UserRole.SELLER),
        payload=_campaign_payload(campaign_type=BroadcastCampaignType.MARKETING),
    )

    with pytest.raises(AppError, match="Invalid MIME type"):
        await service.attach_campaign_image(
            campaign_id=campaign.id,
            actor=_user(role=UserRole.SELLER),
            file=FakeUploadFile(filename="sale.png", content_type="text/plain"),
        )


@pytest.mark.asyncio
async def test_campaign_image_attach_remove_allowed_only_for_draft_or_paused() -> None:
    service, repository, _, _ = _service()
    draft = await service.create_campaign(
        actor=_user(role=UserRole.SELLER),
        payload=_campaign_payload(campaign_type=BroadcastCampaignType.MARKETING),
    )
    repository.campaigns[draft.id].status = BroadcastCampaignStatus.SCHEDULED

    with pytest.raises(AppError, match="Only draft or paused campaigns can change images"):
        await service.attach_campaign_image(
            campaign_id=draft.id,
            actor=_user(role=UserRole.SELLER),
            file=FakeUploadFile(),
        )

    repository.campaigns[draft.id].status = BroadcastCampaignStatus.PAUSED
    attached = await service.attach_campaign_image(
        campaign_id=draft.id,
        actor=_user(role=UserRole.SELLER),
        file=FakeUploadFile(),
    )
    removed = await service.remove_campaign_image(
        campaign_id=draft.id,
        actor=_user(role=UserRole.SELLER),
    )

    assert attached.image_path is not None
    assert removed.image_path is None


@pytest.mark.asyncio
async def test_campaign_image_enforces_caption_limit_but_text_only_allows_4096() -> None:
    service, _, _, _ = _service()
    text_only = await service.create_campaign(
        actor=_user(role=UserRole.SELLER),
        payload=BroadcastCampaignCreate(
            name="Long",
            type=BroadcastCampaignType.MARKETING,
            audience_filter={"scope": "all"},
            message_body="x" * 4096,
        ),
    )
    with_image = await service.create_campaign(
        actor=_user(role=UserRole.SELLER),
        payload=BroadcastCampaignCreate(
            name="Long image",
            type=BroadcastCampaignType.MARKETING,
            audience_filter={"scope": "all"},
            message_body="x" * 1025,
        ),
    )

    assert text_only.message_body == "x" * 4096
    with pytest.raises(AppError, match="caption"):
        await service.attach_campaign_image(
            campaign_id=with_image.id,
            actor=_user(role=UserRole.SELLER),
            file=FakeUploadFile(),
        )


@pytest.mark.asyncio
async def test_invalid_campaign_enable_returns_actionable_fields() -> None:
    service, repository, _, _ = _service()
    repository.subscriptions = {1: _subscription(marketing_opt_in=True)}
    campaign = await service.create_campaign(
        actor=_user(role=UserRole.SELLER),
        payload=BroadcastCampaignCreate(
            name=" ",
            type=BroadcastCampaignType.MARKETING,
            audience_filter={"scope": "all"},
            message_body=" ",
        ),
    )

    with pytest.raises(AppError, match="name is required") as exc_info:
        await service.schedule_campaign(
            campaign_id=campaign.id,
            actor=_user(role=UserRole.SELLER),
            payload=BroadcastCampaignScheduleRequest(),
            start_now=True,
        )

    assert exc_info.value.status_code == 422
    assert "message_body is required" in exc_info.value.message


@pytest.mark.asyncio
async def test_process_batch_sends_bounded_pending_deliveries() -> None:
    service, repository, sender, _ = _service()
    campaign = _campaign(status=BroadcastCampaignStatus.SENDING)
    repository.campaigns[campaign.id] = campaign
    repository.subscriptions = {
        1: _subscription(),
        2: _subscription(id=2, user_id=2, telegram_user_id=43),
        3: _subscription(id=3, user_id=3, telegram_user_id=44),
    }
    repository.add_deliveries(
        [
            _delivery(campaign_id=campaign.id, subscription=subscription)
            for subscription in repository.subscriptions.values()
        ]
    )

    response = await service.process_batch(
        campaign_id=campaign.id,
        actor=_user(role=UserRole.ADMIN),
        payload=BroadcastCampaignProcessBatchRequest(limit=2),
    )

    assert response.processed == 2
    assert response.sent == 2
    assert response.remaining == 1
    assert len(sender.messages) == 2


@pytest.mark.asyncio
async def test_successful_batch_send_stores_message_id_and_sent_at() -> None:
    service, repository, _, _ = _service()
    campaign, delivery, subscription = _campaign_with_delivery(repository)

    await service.process_batch(
        campaign_id=campaign.id,
        actor=_user(role=UserRole.ADMIN),
        payload=BroadcastCampaignProcessBatchRequest(limit=1),
    )

    assert delivery.status == BroadcastDeliveryStatus.SENT
    assert delivery.telegram_message_id == 777
    assert delivery.sent_at == _now()
    assert subscription.blocked_at is None


@pytest.mark.asyncio
async def test_repeated_processing_is_idempotent_after_success() -> None:
    service, repository, sender, _ = _service()
    campaign, _, _ = _campaign_with_delivery(repository)

    first = await service.process_batch(
        campaign_id=campaign.id,
        actor=_user(role=UserRole.ADMIN),
        payload=BroadcastCampaignProcessBatchRequest(limit=1),
    )
    second = await service.process_batch(
        campaign_id=campaign.id,
        actor=_user(role=UserRole.ADMIN),
        payload=BroadcastCampaignProcessBatchRequest(limit=1),
    )

    assert first.sent == 1
    assert second.processed == 0
    assert second.campaign_status == BroadcastCampaignStatus.COMPLETED
    assert len(sender.messages) == 1


@pytest.mark.asyncio
async def test_consent_revoked_after_activation_is_skipped() -> None:
    service, repository, sender, _ = _service()
    campaign, delivery, subscription = _campaign_with_delivery(repository)
    subscription.marketing_opt_in = False

    response = await service.process_batch(
        campaign_id=campaign.id,
        actor=_user(role=UserRole.ADMIN),
        payload=BroadcastCampaignProcessBatchRequest(limit=1),
    )

    assert response.skipped == 1
    assert delivery.status == BroadcastDeliveryStatus.SKIPPED
    assert delivery.error_code == "consent_revoked"
    assert sender.messages == []


@pytest.mark.asyncio
async def test_telegram_403_marks_delivery_and_subscription_blocked() -> None:
    error = TelegramDeliveryError(
        "Forbidden: bot was blocked by the user",
        error_code=403,
        status_code=403,
    )
    service, repository, _, _ = _service(errors=[error])
    campaign, delivery, subscription = _campaign_with_delivery(repository)

    await service.process_batch(
        campaign_id=campaign.id,
        actor=_user(role=UserRole.ADMIN),
        payload=BroadcastCampaignProcessBatchRequest(limit=1),
    )

    assert delivery.status == BroadcastDeliveryStatus.BLOCKED
    assert delivery.error_code == "blocked"
    assert subscription.blocked_at == _now()
    assert subscription.has_chat is False


@pytest.mark.asyncio
async def test_telegram_429_records_retry_after_and_next_attempt() -> None:
    error = TelegramDeliveryError(
        "Too Many Requests: retry after 12",
        error_code=429,
        status_code=429,
        retry_after_seconds=12,
    )
    service, repository, _, _ = _service(errors=[error])
    campaign, delivery, _ = _campaign_with_delivery(repository)

    await service.process_batch(
        campaign_id=campaign.id,
        actor=_user(role=UserRole.ADMIN),
        payload=BroadcastCampaignProcessBatchRequest(limit=1),
    )

    assert delivery.status == BroadcastDeliveryStatus.RATE_LIMITED
    assert delivery.retry_after_seconds == 12
    assert delivery.next_attempt_at == _now() + timedelta(seconds=12)


@pytest.mark.asyncio
async def test_terminal_telegram_error_is_failed_and_secrets_are_redacted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_customer_bot_token", "customer-secret")
    error = TelegramDeliveryError("request failed with customer-secret")
    service, repository, _, _ = _service(errors=[error])
    campaign, delivery, _ = _campaign_with_delivery(repository)
    delivery.attempt_count = settings.customer_campaign_max_attempts - 1

    response = await service.process_batch(
        campaign_id=campaign.id,
        actor=_user(role=UserRole.ADMIN),
        payload=BroadcastCampaignProcessBatchRequest(limit=1),
    )

    assert response.failed == 1
    assert delivery.status == BroadcastDeliveryStatus.FAILED
    assert "customer-secret" not in (delivery.error_message or "")
    assert "[redacted]" in (delivery.error_message or "")


@pytest.mark.asyncio
async def test_cancelled_campaign_skips_remaining_pending_deliveries() -> None:
    service, repository, _, _ = _service()
    campaign, delivery, _ = _campaign_with_delivery(repository)

    cancelled = await service.cancel_campaign(
        campaign_id=campaign.id,
        actor=_user(role=UserRole.ADMIN),
    )

    assert cancelled.status == BroadcastCampaignStatus.CANCELLED
    assert delivery.status == BroadcastDeliveryStatus.SKIPPED
    assert delivery.error_code == "campaign_cancelled"


@pytest.mark.asyncio
async def test_delivery_summary_aggregates_status_counts() -> None:
    service, repository, _, _ = _service()
    campaign = _campaign(status=BroadcastCampaignStatus.SENDING)
    repository.campaigns[campaign.id] = campaign
    repository.subscriptions = {
        1: _subscription(),
        2: _subscription(id=2, user_id=2, telegram_user_id=43),
    }
    repository.add_deliveries(
        [
            _delivery(
                campaign_id=campaign.id,
                subscription=repository.subscriptions[1],
                delivery_status=BroadcastDeliveryStatus.SENT,
            ),
            _delivery(
                campaign_id=campaign.id,
                subscription=repository.subscriptions[2],
                delivery_status=BroadcastDeliveryStatus.FAILED,
            ),
        ]
    )

    summary = await service.get_delivery_summary(campaign.id)

    assert summary.sent == 1
    assert summary.failed == 1
    assert summary.total == 2


@pytest.mark.asyncio
async def test_send_test_campaign_uses_actor_bot_1_subscription() -> None:
    service, repository, sender, audit = _service()
    repository.subscriptions = {1: _subscription(user_id=1, telegram_user_id=42)}
    campaign = await service.create_campaign(
        actor=_user(role=UserRole.SELLER),
        payload=_campaign_payload(campaign_type=BroadcastCampaignType.MARKETING),
    )

    response = await service.send_test_message(
        campaign_id=campaign.id,
        actor=_user(role=UserRole.SELLER),
        payload=BroadcastCampaignTestRequest(),
    )

    assert response.telegram_message_id == 777
    assert sender.messages == [(100, "Campaign body", None)]
    assert audit.actions[-1]["action"] == "customer_notifications.test_message_sent"


@pytest.mark.asyncio
async def test_send_test_campaign_uses_send_photo_when_image_present() -> None:
    service, repository, sender, _ = _service()
    repository.subscriptions = {1: _subscription(user_id=1, telegram_user_id=42)}
    campaign = await service.create_campaign(
        actor=_user(role=UserRole.SELLER),
        payload=_campaign_payload(campaign_type=BroadcastCampaignType.MARKETING),
    )
    saved = await service.attach_campaign_image(
        campaign_id=campaign.id,
        actor=_user(role=UserRole.SELLER),
        file=FakeUploadFile(filename="campaign.png", content_type="image/png"),
    )

    response = await service.send_test_message(
        campaign_id=saved.id,
        actor=_user(role=UserRole.SELLER),
        payload=BroadcastCampaignTestRequest(),
    )

    assert response.telegram_message_id == 778
    assert sender.messages == []
    assert sender.photos == [(100, b"image-bytes", "campaign.png", "image/png", "Campaign body")]


@pytest.mark.asyncio
async def test_delivery_processing_uses_send_photo_when_image_present() -> None:
    service, repository, sender, _ = _service()
    campaign, delivery, subscription = _campaign_with_delivery(repository)
    campaign.image_path = "customer_campaigns/campaign.png"
    campaign.image_original_filename = "campaign.png"
    campaign.image_mime_type = "image/png"
    service.storage.files[campaign.image_path] = b"image-bytes"  # type: ignore[attr-defined]

    response = await service.process_batch(
        campaign_id=campaign.id,
        actor=_user(role=UserRole.ADMIN),
        payload=BroadcastCampaignProcessBatchRequest(limit=1),
    )

    assert response.sent == 1
    assert delivery.status == BroadcastDeliveryStatus.SENT
    assert delivery.telegram_message_id == 778
    assert subscription.blocked_at is None
    assert sender.messages == []
    assert sender.photos == [(100, b"image-bytes", "campaign.png", "image/png", "Campaign body")]


@pytest.mark.asyncio
async def test_missing_campaign_image_fails_campaign_safely() -> None:
    service, repository, sender, _ = _service()
    campaign, delivery, _ = _campaign_with_delivery(repository)
    campaign.image_path = "customer_campaigns/missing.png"
    campaign.image_original_filename = "missing.png"
    campaign.image_mime_type = "image/png"

    response = await service.process_batch(
        campaign_id=campaign.id,
        actor=_user(role=UserRole.ADMIN),
        payload=BroadcastCampaignProcessBatchRequest(limit=1),
    )

    assert response.processed == 0
    assert response.skipped == 1
    assert response.campaign_status == BroadcastCampaignStatus.FAILED
    assert campaign.status == BroadcastCampaignStatus.FAILED
    assert delivery.status == BroadcastDeliveryStatus.SKIPPED
    assert delivery.error_code == "campaign_image_missing"
    assert delivery.error_message == "Campaign image file is unavailable"
    assert sender.messages == []
    assert sender.photos == []


class FakeApiService:
    async def list_campaigns(self, **_: object) -> BroadcastCampaignList:
        return BroadcastCampaignList(items=[], meta={"limit": 20, "offset": 0, "total": 0})

    async def create_template(
        self,
        *,
        actor: User,
        payload: NotificationTemplateCreate,
    ) -> NotificationTemplateRead:
        del actor, payload
        return NotificationTemplateRead(
            id=1,
            key="marketing.test",
            name="Test",
            category=NotificationTemplateCategory.MARKETING,
            channel=NotificationChannel.TELEGRAM,
            title=None,
            body_template="Hello",
            parse_mode=None,
            allowed_variables=[],
            is_active=True,
            created_by_user_id=1,
            updated_by_user_id=1,
            created_at=_now(),
            updated_at=_now(),
        )

    async def list_templates(self, **_: object) -> NotificationTemplateList:
        return NotificationTemplateList(items=[], meta={"limit": 20, "offset": 0, "total": 0})

    async def list_deliveries(self, **_: object) -> BroadcastDeliveryList:
        return BroadcastDeliveryList(items=[], meta={"limit": 20, "offset": 0, "total": 0})

    async def get_delivery_summary(self, _: int) -> BroadcastDeliverySummary:
        return BroadcastDeliverySummary()


def _service(
    *,
    errors: list[TelegramDeliveryError] | None = None,
) -> tuple[
    CustomerNotificationCampaignService,
    FakeCampaignRepository,
    FakeCampaignSender,
    FakeAuditService,
]:
    repository = FakeCampaignRepository()
    sender = FakeCampaignSender(errors=errors)
    audit = FakeAuditService()
    storage = FakeStorage()
    service = CustomerNotificationCampaignService(
        DummySession(),
        repository=repository,
        sender=sender,
        audit_service=audit,
        uploads_service=FakeUploadsService(storage),  # type: ignore[arg-type]
        storage=storage,  # type: ignore[arg-type]
        now_factory=_now,
    )
    return service, repository, sender, audit


def _campaign_payload(
    *,
    campaign_type: BroadcastCampaignType,
) -> BroadcastCampaignCreate:
    return BroadcastCampaignCreate(
        name="Campaign",
        type=campaign_type,
        audience_filter={"scope": "all"},
        message_body="Campaign body",
    )


def _campaign_with_delivery(
    repository: FakeCampaignRepository,
) -> tuple[BroadcastCampaign, BroadcastDelivery, CustomerTelegramSubscription]:
    campaign = _campaign(status=BroadcastCampaignStatus.SENDING)
    subscription = _subscription()
    repository.campaigns[campaign.id] = campaign
    repository.subscriptions[subscription.id] = subscription
    repository.add_deliveries([_delivery(campaign_id=campaign.id, subscription=subscription)])
    return campaign, repository.deliveries[0], subscription


def _campaign(
    *,
    status: BroadcastCampaignStatus,
) -> BroadcastCampaign:
    return BroadcastCampaign(
        id=1,
        template_id=None,
        name="Campaign",
        type=BroadcastCampaignType.MARKETING,
        status=status,
        audience_filter={"scope": "all"},
        recipient_count_estimate=1,
        recipient_count_final=1,
        message_title=None,
        message_body="Campaign body",
        parse_mode=None,
        scheduled_at=None,
        started_at=_now() if status == BroadcastCampaignStatus.SENDING else None,
        completed_at=None,
        created_by_user_id=1,
        created_at=_now(),
        updated_at=_now(),
    )


def _delivery(
    *,
    campaign_id: int,
    subscription: CustomerTelegramSubscription,
    delivery_status: BroadcastDeliveryStatus = BroadcastDeliveryStatus.PENDING,
) -> BroadcastDelivery:
    return BroadcastDelivery(
        campaign_id=campaign_id,
        user_id=subscription.user_id,
        subscription_id=subscription.id,
        telegram_chat_id=subscription.telegram_chat_id,
        status=delivery_status,
        attempt_count=0,
        created_at=_now(),
        updated_at=_now(),
    )


def _subscription(
    *,
    id: int = 1,
    user_id: int | None = 1,
    telegram_user_id: int = 42,
    has_chat: bool = True,
    service_opt_in: bool = True,
    marketing_opt_in: bool = True,
    blocked_at: datetime | None = None,
) -> CustomerTelegramSubscription:
    return CustomerTelegramSubscription(
        id=id,
        user_id=user_id,
        telegram_user_id=telegram_user_id,
        telegram_chat_id=100 + id - 1,
        telegram_username="buyer",
        telegram_first_name="Ada",
        telegram_last_name=None,
        chat_type="private",
        has_chat=has_chat,
        service_opt_in=service_opt_in,
        marketing_opt_in=marketing_opt_in,
        blocked_at=blocked_at,
        created_at=_now(),
        updated_at=_now(),
    )


def _app_with_current_user(user: User):
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: user
    return app


def _user(role: UserRole = UserRole.USER) -> User:
    return User(
        id=1,
        telegram_id=42,
        username="seller",
        first_name="Ada",
        last_name=None,
        phone=None,
        role=role,
        is_active=True,
        created_at=_now(),
        updated_at=_now(),
    )


def _now() -> datetime:
    return datetime(2026, 6, 5, 12, 0, tzinfo=UTC)
