from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.common.deps import get_current_user
from app.core.errors import AppError
from app.db.models import (
    Cart,
    CartItem,
    Order,
    OrderItem,
    OrderStatus,
    Product,
    ProductStatus,
    ProductVariant,
    User,
    UserRole,
)
from app.events.names import ORDER_CREATED
from app.main import create_app
from app.modules.orders.router import get_orders_service
from app.modules.orders.schemas import OrderCheckoutCreate, OrderStatusUpdate
from app.modules.orders.service import OrdersService


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


class FakeOrderEventPublisher:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []

    async def emit(self, name: str, payload: dict[str, object]) -> None:
        self.events.append((name, payload))


class FakeOrdersRepository:
    def __init__(self) -> None:
        self.carts: dict[int, Cart] = {}
        self.orders: dict[int, Order] = {}
        self.variants: dict[int, ProductVariant] = {}
        self.next_order_id = 1
        self.next_order_item_id = 1

    async def get_cart_for_checkout(self, user_id: int) -> Cart | None:
        return self.carts.get(user_id)

    async def lock_variants_by_ids(self, variant_ids: list[int]) -> dict[int, ProductVariant]:
        return {variant_id: self.variants[variant_id] for variant_id in variant_ids}

    async def list_for_user(self, *, user_id: int, limit: int, offset: int) -> list[Order]:
        del limit, offset
        return [order for order in self.orders.values() if order.user_id == user_id]

    async def list_all(self, *, limit: int, offset: int) -> list[Order]:
        del limit, offset
        return list(self.orders.values())

    async def get_by_id(self, order_id: int) -> Order | None:
        return self.orders.get(order_id)

    async def get_for_user(self, *, user_id: int, order_id: int) -> Order | None:
        order = self.orders.get(order_id)
        if order is None or order.user_id != user_id:
            return None
        return order

    def add(self, instance: Order | OrderItem) -> None:
        if isinstance(instance, Order):
            instance.id = self.next_order_id
            self.next_order_id += 1
            instance.created_at = _now()
            instance.updated_at = _now()
            instance.items = []
            self.orders[instance.id] = instance
            return

        instance.id = self.next_order_item_id
        self.next_order_item_id += 1
        instance.created_at = _now()
        order = self.orders[instance.order_id]
        order.items.append(instance)

    async def clear_cart(self, cart_id: int) -> None:
        for cart in self.carts.values():
            if cart.id == cart_id:
                cart.items = []
                return


@pytest.mark.asyncio
async def test_checkout_from_valid_cart() -> None:
    service, repository, session, events = _orders_service()

    order = await service.checkout_current_user_cart(user_id=1, payload=_checkout_payload())

    assert order.user_id == 1
    assert order.status == OrderStatus.NEW
    assert order.total_amount == Decimal("119.80")
    assert order.items[0].product_name == "Hoodie"
    assert order.items[0].variant_size == "M"
    assert order.items[0].variant_sku == "HOODIE-M-BLK"
    assert repository.variants[1].stock_quantity == 3
    assert repository.carts[1].items == []
    assert session.committed is True
    assert events.events == [(ORDER_CREATED, {"order_id": 1, "user_id": 1})]


@pytest.mark.asyncio
async def test_reject_empty_cart_checkout() -> None:
    service, repository, session, events = _orders_service(cart_items=[])

    with pytest.raises(AppError, match="Cart is empty"):
        await service.checkout_current_user_cart(user_id=1, payload=_checkout_payload())

    assert repository.orders == {}
    assert session.rolled_back is True
    assert events.events == []


@pytest.mark.asyncio
async def test_reject_inactive_product_checkout() -> None:
    service, repository, _, _ = _orders_service(product_status=ProductStatus.DRAFT)

    with pytest.raises(AppError, match="Product is not active"):
        await service.checkout_current_user_cart(user_id=1, payload=_checkout_payload())

    assert repository.orders == {}
    assert repository.variants[1].stock_quantity == 5


@pytest.mark.asyncio
async def test_reject_inactive_variant_checkout() -> None:
    service, repository, _, _ = _orders_service(variant_is_active=False)

    with pytest.raises(AppError, match="Product variant is not active"):
        await service.checkout_current_user_cart(user_id=1, payload=_checkout_payload())

    assert repository.orders == {}
    assert repository.variants[1].stock_quantity == 5


