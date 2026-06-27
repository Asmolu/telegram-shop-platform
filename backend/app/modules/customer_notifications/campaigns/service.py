from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import UploadFile, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.pagination import PageMeta
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
)
from app.modules.audit.service import AuditService
from app.modules.customer_notifications.campaigns.repository import (
    PRIVATE_CHAT_TYPE,
    CustomerNotificationCampaignRepository,
)
from app.modules.customer_notifications.campaigns.schemas import (
    BroadcastAudienceFilter,
    BroadcastCampaignCreate,
    BroadcastCampaignDetail,
    BroadcastCampaignList,
    BroadcastCampaignPreview,
    BroadcastCampaignProcessBatchRequest,
    BroadcastCampaignProcessBatchResponse,
    BroadcastCampaignRead,
    BroadcastCampaignScheduleRequest,
    BroadcastCampaignTestRequest,
    BroadcastCampaignTestResponse,
    BroadcastCampaignUpdate,
    BroadcastDeliveryList,
    BroadcastDeliveryRead,
    BroadcastDeliverySummary,
    NotificationTemplateCreate,
    NotificationTemplateList,
    NotificationTemplateRead,
    NotificationTemplateUpdate,
)
from app.modules.telegram.service import TelegramDeliveryError, TelegramService
from app.modules.uploads.service import UploadsService
from app.modules.uploads.storage import LocalStorageService

TELEGRAM_MESSAGE_MAX_LENGTH = 4096
TELEGRAM_PHOTO_CAPTION_MAX_LENGTH = 1024
TELEGRAM_ERROR_MESSAGE_MAX_LENGTH = 500
CAMPAIGN_IMAGE_UPLOAD_FOLDER = "customer_campaigns"
TEMPLATE_PLACEHOLDER_RE = re.compile(r"\{(?P<name>[A-Za-z_][A-Za-z0-9_]{0,63})\}")
SUPPORTED_PARSE_MODES: set[str] = set()

logger = logging.getLogger(__name__)

ACTION_TEMPLATE_CREATED = "customer_notifications.template_created"
ACTION_TEMPLATE_UPDATED = "customer_notifications.template_updated"
ACTION_TEMPLATE_DISABLED = "customer_notifications.template_disabled"
ACTION_CAMPAIGN_CREATED = "customer_notifications.campaign_created"
ACTION_CAMPAIGN_UPDATED = "customer_notifications.campaign_updated"
ACTION_CAMPAIGN_SCHEDULED = "customer_notifications.campaign_scheduled"
ACTION_CAMPAIGN_STARTED = "customer_notifications.campaign_started"
ACTION_CAMPAIGN_PAUSED = "customer_notifications.campaign_paused"
ACTION_CAMPAIGN_CANCELLED = "customer_notifications.campaign_cancelled"
ACTION_CAMPAIGN_IMAGE_ATTACHED = "customer_notifications.campaign_image_attached"
ACTION_CAMPAIGN_IMAGE_REMOVED = "customer_notifications.campaign_image_removed"
ACTION_TEST_MESSAGE_SENT = "customer_notifications.test_message_sent"
ACTION_PROCESS_BATCH_STARTED = "customer_notifications.process_batch_started"
ACTION_PROCESS_BATCH_COMPLETED = "customer_notifications.process_batch_completed"


class CustomerCampaignTelegramSender:
    """Bot 1 sender for customer campaign messages."""

    def __init__(self, telegram_service: TelegramService | None = None) -> None:
        self.telegram_service = telegram_service or TelegramService(
            bot_token=settings.telegram_customer_bot_token,
        )

    async def send_message(
        self,
        *,
        chat_id: int,
        message: str,
        parse_mode: str | None = None,
    ) -> int | None:
        return await self.telegram_service.send_message(
            str(chat_id),
            message,
            parse_mode=parse_mode,
        )

    async def send_photo(
        self,
        *,
        chat_id: int,
        photo: bytes,
        filename: str,
        mime_type: str,
        caption: str,
    ) -> int | None:
        return await self.telegram_service.send_photo_bytes(
            str(chat_id),
            photo,
            filename=filename,
            mime_type=mime_type,
            caption=caption,
        )


@dataclass
class BatchCounts:
    processed: int = 0
    sent: int = 0
    failed: int = 0
    blocked: int = 0
    rate_limited: int = 0
    retried: int = 0
    skipped: int = 0


@dataclass(frozen=True)
class DeliverySkip:
    status: BroadcastDeliveryStatus
    result: str
    error_code: str
    error_message: str


@dataclass(frozen=True)
class CampaignPhoto:
    content: bytes
    filename: str
    mime_type: str


