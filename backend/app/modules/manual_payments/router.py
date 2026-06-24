from typing import Annotated

from fastapi import APIRouter, Depends, File, Header, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.deps import get_current_user, get_db_session, require_roles
from app.db.models import ManualPaymentStatus, User, UserRole
from app.modules.audit.service import AuditService
from app.modules.manual_payments.schemas import (
    ManualPaymentExpireBatchRead,
    ManualPaymentList,
    ManualPaymentRead,
    ManualPaymentReject,
    SellerPaymentSettingsRead,
    SellerPaymentSettingsUpdate,
)
from app.modules.manual_payments.service import ManualPaymentsService

customer_router = APIRouter(prefix="/orders", tags=["manual-payments"])
seller_router = APIRouter(prefix="/seller", tags=["seller-manual-payments"])


def get_manual_payments_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ManualPaymentsService:
    return ManualPaymentsService(session, audit_service=AuditService(session))


@customer_router.get("/{order_id}/payment", response_model=ManualPaymentRead)
async def get_order_payment(
    order_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[ManualPaymentsService, Depends(get_manual_payments_service)],
) -> ManualPaymentRead:
    return await service.get_for_customer(order_id=order_id, user_id=current_user.id)


@customer_router.post("/{order_id}/payment/submit", response_model=ManualPaymentRead)
async def submit_order_payment(
    order_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[ManualPaymentsService, Depends(get_manual_payments_service)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> ManualPaymentRead:
    return await service.submit(
        order_id=order_id,
        user_id=current_user.id,
        idempotency_key=idempotency_key,
    )


@customer_router.post("/{order_id}/payment/receipt", response_model=ManualPaymentRead)
async def upload_order_payment_receipt(
    order_id: int,
    file: Annotated[UploadFile, File()],
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[ManualPaymentsService, Depends(get_manual_payments_service)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> ManualPaymentRead:
    return await service.upload_receipt(
        order_id=order_id,
        user_id=current_user.id,
        file=file,
        idempotency_key=idempotency_key,
    )


@seller_router.get("/settings/payment", response_model=SellerPaymentSettingsRead)
async def get_payment_settings(
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[ManualPaymentsService, Depends(get_manual_payments_service)],
) -> SellerPaymentSettingsRead:
    return await service.get_settings()


@seller_router.put("/settings/payment", response_model=SellerPaymentSettingsRead)
async def update_payment_settings(
    payload: SellerPaymentSettingsUpdate,
    current_user: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[ManualPaymentsService, Depends(get_manual_payments_service)],
) -> SellerPaymentSettingsRead:
    return await service.update_settings(payload, actor_user_id=current_user.id)


@seller_router.get("/payments", response_model=ManualPaymentList)
async def list_manual_payments(
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[ManualPaymentsService, Depends(get_manual_payments_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    status_filter: Annotated[
        ManualPaymentStatus | None,
        Query(alias="status"),
    ] = None,
) -> ManualPaymentList:
    return await service.list_for_seller(
        limit=limit,
        offset=offset,
        status_filter=status_filter,
    )


@seller_router.post("/payments/expire-due", response_model=ManualPaymentExpireBatchRead)
async def expire_due_manual_payments(
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[ManualPaymentsService, Depends(get_manual_payments_service)],
) -> ManualPaymentExpireBatchRead:
    return ManualPaymentExpireBatchRead(expired_count=await service.expire_due_batch())


@seller_router.get("/payments/{payment_id}", response_model=ManualPaymentRead)
async def get_manual_payment(
    payment_id: int,
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[ManualPaymentsService, Depends(get_manual_payments_service)],
) -> ManualPaymentRead:
    return await service.get_for_seller(payment_id)


@seller_router.post("/payments/{payment_id}/approve", response_model=ManualPaymentRead)
async def approve_manual_payment(
    payment_id: int,
    current_user: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[ManualPaymentsService, Depends(get_manual_payments_service)],
) -> ManualPaymentRead:
    return await service.approve(payment_id, actor_user_id=current_user.id)


@seller_router.post("/payments/{payment_id}/reject", response_model=ManualPaymentRead)
async def reject_manual_payment(
    payment_id: int,
    payload: ManualPaymentReject,
    current_user: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[ManualPaymentsService, Depends(get_manual_payments_service)],
) -> ManualPaymentRead:
    return await service.reject(
        payment_id,
        actor_user_id=current_user.id,
        reject_reason=payload.reject_reason,
    )