@pytest.mark.asyncio
async def test_reject_insufficient_stock_checkout() -> None:
    service, repository, _, _ = _orders_service(stock_quantity=1)

    with pytest.raises(AppError, match="Insufficient stock"):
        await service.checkout_current_user_cart(user_id=1, payload=_checkout_payload())

    assert repository.orders == {}
    assert repository.variants[1].stock_quantity == 1


@pytest.mark.asyncio
async def test_stock_deducted_after_successful_checkout() -> None:
    service, repository, _, _ = _orders_service(stock_quantity=7)

    await service.checkout_current_user_cart(user_id=1, payload=_checkout_payload())

    assert repository.variants[1].stock_quantity == 5


@pytest.mark.asyncio
async def test_cart_cleared_after_successful_checkout() -> None:
    service, repository, _, _ = _orders_service()

    await service.checkout_current_user_cart(user_id=1, payload=_checkout_payload())

    assert repository.carts[1].items == []


@pytest.mark.asyncio
async def test_order_item_snapshot_is_immutable() -> None:
    service, repository, _, _ = _orders_service()

    order = await service.checkout_current_user_cart(user_id=1, payload=_checkout_payload())
    repository.carts[1] = _cart(user_id=1)
    repository.carts[1].items[0].product.name = "Renamed Hoodie"
    repository.carts[1].items[0].product.base_price = Decimal("10.00")
    repository.variants[1].size = "L"
    repository.variants[1].sku = "CHANGED"

    assert order.items[0].product_name == "Hoodie"
    assert order.items[0].variant_size == "M"
    assert order.items[0].variant_sku == "HOODIE-M-BLK"
    assert order.items[0].unit_price == Decimal("59.90")


@pytest.mark.asyncio
async def test_user_can_list_own_orders() -> None:
    service, repository, _, _ = _orders_service()
    repository.orders[2] = _order(order_id=2, user_id=2)
    await service.checkout_current_user_cart(user_id=1, payload=_checkout_payload())

    orders = await service.list_current_user_orders(user_id=1)

    assert [order.user_id for order in orders.items] == [1]


@pytest.mark.asyncio
async def test_user_cannot_access_another_users_order() -> None:
    service, repository, _, _ = _orders_service()
    repository.orders[10] = _order(order_id=10, user_id=2)

    with pytest.raises(AppError, match="Order not found"):
        await service.get_current_user_order(user_id=1, order_id=10)


@pytest.mark.asyncio
async def test_seller_admin_can_list_and_update_orders() -> None:
    service, repository, _, _ = _orders_service()
    repository.orders[10] = _order(order_id=10, user_id=1)

    orders = await service.list_orders()
    updated = await service.update_order_status(10, OrderStatusUpdate(status=OrderStatus.SHIPPED))

    assert len(orders.items) == 1
    assert updated.status == OrderStatus.SHIPPED


def test_orders_require_authentication() -> None:
    with TestClient(create_app()) as client:
        list_response = client.get("/api/v1/orders")
        checkout_response = client.post("/api/v1/orders/checkout", json=_checkout_payload_json())

    assert list_response.status_code == 401
    assert checkout_response.status_code == 401


def test_order_admin_routes_reject_regular_user() -> None:
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: _user(UserRole.USER)
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/orders/admin")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json() == {"detail": "Insufficient permissions"}


