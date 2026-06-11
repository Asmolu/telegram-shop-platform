from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.core.errors import AppError
from app.db.models import Cart, CartItem, Product, ProductSizeGrid, ProductStatus, ProductVariant
from app.main import create_app
from app.modules.cart.schemas import CartItemCreate, CartItemUpdate
from app.modules.cart.service import CartService


class DummySession:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True

    async def flush(self) -> None:
        return None


class FakeAnalyticsTracker:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []

    async def track(self, event_name: str, **payload: object) -> None:
        self.events.append((event_name, payload))


class FakeCartRepository:
    def __init__(self) -> None:
        self.carts: dict[int, Cart] = {}
        self.products: dict[int, Product] = {}
        self.variants: dict[int, ProductVariant] = {}
        self.next_cart_id = 1
        self.next_item_id = 1

    async def get_by_user_id(self, user_id: int) -> Cart | None:
        return self.carts.get(user_id)

    async def get_item_for_user(self, *, user_id: int, item_id: int) -> CartItem | None:
        cart = self.carts.get(user_id)
        if cart is None:
            return None
        return next((item for item in cart.items if item.id == item_id), None)

    async def get_item_by_cart_and_variant(
        self,
        *,
        cart_id: int,
        product_variant_id: int,
    ) -> CartItem | None:
        cart = next(
            (candidate for candidate in self.carts.values() if candidate.id == cart_id),
            None,
        )
        if cart is None:
            return None
        return next(
            (item for item in cart.items if item.product_variant_id == product_variant_id),
            None,
        )

    async def get_product_by_id(self, product_id: int) -> Product | None:
        return self.products.get(product_id)

    async def get_product_variant_by_id(self, product_variant_id: int) -> ProductVariant | None:
        return self.variants.get(product_variant_id)

    def add(self, instance: Cart | CartItem) -> None:
        if isinstance(instance, Cart):
            instance.id = self.next_cart_id
            self.next_cart_id += 1
            instance.created_at = _now()
            instance.updated_at = _now()
            instance.items = []
            self.carts[instance.user_id] = instance
            return

        instance.id = self.next_item_id
        self.next_item_id += 1
        instance.product = self.products[instance.product_id]
        instance.product_variant = self.variants[instance.product_variant_id]
        instance.created_at = _now()
        instance.updated_at = _now()
        cart = next(cart for cart in self.carts.values() if cart.id == instance.cart_id)
        cart.items.append(instance)

    async def delete_item(self, item: CartItem) -> None:
        cart = next(cart for cart in self.carts.values() if cart.id == item.cart_id)
        cart.items = [candidate for candidate in cart.items if candidate.id != item.id]

    async def clear_cart(self, cart_id: int) -> None:
        cart = next(cart for cart in self.carts.values() if cart.id == cart_id)
        cart.items = []


@pytest.mark.asyncio
async def test_get_empty_cart() -> None:
    service, _ = _cart_service()

    cart = await service.get_current_user_cart(user_id=1)

    assert cart.user_id == 1
    assert cart.items == []
    assert cart.total == Decimal("0.00")
    assert cart.quantity_total == 0


@pytest.mark.asyncio
async def test_add_item() -> None:
    service, _ = _cart_service()

    cart = await service.add_item(1, CartItemCreate(product_id=1, product_variant_id=1, quantity=2))

    assert len(cart.items) == 1
    assert cart.items[0].quantity == 2
    assert cart.items[0].product.size_grid == ProductSizeGrid.CLOTHING_ALPHA
    assert cart.items[0].subtotal == Decimal("119.80")
    assert cart.total == Decimal("119.80")


@pytest.mark.asyncio
async def test_add_item_tracks_cart_item_added_event() -> None:
    tracker = FakeAnalyticsTracker()
    service, _ = _cart_service(analytics_tracker=tracker)

    await service.add_item(1, CartItemCreate(product_id=1, product_variant_id=1, quantity=2))

    assert tracker.events == [
        (
            "cart.item_added",
            {
                "user_id": 1,
                "product_id": 1,
                "metadata": {
                    "product_variant_id": 1,
                    "quantity": 2,
                    "cart_id": 1,
                },
            },
        )
    ]


@pytest.mark.asyncio
async def test_add_same_item_twice_increases_quantity() -> None:
    service, _ = _cart_service()

    await service.add_item(1, CartItemCreate(product_id=1, product_variant_id=1, quantity=2))
    cart = await service.add_item(1, CartItemCreate(product_id=1, product_variant_id=1, quantity=1))

    assert len(cart.items) == 1
    assert cart.items[0].quantity == 3
    assert cart.quantity_total == 3


