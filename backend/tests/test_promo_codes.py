from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.common.deps import get_current_user
from app.core.errors import AppError
from app.db.models import (
    Cart,
    CartItem,
    CouponUsage,
    DiscountType,
    Product,
    ProductStatus,
    PromoCode,
    User,
    UserRole,
)
from app.main import create_app
from app.modules.promo_codes.router import get_promo_codes_service
from app.modules.promo_codes.schemas import (
    PromoCodeCreate,
    PromoCodeUpdate,
    PromoCodeValidateRequest,
)
from app.modules.promo_codes.service import PromoCodesService


class DummySession:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True

    async def refresh(self, _: object) -> None:
        return None


class FakePromoCodesRepository:
    def __init__(self) -> None:
        self.promo_codes: dict[int, PromoCode] = {}
        self.promo_codes_by_code: dict[str, PromoCode] = {}
        self.usages: list[CouponUsage] = []
        self.carts: dict[int, Cart] = {}
        self.next_promo_code_id = 1
        self.next_usage_id = 1

    async def list(self, *, limit: int, offset: int) -> tuple[list[PromoCode], int]:
        items = list(self.promo_codes.values())
        return items[offset : offset + limit], len(items)

    async def get_by_id(self, promo_code_id: int) -> PromoCode | None:
        return self.promo_codes.get(promo_code_id)

    async def get_by_code(self, code: str, *, for_update: bool = False) -> PromoCode | None:
        del for_update
        return self.promo_codes_by_code.get(code)

    async def count_usages(self, promo_code_id: int) -> int:
        return sum(usage.promo_code_id == promo_code_id for usage in self.usages)

    async def count_user_usages(self, *, promo_code_id: int, user_id: int) -> int:
        return sum(
            usage.promo_code_id == promo_code_id and usage.user_id == user_id
            for usage in self.usages
        )

    async def get_cart_for_validation(self, user_id: int) -> Cart | None:
        return self.carts.get(user_id)

    def add(self, instance: PromoCode | CouponUsage) -> None:
        if isinstance(instance, PromoCode):
            instance.id = self.next_promo_code_id
            self.next_promo_code_id += 1
            instance.created_at = _now()
            instance.updated_at = _now()
            self.promo_codes[instance.id] = instance
            self.promo_codes_by_code[instance.code] = instance
            return

        instance.id = self.next_usage_id
        self.next_usage_id += 1
        instance.used_at = _now()
        self.usages.append(instance)

    async def delete(self, promo_code: PromoCode) -> None:
        self.promo_codes.pop(promo_code.id)
        self.promo_codes_by_code.pop(promo_code.code)


@pytest.mark.asyncio
async def test_create_percentage_promo_code() -> None:
    service, repository, session = _promo_service()

    promo_code = await service.create_promo_code(
        PromoCodeCreate(
            code="save10",
            discount_type=DiscountType.PERCENT,
            discount_value=Decimal("10.00"),
        )
    )

    assert promo_code.code == "SAVE10"
    assert promo_code.discount_type == DiscountType.PERCENT
    assert repository.promo_codes[1].discount_value == Decimal("10.00")
    assert session.committed is True


@pytest.mark.asyncio
async def test_create_fixed_promo_code() -> None:
    service, _, _ = _promo_service()

    promo_code = await service.create_promo_code(
        PromoCodeCreate(
            code="minus500",
            discount_type=DiscountType.FIXED,
            discount_value=Decimal("500.00"),
        )
    )

    assert promo_code.code == "MINUS500"
    assert promo_code.discount_type == DiscountType.FIXED


def test_reject_invalid_discount_values() -> None:
    with pytest.raises(ValidationError):
        PromoCodeCreate(
            code="bad",
            discount_type=DiscountType.FIXED,
            discount_value=Decimal("-1.00"),
        )

    with pytest.raises(ValidationError):
        PromoCodeCreate(
            code="too-much",
            discount_type=DiscountType.PERCENT,
            discount_value=Decimal("101.00"),
        )


@pytest.mark.asyncio
async def test_reject_inactive_promo_code() -> None:
    service, repository, _ = _promo_service()
    repository.add(_promo_code(is_active=False))

    with pytest.raises(AppError, match="Promo code is inactive"):
        await service.validate_for_checkout(
            user_id=1,
            code="SAVE10",
            subtotal_amount=Decimal("100.00"),
            for_update=True,
        )