def test_order_admin_routes_allow_seller_to_update_status() -> None:
    app = create_app()

    class FakeOrdersService:
        async def update_order_status(self, order_id: int, payload: OrderStatusUpdate) -> dict:
            del order_id, payload
            return _order_response(status_value="PROCESSING")

    app.dependency_overrides[get_current_user] = lambda: _user(UserRole.SELLER)
    app.dependency_overrides[get_orders_service] = lambda: FakeOrdersService()
    try:
        with TestClient(app) as client:
            response = client.patch(
                "/api/v1/orders/admin/1/status",
                json={"status": "PROCESSING"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["status"] == "PROCESSING"


def _orders_service(
    *,
    product_status: ProductStatus = ProductStatus.ACTIVE,
    variant_is_active: bool = True,
    stock_quantity: int = 5,
    cart_items: list[CartItem] | None = None,
) -> tuple[OrdersService, FakeOrdersRepository, DummySession, FakeOrderEventPublisher]:
    session = DummySession()
    events = FakeOrderEventPublisher()
    service = OrdersService(session, event_publisher=events)
    repository = FakeOrdersRepository()
    repository.carts[1] = _cart(
        user_id=1,
        product_status=product_status,
        variant_is_active=variant_is_active,
        stock_quantity=stock_quantity,
        items=cart_items,
    )
    if repository.carts[1].items:
        repository.variants[1] = repository.carts[1].items[0].product_variant
    else:
        repository.variants[1] = _variant()
    service.repository = repository
    return service, repository, session, events


def _cart(
    *,
    user_id: int,
    product_status: ProductStatus = ProductStatus.ACTIVE,
    variant_is_active: bool = True,
    stock_quantity: int = 5,
    items: list[CartItem] | None = None,
) -> Cart:
    cart = Cart(id=user_id, user_id=user_id, created_at=_now(), updated_at=_now())
    if items is not None:
        cart.items = items
        return cart

    product = _product(status=product_status)
    variant = _variant(stock_quantity=stock_quantity, is_active=variant_is_active)
    cart.items = [
        CartItem(
            id=1,
            cart_id=cart.id,
            product_id=product.id,
            product_variant_id=variant.id,
            product=product,
            product_variant=variant,
            quantity=2,
            created_at=_now(),
            updated_at=_now(),
        )
    ]
    return cart


def _order(order_id: int, user_id: int, status_value: OrderStatus = OrderStatus.NEW) -> Order:
    return Order(
        id=order_id,
        order_number=f"ORD-{order_id:08d}",
        user_id=user_id,
        status=status_value,
        subtotal_amount=Decimal("59.90"),
        discount_amount=Decimal("0.00"),
        total_amount=Decimal("59.90"),
        contact_name="Ada Lovelace",
        contact_phone="+10000000000",
        delivery_address="Main street",
        delivery_comment=None,
        items=[
            OrderItem(
                id=1,
                order_id=order_id,
                product_id=1,
                product_variant_id=1,
                product_name="Hoodie",
                variant_size="M",
                variant_sku="HOODIE-M-BLK",
                unit_price=Decimal("59.90"),
                quantity=1,
                subtotal=Decimal("59.90"),
                created_at=_now(),
            )
        ],
        created_at=_now(),
        updated_at=_now(),
    )


def _product(status: ProductStatus = ProductStatus.ACTIVE) -> Product:
    return Product(
        id=1,
        name="Hoodie",
        slug="hoodie",
        description="Warm",
        base_price=Decimal("59.90"),
        status=status,
        category_id=None,
        created_at=_now(),
        updated_at=_now(),
    )


def _variant(*, stock_quantity: int = 5, is_active: bool = True) -> ProductVariant:
    return ProductVariant(
        id=1,
        product_id=1,
        size="M",
        color="Black",
        sku="HOODIE-M-BLK",
        stock_quantity=stock_quantity,
        reserved_quantity=0,
        is_active=is_active,
        created_at=_now(),
        updated_at=_now(),
    )


def _checkout_payload() -> OrderCheckoutCreate:
    return OrderCheckoutCreate.model_validate(_checkout_payload_json())


def _checkout_payload_json() -> dict[str, str]:
    return {
        "contact_name": "Ada Lovelace",
        "contact_phone": "+10000000000",
        "delivery_address": "Main street",
        "delivery_comment": "Door code 42",
    }


def _order_response(status_value: str = "NEW") -> dict[str, object]:
    now = _now().isoformat()
    return {
        "id": 1,
        "order_number": "ORD-00000001",
        "user_id": 1,
        "status": status_value,
        "subtotal_amount": "59.90",
        "discount_amount": "0.00",
        "total_amount": "59.90",
        "contact_name": "Ada Lovelace",
        "contact_phone": "+10000000000",
        "delivery_address": "Main street",
        "delivery_comment": None,
        "items": [
            {
                "id": 1,
                "product_id": 1,
                "product_variant_id": 1,
                "product_name": "Hoodie",
                "variant_size": "M",
                "variant_sku": "HOODIE-M-BLK",
                "unit_price": "59.90",
                "quantity": 1,
                "subtotal": "59.90",
                "created_at": now,
            }
        ],
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
