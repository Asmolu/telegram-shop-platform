from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Select, and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import (
    BroadcastCampaign,
    BroadcastCampaignStatus,
    BroadcastCampaignType,
    BroadcastDelivery,
    BroadcastDeliveryStatus,
    CouponUsage,
    CustomerTelegramSubscription,
    NotificationTemplate,
    NotificationTemplateCategory,
    Order,
    OrderItem,
    Product,
)
from app.modules.customer_notifications.campaigns.schemas import BroadcastAudienceFilter

PRIVATE_CHAT_TYPE = "private"


class CustomerNotificationCampaignRepository:
    """Database access for Bot 1 templates, campaigns, and delivery rows."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add_template(self, template: NotificationTemplate) -> None:
        self.session.add(template)

    def add_campaign(self, campaign: BroadcastCampaign) -> None:
        self.session.add(campaign)

    def add_delivery(self, delivery: BroadcastDelivery) -> None:
        self.session.add(delivery)

    def add_deliveries(self, deliveries: list[BroadcastDelivery]) -> None:
        self.session.add_all(deliveries)

    async def get_template_by_id(self, template_id: int) -> NotificationTemplate | None:
        return await self.session.get(NotificationTemplate, template_id)

    async def get_template_by_key(self, key: str) -> NotificationTemplate | None:
        result = await self.session.execute(
            select(NotificationTemplate).where(NotificationTemplate.key == key)
        )
        return result.scalar_one_or_none()

    async def list_templates(
        self,
        *,
        limit: int,
        offset: int,
        category: NotificationTemplateCategory | None = None,
        active: bool | None = None,
    ) -> tuple[list[NotificationTemplate], int]:
        conditions: list[Any] = []
        if category is not None:
            conditions.append(NotificationTemplate.category == category)
        if active is not None:
            conditions.append(NotificationTemplate.is_active == active)

        items_result = await self.session.execute(
            select(NotificationTemplate)
            .where(*conditions)
            .order_by(NotificationTemplate.updated_at.desc(), NotificationTemplate.id.desc())
            .limit(limit)
            .offset(offset)
        )
        count_result = await self.session.execute(
            select(func.count(NotificationTemplate.id)).where(*conditions)
        )
        return list(items_result.scalars().all()), count_result.scalar_one()

    async def get_campaign_by_id(self, campaign_id: int) -> BroadcastCampaign | None:
        return await self.session.get(BroadcastCampaign, campaign_id)

    async def list_campaigns(
        self,
        *,
        limit: int,
        offset: int,
        campaign_type: BroadcastCampaignType | None = None,
        status: BroadcastCampaignStatus | None = None,
    ) -> tuple[list[BroadcastCampaign], int]:
        conditions: list[Any] = []
        if campaign_type is not None:
            conditions.append(BroadcastCampaign.type == campaign_type)
        if status is not None:
            conditions.append(BroadcastCampaign.status == status)

        items_result = await self.session.execute(
            select(BroadcastCampaign)
            .where(*conditions)
            .order_by(BroadcastCampaign.created_at.desc(), BroadcastCampaign.id.desc())
            .limit(limit)
            .offset(offset)
        )
        count_result = await self.session.execute(
            select(func.count(BroadcastCampaign.id)).where(*conditions)
        )
        return list(items_result.scalars().all()), count_result.scalar_one()

    async def count_eligible_recipients(
        self,
        *,
        campaign_type: BroadcastCampaignType,
        audience_filter: BroadcastAudienceFilter,
    ) -> int:
        result = await self.session.execute(
            select(func.count(CustomerTelegramSubscription.id)).where(
                *self._eligible_conditions(
                    campaign_type=campaign_type,
                    audience_filter=audience_filter,
                )
            )
        )
        return result.scalar_one()

    async def list_eligible_recipients(
        self,
        *,
        campaign_type: BroadcastCampaignType,
        audience_filter: BroadcastAudienceFilter,
    ) -> list[CustomerTelegramSubscription]:
        result = await self.session.execute(
            select(CustomerTelegramSubscription)
            .where(
                *self._eligible_conditions(
                    campaign_type=campaign_type,
                    audience_filter=audience_filter,
                )
            )
            .order_by(CustomerTelegramSubscription.id)
        )
        return list(result.scalars().all())

    async def count_campaign_deliveries(self, campaign_id: int) -> int:
        result = await self.session.execute(
            select(func.count(BroadcastDelivery.id)).where(
                BroadcastDelivery.campaign_id == campaign_id
            )
        )
        return result.scalar_one()

    async def delivery_summary(self, campaign_id: int) -> dict[BroadcastDeliveryStatus, int]:
        result = await self.session.execute(
            select(BroadcastDelivery.status, func.count(BroadcastDelivery.id))
            .where(BroadcastDelivery.campaign_id == campaign_id)
            .group_by(BroadcastDelivery.status)
        )
        return {status: count for status, count in result.all()}

    async def list_deliveries(
        self,
        *,
        campaign_id: int,
        limit: int,
        offset: int,
        status: BroadcastDeliveryStatus | None = None,
    ) -> tuple[list[BroadcastDelivery], int]:
        conditions: list[Any] = [BroadcastDelivery.campaign_id == campaign_id]
        if status is not None:
            conditions.append(BroadcastDelivery.status == status)

        items_result = await self.session.execute(
            select(BroadcastDelivery)
            .where(*conditions)
            .order_by(BroadcastDelivery.created_at.desc(), BroadcastDelivery.id.desc())
            .limit(limit)
            .offset(offset)
        )
        count_result = await self.session.execute(
            select(func.count(BroadcastDelivery.id)).where(*conditions)
        )
        return list(items_result.scalars().all()), count_result.scalar_one()

    async def deliveries_for_processing(
        self,
        *,
        campaign_id: int,
        now: datetime,
        limit: int,
    ) -> list[BroadcastDelivery]:
        result = await self.session.execute(
            select(BroadcastDelivery)
            .options(selectinload(BroadcastDelivery.subscription))
            .where(
                BroadcastDelivery.campaign_id == campaign_id,
                or_(
                    and_(
                        BroadcastDelivery.status == BroadcastDeliveryStatus.PENDING,
                        or_(
                            BroadcastDelivery.next_attempt_at.is_(None),
                            BroadcastDelivery.next_attempt_at <= now,
                        ),
                    ),
                    and_(
                        BroadcastDelivery.status == BroadcastDeliveryStatus.RATE_LIMITED,
                        BroadcastDelivery.next_attempt_at <= now,
                    ),
                ),
            )
            .order_by(
                BroadcastDelivery.next_attempt_at.asc().nullsfirst(),
                BroadcastDelivery.id.asc(),
            )
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_unfinished_deliveries(self, *, campaign_id: int) -> int:
        result = await self.session.execute(
            select(func.count(BroadcastDelivery.id)).where(
                BroadcastDelivery.campaign_id == campaign_id,
                BroadcastDelivery.status.in_(
                    [
                        BroadcastDeliveryStatus.PENDING,
                        BroadcastDeliveryStatus.SENDING,
                        BroadcastDeliveryStatus.RATE_LIMITED,
                    ]
                ),
            )
        )
        return result.scalar_one()

    async def count_remaining_processable(self, *, campaign_id: int, now: datetime) -> int:
        result = await self.session.execute(
            select(func.count(BroadcastDelivery.id)).where(
                BroadcastDelivery.campaign_id == campaign_id,
                BroadcastDelivery.status.in_(
                    [
                        BroadcastDeliveryStatus.PENDING,
                        BroadcastDeliveryStatus.SENDING,
                        BroadcastDeliveryStatus.RATE_LIMITED,
                    ]
                ),
                or_(
                    BroadcastDelivery.next_attempt_at.is_(None),
                    BroadcastDelivery.next_attempt_at <= now,
                    BroadcastDelivery.status == BroadcastDeliveryStatus.SENDING,
                ),
            )
        )
        return result.scalar_one()

    async def skip_remaining_deliveries(
        self,
        *,
        campaign_id: int,
        now: datetime,
        error_code: str,
        error_message: str,
    ) -> int:
        result = await self.session.execute(
            update(BroadcastDelivery)
            .where(
                BroadcastDelivery.campaign_id == campaign_id,
                BroadcastDelivery.status.in_(
                    [
                        BroadcastDeliveryStatus.PENDING,
                        BroadcastDeliveryStatus.SENDING,
                        BroadcastDeliveryStatus.RATE_LIMITED,
                    ]
                ),
            )
            .values(
                status=BroadcastDeliveryStatus.SKIPPED,
                next_attempt_at=None,
                error_code=error_code,
                error_message=error_message,
                updated_at=now,
            )
        )
        return int(result.rowcount or 0)

    async def get_test_subscription_for_user(
        self,
        *,
        user_id: int,
        telegram_user_id: int,
    ) -> CustomerTelegramSubscription | None:
        result = await self.session.execute(
            select(CustomerTelegramSubscription)
            .where(
                or_(
                    CustomerTelegramSubscription.user_id == user_id,
                    CustomerTelegramSubscription.telegram_user_id == telegram_user_id,
                )
            )
            .order_by(CustomerTelegramSubscription.user_id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    def _eligible_conditions(
        self,
        *,
        campaign_type: BroadcastCampaignType,
        audience_filter: BroadcastAudienceFilter,
    ) -> list[Any]:
        conditions: list[Any] = [
            CustomerTelegramSubscription.user_id.is_not(None),
            CustomerTelegramSubscription.has_chat.is_(True),
            CustomerTelegramSubscription.telegram_chat_id.is_not(None),
            CustomerTelegramSubscription.chat_type == PRIVATE_CHAT_TYPE,
            CustomerTelegramSubscription.blocked_at.is_(None),
        ]
        if campaign_type == BroadcastCampaignType.MARKETING:
            conditions.append(CustomerTelegramSubscription.marketing_opt_in.is_(True))
        else:
            conditions.append(CustomerTelegramSubscription.service_opt_in.is_(True))

        scope = audience_filter.scope
        if scope == "purchasers":
            conditions.append(self._customer_has_order())
        elif scope == "product":
            conditions.append(self._customer_purchased_product(audience_filter.product_id))
        elif scope == "category":
            conditions.append(self._customer_purchased_category(audience_filter.category_id))
        elif scope == "promo_code":
            conditions.append(self._customer_used_promo_code(audience_filter.promo_code_id))

        return conditions

    def _customer_has_order(self) -> Any:
        return (
            select(Order.id)
            .where(Order.user_id == CustomerTelegramSubscription.user_id)
            .exists()
        )

    def _customer_purchased_product(self, product_id: int | None) -> Any:
        if product_id is None:
            return False
        return self._order_item_query().where(OrderItem.product_id == product_id).exists()

    def _customer_purchased_category(self, category_id: int | None) -> Any:
        if category_id is None:
            return False
        query = self._order_item_query().join(Product, Product.id == OrderItem.product_id)
        return query.where(Product.category_id == category_id).exists()

    def _customer_used_promo_code(self, promo_code_id: int | None) -> Any:
        if promo_code_id is None:
            return False
        return (
            select(CouponUsage.id)
            .where(
                CouponUsage.user_id == CustomerTelegramSubscription.user_id,
                CouponUsage.promo_code_id == promo_code_id,
            )
            .exists()
        )

    def _order_item_query(self) -> Select[tuple[int]]:
        return (
            select(OrderItem.id)
            .join(Order, Order.id == OrderItem.order_id)
            .where(Order.user_id == CustomerTelegramSubscription.user_id)
        )