@pytest.mark.asyncio
async def test_reject_expired_promo_code() -> None:
    service, repository, _ = _promo_service()
    repository.add(_promo_code(ends_at=datetime.now(UTC) - timedelta(days=1)))

    with pytest.raises(AppError, match="Promo code has expired"):
        await service.validate_for_checkout(
            user_id=1,
            code="SAVE10",
            subtotal_amount=Decimal("100.00"),
            for_update=True,
        )


@pytest.mark.asyncio
async def test_reject_not_yet_started_promo_code() -> None:
    service, repository, _ = _promo_service()
    repository.add(_promo_code(starts_at=datetime.now(UTC) + timedelta(days=1)))

    with pytest.raises(AppError, match="Promo code is not active yet"):
        await service.validate_for_checkout(
            user_id=1,
            code="SAVE10",
            subtotal_amount=Decimal("100.00"),
            for_update=True,
        )


@pytest.mark.asyncio
async def test_reject_over_global_usage_limit() -> None:
    service, repository, _ = _promo_service()
    promo_code = _promo_code(usage_limit=1)
    repository.add(promo_code)
    repository.add(CouponUsage(promo_code_id=promo_code.id, user_id=2, order_id=10))

    with pytest.raises(AppError, match="Promo code usage limit exceeded"):
        await service.validate_for_checkout(
            user_id=1,
            code="SAVE10",
            subtotal_amount=Decimal("100.00"),
            for_update=True,
        )


@pytest.mark.asyncio
async def test_reject_over_per_user_usage_limit() -> None:
    service, repository, _ = _promo_service()
    promo_code = _promo_code(per_user_limit=1)
    repository.add(promo_code)
    repository.add(CouponUsage(promo_code_id=promo_code.id, user_id=1, order_id=10))

    with pytest.raises(AppError, match="Promo code per-user limit exceeded"):
        await service.validate_for_checkout(
            user_id=1,
            code="SAVE10",
            subtotal_amount=Decimal("100.00"),
            for_update=True,
        )


@pytest.mark.asyncio
async def test_calculate_percentage_discount_correctly() -> None:
    service, repository, _ = _promo_service()
    repository.add(_promo_code(discount_type=DiscountType.PERCENT, discount_value=Decimal("15.00")))

    result = await service.validate_for_checkout(
        user_id=1,
        code="SAVE10",
        subtotal_amount=Decimal("200.00"),
        for_update=True,
    )

    assert result.discount_amount == Decimal("30.00")
    assert result.total_amount == Decimal("170.00")


@pytest.mark.asyncio
async def test_calculate_fixed_discount_correctly() -> None:
    service, repository, _ = _promo_service()
    repository.add(_promo_code(discount_type=DiscountType.FIXED, discount_value=Decimal("25.00")))

    result = await service.validate_for_checkout(
        user_id=1,
        code="SAVE10",
        subtotal_amount=Decimal("200.00"),
        for_update=True,
    )

    assert result.discount_amount == Decimal("25.00")
    assert result.total_amount == Decimal("175.00")


@pytest.mark.asyncio
async def test_discount_cannot_exceed_cart_total() -> None:
    service, repository, _ = _promo_service()
    repository.add(_promo_code(discount_type=DiscountType.FIXED, discount_value=Decimal("500.00")))

    result = await service.validate_for_checkout(
        user_id=1,
        code="SAVE10",
        subtotal_amount=Decimal("119.80"),
        for_update=True,
    )

    assert result.discount_amount == Decimal("119.80")
    assert result.total_amount == Decimal("0.00")


@pytest.mark.asyncio
async def test_validate_promo_code_against_current_cart() -> None:
    service, repository, _ = _promo_service()
    repository.add(_promo_code(discount_type=DiscountType.PERCENT, discount_value=Decimal("10.00")))
    repository.carts[1] = _cart(user_id=1)

    result = await service.validate_current_cart(user_id=1, code="SAVE10")

    assert result.subtotal_amount == Decimal("119.80")
    assert result.discount_amount == Decimal("11.98")
    assert result.total_amount == Decimal("107.82")
    assert result.is_valid is True
    assert result.is_applied is True
    assert result.promo_code == "SAVE10"
    assert result.discount == Decimal("11.98")
    assert result.total == Decimal("107.82")


def test_validate_request_accepts_checkout_promo_code_field_name() -> None:
    payload = PromoCodeValidateRequest.model_validate({"promo_code": "save10"})

    assert payload.code == "SAVE10"


