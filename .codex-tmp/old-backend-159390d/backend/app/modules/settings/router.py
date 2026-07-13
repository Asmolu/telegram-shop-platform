from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.deps import get_db_session, require_roles
from app.db.models import User, UserRole
from app.modules.audit.service import AuditService
from app.modules.settings.schemas import (
    PaymentSuccessBannerSettingsRead,
    PaymentSuccessBannerSettingsUpdate,
    SellerContactSettingsRead,
    SellerContactSettingsUpdate,
)
from app.modules.settings.service import SettingsService

router = APIRouter(prefix="/settings", tags=["settings"])


def get_settings_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SettingsService:
    return SettingsService(session, audit_service=AuditService(session))


@router.get(
    "/admin/payment-success-banner",
    response_model=PaymentSuccessBannerSettingsRead,
)
async def get_payment_success_banner_settings(
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[SettingsService, Depends(get_settings_service)],
) -> PaymentSuccessBannerSettingsRead:
    return await service.get_payment_success_banner_settings()


@router.get(
    "/seller-contacts",
    response_model=SellerContactSettingsRead,
)
async def get_public_seller_contact_settings(
    service: Annotated[SettingsService, Depends(get_settings_service)],
) -> SellerContactSettingsRead:
    return await service.get_seller_contact_settings()


@router.get(
    "/admin/seller-contacts",
    response_model=SellerContactSettingsRead,
)
async def get_admin_seller_contact_settings(
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[SettingsService, Depends(get_settings_service)],
) -> SellerContactSettingsRead:
    return await service.get_seller_contact_settings()


@router.put(
    "/admin/seller-contacts",
    response_model=SellerContactSettingsRead,
)
async def update_admin_seller_contact_settings(
    payload: SellerContactSettingsUpdate,
    current_user: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[SettingsService, Depends(get_settings_service)],
) -> SellerContactSettingsRead:
    return await service.update_seller_contact_settings(
        payload,
        actor_user_id=current_user.id,
    )


@router.post(
    "/admin/payment-success-banner",
    response_model=PaymentSuccessBannerSettingsRead,
)
async def update_payment_success_banner_settings(
    payload: PaymentSuccessBannerSettingsUpdate,
    current_user: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[SettingsService, Depends(get_settings_service)],
) -> PaymentSuccessBannerSettingsRead:
    return await service.update_payment_success_banner_settings(
        payload,
        actor_user_id=current_user.id,
    )


@router.delete(
    "/admin/payment-success-banner",
    response_model=PaymentSuccessBannerSettingsRead,
)
async def delete_payment_success_banner_settings(
    current_user: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[SettingsService, Depends(get_settings_service)],
) -> PaymentSuccessBannerSettingsRead:
    return await service.delete_payment_success_banner_settings(actor_user_id=current_user.id)
