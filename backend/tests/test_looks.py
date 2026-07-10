import os
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from decimal import Decimal
from io import BytesIO
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import UploadFile
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient, Response
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from starlette.datastructures import Headers

from app.common.deps import get_current_user, get_db_session
from app.core.errors import AppError
from app.db.models import (
    Cart,
    CartItem,
    Category,
    Look,
    LookImage,
    LookItem,
    LookStatus,
    Product,
    ProductCategory,
    ProductImageBadgeType,
    ProductSizeGrid,
    ProductSizeGroup,
    ProductStatus,
    ProductVariant,
    RouteAlias,
    RouteAliasEntityType,
    Tag,
    User,
    UserRole,
)
from app.main import create_app
from app.modules.looks.router import get_looks_service
from app.modules.looks.schemas import LookCartAddRequest, LookCreate, LookItemInput, LookUpdate
from app.modules.looks.service import LooksService

NOW = datetime(2026, 7, 2, 12, 0, tzinfo=UTC)


class DummySession:
    def __init__(self) -> None:
        self.commit_count = 0
        self.rollback_count = 0
        self.flush_count = 0
        self.commit_error: Exception | None = None
        self.flush_error: Exception | None = None

    async def commit(self) -> None:
        self.commit_count += 1
        if self.commit_error is not None:
            raise self.commit_error

    async def rollback(self) -> None:
        self.rollback_count += 1

    async def flush(self) -> None:
        self.flush_count += 1
        if self.flush_error is not None:
            raise self.flush_error

    async def refresh(self, _instance: object) -> None:
        return None

    async def execute(self, _: object) -> "EmptyQueryResult":
        return EmptyQueryResult()


class EmptyQueryResult:
    def scalars(self) -> "EmptyQueryResult":
        return self

    def all(self) -> list[object]:
        return []

    def scalar_one_or_none(self) -> object | None:
        return None


class FakeStorage:
    def __init__(self) -> None:
        self.saved: dict[str, bytes] = {}
        self.deleted: list[str] = []
        self.next_id = 1

    def save_bytes(self, content: bytes, *, folder: str, suffix: str) -> str:
        path = f"{folder}/look-{self.next_id}{suffix}"
        self.next_id += 1
        self.saved[path] = content
        return path

    def delete(self, relative_path: str) -> None:
        self.deleted.append(relative_path)
        self.saved.pop(relative_path, None)


class FakeLooksRepository:
    def __init__(self) -> None:
        self.looks: dict[int, Look] = {}
        self.products: dict[int, Product] = {}
        self.next_look_id = 1
        self.next_item_id = 1
        self.next_image_id = 1
        self.added_look_count = 0

    async def list_public(self, *, limit: int, offset: int) -> tuple[list[Look], int]:
        looks = [
            look
            for look in self.looks.values()
            if look.status == LookStatus.ACTIVE and look.is_listed
        ]
        return looks[offset : offset + limit], len(looks)

    async def list_admin(
        self,
        *,
        limit: int,
        offset: int,
        status_filter: LookStatus | None = None,
    ) -> tuple[list[Look], int]:
        looks = list(self.looks.values())
        if status_filter is not None:
            looks = [look for look in looks if look.status == status_filter]
        return looks[offset : offset + limit], len(looks)

    async def get_public_by_slug(self, slug: str) -> Look | None:
        look = await self.get_by_slug(slug)
        if look is None or look.status != LookStatus.ACTIVE or not look.is_listed:
            return None
        return look

    async def get_public_similarity_context_by_slug(self, slug: str) -> Look | None:
        return await self.get_public_by_slug(slug)

    async def get_public_similarity_context_by_id(self, look_id: int) -> Look | None:
        look = await self.get_admin_by_id(look_id)
        if look is None or look.status != LookStatus.ACTIVE or not look.is_listed:
            return None
        return look

    async def get_admin_by_id(self, look_id: int) -> Look | None:
        return self.looks.get(look_id)

    async def get_by_slug(self, slug: str) -> Look | None:
        return next((look for look in self.looks.values() if look.slug == slug), None)

    async def list_numeric_slug_candidates(self) -> list[str]:
        return [
            look.slug
            for look in self.looks.values()
            if len(look.slug) == 5 and "00001" <= look.slug <= "99999"
        ]

    async def get_product_by_id(self, product_id: int) -> Product | None:
        return self.products.get(product_id)

    async def get_image(self, *, look_id: int, image_id: int) -> LookImage | None:
        look = self.looks.get(look_id)
        if look is None:
            return None
        return next((image for image in look.images if image.id == image_id), None)

    async def next_image_position(self, look_id: int) -> int:
        look = self.looks[look_id]
        if not look.images:
            return 0
        return max(image.position for image in look.images) + 1

    async def clear_primary_images(self, look_id: int) -> None:
        for image in self.looks[look_id].images:
            image.is_primary = False

    def add(self, instance: Look | LookImage | LookItem) -> None:
        if isinstance(instance, Look):
            self.added_look_count += 1
            self._persist_look(instance)
            self.looks[instance.id] = instance
            return

        if isinstance(instance, LookImage):
            instance.id = self.next_image_id
            self.next_image_id += 1
            instance.created_at = NOW
            self.looks[instance.look_id].images.append(instance)

    async def delete(self, instance: LookImage | LookItem) -> None:
        if isinstance(instance, LookImage):
            look = self.looks[instance.look_id]
            look.images = [image for image in look.images if image.id != instance.id]
        elif isinstance(instance, LookItem):
            look = self.looks[instance.look_id]
            look.items = [item for item in look.items if item.id != instance.id]

    def _persist_look(self, look: Look) -> None:
        if getattr(look, "id", None) is None:
            look.id = self.next_look_id
            self.next_look_id += 1
        look.created_at = getattr(look, "created_at", None) or NOW
        look.updated_at = getattr(look, "updated_at", None) or NOW
        look.images = getattr(look, "images", None) or []
        for item in look.items:
            if getattr(item, "id", None) is None:
                item.id = self.next_item_id
                self.next_item_id += 1
            item.look_id = look.id
            item.product = item.product or self.products[item.product_id]
            item.created_at = getattr(item, "created_at", None) or NOW
            item.updated_at = getattr(item, "updated_at", None) or NOW


class FakeCartRepository:
    def __init__(self, products: dict[int, Product]) -> None:
        self.carts: dict[int, Cart] = {}
        self.products = products
        self.variants = {
            variant.id: variant
            for product in products.values()
            for variant in product.variants
        }
        self.next_cart_id = 1
        self.next_item_id = 1

    async def get_by_user_id(self, user_id: int) -> Cart | None:
        return self.carts.get(user_id)

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
            (
                item
                for item in cart.items
                if item.product_variant_id == product_variant_id
                and item.source_type is None
                and item.source_group_id is None
            ),
            None,
        )

    def add(self, instance: Cart | CartItem) -> None:
        if isinstance(instance, Cart):
            instance.id = self.next_cart_id
            self.next_cart_id += 1
            instance.created_at = NOW
            instance.updated_at = NOW
            instance.items = []
            self.carts[instance.user_id] = instance
            return

        instance.id = self.next_item_id
        self.next_item_id += 1
        instance.product = self.products[instance.product_id]
        instance.product_variant = self.variants[instance.product_variant_id]
        instance.created_at = NOW
        instance.updated_at = NOW
        cart = next(cart for cart in self.carts.values() if cart.id == instance.cart_id)
        cart.items.append(instance)


class FakeRouteAliasRepository:
    def __init__(self, aliases: list[RouteAlias] | None = None) -> None:
        self.aliases = aliases or []

    async def get_active_by_slug(
        self,
        entity_type: RouteAliasEntityType,
        alias_slug: str,
    ) -> RouteAlias | None:
        return next(
            (
                alias
                for alias in self.aliases
                if alias.entity_type == entity_type
                and alias.alias_slug == alias_slug
                and alias.is_active
            ),
            None,
        )

    async def list_active_alias_slugs(self, entity_type: RouteAliasEntityType) -> list[str]:
        return [
            alias.alias_slug
            for alias in self.aliases
            if alias.entity_type == entity_type and alias.is_active
        ]

    def add(self, route_alias: RouteAlias) -> None:
        if route_alias.is_active is None:
            route_alias.is_active = True
        route_alias.created_at = getattr(route_alias, "created_at", None) or NOW
        route_alias.updated_at = getattr(route_alias, "updated_at", None) or NOW
        self.aliases.append(route_alias)


