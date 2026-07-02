from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, UploadFile, status
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.deps import get_current_user, get_db_session, require_roles
from app.core.errors import AppError
from app.db.models import ReturnRequestStatus, User, UserRole
from app.modules.returns.schemas import (
    ReturnDecisionRequest,
    ReturnEligibilityRead,
    ReturnLifecycleCommentRequest,
    ReturnRequestCreate,
    ReturnRequestList,
    ReturnRequestRead,
)
from app.modules.returns.service import ReturnsService

customer_router = APIRouter(prefix="/orders", tags=["returns"])
return_customer_router = APIRouter(prefix="/returns", tags=["returns"])
admin_router = APIRouter(prefix="/returns/admin", tags=["returns"])


def get_returns_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ReturnsService:
    return ReturnsService(session)


@customer_router.get("/{order_id}/return-eligibility", response_model=ReturnEligibilityRead)
async def get_return_eligibility(
    order_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[ReturnsService, Depends(get_returns_service)],
) -> ReturnEligibilityRead:
    return await service.get_return_eligibility(order_id=order_id, user_id=current_user.id)


@customer_router.post(
    "/{order_id}/returns",
    response_model=ReturnRequestRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_return_request(
    order_id: int,
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[ReturnsService, Depends(get_returns_service)],
) -> ReturnRequestRead:
    payload, files = await _parse_create_request(request)
    return await service.create_return_request(
        order_id=order_id,
        user_id=current_user.id,
        payload=payload,
        files=files,
    )


@return_customer_router.post("/{return_request_id}/cancel", response_model=ReturnRequestRead)
async def cancel_customer_return_request(
    return_request_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[ReturnsService, Depends(get_returns_service)],
    payload: ReturnLifecycleCommentRequest | None = None,
) -> ReturnRequestRead:
    return await service.cancel_customer(
        return_request_id=return_request_id,
        user_id=current_user.id,
        payload=payload or ReturnLifecycleCommentRequest(),
    )


@admin_router.get("", response_model=ReturnRequestList)
async def list_admin_return_requests(
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[ReturnsService, Depends(get_returns_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    status_filter: Annotated[ReturnRequestStatus | None, Query(alias="status")] = None,
    order_id: int | None = None,
    user_id: int | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
) -> ReturnRequestList:
    return await service.list_admin_return_requests(
        limit=limit,
        offset=offset,
        status_filter=status_filter,
        order_id=order_id,
        user_id=user_id,
        created_from=created_from,
        created_to=created_to,
    )


@admin_router.get("/{return_request_id}", response_model=ReturnRequestRead)
async def get_admin_return_request(
    return_request_id: int,
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[ReturnsService, Depends(get_returns_service)],
) -> ReturnRequestRead:
    return await service.get_admin_return_request(return_request_id)


@admin_router.post("/{return_request_id}/approve", response_model=ReturnRequestRead)
async def approve_return_request(
    return_request_id: int,
    payload: ReturnDecisionRequest,
    current_user: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[ReturnsService, Depends(get_returns_service)],
) -> ReturnRequestRead:
    return await service.approve(
        return_request_id=return_request_id,
        actor_user_id=current_user.id,
        payload=payload,
    )


@admin_router.post("/{return_request_id}/reject", response_model=ReturnRequestRead)
async def reject_return_request(
    return_request_id: int,
    payload: ReturnDecisionRequest,
    current_user: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[ReturnsService, Depends(get_returns_service)],
) -> ReturnRequestRead:
    return await service.reject(
        return_request_id=return_request_id,
        actor_user_id=current_user.id,
        payload=payload,
    )


@admin_router.post("/{return_request_id}/complete", response_model=ReturnRequestRead)
async def complete_return_request(
    return_request_id: int,
    current_user: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[ReturnsService, Depends(get_returns_service)],
    payload: ReturnLifecycleCommentRequest | None = None,
) -> ReturnRequestRead:
    return await service.complete(
        return_request_id=return_request_id,
        actor_user_id=current_user.id,
        payload=payload or ReturnLifecycleCommentRequest(),
    )


@admin_router.post("/{return_request_id}/cancel", response_model=ReturnRequestRead)
async def cancel_admin_return_request(
    return_request_id: int,
    current_user: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[ReturnsService, Depends(get_returns_service)],
    payload: ReturnLifecycleCommentRequest | None = None,
) -> ReturnRequestRead:
    return await service.cancel_admin(
        return_request_id=return_request_id,
        actor_user_id=current_user.id,
        payload=payload or ReturnLifecycleCommentRequest(),
    )


async def _parse_create_request(request: Request) -> tuple[ReturnRequestCreate, list[UploadFile]]:
    content_type = request.headers.get("content-type", "")
    try:
        if "multipart/form-data" in content_type:
            form = await request.form()
            raw_payload = form.get("payload")
            if not isinstance(raw_payload, str):
                raise AppError(
                    "payload form field is required",
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                )
            payload = ReturnRequestCreate.model_validate_json(raw_payload)
            files = [
                item
                for item in [*form.getlist("files"), *form.getlist("files[]")]
                if hasattr(item, "read") and hasattr(item, "filename")
            ]
            return payload, files

        body = await request.json()
        return ReturnRequestCreate.model_validate(body), []
    except ValidationError as exc:
        raise AppError(
            "Invalid return request payload",
            status.HTTP_422_UNPROCESSABLE_CONTENT,
        ) from exc
    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            "Invalid return request payload",
            status.HTTP_422_UNPROCESSABLE_CONTENT,
        ) from exc
