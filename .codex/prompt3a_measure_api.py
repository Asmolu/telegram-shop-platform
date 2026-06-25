import argparse
import asyncio
import gzip
import json
import os
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.models import (
    Banner,
    BannerDisplayType,
    Category,
    Favorite,
    Product,
    ProductCategory,
    ProductImage,
    ProductImageBadgeColor,
    ProductImageBadgePosition,
    ProductImageBadgeType,
    ProductRelatedProduct,
    ProductSizeGrid,
    ProductStatus,
    ProductVariant,
    Tag,
    User,
)
from app.modules.favorites.service import FavoritesService
from app.modules.products.service import ProductsService


@dataclass
class QueryCounter:
    count: int = 0


@contextmanager
def count_queries(engine: Any):
    counter = QueryCounter()

    def before_cursor_execute(*_: Any) -> None:
        counter.count += 1

    event.listen(engine.sync_engine, "before_cursor_execute", before_cursor_execute)
    try:
        yield counter
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", before_cursor_execute)


def model_json_bytes(model: Any) -> bytes:
    if hasattr(model, "model_dump_json"):
        return model.model_dump_json().encode("utf-8")
    return json.dumps(model, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def analyze_payload(payload: bytes) -> dict[str, Any]:
    data = json.loads(payload)
    items = data.get("items") if isinstance(data, dict) else None
    result: dict[str, Any] = {
        "json_bytes": len(payload),
        "gzip_bytes": len(gzip.compress(payload)),
    }
    if isinstance(items, list):
        result["item_count"] = len(items)
        result["avg_bytes_per_item"] = round(len(payload) / max(len(items), 1), 2)
        result["fields"] = sorted(items[0].keys()) if items else []
        result["field_bytes"] = field_bytes(items)
        result["image_count_first_item"] = len(items[0].get("images", [])) if items else 0
        result["variant_count_first_item"] = len(items[0].get("variants", [])) if items else 0
    elif isinstance(data, dict):
        result["fields"] = sorted(data.keys())
    return result


def field_bytes(items: list[dict[str, Any]]) -> dict[str, int]:
    fields: dict[str, int] = {}
    for item in items:
        for key, value in item.items():
            fields[key] = fields.get(key, 0) + len(
                json.dumps({key: value}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            )
    return dict(sorted(fields.items(), key=lambda pair: pair[0]))


async def seed_dataset(session_factory: async_sessionmaker[Any]) -> dict[str, int]:
    async with session_factory() as session:
        existing = await session.scalar(select(func.count(Product.id)))
        if existing:
            category = await session.scalar(select(Category).order_by(Category.id).limit(1))
            user = await session.scalar(select(User).order_by(User.id).limit(1))
            first_product = await session.scalar(
                select(Product).where(Product.status == ProductStatus.ACTIVE).order_by(Product.id)
            )
            return {
                "category_id": category.id if category else 0,
                "user_id": user.id if user else 0,
                "product_id": first_product.id if first_product else 0,
            }

        categories = [
            Category(
                name=f"Category {index}",
                slug=f"category-{index}",
                description=f"Category {index} description",
                image_path=f"categories/{index:032x}.jpg",
            )
            for index in range(1, 5)
        ]
        tags = [
            Tag(name=f"Tag {index}", slug=f"tag-{index}", image_path=f"tags/{index:032x}.jpg")
            for index in range(1, 5)
        ]
        session.add_all(categories + tags)
        user = User(telegram_id=9_000_001, username="prompt3a")
        session.add(user)
        await session.flush()

        products: list[Product] = []
        base_time = datetime(2026, 6, 24, 12, 0, tzinfo=UTC)
        for index in range(1, 51):
            status = ProductStatus.ACTIVE
            if index in {46, 47}:
                status = ProductStatus.ARCHIVED
            elif index in {48, 49, 50}:
                status = ProductStatus.DRAFT

            product = Product(
                name=f"Hoodie Product {index:02d}",
                slug=f"hoodie-product-{index:02d}",
                brand="MENS STYLE" if index % 3 else "Prompt Brand",
                description=(
                    "Long public product description with fabric, care, fit and styling notes. "
                    f"Synthetic item {index}."
                ),
                base_price=Decimal("1000.00") + Decimal(index),
                old_price=Decimal("1300.00") + Decimal(index) if index % 4 == 0 else None,
                search_priority=(index % 3) + 1,
                search_aliases=f"hoodie prompt alias {index}",
                size_grid=ProductSizeGrid.SHOES_EU if index % 10 == 0 else ProductSizeGrid.CLOTHING_ALPHA,
                image_badge_type=ProductImageBadgeType.SALE if index % 4 == 0 else ProductImageBadgeType.NONE,
                image_badge_text=None,
                image_badge_color=ProductImageBadgeColor.RED if index % 4 == 0 else None,
                image_badge_position=(
                    ProductImageBadgePosition.BOTTOM_LEFT if index % 4 == 0 else None
                ),
                status=status,
                category_id=categories[index % len(categories)].id,
                created_at=base_time - timedelta(minutes=index // 2),
                updated_at=base_time + timedelta(minutes=index),
            )
            product.tags.extend([tags[index % len(tags)], tags[(index + 1) % len(tags)]])
            product.product_categories.extend(
                [
                    ProductCategory(category_id=categories[index % len(categories)].id, priority=1),
                    ProductCategory(
                        category_id=categories[(index + 1) % len(categories)].id,
                        priority=2,
                    ),
                ]
            )

            has_derivatives = index % 5 != 0
            product.images.append(
                ProductImage(
                    file_path=f"products/product-{index:02d}.jpg",
                    thumbnail_path=(
                        f"products/product-{index:02d}.thumbnail.webp" if has_derivatives else None
                    ),
                    card_path=f"products/product-{index:02d}.card.webp" if has_derivatives else None,
                    detail_path=(
                        f"products/product-{index:02d}.detail.webp" if has_derivatives else None
                    ),
                    alt_text=f"Hoodie Product {index:02d}",
                    position=0,
                    is_primary=True,
                    original_filename=f"product-{index:02d}.jpg",
                    mime_type="image/jpeg",
                    size_bytes=1_200_000 + index,
                )
            )
            if index % 7 == 0:
                product.images.append(
                    ProductImage(
                        file_path=f"products/product-{index:02d}-alt.jpg",
                        card_path=f"products/product-{index:02d}-alt.card.webp",
                        detail_path=f"products/product-{index:02d}-alt.detail.webp",
                        alt_text=f"Hoodie Product {index:02d} alternate",
                        position=1,
                        is_primary=False,
                        original_filename=f"product-{index:02d}-alt.jpg",
                        mime_type="image/jpeg",
                        size_bytes=1_000_000 + index,
                    )
                )

            sizes = ["S", "M", "L"] if product.size_grid == ProductSizeGrid.CLOTHING_ALPHA else ["40", "41", "42"]
            for variant_index, size in enumerate(sizes):
                out_of_stock = index in {8, 16, 24} or variant_index == 2 and index % 6 == 0
                product.variants.append(
                    ProductVariant(
                        size=size,
                        color="black" if variant_index % 2 == 0 else "white",
                        sku=f"SKU-{index:02d}-{variant_index}",
                        stock_quantity=0 if out_of_stock else 10 + variant_index,
                        reserved_quantity=0 if out_of_stock else variant_index,
                        is_active=variant_index != 2 or index % 9 != 0,
                    )
                )
            products.append(product)

        session.add_all(products)
        await session.flush()

        active_products = [product for product in products if product.status == ProductStatus.ACTIVE]
        related_links: list[ProductRelatedProduct] = []
        for index, product in enumerate(active_products[:12]):
            related_links.extend(
                (
                    ProductRelatedProduct(
                        product_id=product.id,
                        related_product_id=active_products[(index + 1) % len(active_products)].id,
                        position=0,
                    ),
                    ProductRelatedProduct(
                        product_id=product.id,
                        related_product_id=active_products[(index + 2) % len(active_products)].id,
                        position=1,
                    ),
                )
            )
        session.add_all(related_links)

        session.add_all(
            Favorite(user_id=user.id, product_id=product.id)
            for product in active_products[:10]
        )
        session.add_all(
            Banner(
                title=f"Banner {index}",
                subtitle=f"Banner subtitle {index}",
                file_path=f"banners/banner-{index}.jpg",
                original_filename=f"banner-{index}.jpg",
                mime_type="image/jpeg",
                size_bytes=500_000 + index,
                alt_text=f"Banner {index}",
                target_type="product",
                target_id=active_products[index].id,
                display_type=BannerDisplayType.HORIZONTAL,
                position=index,
                is_active=True,
            )
            for index in range(3)
        )

        await session.commit()
        return {
            "category_id": categories[0].id,
            "user_id": user.id,
            "product_id": active_products[0].id,
        }


async def measure_operation(
    engine: Any,
    session_factory: async_sessionmaker[Any],
    name: str,
    callback: Any,
) -> dict[str, Any]:
    async with session_factory() as session:
        with count_queries(engine) as counter:
            started = time.perf_counter()
            model = await callback(session)
            service_ms = (time.perf_counter() - started) * 1000

        serialize_started = time.perf_counter()
        payload = model_json_bytes(model)
        serialize_ms = (time.perf_counter() - serialize_started) * 1000

    return {
        "name": name,
        "query_count": counter.count,
        "service_ms": round(service_ms, 3),
        "serialization_ms": round(serialize_ms, 3),
        **analyze_payload(payload),
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--label", required=True)
    args = parser.parse_args()

    engine = create_async_engine(os.environ["DATABASE_URL"])
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    ids = await seed_dataset(session_factory)

    async def products(session: Any, **kwargs: Any) -> Any:
        return await ProductsService(session).list_public_products(**kwargs)

    async def detail(session: Any) -> Any:
        return await ProductsService(session).get_public_product(ids["product_id"])

    async def favorites(session: Any) -> Any:
        return await FavoritesService(session).list_current_user_favorites(ids["user_id"])

    async def favorite_detail_n_plus_one(session: Any) -> Any:
        service = ProductsService(session)
        favorite_list = await FavoritesService(session).list_current_user_favorites(ids["user_id"])
        items = [
            await service.get_public_product(favorite.product_id)
            for favorite in favorite_list.items
        ]
        return {
            "items": [item.model_dump(mode="json") for item in items],
            "meta": {"limit": len(items), "offset": 0, "total": len(items)},
        }

    operations = [
        (
            "products_limit_20",
            lambda session: products(session, limit=20, offset=0, status=ProductStatus.ACTIVE),
        ),
        (
            "products_limit_40",
            lambda session: products(session, limit=40, offset=0, status=ProductStatus.ACTIVE),
        ),
        (
            "search_results",
            lambda session: products(
                session,
                limit=20,
                offset=0,
                status=ProductStatus.ACTIVE,
                search="hoodie",
            ),
        ),
        (
            "category_results",
            lambda session: products(
                session,
                limit=20,
                offset=0,
                status=ProductStatus.ACTIVE,
                category_id=ids["category_id"],
            ),
        ),
        ("product_detail", detail),
        ("favorites_overlay", favorites),
        ("favorites_current_frontend_n_plus_one", favorite_detail_n_plus_one),
    ]

    measurements = [
        await measure_operation(engine, session_factory, name, callback)
        for name, callback in operations
    ]

    output = {
        "label": args.label,
        "captured_at": datetime.now(UTC).isoformat(),
        "dataset": {
            "active_products": 45,
            "inactive_or_archived_products": 5,
            "categories": 4,
            "tags": 4,
            "favorites": 10,
            "has_derivative_images": True,
            "has_legacy_images": True,
            "has_related_products": True,
            "has_out_of_stock_active_products": True,
        },
        "measurements": measurements,
    }
    Path(args.output).write_text(
        json.dumps(output, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(json.dumps(output, ensure_ascii=False))
    await engine.dispose()


asyncio.run(main())