@pytest.mark.asyncio
async def test_admin_can_create_look_with_hidden_active_product() -> None:
    service, repository, _cart_repository, _session, _storage = _looks_service()
    repository.products[1] = _product(product_id=1, is_listed=False)

    look = await service.create_admin_look(
        LookCreate(
            title="Summer look",
            slug="summer-look",
            status=LookStatus.ACTIVE,
            items=[LookItemInput(product_id=1)],
        )
    )

    assert look.status == LookStatus.ACTIVE
    assert look.items[0].product_id == 1


@pytest.mark.asyncio
async def test_create_look_with_multiple_active_colors_fails() -> None:
    service, repository, _cart_repository, _session, _storage = _looks_service()
    repository.products[1] = _product(
        product_id=1,
        variants=[
            _variant(variant_id=1, product_id=1, size="M", color="Black"),
            _variant(variant_id=2, product_id=1, size="L", color="White"),
        ],
    )

    with pytest.raises(AppError) as exc_info:
        await service.create_admin_look(
            LookCreate(
                title="Two colors",
                slug="two-colors",
                status=LookStatus.ACTIVE,
                items=[LookItemInput(product_id=1)],
            )
        )

    assert exc_info.value.message == "Products in a Look cannot have more than one active color"


@pytest.mark.asyncio
async def test_active_look_requires_default_selected_item() -> None:
    service, repository, _cart_repository, _session, _storage = _looks_service()
    repository.products[1] = _product(product_id=1)

    with pytest.raises(AppError) as exc_info:
        await service.create_admin_look(
            LookCreate(
                title="No defaults",
                slug="no-defaults",
                status=LookStatus.ACTIVE,
                items=[LookItemInput(product_id=1, is_default_selected=False)],
            )
        )

    assert exc_info.value.message == "Active Look must have at least one default selected item"


@pytest.mark.asyncio
async def test_active_look_requires_active_products() -> None:
    service, repository, _cart_repository, _session, _storage = _looks_service()
    repository.products[1] = _product(product_id=1, status_value=ProductStatus.DRAFT)

    with pytest.raises(AppError) as exc_info:
        await service.create_admin_look(
            LookCreate(
                title="Draft component",
                slug="draft-component",
                status=LookStatus.ACTIVE,
                items=[LookItemInput(product_id=1)],
            )
        )

    assert exc_info.value.message == "Active Look can include only active products"


@pytest.mark.asyncio
async def test_duplicate_slug_returns_conflict() -> None:
    service, repository, _cart_repository, _session, _storage = _looks_service()
    repository.products[1] = _product(product_id=1)
    repository.add(_look(look_id=1, slug="same-slug", items=[]))
    existing_count = len(repository.looks)
    add_count = repository.added_look_count

    with pytest.raises(AppError) as exc_info:
        await service.create_admin_look(
            LookCreate(
                title="Same",
                slug="same-slug",
                items=[LookItemInput(product_id=1)],
            )
        )

    assert exc_info.value.status_code == 409
    assert len(repository.looks) == existing_count
    assert repository.added_look_count == add_count


