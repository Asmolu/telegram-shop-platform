from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Favorite, Product, ProductImage, ProductStatus, ProductVariant


class FavoritesRepository:
    """Database access layer for favorites."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def product_exists(self, product_id: int) -> bool:
        result = await self.session.execute(select(Product.id).where(Product.id == product_id))
        return result.scalar_one_or_none() is not None

    async def get_for_user_product(self, *, user_id: int, product_id: int) -> Favorite | None:
        result = await self.session.execute(
            select(Favorite).where(Favorite.user_id == user_id, Favorite.product_id == product_id)
        )
        return result.scalar_one_or_none()

    async def list_for_user(self, *, user_id: int) -> list[Favorite]:
        result = await self.session.execute(
            select(Favorite)
            .options(
                selectinload(Favorite.product).load_only(
                    Product.id,
                    Product.name,
                    Product.slug,
                    Product.brand,
                    Product.base_price,
                    Product.old_price,
                    Product.size_grid,
                    Product.image_badge_type,
                    Product.image_badge_text,
                    Product.image_badge_color,
                    Product.image_badge_position,
                    Product.created_at,
                ),
                selectinload(Favorite.product)
                .selectinload(Product.images)
                .load_only(
                    ProductImage.id,
                    ProductImage.product_id,
                    ProductImage.file_path,
                    ProductImage.thumbnail_path,
                    ProductImage.card_path,
                    ProductImage.detail_path,
                    ProductImage.alt_text,
                    ProductImage.position,
                    ProductImage.is_primary,
                ),
                selectinload(Favorite.product)
                .selectinload(Product.variants.and_(ProductVariant.is_active.is_(True)))
                .load_only(
                    ProductVariant.id,
                    ProductVariant.product_id,
                    ProductVariant.size,
                    ProductVariant.color,
                    ProductVariant.stock_quantity,
                    ProductVariant.reserved_quantity,
                    ProductVariant.is_active,
                ),
            )
            .where(Favorite.user_id == user_id)
            .where(Favorite.product.has(Product.status == ProductStatus.ACTIVE))
            .order_by(Favorite.created_at.desc(), Favorite.id.desc())
        )
        return list(result.scalars())

    async def delete_for_user_product(self, *, user_id: int, product_id: int) -> bool:
        result = await self.session.execute(
            delete(Favorite).where(Favorite.user_id == user_id, Favorite.product_id == product_id)
        )
        return bool(result.rowcount)

    def add(self, favorite: Favorite) -> None:
        self.session.add(favorite)