class CustomerNotificationCampaignService:
    """Business logic for Bot 1 templates, campaigns, delivery rows, and reports."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        repository: CustomerNotificationCampaignRepository | None = None,
        sender: CustomerCampaignTelegramSender | None = None,
        audit_service: AuditService | None = None,
        uploads_service: UploadsService | None = None,
        storage: LocalStorageService | None = None,
        now_factory: Any | None = None,
    ) -> None:
        self.session = session
        self.repository = repository or CustomerNotificationCampaignRepository(session)
        self.sender = sender or CustomerCampaignTelegramSender()
        self.audit_service = audit_service or AuditService(session)
        self.uploads_service = uploads_service or UploadsService(session)
        self.storage = storage or self.uploads_service.storage
        self.now_factory = now_factory or (lambda: datetime.now(UTC))

    async def create_template(
        self,
        *,
        actor: User,
        payload: NotificationTemplateCreate,
    ) -> NotificationTemplateRead:
        self._validate_template_payload(
            body_template=payload.body_template,
            allowed_variables=payload.allowed_variables,
            parse_mode=payload.parse_mode,
            channel=payload.channel,
        )
        template = NotificationTemplate(
            key=payload.key,
            name=payload.name,
            category=payload.category,
            channel=payload.channel,
            title=payload.title,
            body_template=payload.body_template,
            parse_mode=self._normalize_parse_mode(payload.parse_mode),
            allowed_variables=payload.allowed_variables,
            is_active=payload.is_active,
            created_by_user_id=actor.id,
            updated_by_user_id=actor.id,
        )
        self.repository.add_template(template)
        await self._flush_if_supported()
        await self._audit(
            actor=actor,
            action=ACTION_TEMPLATE_CREATED,
            entity_type="notification_template",
            entity_id=template.id,
            after_data=self._template_snapshot(template),
        )
        await self._commit("Notification template create failed")
        await self._refresh_if_supported(template)
        return NotificationTemplateRead.model_validate(template)

    async def list_templates(
        self,
        *,
        limit: int,
        offset: int,
        category: NotificationTemplateCategory | None = None,
        active: bool | None = None,
    ) -> NotificationTemplateList:
        items, total = await self.repository.list_templates(
            limit=limit,
            offset=offset,
            category=category,
            active=active,
        )
        return NotificationTemplateList(
            items=[NotificationTemplateRead.model_validate(item) for item in items],
            meta=PageMeta(limit=limit, offset=offset, total=total),
        )

    async def get_template(self, template_id: int) -> NotificationTemplateRead:
        template = await self._get_template_or_404(template_id)
        return NotificationTemplateRead.model_validate(template)

    async def update_template(
        self,
        *,
        template_id: int,
        actor: User,
        payload: NotificationTemplateUpdate,
    ) -> NotificationTemplateRead:
        template = await self._get_template_or_404(template_id)
        before_data = self._template_snapshot(template)

        if "key" in payload.model_fields_set and payload.key is not None:
            template.key = payload.key
        if "name" in payload.model_fields_set and payload.name is not None:
            template.name = payload.name
        if "category" in payload.model_fields_set and payload.category is not None:
            template.category = payload.category
        if "title" in payload.model_fields_set:
            template.title = payload.title
        if "body_template" in payload.model_fields_set and payload.body_template is not None:
            template.body_template = payload.body_template
        if "parse_mode" in payload.model_fields_set:
            template.parse_mode = self._normalize_parse_mode(payload.parse_mode)
        if (
            "allowed_variables" in payload.model_fields_set
            and payload.allowed_variables is not None
        ):
            template.allowed_variables = payload.allowed_variables
        if "is_active" in payload.model_fields_set and payload.is_active is not None:
            template.is_active = payload.is_active
        template.updated_by_user_id = actor.id

        self._validate_template_payload(
            body_template=template.body_template,
            allowed_variables=list(template.allowed_variables),
            parse_mode=template.parse_mode,
            channel=template.channel,
        )
        action = (
            ACTION_TEMPLATE_DISABLED
            if before_data["is_active"] and not template.is_active
            else ACTION_TEMPLATE_UPDATED
        )
        await self._audit(
            actor=actor,
            action=action,
            entity_type="notification_template",
            entity_id=template.id,
            before_data=before_data,
            after_data=self._template_snapshot(template),
        )
        await self._commit("Notification template update failed")
        await self._refresh_if_supported(template)
        return NotificationTemplateRead.model_validate(template)

    async def disable_template(
        self,
        *,
        template_id: int,
        actor: User,
    ) -> NotificationTemplateRead:
        template = await self._get_template_or_404(template_id)
        before_data = self._template_snapshot(template)
        template.is_active = False
        template.updated_by_user_id = actor.id
        await self._audit(
            actor=actor,
            action=ACTION_TEMPLATE_DISABLED,
            entity_type="notification_template",
            entity_id=template.id,
            before_data=before_data,
            after_data=self._template_snapshot(template),
        )
        await self._commit("Notification template disable failed")
        await self._refresh_if_supported(template)
        return NotificationTemplateRead.model_validate(template)

    async def create_campaign(
        self,
        *,
        actor: User,
        payload: BroadcastCampaignCreate,
    ) -> BroadcastCampaignRead:
        audience_filter = self._parse_audience_filter(payload.audience_filter)
        message_body, parse_mode, template = await self._campaign_message_from_payload(
            template_id=payload.template_id,
            campaign_type=payload.type,
            message_body=payload.message_body,
            parse_mode=payload.parse_mode,
            template_variables=payload.template_variables,
        )
        campaign = BroadcastCampaign(
            template_id=template.id if template is not None else None,
            name=payload.name,
            type=payload.type,
            status=BroadcastCampaignStatus.DRAFT,
            audience_filter=audience_filter.model_dump(exclude_none=True),
            recipient_count_estimate=0,
            recipient_count_final=None,
            message_title=payload.message_title or (template.title if template else None),
            message_body=message_body,
            parse_mode=parse_mode,
            scheduled_at=payload.scheduled_at,
            created_by_user_id=actor.id,
        )
        self.repository.add_campaign(campaign)
        await self._flush_if_supported()
        await self._audit(
            actor=actor,
            action=ACTION_CAMPAIGN_CREATED,
            entity_type="broadcast_campaign",
            entity_id=campaign.id,
            after_data=self._campaign_snapshot(campaign),
            metadata={
                "message_length": len(campaign.message_body),
                "campaign_type": campaign.type.value,
            },
        )
        await self._commit("Broadcast campaign create failed")
        await self._refresh_if_supported(campaign)
        return BroadcastCampaignRead.model_validate(campaign)

    async def list_campaigns(
        self,
        *,
        limit: int,
        offset: int,
        campaign_type: BroadcastCampaignType | None = None,
        status_filter: BroadcastCampaignStatus | None = None,
    ) -> BroadcastCampaignList:
        items, total = await self.repository.list_campaigns(
            limit=limit,
            offset=offset,
            campaign_type=campaign_type,
            status=status_filter,
        )
        return BroadcastCampaignList(
            items=[BroadcastCampaignRead.model_validate(item) for item in items],
            meta=PageMeta(limit=limit, offset=offset, total=total),
        )

    async def get_campaign_detail(self, campaign_id: int) -> BroadcastCampaignDetail:
        campaign = await self._get_campaign_or_404(campaign_id)
        return BroadcastCampaignDetail(
            campaign=BroadcastCampaignRead.model_validate(campaign),
            delivery_summary=await self.get_delivery_summary(campaign_id),
        )

    async def update_campaign(
        self,
        *,
        campaign_id: int,
        actor: User,
        payload: BroadcastCampaignUpdate,
    ) -> BroadcastCampaignRead:
        campaign = await self._get_campaign_or_404(campaign_id)
        self._require_status(
            campaign,
            {BroadcastCampaignStatus.DRAFT},
            "Only draft campaigns can be edited",
        )
        before_data = self._campaign_snapshot(campaign)

        next_type = payload.type or campaign.type
        if "template_id" in payload.model_fields_set:
            campaign.template_id = payload.template_id
        if "name" in payload.model_fields_set and payload.name is not None:
            campaign.name = payload.name
        if "type" in payload.model_fields_set and payload.type is not None:
            campaign.type = payload.type
        if "audience_filter" in payload.model_fields_set and payload.audience_filter is not None:
            audience_filter = self._parse_audience_filter(payload.audience_filter)
            campaign.audience_filter = audience_filter.model_dump(exclude_none=True)
        if "message_title" in payload.model_fields_set:
            campaign.message_title = payload.message_title
        if "scheduled_at" in payload.model_fields_set:
            campaign.scheduled_at = payload.scheduled_at

        if self._message_needs_render(payload):
            message_body, parse_mode, template = await self._campaign_message_from_payload(
                template_id=campaign.template_id,
                campaign_type=next_type,
                message_body=payload.message_body,
                parse_mode=payload.parse_mode,
                template_variables=payload.template_variables or {},
            )
            campaign.message_body = message_body
            campaign.parse_mode = parse_mode
            if template is not None and not campaign.message_title:
                campaign.message_title = template.title
        elif "parse_mode" in payload.model_fields_set:
            campaign.parse_mode = self._normalize_parse_mode(payload.parse_mode)

        self._validate_campaign_message(
            campaign.message_body,
            campaign.parse_mode,
            has_image=campaign.image_path is not None,
        )
        campaign.recipient_count_estimate = 0
        campaign.recipient_count_final = None
        await self._audit(
            actor=actor,
            action=ACTION_CAMPAIGN_UPDATED,
            entity_type="broadcast_campaign",
            entity_id=campaign.id,
            before_data=before_data,
            after_data=self._campaign_snapshot(campaign),
            metadata={
                "message_length": len(campaign.message_body),
                "campaign_type": campaign.type.value,
            },
        )
        await self._commit("Broadcast campaign update failed")
        await self._refresh_if_supported(campaign)
        return BroadcastCampaignRead.model_validate(campaign)

    async def attach_campaign_image(
        self,
        *,
        campaign_id: int,
        actor: User,
        file: UploadFile,
    ) -> BroadcastCampaignRead:
        campaign = await self.repository.get_campaign_by_id_for_update(campaign_id)
        if campaign is None:
            raise AppError("Broadcast campaign not found", status.HTTP_404_NOT_FOUND)
        self._require_status(
            campaign,
            {BroadcastCampaignStatus.DRAFT, BroadcastCampaignStatus.PAUSED},
            "Only draft or paused campaigns can change images",
        )

        upload = await self.uploads_service.validate_and_read_image(file)
        self._validate_campaign_message(
            campaign.message_body,
            campaign.parse_mode,
            has_image=True,
        )
        previous_path = campaign.image_path
        before_data = self._campaign_snapshot(campaign)
        new_path = self.storage.save_bytes(
            upload.content,
            folder=CAMPAIGN_IMAGE_UPLOAD_FOLDER,
            suffix=upload.extension,
        )
        campaign.image_path = new_path
        campaign.image_original_filename = upload.original_filename
        campaign.image_mime_type = upload.mime_type
        campaign.image_size_bytes = upload.size_bytes

        try:
            await self._audit(
                actor=actor,
                action=ACTION_CAMPAIGN_IMAGE_ATTACHED,
                entity_type="broadcast_campaign",
                entity_id=campaign.id,
                before_data=before_data,
                after_data=self._campaign_snapshot(campaign),
                metadata={
                    "campaign_type": campaign.type.value,
                    "image_size_bytes": upload.size_bytes,
                    "replaced": previous_path is not None,
                },
            )
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            self._delete_upload_safely(new_path, stage="campaign_image_db_integrity")
            raise AppError(
                "Broadcast campaign image attach failed",
                status.HTTP_409_CONFLICT,
            ) from exc
        except Exception:
            await self.session.rollback()
            self._delete_upload_safely(new_path, stage="campaign_image_db_failure")
            raise

        if previous_path and previous_path != new_path:
            self._delete_upload_safely(previous_path, stage="campaign_image_replace")
        await self._refresh_if_supported(campaign)
        return BroadcastCampaignRead.model_validate(campaign)

    async def remove_campaign_image(
        self,
        *,
        campaign_id: int,
        actor: User,
    ) -> BroadcastCampaignRead:
        campaign = await self.repository.get_campaign_by_id_for_update(campaign_id)
        if campaign is None:
            raise AppError("Broadcast campaign not found", status.HTTP_404_NOT_FOUND)
        self._require_status(
            campaign,
            {BroadcastCampaignStatus.DRAFT, BroadcastCampaignStatus.PAUSED},
            "Only draft or paused campaigns can change images",
        )
        previous_path = campaign.image_path
        if previous_path is None:
            return BroadcastCampaignRead.model_validate(campaign)

        before_data = self._campaign_snapshot(campaign)
        self._clear_campaign_image_fields(campaign)
        await self._audit(
            actor=actor,
            action=ACTION_CAMPAIGN_IMAGE_REMOVED,
            entity_type="broadcast_campaign",
            entity_id=campaign.id,
            before_data=before_data,
            after_data=self._campaign_snapshot(campaign),
            metadata={"campaign_type": campaign.type.value},
        )
        await self._commit("Broadcast campaign image remove failed")
        self._delete_upload_safely(previous_path, stage="campaign_image_remove")
        await self._refresh_if_supported(campaign)
        return BroadcastCampaignRead.model_validate(campaign)

    async def preview_campaign(self, campaign_id: int) -> BroadcastCampaignPreview:
        campaign = await self._get_campaign_or_404(campaign_id)
        audience_filter = self._parse_audience_filter(campaign.audience_filter)
        self._validate_campaign_message(
            campaign.message_body,
            campaign.parse_mode,
            has_image=campaign.image_path is not None,
        )
        recipient_count = await self.repository.count_eligible_recipients(
            campaign_type=campaign.type,
            audience_filter=audience_filter,
        )
        campaign.recipient_count_estimate = recipient_count
        await self._commit("Broadcast campaign preview failed")
        return BroadcastCampaignPreview(
            campaign_id=campaign.id,
            recipient_count_estimate=recipient_count,
            rendered_sample=campaign.message_body,
            eligibility_warnings=self._eligibility_warnings(campaign, recipient_count),
        )

    async def send_test_message(
        self,
        *,
        campaign_id: int,
        actor: User,
        payload: BroadcastCampaignTestRequest,
    ) -> BroadcastCampaignTestResponse:
        campaign = await self._get_campaign_or_404(campaign_id)
        has_image = campaign.image_path is not None
        self._validate_campaign_message(
            campaign.message_body,
            campaign.parse_mode,
            has_image=has_image,
        )
        subscription = await self.repository.get_test_subscription_for_user(
            user_id=actor.id,
            telegram_user_id=actor.telegram_id,
        )
        if not self._has_active_private_chat(subscription):
            raise AppError(
                "Current seller/admin must open Bot 1 with /start before test send",
                status.HTTP_400_BAD_REQUEST,
            )

        message = campaign.message_body
        if payload.message_suffix:
            message = f"{message}\n\n{payload.message_suffix}"
            self._validate_campaign_message(
                message,
                campaign.parse_mode,
                has_image=has_image,
            )

        assert subscription is not None
        assert subscription.telegram_chat_id is not None
        try:
            photo = self._read_campaign_photo(campaign)
            if photo is not None:
                telegram_message_id = await self.sender.send_photo(
                    chat_id=subscription.telegram_chat_id,
                    photo=photo.content,
                    filename=photo.filename,
                    mime_type=photo.mime_type,
                    caption=message,
                )
            else:
                telegram_message_id = await self.sender.send_message(
                    chat_id=subscription.telegram_chat_id,
                    message=message,
                    parse_mode=campaign.parse_mode,
                )
        except OSError as exc:
            raise AppError(
                "Campaign image file is unavailable",
                status.HTTP_422_UNPROCESSABLE_CONTENT,
            ) from exc
        except TelegramDeliveryError as exc:
            raise AppError(
                self._sanitize_error_message(exc),
                status.HTTP_502_BAD_GATEWAY,
            ) from exc
        await self._audit(
            actor=actor,
            action=ACTION_TEST_MESSAGE_SENT,
            entity_type="broadcast_campaign",
            entity_id=campaign.id,
            metadata={
                "message_length": len(message),
                "campaign_type": campaign.type.value,
                "recipient_user_id": subscription.user_id,
            },
        )
        await self._commit("Broadcast campaign test-send audit failed")
        return BroadcastCampaignTestResponse(
            campaign_id=campaign.id,
            telegram_message_id=telegram_message_id,
            recipient_user_id=subscription.user_id,
            recipient_username=subscription.telegram_username,
        )

    async def schedule_campaign(
        self,
        *,
        campaign_id: int,
        actor: User,
        payload: BroadcastCampaignScheduleRequest,
        start_now: bool = False,
    ) -> BroadcastCampaignRead:
        campaign = await self.repository.get_campaign_by_id_for_update(campaign_id)
        if campaign is None:
            raise AppError("Broadcast campaign not found", status.HTTP_404_NOT_FOUND)
        if campaign.status in {
            BroadcastCampaignStatus.SCHEDULED,
            BroadcastCampaignStatus.SENDING,
        }:
            return BroadcastCampaignRead.model_validate(campaign)
        self._require_status(
            campaign,
            {BroadcastCampaignStatus.DRAFT, BroadcastCampaignStatus.PAUSED},
            "Only draft or paused campaigns can be scheduled",
        )
        await self._validate_campaign_for_activation(campaign)
        before_data = self._campaign_snapshot(campaign)
        now = self._now()
        scheduled_at = now if start_now else payload.scheduled_at or campaign.scheduled_at or now
        final_count = await self._materialize_deliveries(campaign)
        if final_count <= 0:
            raise AppError(
                "Campaign cannot be enabled: no eligible Bot 1 recipients match the audience",
                status.HTTP_422_UNPROCESSABLE_CONTENT,
            )

        campaign.recipient_count_estimate = final_count
        campaign.recipient_count_final = final_count
        campaign.scheduled_at = scheduled_at
        if scheduled_at <= now:
            campaign.status = BroadcastCampaignStatus.SENDING
            campaign.started_at = now
            action = ACTION_CAMPAIGN_STARTED
        else:
            campaign.status = BroadcastCampaignStatus.SCHEDULED
            action = ACTION_CAMPAIGN_SCHEDULED

        await self._audit(
            actor=actor,
            action=action,
            entity_type="broadcast_campaign",
            entity_id=campaign.id,
            before_data=before_data,
            after_data=self._campaign_snapshot(campaign),
            metadata={
                "recipient_count": final_count,
                "campaign_type": campaign.type.value,
                "source": "manual_api",
            },
        )
        await self._commit("Broadcast campaign schedule failed")
        await self._refresh_if_supported(campaign)
        return BroadcastCampaignRead.model_validate(campaign)

    async def pause_campaign(self, *, campaign_id: int, actor: User) -> BroadcastCampaignRead:
        campaign = await self._get_campaign_or_404(campaign_id)
        self._require_status(
            campaign,
            {BroadcastCampaignStatus.SCHEDULED, BroadcastCampaignStatus.SENDING},
            "Only scheduled or sending campaigns can be paused",
        )
        before_data = self._campaign_snapshot(campaign)
        campaign.status = BroadcastCampaignStatus.PAUSED
        await self._audit(
            actor=actor,
            action=ACTION_CAMPAIGN_PAUSED,
            entity_type="broadcast_campaign",
            entity_id=campaign.id,
            before_data=before_data,
            after_data=self._campaign_snapshot(campaign),
            metadata={"campaign_type": campaign.type.value},
        )
        await self._commit("Broadcast campaign pause failed")
        await self._refresh_if_supported(campaign)
        return BroadcastCampaignRead.model_validate(campaign)

    async def cancel_campaign(self, *, campaign_id: int, actor: User) -> BroadcastCampaignRead:
        campaign = await self._get_campaign_or_404(campaign_id)
        if campaign.status in {
            BroadcastCampaignStatus.COMPLETED,
            BroadcastCampaignStatus.CANCELLED,
        }:
            raise AppError("Campaign is already closed", status.HTTP_400_BAD_REQUEST)

        before_data = self._campaign_snapshot(campaign)
        now = self._now()
        skipped = await self.repository.skip_remaining_deliveries(
            campaign_id=campaign.id,
            now=now,
            error_code="campaign_cancelled",
            error_message="Campaign was cancelled before delivery",
        )
        campaign.status = BroadcastCampaignStatus.CANCELLED
        campaign.cancelled_by_user_id = actor.id
        campaign.completed_at = now
        await self._audit(
            actor=actor,
            action=ACTION_CAMPAIGN_CANCELLED,
            entity_type="broadcast_campaign",
            entity_id=campaign.id,
            before_data=before_data,
            after_data=self._campaign_snapshot(campaign),
            metadata={"skipped": skipped, "campaign_type": campaign.type.value},
        )
        await self._commit("Broadcast campaign cancel failed")
        await self._refresh_if_supported(campaign)
        return BroadcastCampaignRead.model_validate(campaign)

    async def process_batch(
        self,
        *,
        campaign_id: int,
        actor: User | None,
        payload: BroadcastCampaignProcessBatchRequest,
    ) -> BroadcastCampaignProcessBatchResponse:
        campaign = await self._get_campaign_or_404(campaign_id)
        if campaign.status == BroadcastCampaignStatus.COMPLETED:
            return BroadcastCampaignProcessBatchResponse(
                campaign_id=campaign.id,
                processed=0,
                sent=0,
                failed=0,
                blocked=0,
                rate_limited=0,
                retried=0,
                skipped=0,
                remaining=0,
                campaign_status=campaign.status,
            )
        self._require_status(
            campaign,
            {BroadcastCampaignStatus.SCHEDULED, BroadcastCampaignStatus.SENDING},
            "Only scheduled or sending campaigns can process batches",
        )
        limit = self._batch_limit(payload.limit)
        now = self._now()
        await self.repository.recover_stale_sending_deliveries(
            campaign_id=campaign.id,
            stale_before=now
            - timedelta(seconds=max(1, settings.customer_campaign_sending_timeout_seconds)),
            now=now,
        )
        await self._audit(
            actor=actor,
            action=ACTION_PROCESS_BATCH_STARTED,
            entity_type="broadcast_campaign",
            entity_id=campaign.id,
            metadata={"limit": limit, "campaign_type": campaign.type.value},
        )

        if campaign.status == BroadcastCampaignStatus.SCHEDULED:
            if campaign.scheduled_at is not None and campaign.scheduled_at > now:
                remaining = await self.repository.count_unfinished_deliveries(
                    campaign_id=campaign.id
                )
                await self._audit(
                    actor=actor,
                    action=ACTION_PROCESS_BATCH_COMPLETED,
                    entity_type="broadcast_campaign",
                    entity_id=campaign.id,
                    metadata={
                        "processed": 0,
                        "remaining": remaining,
                        "campaign_type": campaign.type.value,
                        "source": "scheduled_not_due",
                    },
                )
                await self._commit("Broadcast campaign process-batch audit failed")
                return BroadcastCampaignProcessBatchResponse(
                    campaign_id=campaign.id,
                    processed=0,
                    sent=0,
                    failed=0,
                    blocked=0,
                    rate_limited=0,
                    retried=0,
                    skipped=0,
                    remaining=remaining,
                    campaign_status=campaign.status,
                )
            campaign.status = BroadcastCampaignStatus.SENDING
            campaign.started_at = campaign.started_at or now

        try:
            campaign_photo = self._read_campaign_photo(campaign)
        except OSError:
            counts = BatchCounts()
            counts.skipped += await self.repository.skip_remaining_deliveries(
                campaign_id=campaign.id,
                now=now,
                error_code="campaign_image_missing",
                error_message="Campaign image file is unavailable",
            )
            campaign.status = BroadcastCampaignStatus.FAILED
            campaign.completed_at = now
            remaining = await self.repository.count_unfinished_deliveries(
                campaign_id=campaign.id
            )
            await self._audit(
                actor=actor,
                action=ACTION_PROCESS_BATCH_COMPLETED,
                entity_type="broadcast_campaign",
                entity_id=campaign.id,
                metadata={
                    "processed": 0,
                    "skipped": counts.skipped,
                    "remaining": remaining,
                    "campaign_type": campaign.type.value,
                    "error_code": "campaign_image_missing",
                },
            )
            await self._commit("Broadcast campaign process-batch failed")
            return BroadcastCampaignProcessBatchResponse(
                campaign_id=campaign.id,
                processed=0,
                sent=0,
                failed=0,
                blocked=0,
                rate_limited=0,
                retried=0,
                skipped=counts.skipped,
                remaining=remaining,
                campaign_status=campaign.status,
            )

        deliveries = await self.repository.deliveries_for_processing(
            campaign_id=campaign.id,
            now=now,
            limit=limit,
        )
        counts = BatchCounts()
        campaign_failed = False
        for delivery in deliveries:
            counts.processed += 1
            result = await self._process_delivery(
                campaign=campaign,
                delivery=delivery,
                campaign_photo=campaign_photo,
            )
            setattr(counts, result, getattr(counts, result) + 1)
            if delivery.error_code == "bad_request":
                campaign_failed = True
                break

        now = self._now()
        if campaign_failed:
            counts.skipped += await self.repository.skip_remaining_deliveries(
                campaign_id=campaign.id,
                now=now,
                error_code="campaign_failed",
                error_message="Campaign failed due to Telegram message formatting",
            )
            campaign.status = BroadcastCampaignStatus.FAILED
            campaign.completed_at = now
        else:
            remaining = await self.repository.count_unfinished_deliveries(campaign_id=campaign.id)
            if remaining == 0:
                campaign.status = BroadcastCampaignStatus.COMPLETED
                campaign.completed_at = now

        remaining = await self.repository.count_unfinished_deliveries(campaign_id=campaign.id)
        await self._audit(
            actor=actor,
            action=ACTION_PROCESS_BATCH_COMPLETED,
            entity_type="broadcast_campaign",
            entity_id=campaign.id,
            metadata={
                "processed": counts.processed,
                "sent": counts.sent,
                "failed": counts.failed,
                "blocked": counts.blocked,
                "rate_limited": counts.rate_limited,
                "retried": counts.retried,
                "skipped": counts.skipped,
                "remaining": remaining,
                "campaign_type": campaign.type.value,
            },
        )
        await self._commit("Broadcast campaign process-batch failed")
        return BroadcastCampaignProcessBatchResponse(
            campaign_id=campaign.id,
            processed=counts.processed,
            sent=counts.sent,
            failed=counts.failed,
            blocked=counts.blocked,
            rate_limited=counts.rate_limited,
            retried=counts.retried,
            skipped=counts.skipped,
            remaining=remaining,
            campaign_status=campaign.status,
        )

    async def list_deliveries(
        self,
        *,
        campaign_id: int,
        limit: int,
        offset: int,
        status_filter: BroadcastDeliveryStatus | None = None,
    ) -> BroadcastDeliveryList:
        await self._get_campaign_or_404(campaign_id)
        items, total = await self.repository.list_deliveries(
            campaign_id=campaign_id,
            limit=limit,
            offset=offset,
            status=status_filter,
        )
        return BroadcastDeliveryList(
            items=[self._delivery_read(item) for item in items],
            meta=PageMeta(limit=limit, offset=offset, total=total),
        )

    async def get_delivery_summary(self, campaign_id: int) -> BroadcastDeliverySummary:
        summary = await self.repository.delivery_summary(campaign_id)
        values = {
            BroadcastDeliveryStatus.PENDING: summary.get(BroadcastDeliveryStatus.PENDING, 0),
            BroadcastDeliveryStatus.SENDING: summary.get(BroadcastDeliveryStatus.SENDING, 0),
            BroadcastDeliveryStatus.SENT: summary.get(BroadcastDeliveryStatus.SENT, 0),
            BroadcastDeliveryStatus.FAILED: summary.get(BroadcastDeliveryStatus.FAILED, 0),
            BroadcastDeliveryStatus.SKIPPED: summary.get(BroadcastDeliveryStatus.SKIPPED, 0),
            BroadcastDeliveryStatus.BLOCKED: summary.get(BroadcastDeliveryStatus.BLOCKED, 0),
            BroadcastDeliveryStatus.RATE_LIMITED: summary.get(
                BroadcastDeliveryStatus.RATE_LIMITED,
                0,
            ),
        }
        total = sum(values.values())
        return BroadcastDeliverySummary(
            pending=values[BroadcastDeliveryStatus.PENDING],
            sending=values[BroadcastDeliveryStatus.SENDING],
            sent=values[BroadcastDeliveryStatus.SENT],
            failed=values[BroadcastDeliveryStatus.FAILED],
            skipped=values[BroadcastDeliveryStatus.SKIPPED],
            blocked=values[BroadcastDeliveryStatus.BLOCKED],
            rate_limited=values[BroadcastDeliveryStatus.RATE_LIMITED],
            total=total,
        )

    async def _materialize_deliveries(self, campaign: BroadcastCampaign) -> int:
        existing = await self.repository.count_campaign_deliveries(campaign.id)
        if existing:
            return existing
        audience_filter = self._parse_audience_filter(campaign.audience_filter)
        subscriptions = await self.repository.list_eligible_recipients(
            campaign_type=campaign.type,
            audience_filter=audience_filter,
        )
        deliveries = [
            BroadcastDelivery(
                campaign_id=campaign.id,
                user_id=subscription.user_id,
                subscription_id=subscription.id,
                telegram_chat_id=subscription.telegram_chat_id,
                status=BroadcastDeliveryStatus.PENDING,
            )
            for subscription in subscriptions
            if subscription.telegram_chat_id is not None
        ]
        self.repository.add_deliveries(deliveries)
        return len(deliveries)

    async def _process_delivery(
        self,
        *,
        campaign: BroadcastCampaign,
        delivery: BroadcastDelivery,
        campaign_photo: CampaignPhoto | None,
    ) -> str:
        now = self._now()
        skip = self._delivery_skip(campaign=campaign, delivery=delivery)
        if skip is not None:
            delivery.status = skip.status
            delivery.next_attempt_at = None
            delivery.error_code = skip.error_code
            delivery.error_message = skip.error_message
            delivery.retry_after_seconds = None
            delivery.telegram_message_id = None
            delivery.sent_at = None
            return skip.result

        delivery.status = BroadcastDeliveryStatus.SENDING
        delivery.attempt_count += 1
        delivery.last_attempt_at = now
        try:
            if campaign_photo is not None:
                telegram_message_id = await self.sender.send_photo(
                    chat_id=delivery.telegram_chat_id,
                    photo=campaign_photo.content,
                    filename=campaign_photo.filename,
                    mime_type=campaign_photo.mime_type,
                    caption=campaign.message_body,
                )
            else:
                telegram_message_id = await self.sender.send_message(
                    chat_id=delivery.telegram_chat_id,
                    message=campaign.message_body,
                    parse_mode=campaign.parse_mode,
                )
        except TelegramDeliveryError as exc:
            return self._mark_delivery_error(delivery=delivery, error=exc, now=now)

        delivery.status = BroadcastDeliveryStatus.SENT
        delivery.telegram_message_id = telegram_message_id
        delivery.sent_at = now
        delivery.next_attempt_at = None
        delivery.error_code = None
        delivery.error_message = None
        delivery.retry_after_seconds = None
        return "sent"

    def _delivery_skip(
        self,
        *,
        campaign: BroadcastCampaign,
        delivery: BroadcastDelivery,
    ) -> DeliverySkip | None:
        subscription = delivery.subscription
        if subscription is None:
            return DeliverySkip(
                status=BroadcastDeliveryStatus.SKIPPED,
                result="skipped",
                error_code="subscription_missing",
                error_message="Bot 1 subscription no longer exists",
            )
        if subscription.blocked_at is not None:
            return DeliverySkip(
                status=BroadcastDeliveryStatus.BLOCKED,
                result="blocked",
                error_code="blocked",
                error_message="Customer blocked Bot 1",
            )
        if (
            not subscription.has_chat
            or subscription.telegram_chat_id is None
            or subscription.chat_type != PRIVATE_CHAT_TYPE
        ):
            return DeliverySkip(
                status=BroadcastDeliveryStatus.SKIPPED,
                result="skipped",
                error_code="bot1_chat_unavailable",
                error_message="Customer has no active private chat with Bot 1",
            )
        opted_in = (
            subscription.marketing_opt_in
            if campaign.type == BroadcastCampaignType.MARKETING
            else subscription.service_opt_in
        )
        if not opted_in:
            return DeliverySkip(
                status=BroadcastDeliveryStatus.SKIPPED,
                result="skipped",
                error_code="consent_revoked",
                error_message="Customer consent no longer permits this campaign",
            )
        return None

    def _mark_delivery_error(
        self,
        *,
        delivery: BroadcastDelivery,
        error: TelegramDeliveryError,
        now: datetime,
    ) -> str:
        error_code = self._delivery_error_code(error)
        error_message = self._sanitize_error_message(error)
        delivery.error_code = error_code
        delivery.error_message = error_message
        delivery.retry_after_seconds = error.retry_after_seconds
        delivery.telegram_message_id = None
        delivery.sent_at = None

        if error_code == "blocked":
            delivery.status = BroadcastDeliveryStatus.BLOCKED
            self._mark_subscription_blocked(delivery.subscription, now, error_message)
            return "blocked"
        if error_code == "rate_limited":
            retry_after = error.retry_after_seconds or settings.customer_campaign_retry_base_seconds
            delivery.status = BroadcastDeliveryStatus.RATE_LIMITED
            delivery.retry_after_seconds = retry_after
            delivery.next_attempt_at = now + timedelta(seconds=retry_after)
            return "rate_limited"
        if error_code == "bad_request":
            delivery.status = BroadcastDeliveryStatus.FAILED
            delivery.next_attempt_at = None
            return "failed"
        if delivery.attempt_count < settings.customer_campaign_max_attempts:
            delivery.status = BroadcastDeliveryStatus.PENDING
            delivery.next_attempt_at = now + timedelta(
                seconds=self._retry_delay_seconds(delivery.attempt_count)
            )
            return "retried"

        delivery.status = BroadcastDeliveryStatus.FAILED
        delivery.next_attempt_at = None
        return "failed"

    def _mark_subscription_blocked(
        self,
        subscription: CustomerTelegramSubscription | None,
        now: datetime,
        error_message: str,
    ) -> None:
        if subscription is None:
            return
        subscription.blocked_at = now
        subscription.has_chat = False
        subscription.last_delivery_error = error_message

    async def _campaign_message_from_payload(
        self,
        *,
        template_id: int | None,
        campaign_type: BroadcastCampaignType,
        message_body: str | None,
        parse_mode: str | None,
        template_variables: dict[str, Any],
    ) -> tuple[str, str | None, NotificationTemplate | None]:
        normalized_parse_mode = self._normalize_parse_mode(parse_mode)
        template = None
        if template_id is not None:
            template = await self._get_template_or_404(template_id)
            if not template.is_active:
                raise AppError("Template is disabled", status.HTTP_400_BAD_REQUEST)
            if template.channel != NotificationChannel.TELEGRAM:
                raise AppError("Only Telegram templates are supported", status.HTTP_400_BAD_REQUEST)
            if template.category.value != campaign_type.value:
                raise AppError(
                    "Template category does not match campaign type",
                    status.HTTP_400_BAD_REQUEST,
                )
            normalized_parse_mode = self._normalize_parse_mode(parse_mode or template.parse_mode)
            if message_body is None:
                message_body = self._render_template(template, template_variables)

        if message_body is None:
            raise AppError("Campaign message body is required", status.HTTP_400_BAD_REQUEST)

        self._validate_campaign_message(message_body, normalized_parse_mode)
        return message_body, normalized_parse_mode, template

    def _render_template(
        self,
        template: NotificationTemplate,
        variables: dict[str, Any],
    ) -> str:
        allowed_variables = set(template.allowed_variables)
        provided_variables = set(variables)
        unsupported = sorted(provided_variables - allowed_variables)
        if unsupported:
            raise AppError(
                f"Unsupported template variables: {', '.join(unsupported)}",
                status.HTTP_400_BAD_REQUEST,
            )
        placeholders = set(TEMPLATE_PLACEHOLDER_RE.findall(template.body_template))
        missing = sorted(placeholders - provided_variables)
        if missing:
            raise AppError(
                f"Missing template variables: {', '.join(missing)}",
                status.HTTP_400_BAD_REQUEST,
            )
        return TEMPLATE_PLACEHOLDER_RE.sub(
            lambda match: str(variables.get(match.group("name"), "")),
            template.body_template,
        )

    def _validate_template_payload(
        self,
        *,
        body_template: str,
        allowed_variables: list[str],
        parse_mode: str | None,
        channel: NotificationChannel,
    ) -> None:
        if channel != NotificationChannel.TELEGRAM:
            raise AppError("Only Telegram templates are supported", status.HTTP_400_BAD_REQUEST)
        self._normalize_parse_mode(parse_mode)
        placeholders = set(TEMPLATE_PLACEHOLDER_RE.findall(body_template))
        allowed = set(allowed_variables)
        unknown = sorted(placeholders - allowed)
        if unknown:
            raise AppError(
                f"Template uses variables not present in allowed_variables: {', '.join(unknown)}",
                status.HTTP_400_BAD_REQUEST,
            )
        if len(body_template) > TELEGRAM_MESSAGE_MAX_LENGTH:
            raise AppError(
                "Template body exceeds Telegram message length",
                status.HTTP_400_BAD_REQUEST,
            )

    def _validate_campaign_message(
        self,
        message_body: str,
        parse_mode: str | None,
        *,
        has_image: bool = False,
    ) -> None:
        self._normalize_parse_mode(parse_mode)
        max_length = TELEGRAM_PHOTO_CAPTION_MAX_LENGTH if has_image else TELEGRAM_MESSAGE_MAX_LENGTH
        if len(message_body) > max_length:
            message = (
                "Campaign image caption exceeds Telegram photo caption length"
                if has_image
                else "Campaign message exceeds Telegram message length"
            )
            raise AppError(
                message,
                status.HTTP_400_BAD_REQUEST,
            )

    async def _validate_campaign_for_activation(self, campaign: BroadcastCampaign) -> None:
        issues: list[str] = []
        if not campaign.name.strip():
            issues.append("name is required")
        if not campaign.message_body.strip():
            issues.append("message_body is required")
        else:
            try:
                self._validate_campaign_message(
                    campaign.message_body,
                    campaign.parse_mode,
                    has_image=campaign.image_path is not None,
                )
            except AppError as exc:
                issues.append(exc.message)
        if campaign.image_path is not None and not self.storage.exists(campaign.image_path):
            issues.append("campaign image file is unavailable")
        try:
            self._parse_audience_filter(campaign.audience_filter)
        except AppError as exc:
            issues.append(exc.message)

        if campaign.template_id is not None:
            template = await self.repository.get_template_by_id(campaign.template_id)
            if template is None:
                issues.append("template does not exist")
            elif not template.is_active:
                issues.append("template is disabled")
            elif template.category.value != campaign.type.value:
                issues.append("template category does not match campaign type")

        if issues:
            raise AppError(
                f"Campaign cannot be enabled: {'; '.join(issues)}",
                status.HTTP_422_UNPROCESSABLE_CONTENT,
            )

    def _normalize_parse_mode(self, parse_mode: str | None) -> str | None:
        if parse_mode is None or parse_mode == "":
            return None
        if parse_mode not in SUPPORTED_PARSE_MODES:
            raise AppError(
                "Telegram parse_mode is not supported for campaign MVP",
                status.HTTP_400_BAD_REQUEST,
            )
        return parse_mode

    def _parse_audience_filter(self, value: dict[str, Any]) -> BroadcastAudienceFilter:
        try:
            audience_filter = BroadcastAudienceFilter.model_validate(value or {"scope": "all"})
        except ValueError as exc:
            raise AppError("Unsupported audience filter", status.HTTP_400_BAD_REQUEST) from exc
        if audience_filter.scope == "product" and audience_filter.product_id is None:
            raise AppError(
                "product_id is required for product audience",
                status.HTTP_400_BAD_REQUEST,
            )
        if audience_filter.scope == "category" and audience_filter.category_id is None:
            raise AppError(
                "category_id is required for category audience",
                status.HTTP_400_BAD_REQUEST,
            )
        if audience_filter.scope == "promo_code" and audience_filter.promo_code_id is None:
            raise AppError(
                "promo_code_id is required for promo audience",
                status.HTTP_400_BAD_REQUEST,
            )
        return audience_filter

    def _eligibility_warnings(
        self,
        campaign: BroadcastCampaign,
        recipient_count: int,
    ) -> list[str]:
        warnings: list[str] = [
            "Recipients require Bot 1 private chat, matching opt-in, and no blocked_at flag.",
        ]
        if campaign.type == BroadcastCampaignType.MARKETING:
            warnings.append("Marketing estimate excludes customers without marketing opt-in.")
        else:
            warnings.append("Service estimate excludes customers without service opt-in.")
        audience_filter = self._parse_audience_filter(campaign.audience_filter)
        if audience_filter.scope == "connected":
            warnings.append(
                "Connected audience can include Bot 1 recipients not linked to Mini App users."
            )
        if campaign.image_path is not None:
            warnings.append("Campaign image uses Telegram photo caption limit: 1024 characters.")
        if recipient_count == 0:
            warnings.append("No eligible recipients match this campaign audience.")
        return warnings

    def _message_needs_render(self, payload: BroadcastCampaignUpdate) -> bool:
        return any(
            field in payload.model_fields_set
            for field in ("template_id", "message_body", "template_variables", "type")
        )

    async def _get_template_or_404(self, template_id: int) -> NotificationTemplate:
        template = await self.repository.get_template_by_id(template_id)
        if template is None:
            raise AppError("Notification template not found", status.HTTP_404_NOT_FOUND)
        return template

    async def _get_campaign_or_404(self, campaign_id: int) -> BroadcastCampaign:
        campaign = await self.repository.get_campaign_by_id(campaign_id)
        if campaign is None:
            raise AppError("Broadcast campaign not found", status.HTTP_404_NOT_FOUND)
        return campaign

    def _require_status(
        self,
        campaign: BroadcastCampaign,
        allowed: set[BroadcastCampaignStatus],
        message: str,
    ) -> None:
        if campaign.status not in allowed:
            raise AppError(message, status.HTTP_400_BAD_REQUEST)

    def _has_active_private_chat(self, subscription: CustomerTelegramSubscription | None) -> bool:
        return (
            subscription is not None
            and subscription.has_chat
            and subscription.telegram_chat_id is not None
            and subscription.chat_type == PRIVATE_CHAT_TYPE
            and subscription.blocked_at is None
        )

    def _read_campaign_photo(self, campaign: BroadcastCampaign) -> CampaignPhoto | None:
        if campaign.image_path is None:
            return None
        return CampaignPhoto(
            content=self.storage.read_bytes(campaign.image_path),
            filename=campaign.image_original_filename or "campaign-image",
            mime_type=campaign.image_mime_type or "image/jpeg",
        )

    def _clear_campaign_image_fields(self, campaign: BroadcastCampaign) -> None:
        campaign.image_path = None
        campaign.image_original_filename = None
        campaign.image_mime_type = None
        campaign.image_size_bytes = None

    def _delete_upload_safely(self, path: str, *, stage: str) -> None:
        try:
            self.storage.delete(path)
        except OSError:
            logger.warning("Failed to delete campaign upload at stage %s", stage)

    def _batch_limit(self, requested_limit: int | None) -> int:
        configured = max(1, settings.customer_campaign_batch_size)
        return min(requested_limit or configured, configured)

    def _retry_delay_seconds(self, attempt_count: int) -> int:
        base = max(1, settings.customer_campaign_retry_base_seconds)
        return base * (2 ** max(0, attempt_count - 1))

    def _delivery_error_code(self, error: TelegramDeliveryError) -> str:
        message = str(error).lower()
        if (
            error.status_code == status.HTTP_403_FORBIDDEN
            or str(error.error_code) == "403"
            or "forbidden" in message
            or "blocked" in message
        ):
            return "blocked"
        if (
            error.status_code == status.HTTP_429_TOO_MANY_REQUESTS
            or str(error.error_code) == "429"
            or error.retry_after_seconds is not None
            or "too many requests" in message
            or "retry after" in message
        ):
            return "rate_limited"
        if (
            error.status_code == status.HTTP_400_BAD_REQUEST
            or str(error.error_code) == "400"
            or "bad request" in message
        ):
            return "bad_request"
        if "token is not configured" in message:
            return "configuration_error"
        if error.status_code is not None:
            return f"telegram_http_{error.status_code}"
        if error.error_code is not None:
            return self._sanitize_error_code(str(error.error_code))
        return "telegram_error"

    def _sanitize_error_code(self, error_code: str) -> str:
        sanitized = re.sub(r"[^a-zA-Z0-9_]+", "_", error_code.strip().lower()).strip("_")
        return sanitized[:100] or "telegram_error"

    def _sanitize_error_message(self, error: TelegramDeliveryError) -> str:
        message = str(error) or "Telegram delivery failed"
        for secret in (
            settings.telegram_customer_bot_token,
            settings.telegram_bot_token,
            settings.telegram_webapp_bot_token,
            settings.telegram_customer_webhook_secret,
            settings.telegram_seller_webhook_secret,
        ):
            if secret:
                message = message.replace(secret, "[redacted]")
        message = " ".join(message.split())
        if error.retry_after_seconds is not None and "retry_after_seconds" not in message:
            message = f"{message} retry_after_seconds={error.retry_after_seconds}"
        return message[:TELEGRAM_ERROR_MESSAGE_MAX_LENGTH]

    def _template_snapshot(self, template: NotificationTemplate) -> dict[str, Any]:
        return {
            "key": template.key,
            "name": template.name,
            "category": template.category.value,
            "channel": template.channel.value,
            "title": template.title,
            "parse_mode": template.parse_mode,
            "allowed_variables": list(template.allowed_variables),
            "is_active": template.is_active,
        }

    def _campaign_snapshot(self, campaign: BroadcastCampaign) -> dict[str, Any]:
        return {
            "template_id": campaign.template_id,
            "name": campaign.name,
            "type": campaign.type.value,
            "status": campaign.status.value,
            "audience_filter": campaign.audience_filter,
            "recipient_count_estimate": campaign.recipient_count_estimate,
            "recipient_count_final": campaign.recipient_count_final,
            "message_title": campaign.message_title,
            "message_length": len(campaign.message_body),
            "parse_mode": campaign.parse_mode,
            "has_image": campaign.image_path is not None,
            "image_original_filename": campaign.image_original_filename,
            "image_mime_type": campaign.image_mime_type,
            "image_size_bytes": campaign.image_size_bytes,
            "scheduled_at": self._date_value(campaign.scheduled_at),
            "started_at": self._date_value(campaign.started_at),
            "completed_at": self._date_value(campaign.completed_at),
            "cancelled_by_user_id": campaign.cancelled_by_user_id,
        }

    def _delivery_read(self, delivery: BroadcastDelivery) -> BroadcastDeliveryRead:
        return BroadcastDeliveryRead(
            id=delivery.id,
            campaign_id=delivery.campaign_id,
            user_id=delivery.user_id,
            subscription_id=delivery.subscription_id,
            telegram_chat_id_masked=self._mask_chat_id(delivery.telegram_chat_id),
            status=delivery.status,
            attempt_count=delivery.attempt_count,
            next_attempt_at=delivery.next_attempt_at,
            sent_at=delivery.sent_at,
            last_attempt_at=delivery.last_attempt_at,
            telegram_message_id=delivery.telegram_message_id,
            error_code=delivery.error_code,
            error_message=delivery.error_message,
            retry_after_seconds=delivery.retry_after_seconds,
            created_at=delivery.created_at,
            updated_at=delivery.updated_at,
        )

    def _mask_chat_id(self, chat_id: int | None) -> str:
        if chat_id is None:
            return ""
        value = str(chat_id)
        prefix = "-" if value.startswith("-") else ""
        return f"{prefix}***{value[-4:]}"

    def _date_value(self, value: datetime | None) -> str | None:
        return value.isoformat() if value is not None else None

    async def _audit(
        self,
        *,
        actor: User | None,
        action: str,
        entity_type: str,
        entity_id: int | None,
        before_data: dict[str, Any] | None = None,
        after_data: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        await self.audit_service.record_action(
            actor_user_id=actor.id if actor is not None else None,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            before_data=before_data,
            after_data=after_data,
            metadata=metadata,
            commit=False,
        )

    async def _commit(self, error_message: str) -> None:
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError(error_message, status.HTTP_409_CONFLICT) from exc

    async def _flush_if_supported(self) -> None:
        flush = getattr(self.session, "flush", None)
        if callable(flush):
            await flush()

    async def _refresh_if_supported(self, instance: object) -> None:
        refresh = getattr(self.session, "refresh", None)
        if callable(refresh):
            await refresh(instance)

    def _now(self) -> datetime:
        return self.now_factory()