@pytest.mark.asyncio
async def test_create_look_slug_conflicting_with_active_look_alias_returns_conflict() -> None:
    service, repository, _cart_repository, session, _storage = _looks_service(
        aliases=[_alias(RouteAliasEntityType.LOOK, entity_id=99, alias_slug="taken-slug")]
    )
    repository.products[1] = _product(product_id=1)

    with pytest.raises(AppError) as exc_info:
        await service.create_admin_look(
            LookCreate(
                title="Taken",
                slug="taken-slug",
                items=[LookItemInput(product_id=1)],
            )
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.message == "Look slug conflicts with an active route alias"
    assert repository.looks == {}
    assert repository.added_look_count == 0
    assert session.commit_count == 0
    assert session.rollback_count == 1


@pytest.mark.asyncio
async def test_update_look_duplicate_slug_returns_conflict() -> None:
    service, repository, _cart_repository, _session, _storage = _looks_service()
    repository.add(_look(look_id=1, slug="first-look"))
    repository.add(_look(look_id=2, slug="second-look"))

    with pytest.raises(AppError) as exc_info:
        await service.update_admin_look(1, LookUpdate(slug="second-look"))

    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_update_look_slug_conflicting_with_active_look_alias_returns_conflict() -> None:
    service, repository, _cart_repository, session, _storage = _looks_service(
        aliases=[_alias(RouteAliasEntityType.LOOK, entity_id=2, alias_slug="taken-slug")]
    )
    repository.add(_look(look_id=1, slug="first-look"))

    with pytest.raises(AppError) as exc_info:
        await service.update_admin_look(1, LookUpdate(slug="taken-slug"))

    assert exc_info.value.status_code == 409
    assert exc_info.value.message == "Look slug conflicts with an active route alias"
    assert repository.looks[1].slug == "first-look"
    assert session.commit_count == 0
    assert session.rollback_count == 1


@pytest.mark.asyncio
async def test_update_look_old_slug_alias_conflict_returns_conflict() -> None:
    service, repository, _cart_repository, session, _storage = _looks_service(
        aliases=[_alias(RouteAliasEntityType.LOOK, entity_id=2, alias_slug="first-look")]
    )
    repository.add(_look(look_id=1, slug="first-look"))

    with pytest.raises(AppError) as exc_info:
        await service.update_admin_look(1, LookUpdate(slug="next-look"))

    assert exc_info.value.status_code == 409
    assert exc_info.value.message == "Look slug conflicts with an active route alias"
    assert repository.looks[1].slug == "first-look"
    assert session.commit_count == 0
    assert session.rollback_count == 1


@pytest.mark.asyncio
async def test_look_slug_integrity_error_returns_conflict() -> None:
    service, repository, _cart_repository, session, _storage = _looks_service()
    repository.products[1] = _product(product_id=1)
    session.commit_error = IntegrityError(
        "INSERT INTO looks",
        {},
        Exception("UNIQUE constraint failed: looks.slug"),
    )

    with pytest.raises(AppError) as exc_info:
        await service.create_admin_look(
            LookCreate(
                title="Race",
                slug="race-slug",
                items=[LookItemInput(product_id=1)],
            )
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.message == "Look slug already exists"
    assert exc_info.value.message != "Database service unavailable"
    assert session.rollback_count == 1


@pytest.mark.asyncio
async def test_look_route_alias_integrity_error_returns_conflict() -> None:
    service, repository, _cart_repository, session, _storage = _looks_service()
    repository.add(_look(look_id=1, slug="first-look"))
    session.commit_error = IntegrityError(
        "INSERT INTO route_aliases",
        {},
        Exception("UNIQUE constraint failed: route_aliases.entity_type, route_aliases.alias_slug"),
    )

    with pytest.raises(AppError) as exc_info:
        await service.update_admin_look(1, LookUpdate(slug="next-look"))

    assert exc_info.value.status_code == 409
    assert exc_info.value.message == "Look slug conflicts with an active route alias"
    assert exc_info.value.message != "Database service unavailable"
    assert session.rollback_count == 1


@pytest.mark.asyncio
async def test_real_database_full_unchanged_patch_preserves_item_ids_and_rows(
    postgres_looks_session: AsyncSession,
) -> None:
    look, _products = await _seed_postgres_look(postgres_looks_session)
    original_ids = _look_item_ids_by_product(look)
    payload = _full_update_payload(look)

    updated = await LooksService(postgres_looks_session).update_admin_look(look.id, payload)

    assert updated.slug == look.slug
    assert {item.product_id: item.id for item in updated.items} == original_ids
    assert [item.position for item in updated.items] == [0, 1, 2]
    assert await _look_item_row_count(postgres_looks_session, look.id) == 3
    assert await _active_look_alias_count(postgres_looks_session, look.id) == 0


@pytest.mark.asyncio
async def test_real_database_title_description_update_preserves_items(
    postgres_looks_session: AsyncSession,
) -> None:
    look, _products = await _seed_postgres_look(postgres_looks_session)
    original_ids = _look_item_ids_by_product(look)

    updated = await LooksService(postgres_looks_session).update_admin_look(
        look.id,
        LookUpdate(title="Updated title", description="Updated description"),
    )

    assert updated.title == "Updated title"
    assert updated.description == "Updated description"
    assert updated.slug == look.slug
    assert {item.product_id: item.id for item in updated.items} == original_ids


@pytest.mark.asyncio
async def test_real_database_draft_to_active_preserves_items(
    postgres_looks_session: AsyncSession,
) -> None:
    look, _products = await _seed_postgres_look(
        postgres_looks_session,
        status_value=LookStatus.DRAFT,
    )
    original_ids = _look_item_ids_by_product(look)

    updated = await LooksService(postgres_looks_session).update_admin_look(
        look.id,
        LookUpdate(status=LookStatus.ACTIVE),
    )

    assert updated.status == LookStatus.ACTIVE
    assert {item.product_id: item.id for item in updated.items} == original_ids


@pytest.mark.asyncio
async def test_real_database_slug_change_creates_resolving_alias_and_preserves_items(
    postgres_looks_session: AsyncSession,
) -> None:
    look, _products = await _seed_postgres_look(
        postgres_looks_session,
        status_value=LookStatus.ACTIVE,
    )
    old_slug = look.slug
    new_slug = f"look-{uuid4().hex}"
    original_ids = _look_item_ids_by_product(look)
    service = LooksService(postgres_looks_session)

    updated = await service.update_admin_look(
        look.id,
        LookUpdate(slug=new_slug, items=_item_inputs(look)),
    )

    assert updated.slug == new_slug
    assert {item.product_id: item.id for item in updated.items} == original_ids
    alias = await service.route_aliases.repository.get_active_by_slug(
        RouteAliasEntityType.LOOK,
        old_slug,
    )
    assert alias is not None
    assert alias.entity_id == look.id
    assert (await service.get_public_look(new_slug)).slug == new_slug
    assert (await service.get_public_look(old_slug)).slug == new_slug


@pytest.mark.asyncio
async def test_real_database_reorder_preserves_item_ids(
    postgres_looks_session: AsyncSession,
) -> None:
    look, _products = await _seed_postgres_look(postgres_looks_session)
    original_ids = _look_item_ids_by_product(look)
    expected_product_ids = [item.product_id for item in reversed(look.items)]
    reversed_items = [
        LookItemInput(
            product_id=item.product_id,
            position=position,
            quantity=item.quantity,
            is_default_selected=item.is_default_selected,
        )
        for position, item in enumerate(reversed(look.items))
    ]

    updated = await LooksService(postgres_looks_session).update_admin_look(
        look.id,
        LookUpdate(items=reversed_items),
    )

    assert [item.product_id for item in updated.items] == expected_product_ids
    assert {item.product_id: item.id for item in updated.items} == original_ids


@pytest.mark.asyncio
async def test_real_database_quantity_and_default_updates_preserve_item_ids(
    postgres_looks_session: AsyncSession,
) -> None:
    look, _products = await _seed_postgres_look(postgres_looks_session)
    original_ids = _look_item_ids_by_product(look)
    inputs = _item_inputs(look)
    inputs[0].quantity = 3
    inputs[0].is_default_selected = False
    inputs[1].is_default_selected = True

    updated = await LooksService(postgres_looks_session).update_admin_look(
        look.id,
        LookUpdate(items=inputs),
    )

    assert updated.items[0].quantity == 3
    assert updated.items[0].is_default_selected is False
    assert updated.items[1].is_default_selected is True
    assert {item.product_id: item.id for item in updated.items} == original_ids


@pytest.mark.asyncio
async def test_real_database_add_product_creates_only_one_item(
    postgres_looks_session: AsyncSession,
) -> None:
    look, products = await _seed_postgres_look(postgres_looks_session)
    original_ids = _look_item_ids_by_product(look)
    inputs = _item_inputs(look)
    inputs.append(
        LookItemInput(
            product_id=products[3].id,
            position=3,
            quantity=2,
            is_default_selected=False,
        )
    )

    updated = await LooksService(postgres_looks_session).update_admin_look(
        look.id,
        LookUpdate(items=inputs),
    )

    assert {item.product_id: item.id for item in updated.items[:3]} == original_ids
    assert len(updated.items) == 4
    assert updated.items[3].product_id == products[3].id
    assert updated.items[3].id not in original_ids.values()
    assert updated.items[3].quantity == 2


@pytest.mark.asyncio
async def test_real_database_remove_product_deletes_only_omitted_item(
    postgres_looks_session: AsyncSession,
) -> None:
    look, _products = await _seed_postgres_look(postgres_looks_session)
    original_ids = _look_item_ids_by_product(look)
    removed_product_id = look.items[1].product_id
    inputs = [item for item in _item_inputs(look) if item.product_id != removed_product_id]

    updated = await LooksService(postgres_looks_session).update_admin_look(
        look.id,
        LookUpdate(items=inputs),
    )

    assert removed_product_id not in {item.product_id for item in updated.items}
    assert {item.product_id: item.id for item in updated.items} == {
        product_id: item_id
        for product_id, item_id in original_ids.items()
        if product_id != removed_product_id
    }
    assert await _look_item_row_count(postgres_looks_session, look.id) == 2


@pytest.mark.asyncio
async def test_real_database_replace_product_preserves_unchanged_rows(
    postgres_looks_session: AsyncSession,
) -> None:
    look, products = await _seed_postgres_look(postgres_looks_session)
    original_ids = _look_item_ids_by_product(look)
    removed_product_id = look.items[1].product_id
    inputs = _item_inputs(look)
    inputs[1] = LookItemInput(
        product_id=products[3].id,
        position=1,
        quantity=2,
        is_default_selected=False,
    )

    updated = await LooksService(postgres_looks_session).update_admin_look(
        look.id,
        LookUpdate(items=inputs),
    )

    updated_ids = {item.product_id: item.id for item in updated.items}
    assert removed_product_id not in updated_ids
    assert updated_ids[products[0].id] == original_ids[products[0].id]
    assert updated_ids[products[2].id] == original_ids[products[2].id]
    assert updated_ids[products[3].id] not in original_ids.values()
    assert await _look_item_row_count(postgres_looks_session, look.id) == 3


@pytest.mark.asyncio
async def test_real_database_duplicate_product_constraint_is_truthfully_mapped_and_rolled_back(
    postgres_looks_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    look, _products = await _seed_postgres_look(postgres_looks_session)
    look_id = look.id
    original_slug = look.slug
    next_slug = f"look-{uuid4().hex}"
    original_title = look.title
    original_ids = _look_item_ids_by_product(look)
    service = LooksService(postgres_looks_session)

    async def add_duplicate_item(
        target: Look,
        _inputs: list[LookItemInput],
        *,
        products_by_id: dict[int, Product],
    ) -> None:
        product_id = target.items[0].product_id
        postgres_looks_session.add(
            LookItem(
                look_id=target.id,
                product_id=product_id,
                product=products_by_id[product_id],
                position=9,
                quantity=1,
                is_default_selected=False,
            )
        )

    monkeypatch.setattr(service, "_synchronize_items", add_duplicate_item)

    with pytest.raises(AppError) as exc_info:
        await service.update_admin_look(
            look.id,
            LookUpdate(
                title="Must roll back",
                slug=next_slug,
                items=_item_inputs(look),
            ),
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.message == "Product is already included in this Look"
    persisted = await service.repository.get_admin_by_id(look_id)
    assert persisted is not None
    assert persisted.title == original_title
    assert persisted.slug == original_slug
    assert _look_item_ids_by_product(persisted) == original_ids
    assert await _look_item_row_count(postgres_looks_session, look_id) == 3
    assert await _active_look_alias_count(postgres_looks_session, look_id) == 0


@pytest.mark.asyncio
async def test_real_database_duplicate_current_slug_and_alias_conflicts_are_distinct(
    postgres_looks_session: AsyncSession,
) -> None:
    first, _products = await _seed_postgres_look(postgres_looks_session)
    second, _products = await _seed_postgres_look(postgres_looks_session)
    first_id = first.id
    second_id = second.id
    second_slug = second.slug
    service = LooksService(postgres_looks_session)

    with pytest.raises(AppError) as slug_error:
        await service.update_admin_look(first_id, LookUpdate(slug=second_slug))
    assert slug_error.value.status_code == 409
    assert slug_error.value.message == "Look slug already exists"

    alias_slug = f"alias-{uuid4().hex}"
    postgres_looks_session.add(
        RouteAlias(
            entity_type=RouteAliasEntityType.LOOK,
            entity_id=second_id,
            alias_slug=alias_slug,
            is_active=True,
        )
    )
    await postgres_looks_session.commit()

    with pytest.raises(AppError) as alias_error:
        await service.update_admin_look(first_id, LookUpdate(slug=alias_slug))
    assert alias_error.value.status_code == 409
    assert alias_error.value.message == "Look slug conflicts with an active route alias"


@pytest.mark.asyncio
async def test_patch_endpoint_with_unchanged_persisted_items_returns_200(
    postgres_looks_session: AsyncSession,
) -> None:
    look, _products = await _seed_postgres_look(postgres_looks_session)
    original_ids = _look_item_ids_by_product(look)
    response = await _patch_look(postgres_looks_session, look, _full_update_payload(look))

    assert response.status_code == 200
    assert {item["product_id"]: item["id"] for item in response.json()["items"]} == original_ids


@pytest.mark.asyncio
async def test_patch_endpoint_duplicate_product_payload_is_validation_error_without_changes(
    postgres_looks_session: AsyncSession,
) -> None:
    look, _products = await _seed_postgres_look(postgres_looks_session)
    original_ids = _look_item_ids_by_product(look)
    duplicate = _item_inputs(look)[0]
    payload = _full_update_payload(look).model_dump(mode="json")
    payload["items"] = [duplicate.model_dump(), duplicate.model_dump()]

    response = await _patch_look(postgres_looks_session, look, payload)

    assert response.status_code == 422
    assert "Product can be added to a Look only once" in str(response.json()["detail"])
    persisted = await LooksService(postgres_looks_session).repository.get_admin_by_id(look.id)
    assert persisted is not None
    assert _look_item_ids_by_product(persisted) == original_ids


def test_unrelated_look_integrity_error_uses_sanitized_persistence_message() -> None:
    error = IntegrityError("unsafe sql", {"secret": "value"}, Exception("foreign key failed"))

    message = LooksService._look_integrity_error_message(
        error,
        fallback_message="Could not update Look",
    )

    assert message == "Could not update Look"
    assert "unsafe" not in message
    assert "secret" not in message


@pytest.mark.asyncio
async def test_generate_look_slugs_starts_at_first_numeric_value() -> None:
    service, _repository, _cart_repository, _session, _storage = _looks_service()

    result = await service.generate_look_slugs(1)

    assert result.items == ["00001"]


@pytest.mark.asyncio
async def test_generate_look_slugs_skips_existing_look_slug() -> None:
    service, repository, _cart_repository, _session, _storage = _looks_service()
    repository.add(_look(look_id=1, slug="00001"))

    result = await service.generate_look_slugs(1)

    assert result.items == ["00002"]


@pytest.mark.asyncio
async def test_generate_look_slugs_ignores_product_slug() -> None:
    service, repository, _cart_repository, _session, _storage = _looks_service()
    product = _product(product_id=2)
    product.slug = "00001"
    repository.products[2] = product

    result = await service.generate_look_slugs(1)

    assert result.items == ["00001"]


@pytest.mark.asyncio
async def test_generate_look_slugs_skips_active_look_route_alias() -> None:
    service, _repository, _cart_repository, _session, _storage = _looks_service(
        aliases=[_alias(RouteAliasEntityType.LOOK, entity_id=1, alias_slug="00001")]
    )

    result = await service.generate_look_slugs(1)

    assert result.items == ["00002"]


@pytest.mark.asyncio
async def test_generate_look_slugs_ignores_inactive_look_route_alias() -> None:
    service, _repository, _cart_repository, _session, _storage = _looks_service(
        aliases=[
            _alias(
                RouteAliasEntityType.LOOK,
                entity_id=1,
                alias_slug="00001",
                is_active=False,
            )
        ]
    )

    result = await service.generate_look_slugs(1)

    assert result.items == ["00001"]


@pytest.mark.asyncio
async def test_generate_look_slugs_ignores_product_and_category_route_aliases() -> None:
    service, _repository, _cart_repository, _session, _storage = _looks_service(
        aliases=[
            _alias(RouteAliasEntityType.PRODUCT, entity_id=1, alias_slug="00001"),
            _alias(RouteAliasEntityType.CATEGORY, entity_id=1, alias_slug="00002"),
        ]
    )

    result = await service.generate_look_slugs(2)

    assert result.items == ["00001", "00002"]


@pytest.mark.asyncio
async def test_generate_look_slugs_returns_multiple_values() -> None:
    service, repository, _cart_repository, _session, _storage = _looks_service(
        aliases=[_alias(RouteAliasEntityType.LOOK, entity_id=1, alias_slug="00002")]
    )
    repository.add(_look(look_id=1, slug="00001"))

    result = await service.generate_look_slugs(3)

    assert result.items == ["00003", "00004", "00005"]


@pytest.mark.asyncio
async def test_generate_look_slugs_reports_exhaustion() -> None:
    service, repository, _cart_repository, _session, _storage = _looks_service()
    repository.list_numeric_slug_candidates = AsyncMock(
        return_value=[f"{value:05d}" for value in range(1, 100000)]
    )

    with pytest.raises(AppError, match="Numeric Look slug range 00001-99999 is exhausted"):
        await service.generate_look_slugs(1)


@pytest.mark.asyncio
async def test_admin_list_includes_draft_archived_and_unlisted_looks() -> None:
    service, repository, _cart_repository, _session, _storage = _looks_service()
    repository.add(_look(look_id=1, slug="draft", status_value=LookStatus.DRAFT))
    repository.add(_look(look_id=2, slug="archived", status_value=LookStatus.ARCHIVED))
    repository.add(_look(look_id=3, slug="unlisted", is_listed=False))

    looks = await service.list_admin_looks(limit=20, offset=0)

    assert {look.slug for look in looks.items} == {"draft", "archived", "unlisted"}


@pytest.mark.asyncio
async def test_public_list_returns_only_active_listed_looks() -> None:
    service, repository, _cart_repository, _session, _storage = _looks_service()
    repository.add(_look(look_id=1, slug="active-listed"))
    repository.add(_look(look_id=2, slug="draft", status_value=LookStatus.DRAFT))
    repository.add(_look(look_id=3, slug="unlisted", is_listed=False))

    looks = await service.list_public_looks(limit=20, offset=0)

    assert [look.slug for look in looks.items] == ["active-listed"]


@pytest.mark.asyncio
async def test_public_detail_includes_hidden_component_product_and_computes_price() -> None:
    service, repository, _cart_repository, _session, _storage = _looks_service()
    product = _product(
        product_id=1,
        is_listed=False,
        base_price=Decimal("100.00"),
        old_price=Decimal("120.00"),
    )
    look = _look(
        look_id=1,
        slug="hidden-component",
        items=[_look_item(item_id=1, look_id=1, product=product, quantity=2)],
    )
    repository.add(look)

    detail = await service.get_public_look("hidden-component")

    assert detail.items[0].product_id == 1
    assert detail.default_price == Decimal("200.00")
    assert detail.old_price == Decimal("240.00")
    assert detail.available_sizes == ["M"]
    assert detail.available_clothing_sizes == ["M"]
    assert detail.available_footwear_sizes == []
    assert detail.requires_clothing_size is True
    assert detail.requires_footwear_size is False
    assert detail.is_available is True


@pytest.mark.asyncio
async def test_look_similar_uses_component_categories_and_tags() -> None:
    service, repository, _cart_repository, _session, _storage = _looks_service()
    hidden_component = _product(
        product_id=1,
        is_listed=False,
        category_ids=[10],
        tag_ids=[7],
    )
    shoes = _product(product_id=2, category_ids=[20], tag_ids=[8])
    same_category = _product(product_id=3, category_ids=[10], tag_ids=[])
    shared_tag = _product(product_id=4, category_ids=[], tag_ids=[8])
    repository.add(
        _look(
            look_id=1,
            slug="similar-look",
            items=[
                _look_item(item_id=1, look_id=1, product=hidden_component),
                _look_item(item_id=2, look_id=1, product=shoes),
            ],
        )
    )
    service.products_service.repository.list_public_similarity_candidates = AsyncMock(
        return_value=[hidden_component, shoes, same_category, shared_tag]
    )

    result = await service.list_similar_products("similar-look")

    assert [item.id for item in result.items] == [3, 4]
    service.products_service.repository.list_public_similarity_candidates.assert_awaited_once_with(
        category_ids={10, 20},
        tag_ids={7, 8},
        exclude_product_ids={1, 2},
    )


@pytest.mark.asyncio
async def test_look_similar_excludes_hidden_standalone_products() -> None:
    service, repository, _cart_repository, _session, _storage = _looks_service()
    component = _product(product_id=1, category_ids=[10], tag_ids=[7])
    hidden_candidate = _product(product_id=2, is_listed=False, category_ids=[10], tag_ids=[7])
    visible_candidate = _product(product_id=3, category_ids=[10], tag_ids=[7])
    repository.add(
        _look(
            look_id=1,
            slug="visibility-look",
            items=[_look_item(item_id=1, look_id=1, product=component)],
        )
    )
    service.products_service.repository.list_public_similarity_candidates = AsyncMock(
        return_value=[hidden_candidate, visible_candidate]
    )

    result = await service.list_similar_products("visibility-look")

    assert [item.id for item in result.items] == [3]


@pytest.mark.asyncio
async def test_look_similar_empty_context_returns_empty_list() -> None:
    service, repository, _cart_repository, _session, _storage = _looks_service()
    component = _product(product_id=1)
    repository.add(
        _look(
            look_id=1,
            slug="empty-similarity",
            items=[_look_item(item_id=1, look_id=1, product=component)],
        )
    )
    service.products_service.repository.list_public_similarity_candidates = AsyncMock(
        return_value=[]
    )

    result = await service.list_similar_products("empty-similarity")

    assert result.items == []
    assert result.meta.total == 0
    service.products_service.repository.list_public_similarity_candidates.assert_not_awaited()


@pytest.mark.asyncio
async def test_public_detail_404_for_draft_or_unlisted_look() -> None:
    service, repository, _cart_repository, _session, _storage = _looks_service()
    repository.add(_look(look_id=1, slug="draft", status_value=LookStatus.DRAFT))
    repository.add(_look(look_id=2, slug="unlisted", is_listed=False))

    with pytest.raises(AppError) as draft_error:
        await service.get_public_look("draft")
    with pytest.raises(AppError) as unlisted_error:
        await service.get_public_look("unlisted")

    assert draft_error.value.status_code == 404
    assert unlisted_error.value.status_code == 404


@pytest.mark.asyncio
async def test_common_sizes_and_one_size_components_are_computed() -> None:
    service, repository, _cart_repository, _session, _storage = _looks_service()
    hoodie = _product(
        product_id=1,
        variants=[
            _variant(variant_id=1, product_id=1, size="M"),
            _variant(variant_id=2, product_id=1, size="L"),
        ],
    )
    pants = _product(
        product_id=2,
        variants=[
            _variant(variant_id=3, product_id=2, size="M"),
            _variant(variant_id=4, product_id=2, size="XL"),
        ],
    )
    bag = _product(
        product_id=3,
        size_group=ProductSizeGroup.ONE_SIZE,
        variants=[_variant(variant_id=5, product_id=3, size="ONE_SIZE")],
    )
    repository.add(
        _look(
            look_id=1,
            slug="common-size",
            items=[
                _look_item(item_id=1, look_id=1, product=hoodie),
                _look_item(item_id=2, look_id=1, product=pants),
                _look_item(item_id=3, look_id=1, product=bag),
            ],
        )
    )

    detail = await service.get_public_look("common-size")

    assert detail.available_sizes == ["M"]
    assert detail.available_clothing_sizes == ["M"]
    assert detail.available_footwear_sizes == []
    assert detail.requires_clothing_size is True
    assert detail.requires_footwear_size is False
    assert detail.items[2].one_size is True
    assert detail.items[2].size_group == ProductSizeGroup.ONE_SIZE


@pytest.mark.asyncio
async def test_look_with_footwear_only_returns_footwear_sizes() -> None:
    service, repository, _cart_repository, _session, _storage = _looks_service()
    shoes = _product(
        product_id=1,
        size_grid=ProductSizeGrid.SHOES_EU,
        size_group=ProductSizeGroup.FOOTWEAR,
        variants=[
            _variant(variant_id=1, product_id=1, size="40"),
            _variant(variant_id=2, product_id=1, size="41"),
        ],
    )
    repository.add(
        _look(
            look_id=1,
            slug="footwear-look",
            items=[_look_item(item_id=1, look_id=1, product=shoes)],
        )
    )

    detail = await service.get_public_look("footwear-look")

    assert detail.available_sizes == ["40", "41"]
    assert detail.available_clothing_sizes == []
    assert detail.available_footwear_sizes == ["40", "41"]
    assert detail.requires_clothing_size is False
    assert detail.requires_footwear_size is True
    assert detail.items[0].size_group == ProductSizeGroup.FOOTWEAR


@pytest.mark.asyncio
async def test_look_with_clothing_and_footwear_returns_groups_separately() -> None:
    service, repository, _cart_repository, _session, _storage = _looks_service()
    hoodie = _product(
        product_id=1,
        variants=[
            _variant(variant_id=1, product_id=1, size="M"),
            _variant(variant_id=2, product_id=1, size="L"),
        ],
    )
    shoes = _product(
        product_id=2,
        size_grid=ProductSizeGrid.SHOES_EU,
        size_group=ProductSizeGroup.FOOTWEAR,
        variants=[
            _variant(variant_id=3, product_id=2, size="40"),
            _variant(variant_id=4, product_id=2, size="41"),
        ],
    )
    repository.add(
        _look(
            look_id=1,
            slug="mixed-look",
            items=[
                _look_item(item_id=1, look_id=1, product=hoodie),
                _look_item(item_id=2, look_id=1, product=shoes),
            ],
        )
    )

    detail = await service.get_public_look("mixed-look")

    assert detail.available_sizes == ["L", "M"]
    assert detail.available_clothing_sizes == ["L", "M"]
    assert detail.available_footwear_sizes == ["40", "41"]
    assert detail.requires_clothing_size is True
    assert detail.requires_footwear_size is True
    assert detail.is_available is True


@pytest.mark.asyncio
async def test_no_common_size_marks_look_unavailable() -> None:
    service, repository, _cart_repository, _session, _storage = _looks_service()
    hoodie = _product(product_id=1, variants=[_variant(variant_id=1, product_id=1, size="S")])
    pants = _product(product_id=2, variants=[_variant(variant_id=2, product_id=2, size="M")])
    repository.add(
        _look(
            look_id=1,
            slug="no-common-size",
            items=[
                _look_item(item_id=1, look_id=1, product=hoodie),
                _look_item(item_id=2, look_id=1, product=pants),
            ],
        )
    )

    detail = await service.get_public_look("no-common-size")

    assert detail.available_sizes == []
    assert detail.available_clothing_sizes == []
    assert detail.available_footwear_sizes == []
    assert detail.is_available is False


@pytest.mark.asyncio
async def test_add_look_to_cart_adds_selected_items_atomically() -> None:
    service, repository, cart_repository, _session, _storage = _looks_service()
    hoodie = _product(product_id=1, is_listed=False)
    pants = _product(product_id=2, variants=[_variant(variant_id=2, product_id=2, size="M")])
    repository.products = {1: hoodie, 2: pants}
    cart_repository.products = repository.products
    cart_repository.variants = {1: hoodie.variants[0], 2: pants.variants[0]}
    repository.add(
        _look(
            look_id=1,
            slug="cart-look",
            items=[
                _look_item(item_id=1, look_id=1, product=hoodie),
                _look_item(item_id=2, look_id=1, product=pants),
            ],
        )
    )

    response = await service.add_look_to_cart(
        slug="cart-look",
        user_id=1,
        payload=LookCartAddRequest(selected_item_ids=[1, 2], size="M"),
    )

    assert response.cart.quantity_total == 2
    assert {item.product.id for item in response.cart.items} == {1, 2}
    assert {item.source_type for item in response.cart.items} == {"LOOK"}
    assert {item.source_look_id for item in response.cart.items} == {1}
    assert {item.source_look_slug for item in response.cart.items} == {"cart-look"}
    assert {item.source_look_title for item in response.cart.items} == {"Cart Look"}
    group_ids = {item.source_group_id for item in response.cart.items}
    assert len(group_ids) == 1
    assert None not in group_ids


@pytest.mark.asyncio
async def test_add_look_to_cart_clothing_and_footwear_uses_separate_sizes() -> None:
    service, repository, cart_repository, _session, _storage = _looks_service()
    hoodie = _product(
        product_id=1,
        variants=[
            _variant(variant_id=1, product_id=1, size="M"),
            _variant(variant_id=2, product_id=1, size="L"),
        ],
    )
    shoes = _product(
        product_id=2,
        size_grid=ProductSizeGrid.SHOES_EU,
        size_group=ProductSizeGroup.FOOTWEAR,
        variants=[
            _variant(variant_id=3, product_id=2, size="41"),
            _variant(variant_id=4, product_id=2, size="42"),
        ],
    )
    repository.products = {1: hoodie, 2: shoes}
    cart_repository.products = repository.products
    cart_repository.variants = {
        variant.id: variant
        for product in repository.products.values()
        for variant in product.variants
    }
    repository.add(
        _look(
            look_id=1,
            slug="mixed-cart-look",
            items=[
                _look_item(item_id=1, look_id=1, product=hoodie),
                _look_item(item_id=2, look_id=1, product=shoes),
            ],
        )
    )

    response = await service.add_look_to_cart(
        slug="mixed-cart-look",
        user_id=1,
        payload=LookCartAddRequest(
            selected_item_ids=[1, 2],
            clothing_size="M",
            footwear_size="42",
        ),
    )

    assert {item.product_variant.size for item in response.cart.items} == {"M", "42"}


@pytest.mark.asyncio
async def test_add_look_to_cart_rejects_ambiguous_legacy_size_for_mixed_groups() -> None:
    service, repository, _cart_repository, _session, _storage = _looks_service()
    hoodie = _product(product_id=1)
    shoes = _product(
        product_id=2,
        size_grid=ProductSizeGrid.SHOES_EU,
        size_group=ProductSizeGroup.FOOTWEAR,
        variants=[_variant(variant_id=2, product_id=2, size="42")],
    )
    repository.add(
        _look(
            look_id=1,
            slug="mixed-legacy-size",
            items=[
                _look_item(item_id=1, look_id=1, product=hoodie),
                _look_item(item_id=2, look_id=1, product=shoes),
            ],
        )
    )

    with pytest.raises(AppError) as exc_info:
        await service.add_look_to_cart(
            slug="mixed-legacy-size",
            user_id=1,
            payload=LookCartAddRequest(selected_item_ids=[1, 2], size="M"),
        )

    assert exc_info.value.message == "Выберите размер одежды"


@pytest.mark.asyncio
async def test_add_look_to_cart_snapshots_look_image() -> None:
    service, repository, cart_repository, _session, _storage = _looks_service()
    look = _look(look_id=1, slug="image-look")
    look.images = [
        LookImage(
            id=1,
            look_id=1,
            file_path="looks/image-look.webp",
            original_filename="image-look.webp",
            mime_type="image/webp",
            size_bytes=120,
            alt_text="Image look",
            position=0,
            is_primary=True,
            created_at=NOW,
        )
    ]
    repository.add(look)

    response = await service.add_look_to_cart(
        slug="image-look",
        user_id=1,
        payload=LookCartAddRequest(selected_item_ids=[1], size="M"),
    )

    assert response.cart.items[0].source_look_image_url == "/uploads/looks/image-look.webp"


@pytest.mark.asyncio
async def test_separate_look_add_to_cart_calls_use_distinct_groups_without_merging() -> None:
    service, repository, _cart_repository, _session, _storage = _looks_service()
    repository.add(_look(look_id=1, slug="repeat-look"))

    first = await service.add_look_to_cart(
        slug="repeat-look",
        user_id=1,
        payload=LookCartAddRequest(selected_item_ids=[1], size="M"),
    )
    second = await service.add_look_to_cart(
        slug="repeat-look",
        user_id=1,
        payload=LookCartAddRequest(selected_item_ids=[1], size="M"),
    )

    assert first.cart.items[0].source_group_id != second.cart.items[1].source_group_id
    assert len(second.cart.items) == 2
    assert [item.quantity for item in second.cart.items] == [1, 1]


@pytest.mark.asyncio
async def test_look_cart_items_do_not_merge_with_normal_cart_items_for_same_variant() -> None:
    service, repository, cart_repository, _session, _storage = _looks_service()
    product = repository.products[1]
    variant = product.variants[0]
    normal_cart = Cart(id=1, user_id=1, created_at=NOW, updated_at=NOW)
    normal_cart.items = [
        CartItem(
            id=1,
            cart_id=1,
            product_id=product.id,
            product_variant_id=variant.id,
            product=product,
            product_variant=variant,
            quantity=1,
            is_selected=True,
            created_at=NOW,
            updated_at=NOW,
        )
    ]
    cart_repository.carts[1] = normal_cart
    cart_repository.next_cart_id = 2
    cart_repository.next_item_id = 2
    repository.add(_look(look_id=1, slug="same-variant-look"))

    response = await service.add_look_to_cart(
        slug="same-variant-look",
        user_id=1,
        payload=LookCartAddRequest(selected_item_ids=[1], size="M"),
    )

    assert len(response.cart.items) == 2
    assert response.cart.items[0].source_type is None
    assert response.cart.items[1].source_type == "LOOK"
    assert response.cart.items[1].source_group_id is not None


@pytest.mark.asyncio
async def test_add_look_to_cart_rejects_missing_size_for_clothing() -> None:
    service, repository, _cart_repository, _session, _storage = _looks_service()
    repository.add(_look(look_id=1, slug="needs-size"))

    with pytest.raises(AppError) as exc_info:
        await service.add_look_to_cart(
            slug="needs-size",
            user_id=1,
            payload=LookCartAddRequest(selected_item_ids=[1]),
        )

    assert exc_info.value.message == "Выберите размер одежды"


@pytest.mark.asyncio
async def test_add_look_to_cart_rejects_missing_footwear_size() -> None:
    service, repository, _cart_repository, _session, _storage = _looks_service()
    shoes = _product(
        product_id=1,
        size_grid=ProductSizeGrid.SHOES_EU,
        size_group=ProductSizeGroup.FOOTWEAR,
        variants=[_variant(variant_id=1, product_id=1, size="42")],
    )
    repository.add(
        _look(
            look_id=1,
            slug="needs-shoe-size",
            items=[_look_item(item_id=1, look_id=1, product=shoes)],
        )
    )

    with pytest.raises(AppError) as exc_info:
        await service.add_look_to_cart(
            slug="needs-shoe-size",
            user_id=1,
            payload=LookCartAddRequest(selected_item_ids=[1]),
        )

    assert exc_info.value.message == "Выберите размер обуви"


@pytest.mark.asyncio
async def test_add_look_to_cart_footwear_only_accepts_legacy_size() -> None:
    service, repository, cart_repository, _session, _storage = _looks_service()
    shoes = _product(
        product_id=1,
        size_grid=ProductSizeGrid.SHOES_EU,
        size_group=ProductSizeGroup.FOOTWEAR,
        variants=[_variant(variant_id=1, product_id=1, size="42")],
    )
    repository.products = {1: shoes}
    cart_repository.products = repository.products
    cart_repository.variants = {1: shoes.variants[0]}
    repository.add(
        _look(
            look_id=1,
            slug="shoe-look",
            items=[_look_item(item_id=1, look_id=1, product=shoes)],
        )
    )

    response = await service.add_look_to_cart(
        slug="shoe-look",
        user_id=1,
        payload=LookCartAddRequest(selected_item_ids=[1], size="42"),
    )

    assert response.cart.items[0].product_variant.size == "42"


@pytest.mark.asyncio
async def test_add_look_to_cart_rejects_unavailable_group_size() -> None:
    service, repository, _cart_repository, _session, _storage = _looks_service()
    repository.add(_look(look_id=1, slug="unavailable-size"))

    with pytest.raises(AppError) as exc_info:
        await service.add_look_to_cart(
            slug="unavailable-size",
            user_id=1,
            payload=LookCartAddRequest(selected_item_ids=[1], clothing_size="XL"),
        )

    assert exc_info.value.message == "Выбранный размер одежды недоступен"


@pytest.mark.asyncio
async def test_one_size_only_look_can_add_without_size() -> None:
    service, repository, cart_repository, _session, _storage = _looks_service()
    bag = _product(
        product_id=1,
        size_group=ProductSizeGroup.ONE_SIZE,
        variants=[_variant(variant_id=1, product_id=1, size="ONE_SIZE")],
    )
    repository.products = {1: bag}
    cart_repository.products = repository.products
    cart_repository.variants = {1: bag.variants[0]}
    repository.add(
        _look(
            look_id=1,
            slug="bag-look",
            items=[_look_item(item_id=1, look_id=1, product=bag)],
        )
    )

    response = await service.add_look_to_cart(
        slug="bag-look",
        user_id=1,
        payload=LookCartAddRequest(selected_item_ids=[1]),
    )

    assert response.cart.quantity_total == 1
    assert response.cart.items[0].product_variant.size == "ONE_SIZE"


@pytest.mark.asyncio
async def test_add_look_to_cart_rejects_item_not_in_look() -> None:
    service, repository, _cart_repository, _session, _storage = _looks_service()
    repository.add(_look(look_id=1, slug="bad-item"))

    with pytest.raises(AppError) as exc_info:
        await service.add_look_to_cart(
            slug="bad-item",
            user_id=1,
            payload=LookCartAddRequest(selected_item_ids=[999], size="M"),
        )

    assert exc_info.value.message == "Selected look item does not belong to this Look"


@pytest.mark.asyncio
async def test_add_look_to_cart_is_atomic_when_component_has_insufficient_stock() -> None:
    service, repository, cart_repository, session, _storage = _looks_service()
    hoodie = _product(product_id=1)
    pants = _product(
        product_id=2,
        variants=[_variant(variant_id=2, product_id=2, size="M", stock_quantity=0)],
    )
    repository.products = {1: hoodie, 2: pants}
    cart_repository.products = repository.products
    cart_repository.variants = {1: hoodie.variants[0], 2: pants.variants[0]}
    repository.add(
        _look(
            look_id=1,
            slug="atomic-look",
            items=[
                _look_item(item_id=1, look_id=1, product=hoodie),
                _look_item(item_id=2, look_id=1, product=pants),
            ],
        )
    )

    with pytest.raises(AppError) as exc_info:
        await service.add_look_to_cart(
            slug="atomic-look",
            user_id=1,
            payload=LookCartAddRequest(selected_item_ids=[1, 2], size="M"),
        )

    assert exc_info.value.message == "Выбранный размер одежды недоступен"
    assert cart_repository.carts == {}
    assert session.commit_count == 0


@pytest.mark.asyncio
async def test_upload_and_delete_look_image() -> None:
    service, repository, _cart_repository, _session, storage = _looks_service()
    repository.add(_look(look_id=1, slug="with-image", items=[]))

    image = await service.upload_image(
        look_id=1,
        file=_upload_file("look.jpg", _image_bytes(), "image/jpeg"),
        alt_text="Look",
        is_primary=True,
    )

    assert image.file_path.startswith("looks/")
    assert image.is_primary is True
    assert image.file_path in storage.saved

    await service.delete_image(look_id=1, image_id=image.id)

    assert image.file_path in storage.deleted
    assert repository.looks[1].images == []


def test_empty_selected_item_ids_payload_is_invalid() -> None:
    with pytest.raises(ValueError):
        LookCartAddRequest(selected_item_ids=[])


def test_regular_user_cannot_access_admin_look_endpoints() -> None:
    app = create_app()

    async def current_user() -> User:
        return _user(UserRole.USER)

    app.dependency_overrides[get_current_user] = current_user
    app.dependency_overrides[get_looks_service] = lambda: object()
    try:
        response = TestClient(app).post(
            "/api/v1/looks/admin",
            json={"title": "Look", "slug": "look"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_look_slug_generation_allows_seller() -> None:
    app = create_app()

    class FakeLooksService:
        async def generate_look_slugs(self, count: int) -> dict[str, object]:
            assert count == 2
            return {"items": ["00001", "00002"]}

    app.dependency_overrides[get_current_user] = lambda: _user(UserRole.SELLER)
    app.dependency_overrides[get_looks_service] = lambda: FakeLooksService()
    try:
        response = TestClient(app).get("/api/v1/looks/admin/slugs/next?count=2")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"items": ["00001", "00002"]}


def test_public_look_similar_products_route_allows_anonymous_access() -> None:
    app = create_app()

    class FakeLooksService:
        async def list_similar_products(self, slug: str, *, limit: int) -> dict[str, object]:
            assert slug == "summer-look"
            assert limit == 2
            return {
                "items": [_product_card_payload(product_id=2, slug="similar-hoodie")],
                "meta": {"limit": 2, "offset": 0, "total": 1},
            }

    app.dependency_overrides[get_looks_service] = lambda: FakeLooksService()
    try:
        response = TestClient(app).get("/api/v1/looks/summer-look/similar-products?limit=2")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["items"][0]["slug"] == "similar-hoodie"
    assert response.json()["meta"] == {"limit": 2, "offset": 0, "total": 1}


def test_look_slug_generation_rejects_invalid_count() -> None:
    app = create_app()

    class FakeLooksService:
        async def generate_look_slugs(self, count: int) -> dict[str, object]:
            return {"items": [f"{count:05d}"]}

    app.dependency_overrides[get_current_user] = lambda: _user(UserRole.SELLER)
    app.dependency_overrides[get_looks_service] = lambda: FakeLooksService()
    try:
        response = TestClient(app).get("/api/v1/looks/admin/slugs/next?count=0")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_look_slug_generation_requires_seller_or_admin() -> None:
    app = create_app()
    with TestClient(app) as client:
        unauthenticated = client.get("/api/v1/looks/admin/slugs/next")

    app.dependency_overrides[get_current_user] = lambda: _user(UserRole.USER)
    app.dependency_overrides[get_looks_service] = lambda: object()
    try:
        regular_user = TestClient(app).get("/api/v1/looks/admin/slugs/next")
    finally:
        app.dependency_overrides.clear()

    assert unauthenticated.status_code == 401
    assert regular_user.status_code == 403


@pytest.fixture
async def postgres_looks_session() -> AsyncGenerator[AsyncSession, None]:
    database_url = os.getenv("LOOKS_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("set LOOKS_TEST_DATABASE_URL to run PostgreSQL Look regression tests")

    engine = create_async_engine(database_url)
    connection = await engine.connect()
    transaction = await connection.begin()
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        async with session_factory() as session:
            yield session
    finally:
        if transaction.is_active:
            await transaction.rollback()
        await connection.close()
        await engine.dispose()


async def _seed_postgres_look(
    session: AsyncSession,
    *,
    status_value: LookStatus = LookStatus.DRAFT,
) -> tuple[Look, list[Product]]:
    prefix = uuid4().hex
    id_base = int(prefix[:7], 16)
    products = [
        _product(
            product_id=id_base + index,
            variants=[
                _variant(
                    variant_id=id_base + index,
                    product_id=id_base + index,
                    size="M",
                )
            ],
        )
        for index in range(1, 5)
    ]
    look = Look(
        slug=f"look-{prefix}",
        title="Persisted Look",
        description="Persisted description",
        status=status_value,
        is_listed=True,
        search_priority=1,
        items=[
            LookItem(
                product=product,
                position=position,
                quantity=position + 1,
                is_default_selected=position != 1,
            )
            for position, product in enumerate(products[:3])
        ],
    )
    session.add_all([*products, look])
    await session.commit()

    persisted = await LooksService(session).repository.get_admin_by_id(look.id)
    assert persisted is not None
    return persisted, products


def _item_inputs(look: Look) -> list[LookItemInput]:
    return [
        LookItemInput(
            product_id=item.product_id,
            position=item.position,
            quantity=item.quantity,
            is_default_selected=item.is_default_selected,
        )
        for item in look.items
    ]


def _full_update_payload(look: Look) -> LookUpdate:
    return LookUpdate(
        title=look.title,
        slug=look.slug,
        description=look.description,
        status=look.status,
        is_listed=look.is_listed,
        search_priority=look.search_priority,
        items=_item_inputs(look),
    )


def _look_item_ids_by_product(look: Look) -> dict[int, int]:
    return {item.product_id: item.id for item in look.items}


async def _look_item_row_count(session: AsyncSession, look_id: int) -> int:
    result = await session.execute(
        select(func.count()).select_from(LookItem).where(LookItem.look_id == look_id)
    )
    return int(result.scalar_one())


async def _active_look_alias_count(session: AsyncSession, look_id: int) -> int:
    result = await session.execute(
        select(func.count())
        .select_from(RouteAlias)
        .where(
            RouteAlias.entity_type == RouteAliasEntityType.LOOK,
            RouteAlias.entity_id == look_id,
            RouteAlias.is_active.is_(True),
        )
    )
    return int(result.scalar_one())


async def _patch_look(
    session: AsyncSession,
    look: Look,
    payload: LookUpdate | dict[str, object],
) -> Response:
    app = create_app()

    async def current_user() -> User:
        return _user(UserRole.SELLER)

    async def database_session() -> AsyncGenerator[AsyncSession, None]:
        yield session

    app.dependency_overrides[get_current_user] = current_user
    app.dependency_overrides[get_db_session] = database_session
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            return await client.patch(
                f"/api/v1/looks/admin/{look.id}",
                json=payload.model_dump(mode="json")
                if isinstance(payload, LookUpdate)
                else payload,
            )
    finally:
        app.dependency_overrides.clear()


def _looks_service_with_aliases(
    aliases: list[RouteAlias] | None = None,
) -> tuple[
    LooksService,
    FakeLooksRepository,
    FakeCartRepository,
    DummySession,
    FakeStorage,
]:
    session = DummySession()
    storage = FakeStorage()
    service = LooksService(session, storage=storage)
    repository = FakeLooksRepository()
    product = _product(product_id=1)
    repository.products[1] = product
    cart_repository = FakeCartRepository(repository.products)
    service.repository = repository  # type: ignore[assignment]
    service.cart_repository = cart_repository  # type: ignore[assignment]
    service.route_aliases.repository = FakeRouteAliasRepository(aliases)  # type: ignore[assignment]
    return service, repository, cart_repository, session, storage


def _looks_service(
    *,
    aliases: list[RouteAlias] | None = None,
) -> tuple[
    LooksService,
    FakeLooksRepository,
    FakeCartRepository,
    DummySession,
    FakeStorage,
]:
    return _looks_service_with_aliases(aliases)


def _look(
    *,
    look_id: int,
    slug: str,
    status_value: LookStatus = LookStatus.ACTIVE,
    is_listed: bool = True,
    items: list[LookItem] | None = None,
) -> Look:
    product = _product(product_id=1)
    return Look(
        id=look_id,
        title=slug.replace("-", " ").title(),
        slug=slug,
        description=None,
        status=status_value,
        is_listed=is_listed,
        search_priority=1,
        images=[],
        items=items
        if items is not None
        else [_look_item(item_id=1, look_id=look_id, product=product)],
        created_at=NOW,
        updated_at=NOW,
    )


def _look_item(
    *,
    item_id: int,
    look_id: int,
    product: Product,
    quantity: int = 1,
    is_default_selected: bool = True,
) -> LookItem:
    return LookItem(
        id=item_id,
        look_id=look_id,
        product_id=product.id,
        product=product,
        position=item_id,
        quantity=quantity,
        is_default_selected=is_default_selected,
        created_at=NOW,
        updated_at=NOW,
    )


def _product(
    *,
    product_id: int,
    status_value: ProductStatus = ProductStatus.ACTIVE,
    is_listed: bool = True,
    base_price: Decimal = Decimal("59.90"),
    old_price: Decimal | None = None,
    variants: list[ProductVariant] | None = None,
    size_grid: ProductSizeGrid = ProductSizeGrid.CLOTHING_ALPHA,
    size_group: ProductSizeGroup = ProductSizeGroup.CLOTHING,
    category_ids: list[int] | None = None,
    tag_ids: list[int] | None = None,
    search_priority: int = 2,
    created_at: datetime = NOW,
) -> Product:
    normalized_category_ids = category_ids or []
    product = Product(
        id=product_id,
        name=f"Product {product_id}",
        slug=f"product-{product_id}",
        brand="ICON",
        description="Product description",
        base_price=base_price,
        old_price=old_price,
        search_priority=search_priority,
        size_grid=size_grid,
        size_group=size_group,
        image_badge_type=ProductImageBadgeType.NONE,
        image_badge_text=None,
        image_badge_color=None,
        image_badge_position=None,
        status=status_value,
        is_listed=is_listed,
        is_returnable=True,
        category_id=normalized_category_ids[0] if normalized_category_ids else None,
        category=_category(normalized_category_ids[0]) if normalized_category_ids else None,
        product_categories=[
            ProductCategory(
                product_id=product_id,
                category_id=category_id,
                priority=index + 1,
                category=_category(category_id),
            )
            for index, category_id in enumerate(normalized_category_ids[:3])
        ],
        tags=[_tag(tag_id) for tag_id in tag_ids or []],
        images=[],
        variants=variants or [_variant(variant_id=product_id, product_id=product_id, size="M")],
        created_at=created_at,
        updated_at=created_at,
    )
    for variant in product.variants:
        variant.product = product
    return product


def _variant(
    *,
    variant_id: int,
    product_id: int,
    size: str,
    color: str | None = "Black",
    stock_quantity: int = 5,
    reserved_quantity: int = 0,
    is_active: bool = True,
) -> ProductVariant:
    return ProductVariant(
        id=variant_id,
        product_id=product_id,
        size=size,
        color=color,
        sku=f"SKU-{variant_id}",
        stock_quantity=stock_quantity,
        reserved_quantity=reserved_quantity,
        is_active=is_active,
        created_at=NOW,
        updated_at=NOW,
    )


def _category(category_id: int) -> Category:
    return Category(
        id=category_id,
        name=f"Category {category_id}",
        slug=f"category-{category_id}",
        description=None,
        created_at=NOW,
        updated_at=NOW,
    )


def _tag(tag_id: int) -> Tag:
    return Tag(
        id=tag_id,
        name=f"Tag {tag_id}",
        slug=f"tag-{tag_id}",
        created_at=NOW,
        updated_at=NOW,
    )


def _product_card_payload(*, product_id: int, slug: str) -> dict[str, object]:
    return {
        "id": product_id,
        "name": slug.replace("-", " ").title(),
        "slug": slug,
        "brand": "ICON",
        "base_price": "59.90",
        "old_price": None,
        "size_grid": "clothing_alpha",
        "size_group": "CLOTHING",
        "image_badge_type": "none",
        "image_badge_text": None,
        "image_badge_color": None,
        "image_badge_position": None,
        "image_url": None,
        "thumbnail_image_url": None,
        "variants": [],
        "is_available": False,
        "created_at": NOW.isoformat(),
    }


def _alias(
    entity_type: RouteAliasEntityType,
    *,
    entity_id: int,
    alias_slug: str,
    is_active: bool = True,
) -> RouteAlias:
    return RouteAlias(
        entity_type=entity_type,
        entity_id=entity_id,
        alias_slug=alias_slug,
        is_active=is_active,
        created_at=NOW,
        updated_at=NOW,
    )


def _user(role: UserRole) -> User:
    return User(
        id=1,
        telegram_id=1001,
        role=role,
        is_active=True,
        created_at=NOW,
        updated_at=NOW,
    )


def _upload_file(filename: str, content: bytes, mime_type: str) -> UploadFile:
    return UploadFile(
        filename=filename,
        file=BytesIO(content),
        headers=Headers({"content-type": mime_type}),
    )


def _image_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (800, 1000), color=(20, 20, 20)).save(buffer, format="JPEG")
    return buffer.getvalue()
