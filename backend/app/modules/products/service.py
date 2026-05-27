from fastapi import status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.pagination import PageMeta
from app.core.errors import AppError
from app.db.models import Product, ProductImage, ProductStatus, Tag
from app.modules.categories.repository import CategoriesRepository
from app.modules.products.repository import ProductsRepository
from app.modules.products.schemas import (
    ProductCreate,
    ProductImageCreate,
    ProductList,
    ProductUpdate,
)
from app.modules.tags.repository import TagsRepository


class ProductsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = ProductsRepository(session)
        self.categories_repository = CategoriesRepository(session)
        self.tags_repository = TagsRepository(session)

    async def list_public_products(
        self,
        *,
        limit: int,
        offset: int,
        category_id: int | None = None,
        tag_id: int | None = None,
        status: ProductStatus | None = None,
        search: str | None = None,
    ) -> ProductList:
        if status is not None and status != ProductStatus.ACTIVE:
            return ProductList(items=[], meta=PageMeta(limit=limit, offset=offset, total=0))

        return await self.list_products(
            limit=limit,
            offset=offset,
            category_id=category_id,
            tag_id=tag_id,
            status=ProductStatus.ACTIVE,
            search=search,
        )

    async def list_products(
        self,
        *,
        limit: int,
        offset: int,
        category_id: int | None = None,
        tag_id: int | None = None,
        status: ProductStatus | None = None,
        search: str | None = None,
    ) -> ProductList:
        items, total = await self.repository.list(
            limit=limit,
            offset=offset,
            category_id=category_id,
            tag_id=tag_id,
            status=status,
            search=search,
        )
        return ProductList(items=items, meta=PageMeta(limit=limit, offset=offset, total=total))

    async def get_public_product(self, product_id: int) -> Product:
        product = await self.repository.get_active_by_id(product_id)
        if product is None:
            raise AppError("Product not found", status.HTTP_404_NOT_FOUND)
        return product

    async def get_product(self, product_id: int) -> Product:
        product = await self.repository.get_by_id(product_id)
        if product is None:
            raise AppError("Product not found", status.HTTP_404_NOT_FOUND)
        return product

    async def create_product(self, payload: ProductCreate) -> Product:
        tags = await self._resolve_tags(payload.tag_ids)
        await self._ensure_category_exists(payload.category_id)
        self._validate_images(payload.images)

        product_data = payload.model_dump(exclude={"tag_ids", "images"})
        product = Product(
            **product_data,
            tags=tags,
            images=[ProductImage(**image.model_dump()) for image in payload.images],
        )
        self.repository.add(product)
        product_id = await self._flush_commit_and_get_id(product)
        created_product = await self.repository.get_by_id(product_id)
        if created_product is None:
            raise AppError("Product not found", status.HTTP_404_NOT_FOUND)
        return created_product

    async def update_product(self, product_id: int, payload: ProductUpdate) -> Product:
        product = await self.get_product(product_id)
        data = payload.model_dump(exclude_unset=True, exclude={"tag_ids", "images"})

        if "category_id" in data:
            await self._ensure_category_exists(data["category_id"])

        if "tag_ids" in payload.model_fields_set and payload.tag_ids is not None:
            product.tags = await self._resolve_tags(payload.tag_ids)

        if "images" in payload.model_fields_set and payload.images is not None:
            self._validate_images(payload.images)
            product.images = [ProductImage(**image.model_dump()) for image in payload.images]

        for field, value in data.items():
            setattr(product, field, value)

        product_id = await self._flush_commit_and_get_id(product)
        updated_product = await self.repository.get_by_id(product_id)
        if updated_product is None:
            raise AppError("Product not found", status.HTTP_404_NOT_FOUND)
        return updated_product

    async def delete_product(self, product_id: int) -> None:
        product = await self.get_product(product_id)
        await self.repository.delete(product)
        await self._commit()

    async def _ensure_category_exists(self, category_id: int | None) -> None:
        if category_id is None:
            return
        category = await self.categories_repository.get_by_id(category_id)
        if category is None:
            raise AppError("Category not found", status.HTTP_404_NOT_FOUND)

    async def _resolve_tags(self, tag_ids: list[int]) -> list[Tag]:
        unique_tag_ids = list(dict.fromkeys(tag_ids))
        tags = await self.tags_repository.list_by_ids(unique_tag_ids)
        if len(tags) != len(unique_tag_ids):
            raise AppError("Tag not found", status.HTTP_404_NOT_FOUND)
        return tags

    def _validate_images(self, images: list[ProductImageCreate]) -> None:
        primary_count = sum(1 for image in images if image.is_primary)
        if primary_count > 1:
            raise AppError("Only one primary product image is allowed", status.HTTP_400_BAD_REQUEST)

    async def _flush_commit_and_get_id(self, product: Product) -> int:
        try:
            await self.session.flush()
            product_id = product.id
            await self.session.commit()
            return product_id
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError("Product slug already exists", status.HTTP_409_CONFLICT) from exc

    async def _commit(self) -> None:
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError("Product slug already exists", status.HTTP_409_CONFLICT) from exc
