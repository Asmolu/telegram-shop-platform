from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.cache import CacheService
from app.common.deps import get_db_session, get_optional_current_user, require_roles
from app.common.pagination import PaginationParams
from app.db.models import ProductSizeGrid, ProductStatus, User, UserRole
from app.modules.analytics.service import IsolatedAnalyticsTracker
from app.modules.audit.service import AuditService
from app.modules.products.schemas import (
    ProductCreate,
    ProductList,
    ProductRead,
    ProductStatusUpdate,
    ProductUpdate,
    ProductVariantCreate,
    ProductVariantList,
    ProductVariantRead,
    ProductVariantUpdate,
)
from app.modules.products.service import ProductsService

router = APIRouter(prefix="/products", tags=["products"])


def get_products_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProductsService:
    return ProductsService(
        session,
        analytics_tracker=IsolatedAnalyticsTracker(),
        audit_service=AuditService(session),
        cache=CacheService(),
    )


@router.get("", response_model=ProductList)
async def list_public_products(
    pagination: Annotated[PaginationParams, Depends()],
    service: Annotated[ProductsService, Depends(get_products_service)],
    current_user: Annotated[User | None, Depends(get_optional_current_user)],
    category_id: int | None = None,
    tag_id: int | None = None,
    status_filter: Annotated[ProductStatus | None, Query(alias="status")] = None,
    search: Annotated[str | None, Query(min_length=1, max_length=255)] = None,
    size_grid: ProductSizeGrid | None = None,
    size: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
    color: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
) -> ProductList:
    return await service.list_public_products(
        limit=pagination.limit,
        offset=pagination.offset,
        category_id=category_id,
        tag_id=tag_id,
        status=status_filter,
        search=search,
        size_grid=size_grid,
        size=size,
        color=color,
        user_id=current_user.id if current_user is not None else None,
    )


@router.get("/admin", response_model=ProductList)
async def list_products(
    pagination: Annotated[PaginationParams, Depends()],
    service: Annotated[ProductsService, Depends(get_products_service)],
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    category_id: int | None = None,
    tag_id: int | None = None,
    status_filter: Annotated[ProductStatus | None, Query(alias="status")] = None,
    search: Annotated[str | None, Query(min_length=1, max_length=255)] = None,
    size_grid: ProductSizeGrid | None = None,
    size: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
    color: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
) -> ProductList:
    return await service.list_products(
        limit=pagination.limit,
        offset=pagination.offset,
        category_id=category_id,
        tag_id=tag_id,
        status=status_filter,
        search=search,
        size_grid=size_grid,
        size=size,
        color=color,
    )


@router.get("/admin/{product_id}", response_model=ProductRead)
async def get_product(
    product_id: int,
    service: Annotated[ProductsService, Depends(get_products_service)],
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
) -> object:
    return await service.get_product(product_id)


@router.get("/admin/{product_id}/variants", response_model=ProductVariantList)
async def list_product_variants(
    product_id: int,
    service: Annotated[ProductsService, Depends(get_products_service)],
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
) -> ProductVariantList:
    return await service.list_product_variants(product_id)


@router.get("/{product_id}/variants", response_model=ProductVariantList)
async def list_public_product_variants(
    product_id: int,
    service: Annotated[ProductsService, Depends(get_products_service)],
) -> ProductVariantList:
    return await service.list_public_product_variants(product_id)


@router.post(
    "/{product_id}/variants",
    response_model=ProductVariantRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_product_variant(
    product_id: int,
    payload: ProductVariantCreate,
    service: Annotated[ProductsService, Depends(get_products_service)],
    current_user: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
) -> object:
    return await service.create_product_variant(product_id, payload, actor_user_id=current_user.id)


@router.patch("/variants/{variant_id}", response_model=ProductVariantRead)
async def update_product_variant(
    variant_id: int,
    payload: ProductVariantUpdate,
    service: Annotated[ProductsService, Depends(get_products_service)],
    current_user: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
) -> object:
    return await service.update_product_variant(variant_id, payload, actor_user_id=current_user.id)


@router.patch("/variants/{variant_id}/deactivate", response_model=ProductVariantRead)
async def deactivate_product_variant(
    variant_id: int,
    service: Annotated[ProductsService, Depends(get_products_service)],
    current_user: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
) -> object:
    return await service.deactivate_product_variant(variant_id, actor_user_id=current_user.id)


@router.delete("/variants/{variant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product_variant(
    variant_id: int,
    service: Annotated[ProductsService, Depends(get_products_service)],
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
) -> Response:
    await service.delete_product_variant(variant_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/{product_id}/status", response_model=ProductRead)
async def update_product_status(
    product_id: int,
    payload: ProductStatusUpdate,
    service: Annotated[ProductsService, Depends(get_products_service)],
    current_user: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
) -> object:
    return await service.update_product_status(
        product_id,
        payload,
        actor_user_id=current_user.id,
    )


@router.patch("/{product_id}/archive", response_model=ProductRead)
async def archive_product(
    product_id: int,
    service: Annotated[ProductsService, Depends(get_products_service)],
    current_user: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
) -> object:
    return await service.archive_product(product_id, actor_user_id=current_user.id)


@router.get("/{product_id}", response_model=ProductRead)
async def get_public_product(
    product_id: int,
    service: Annotated[ProductsService, Depends(get_products_service)],
    current_user: Annotated[User | None, Depends(get_optional_current_user)],
) -> object:
    return await service.get_public_product(
        product_id,
        user_id=current_user.id if current_user is not None else None,
    )


@router.post("", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
async def create_product(
    payload: ProductCreate,
    service: Annotated[ProductsService, Depends(get_products_service)],
    current_user: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
) -> object:
    return await service.create_product(payload, actor_user_id=current_user.id)


@router.patch("/{product_id}", response_model=ProductRead)
async def update_product(
    product_id: int,
    payload: ProductUpdate,
    service: Annotated[ProductsService, Depends(get_products_service)],
    current_user: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
) -> object:
    return await service.update_product(product_id, payload, actor_user_id=current_user.id)


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    product_id: int,
    service: Annotated[ProductsService, Depends(get_products_service)],
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
) -> Response:
    await service.delete_product(product_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
