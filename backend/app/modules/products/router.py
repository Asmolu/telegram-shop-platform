from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.deps import get_db_session, require_roles
from app.common.pagination import PaginationParams
from app.db.models import ProductStatus, User, UserRole
from app.modules.products.schemas import ProductCreate, ProductList, ProductRead, ProductUpdate
from app.modules.products.service import ProductsService

router = APIRouter(prefix="/products", tags=["products"])


def get_products_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProductsService:
    return ProductsService(session)


@router.get("", response_model=ProductList)
async def list_public_products(
    pagination: Annotated[PaginationParams, Depends()],
    service: Annotated[ProductsService, Depends(get_products_service)],
    category_id: int | None = None,
    tag_id: int | None = None,
    status_filter: Annotated[ProductStatus | None, Query(alias="status")] = None,
    search: Annotated[str | None, Query(min_length=1, max_length=255)] = None,
) -> ProductList:
    return await service.list_public_products(
        limit=pagination.limit,
        offset=pagination.offset,
        category_id=category_id,
        tag_id=tag_id,
        status=status_filter,
        search=search,
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
) -> ProductList:
    return await service.list_products(
        limit=pagination.limit,
        offset=pagination.offset,
        category_id=category_id,
        tag_id=tag_id,
        status=status_filter,
        search=search,
    )


@router.get("/admin/{product_id}", response_model=ProductRead)
async def get_product(
    product_id: int,
    service: Annotated[ProductsService, Depends(get_products_service)],
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
) -> object:
    return await service.get_product(product_id)


@router.get("/{product_id}", response_model=ProductRead)
async def get_public_product(
    product_id: int,
    service: Annotated[ProductsService, Depends(get_products_service)],
) -> object:
    return await service.get_public_product(product_id)


@router.post("", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
async def create_product(
    payload: ProductCreate,
    service: Annotated[ProductsService, Depends(get_products_service)],
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
) -> object:
    return await service.create_product(payload)


@router.patch("/{product_id}", response_model=ProductRead)
async def update_product(
    product_id: int,
    payload: ProductUpdate,
    service: Annotated[ProductsService, Depends(get_products_service)],
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
) -> object:
    return await service.update_product(product_id, payload)


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    product_id: int,
    service: Annotated[ProductsService, Depends(get_products_service)],
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
) -> Response:
    await service.delete_product(product_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