def test_promo_validation_response_shape_is_frontend_friendly() -> None:
    app = create_app()

    class FakePromoCodesService:
        async def validate_current_cart(self, **_: object) -> dict[str, object]:
            return {
                "code": "SAVE10",
                "discount_type": "PERCENT",
                "discount_value": "10.00",
                "subtotal_amount": "119.80",
                "discount_amount": "11.98",
                "total_amount": "107.82",
            }

    app.dependency_overrides[get_current_user] = lambda: _user(UserRole.USER)
    app.dependency_overrides[get_promo_codes_service] = lambda: FakePromoCodesService()
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/promo-codes/validate", json={"code": "save10"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == "SAVE10"
    assert body["promo_code"] == "SAVE10"
    assert body["is_valid"] is True
    assert body["is_applied"] is True
    assert body["discount_amount"] == "11.98"
    assert body["discount"] == "11.98"
    assert body["total_amount"] == "107.82"
    assert body["total"] == "107.82"


def test_promo_validation_requires_authentication() -> None:
    with TestClient(create_app()) as client:
        response = client.post("/api/v1/promo-codes/validate", json={"code": "SAVE10"})

    assert response.status_code == 401


def test_promo_management_requires_authentication() -> None:
    with TestClient(create_app()) as client:
        response = client.post("/api/v1/promo-codes", json=_promo_payload())

    assert response.status_code == 401


def test_promo_management_rejects_regular_user() -> None:
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: _user(UserRole.USER)
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/promo-codes", json=_promo_payload())
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json() == {"detail": "Insufficient permissions"}


def test_promo_management_allows_seller() -> None:
    app = create_app()

    class FakePromoCodesService:
        async def create_promo_code(self, _: PromoCodeCreate, **__: object) -> dict[str, object]:
            return _promo_response()

    app.dependency_overrides[get_current_user] = lambda: _user(UserRole.SELLER)
    app.dependency_overrides[get_promo_codes_service] = lambda: FakePromoCodesService()
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/promo-codes", json=_promo_payload())
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["code"] == "SAVE10"


@pytest.mark.asyncio
async def test_update_can_deactivate_promo_code() -> None:
    service, repository, _ = _promo_service()
    repository.add(_promo_code())

    updated = await service.update_promo_code(1, PromoCodeUpdate(is_active=False))

    assert updated.is_active is False


def _promo_service() -> tuple[PromoCodesService, FakePromoCodesRepository, DummySession]:
    session = DummySession()
    service = PromoCodesService(session)
    repository = FakePromoCodesRepository()
    service.repository = repository
    return service, repository, session


def _promo_code(
    *,
    is_active: bool = True,
    discount_type: DiscountType = DiscountType.PERCENT,
    discount_value: Decimal = Decimal("10.00"),
    starts_at: datetime | None = None,
    ends_at: datetime | None = None,
    usage_limit: int | None = None,
    per_user_limit: int | None = None,
) -> PromoCode:
    return PromoCode(
        code="SAVE10",
        discount_type=discount_type,
        discount_value=discount_value,
        is_active=is_active,
        starts_at=starts_at,
        ends_at=ends_at,
        usage_limit=usage_limit,
        per_user_limit=per_user_limit,
        created_at=_now(),
        updated_at=_now(),
    )


def _cart(*, user_id: int) -> Cart:
    product = Product(
        id=1,
        name="Hoodie",
        slug="hoodie",
        description="Warm",
        base_price=Decimal("59.90"),
        status=ProductStatus.ACTIVE,
        category_id=None,
        created_at=_now(),
        updated_at=_now(),
    )
    return Cart(
        id=user_id,
        user_id=user_id,
        items=[
            CartItem(
                id=1,
                cart_id=user_id,
                product_id=product.id,
                product=product,
                product_variant_id=1,
                quantity=2,
                created_at=_now(),
                updated_at=_now(),
            )
        ],
        created_at=_now(),
        updated_at=_now(),
    )


def _promo_payload() -> dict[str, object]:
    return {
        "code": "SAVE10",
        "discount_type": "PERCENT",
        "discount_value": "10.00",
        "is_active": True,
        "starts_at": None,
        "ends_at": None,
        "usage_limit": None,
        "per_user_limit": None,
    }


def _promo_response() -> dict[str, object]:
    now = _now().isoformat()
    return {
        **_promo_payload(),
        "id": 1,
        "created_at": now,
        "updated_at": now,
    }


def _user(role: UserRole) -> User:
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
    return datetime(2026, 5, 27, tzinfo=UTC)