@pytest.mark.asyncio
async def test_update_quantity() -> None:
    service, _ = _cart_service()

    cart = await service.add_item(1, CartItemCreate(product_id=1, product_variant_id=1, quantity=1))
    updated = await service.update_item_quantity(
        1,
        cart.items[0].id,
        CartItemUpdate(quantity=4),
    )

    assert updated.items[0].quantity == 4
    assert updated.total == Decimal("239.60")


@pytest.mark.asyncio
async def test_remove_item() -> None:
    service, _ = _cart_service()

    cart = await service.add_item(1, CartItemCreate(product_id=1, product_variant_id=1, quantity=1))
    updated = await service.remove_item(1, cart.items[0].id)

    assert updated.items == []
    assert updated.total == Decimal("0.00")


@pytest.mark.asyncio
async def test_clear_cart() -> None:
    service, _ = _cart_service()

    await service.add_item(1, CartItemCreate(product_id=1, product_variant_id=1, quantity=1))
    cart = await service.clear_cart(1)

    assert cart.items == []
    assert cart.quantity_total == 0


@pytest.mark.asyncio
async def test_reject_inactive_product() -> None:
    service, repository = _cart_service(product_status=ProductStatus.DRAFT)

    with pytest.raises(AppError, match="Product is not active"):
        await service.add_item(
            1,
            CartItemCreate(product_id=1, product_variant_id=1, quantity=1),
        )

    assert repository.carts[1].items == []


@pytest.mark.asyncio
async def test_reject_inactive_variant() -> None:
    service, _ = _cart_service(variant_is_active=False)

    with pytest.raises(AppError, match="Product variant is not active"):
        await service.add_item(
            1,
            CartItemCreate(product_id=1, product_variant_id=1, quantity=1),
        )


@pytest.mark.asyncio
async def test_reject_insufficient_stock() -> None:
    service, _ = _cart_service(stock_quantity=2, reserved_quantity=1)

    with pytest.raises(AppError, match="Insufficient stock"):
        await service.add_item(
            1,
            CartItemCreate(product_id=1, product_variant_id=1, quantity=2),
        )


def test_cart_requires_authentication() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/cart")

    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}


@pytest.mark.asyncio
async def test_user_cannot_access_another_users_cart_item() -> None:
    service, _ = _cart_service()
    other_user_cart = await service.add_item(
        2,
        CartItemCreate(product_id=1, product_variant_id=1, quantity=1),
    )

    with pytest.raises(AppError, match="Cart item not found"):
        await service.update_item_quantity(
            1,
            other_user_cart.items[0].id,
            CartItemUpdate(quantity=2),
        )


def _cart_service(
    *,
    product_status: ProductStatus = ProductStatus.ACTIVE,
    variant_is_active: bool = True,
    stock_quantity: int = 5,
    reserved_quantity: int = 0,
    analytics_tracker: FakeAnalyticsTracker | None = None,
) -> tuple[CartService, FakeCartRepository]:
    service = CartService(DummySession(), analytics_tracker=analytics_tracker)
    repository = FakeCartRepository()
    repository.products[1] = _product(status=product_status)
    repository.variants[1] = _variant(
        stock_quantity=stock_quantity,
        reserved_quantity=reserved_quantity,
        is_active=variant_is_active,
    )
    service.repository = repository
    return service, repository


def _product(status: ProductStatus = ProductStatus.ACTIVE) -> Product:
    return Product(
        id=1,
        name="Hoodie",
        slug="hoodie",
        description="Warm",
        base_price=Decimal("59.90"),
        size_grid=ProductSizeGrid.CLOTHING_ALPHA,
        status=status,
        category_id=None,
        created_at=_now(),
        updated_at=_now(),
    )


def _variant(
    *,
    stock_quantity: int,
    reserved_quantity: int,
    is_active: bool,
) -> ProductVariant:
    return ProductVariant(
        id=1,
        product_id=1,
        size="M",
        color="Black",
        sku="HOODIE-M-BLK",
        stock_quantity=stock_quantity,
        reserved_quantity=reserved_quantity,
        is_active=is_active,
        created_at=_now(),
        updated_at=_now(),
    )


def _now() -> datetime:
    return datetime(2026, 5, 27, tzinfo=UTC)
