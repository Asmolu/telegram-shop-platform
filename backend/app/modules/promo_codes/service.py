from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from fastapi import status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.pagination import PageMeta
from app.core.errors import AppError
from app.db.models import CouponUsage, DiscountType, PromoCode
from app.modules.promo_codes.repository import PromoCodesRepository, calculate_cart_subtotal
from app.modules.promo_codes.schemas import (
    PromoCodeCreate,
    PromoCodeList,
    PromoCodeRead,
    PromoCodeUpdate,
    PromoCodeValidationRead,
)

MONEY_QUANT = Decimal("0.01")


@dataclass(frozen=True)
class PromoCodeCalculation:
    promo_code: PromoCode
    subtotal_amount: Decimal
    discount_amount: Decimal
    total_amount: Decimal


class PromoCodesService:
    """Promo code management and validation business logic."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = PromoCodesRepository(session)

    async def create_promo_code(self, payload: PromoCodeCreate) -> PromoCodeRead:
        self._validate_discount_value(payload.discount_type, payload.discount_value)
        promo_code = PromoCode(**payload.model_dump())
        self.repository.add(promo_code)
        try:
            await self.session.commit()
            await self.session.refresh(promo_code)
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError("Promo code already exists", status.HTTP_409_CONFLICT) from exc

        return PromoCodeRead.model_validate(promo_code)

    async def list_promo_codes(self, *, limit: int, offset: int) -> PromoCodeList:
        items, total = await self.repository.list(limit=limit, offset=offset)
        return PromoCodeList(
            items=[PromoCodeRead.model_validate(item) for item in items],
            meta=PageMeta(limit=limit, offset=offset, total=total),
        )

    async def get_promo_code(self, promo_code_id: int) -> PromoCodeRead:
        promo_code = await self._get_existing_promo_code(promo_code_id)
        return PromoCodeRead.model_validate(promo_code)

    async def update_promo_code(
        self,
        promo_code_id: int,
        payload: PromoCodeUpdate,
    ) -> PromoCodeRead:
        promo_code = await self._get_existing_promo_code(promo_code_id)
        data = payload.model_dump(exclude_unset=True)

        discount_type = data.get("discount_type", promo_code.discount_type)
        discount_value = data.get("discount_value", promo_code.discount_value)
        self._validate_discount_value(discount_type, discount_value)

        starts_at = data.get("starts_at", promo_code.starts_at)
        ends_at = data.get("ends_at", promo_code.ends_at)
        self._validate_date_range(starts_at, ends_at)

        for field, value in data.items():
            setattr(promo_code, field, value)

        try:
            await self.session.commit()
            await self.session.refresh(promo_code)
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError("Promo code already exists", status.HTTP_409_CONFLICT) from exc

        return PromoCodeRead.model_validate(promo_code)

    async def deactivate_promo_code(self, promo_code_id: int) -> None:
        promo_code = await self._get_existing_promo_code(promo_code_id)
        promo_code.is_active = False
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError("Promo code update failed", status.HTTP_409_CONFLICT) from exc

    async def validate_current_cart(self, *, user_id: int, code: str) -> PromoCodeValidationRead:
        cart = await self.repository.get_cart_for_validation(user_id)
        if cart is None or not cart.items:
            raise AppError("Cart is empty", status.HTTP_400_BAD_REQUEST)

        subtotal = calculate_cart_subtotal(cart)
        calculation = await self.validate_for_checkout(
            user_id=user_id,
            code=code,
            subtotal_amount=subtotal,
            for_update=False,
        )
        promo_code = calculation.promo_code
        return PromoCodeValidationRead(
            code=promo_code.code,
            discount_type=promo_code.discount_type,
            discount_value=promo_code.discount_value,
            subtotal_amount=calculation.subtotal_amount,
            discount_amount=calculation.discount_amount,
            total_amount=calculation.total_amount,
        )

    async def validate_for_checkout(
        self,
        *,
        user_id: int,
        code: str,
        subtotal_amount: Decimal,
        for_update: bool,
    ) -> PromoCodeCalculation:
        promo_code = await self.repository.get_by_code(code, for_update=for_update)
        if promo_code is None:
            raise AppError("Promo code not found", status.HTTP_404_NOT_FOUND)

        self._validate_active_window(promo_code)
        await self._validate_usage_limits(promo_code=promo_code, user_id=user_id)
        discount_amount = self.calculate_discount(
            discount_type=promo_code.discount_type,
            discount_value=promo_code.discount_value,
            subtotal_amount=subtotal_amount,
        )
        total_amount = (subtotal_amount - discount_amount).quantize(
            MONEY_QUANT,
            rounding=ROUND_HALF_UP,
        )
        return PromoCodeCalculation(
            promo_code=promo_code,
            subtotal_amount=subtotal_amount,
            discount_amount=discount_amount,
            total_amount=total_amount,
        )

    def record_usage_for_checkout(
        self,
        *,
        promo_code_id: int,
        user_id: int,
        order_id: int,
    ) -> None:
        self.repository.add(
            CouponUsage(
                promo_code_id=promo_code_id,
                user_id=user_id,
                order_id=order_id,
            )
        )

    def calculate_discount(
        self,
        *,
        discount_type: DiscountType,
        discount_value: Decimal,
        subtotal_amount: Decimal,
    ) -> Decimal:
        if discount_type == DiscountType.PERCENT:
            raw_discount = subtotal_amount * discount_value / Decimal("100")
        else:
            raw_discount = discount_value

        discount = raw_discount.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)
        if discount > subtotal_amount:
            return subtotal_amount.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)
        return discount

    async def _get_existing_promo_code(self, promo_code_id: int) -> PromoCode:
        promo_code = await self.repository.get_by_id(promo_code_id)
        if promo_code is None:
            raise AppError("Promo code not found", status.HTTP_404_NOT_FOUND)
        return promo_code

    async def _validate_usage_limits(self, *, promo_code: PromoCode, user_id: int) -> None:
        if promo_code.usage_limit is not None:
            usage_count = await self.repository.count_usages(promo_code.id)
            if usage_count >= promo_code.usage_limit:
                raise AppError(
                    "Promo code usage limit exceeded",
                    status.HTTP_400_BAD_REQUEST,
                )

        if promo_code.per_user_limit is not None:
            user_usage_count = await self.repository.count_user_usages(
                promo_code_id=promo_code.id,
                user_id=user_id,
            )
            if user_usage_count >= promo_code.per_user_limit:
                raise AppError(
                    "Promo code per-user limit exceeded",
                    status.HTTP_400_BAD_REQUEST,
                )

    def _validate_active_window(self, promo_code: PromoCode) -> None:
        if not promo_code.is_active:
            raise AppError("Promo code is inactive", status.HTTP_400_BAD_REQUEST)

        now = datetime.now(UTC)
        if promo_code.starts_at is not None and self._as_utc(promo_code.starts_at) > now:
            raise AppError("Promo code is not active yet", status.HTTP_400_BAD_REQUEST)
        if promo_code.ends_at is not None and self._as_utc(promo_code.ends_at) <= now:
            raise AppError("Promo code has expired", status.HTTP_400_BAD_REQUEST)

    def _validate_discount_value(
        self,
        discount_type: DiscountType,
        discount_value: Decimal,
    ) -> None:
        if discount_value <= 0:
            raise AppError("Discount value must be positive", status.HTTP_400_BAD_REQUEST)
        if discount_type == DiscountType.PERCENT and discount_value > Decimal("100"):
            raise AppError(
                "Percentage discount cannot exceed 100",
                status.HTTP_400_BAD_REQUEST,
            )

    def _validate_date_range(
        self,
        starts_at: datetime | None,
        ends_at: datetime | None,
    ) -> None:
        if starts_at is None or ends_at is None:
            return
        if self._as_utc(starts_at) >= self._as_utc(ends_at):
            raise AppError("starts_at must be before ends_at", status.HTTP_400_BAD_REQUEST)

    def _as_utc(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
