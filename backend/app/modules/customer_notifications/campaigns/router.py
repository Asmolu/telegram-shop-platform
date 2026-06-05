from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.deps import get_db_session, require_roles
from app.common.pagination import PaginationParams
from app.db.models import (
    BroadcastCampaignStatus,
    BroadcastCampaignType,
    BroadcastDeliveryStatus,
    NotificationTemplateCategory,
    User,
    UserRole,
)
from app.modules.customer_notifications.campaigns.schemas import (
    BroadcastCampaignCreate,
    BroadcastCampaignDetail,
    BroadcastCampaignList,
    BroadcastCampaignPreview,
    BroadcastCampaignProcessBatchRequest,
    BroadcastCampaignProcessBatchResponse,
    BroadcastCampaignRead,
    BroadcastCampaignScheduleRequest,
    BroadcastCampaignTestRequest,
    BroadcastCampaignTestResponse,
    BroadcastCampaignUpdate,
    BroadcastDeliveryList,
    BroadcastDeliverySummary,
    NotificationTemplateCreate,
    NotificationTemplateList,
    NotificationTemplateRead,
    NotificationTemplateUpdate,
)
from app.modules.customer_notifications.campaigns.service import (
    CustomerNotificationCampaignService,
)

router = APIRouter(prefix="/customer-notifications", tags=["customer-notifications"])


def get_customer_campaign_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CustomerNotificationCampaignService:
    return CustomerNotificationCampaignService(session)


@router.post("/templates", response_model=NotificationTemplateRead)
async def create_template(
    payload: NotificationTemplateCreate,
    actor: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[
        CustomerNotificationCampaignService,
        Depends(get_customer_campaign_service),
    ],
) -> NotificationTemplateRead:
    return await service.create_template(actor=actor, payload=payload)


@router.get("/templates", response_model=NotificationTemplateList)
async def list_templates(
    pagination: Annotated[PaginationParams, Depends()],
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[
        CustomerNotificationCampaignService,
        Depends(get_customer_campaign_service),
    ],
    category: Annotated[NotificationTemplateCategory | None, Query()] = None,
    active: Annotated[bool | None, Query()] = None,
) -> NotificationTemplateList:
    return await service.list_templates(
        limit=pagination.limit,
        offset=pagination.offset,
        category=category,
        active=active,
    )


@router.get("/templates/{template_id}", response_model=NotificationTemplateRead)
async def get_template(
    template_id: int,
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[
        CustomerNotificationCampaignService,
        Depends(get_customer_campaign_service),
    ],
) -> NotificationTemplateRead:
    return await service.get_template(template_id)


@router.patch("/templates/{template_id}", response_model=NotificationTemplateRead)
async def update_template(
    template_id: int,
    payload: NotificationTemplateUpdate,
    actor: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[
        CustomerNotificationCampaignService,
        Depends(get_customer_campaign_service),
    ],
) -> NotificationTemplateRead:
    return await service.update_template(template_id=template_id, actor=actor, payload=payload)


@router.post("/templates/{template_id}/disable", response_model=NotificationTemplateRead)
async def disable_template(
    template_id: int,
    actor: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[
        CustomerNotificationCampaignService,
        Depends(get_customer_campaign_service),
    ],
) -> NotificationTemplateRead:
    return await service.disable_template(template_id=template_id, actor=actor)


@router.post("/campaigns", response_model=BroadcastCampaignRead)
async def create_campaign(
    payload: BroadcastCampaignCreate,
    actor: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[
        CustomerNotificationCampaignService,
        Depends(get_customer_campaign_service),
    ],
) -> BroadcastCampaignRead:
    return await service.create_campaign(actor=actor, payload=payload)


@router.get("/campaigns", response_model=BroadcastCampaignList)
async def list_campaigns(
    pagination: Annotated[PaginationParams, Depends()],
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[
        CustomerNotificationCampaignService,
        Depends(get_customer_campaign_service),
    ],
    campaign_type: Annotated[
        BroadcastCampaignType | None,
        Query(alias="type"),
    ] = None,
    status_filter: Annotated[
        BroadcastCampaignStatus | None,
        Query(alias="status"),
    ] = None,
) -> BroadcastCampaignList:
    return await service.list_campaigns(
        limit=pagination.limit,
        offset=pagination.offset,
        campaign_type=campaign_type,
        status_filter=status_filter,
    )


@router.get("/campaigns/{campaign_id}", response_model=BroadcastCampaignDetail)
async def get_campaign(
    campaign_id: int,
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[
        CustomerNotificationCampaignService,
        Depends(get_customer_campaign_service),
    ],
) -> BroadcastCampaignDetail:
    return await service.get_campaign_detail(campaign_id)


@router.patch("/campaigns/{campaign_id}", response_model=BroadcastCampaignRead)
async def update_campaign(
    campaign_id: int,
    payload: BroadcastCampaignUpdate,
    actor: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[
        CustomerNotificationCampaignService,
        Depends(get_customer_campaign_service),
    ],
) -> BroadcastCampaignRead:
    return await service.update_campaign(campaign_id=campaign_id, actor=actor, payload=payload)


@router.post("/campaigns/{campaign_id}/preview", response_model=BroadcastCampaignPreview)
async def preview_campaign(
    campaign_id: int,
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[
        CustomerNotificationCampaignService,
        Depends(get_customer_campaign_service),
    ],
) -> BroadcastCampaignPreview:
    return await service.preview_campaign(campaign_id)


@router.post("/campaigns/{campaign_id}/test", response_model=BroadcastCampaignTestResponse)
async def send_test_campaign(
    campaign_id: int,
    payload: BroadcastCampaignTestRequest,
    actor: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[
        CustomerNotificationCampaignService,
        Depends(get_customer_campaign_service),
    ],
) -> BroadcastCampaignTestResponse:
    return await service.send_test_message(campaign_id=campaign_id, actor=actor, payload=payload)


@router.post("/campaigns/{campaign_id}/schedule", response_model=BroadcastCampaignRead)
async def schedule_campaign(
    campaign_id: int,
    payload: BroadcastCampaignScheduleRequest,
    actor: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[
        CustomerNotificationCampaignService,
        Depends(get_customer_campaign_service),
    ],
) -> BroadcastCampaignRead:
    return await service.schedule_campaign(
        campaign_id=campaign_id,
        actor=actor,
        payload=payload,
    )


@router.post("/campaigns/{campaign_id}/start", response_model=BroadcastCampaignRead)
async def start_campaign(
    campaign_id: int,
    actor: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[
        CustomerNotificationCampaignService,
        Depends(get_customer_campaign_service),
    ],
) -> BroadcastCampaignRead:
    return await service.schedule_campaign(
        campaign_id=campaign_id,
        actor=actor,
        payload=BroadcastCampaignScheduleRequest(),
        start_now=True,
    )


@router.post("/campaigns/{campaign_id}/pause", response_model=BroadcastCampaignRead)
async def pause_campaign(
    campaign_id: int,
    actor: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[
        CustomerNotificationCampaignService,
        Depends(get_customer_campaign_service),
    ],
) -> BroadcastCampaignRead:
    return await service.pause_campaign(campaign_id=campaign_id, actor=actor)


@router.post("/campaigns/{campaign_id}/cancel", response_model=BroadcastCampaignRead)
async def cancel_campaign(
    campaign_id: int,
    actor: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[
        CustomerNotificationCampaignService,
        Depends(get_customer_campaign_service),
    ],
) -> BroadcastCampaignRead:
    return await service.cancel_campaign(campaign_id=campaign_id, actor=actor)


@router.post(
    "/campaigns/{campaign_id}/process-batch",
    response_model=BroadcastCampaignProcessBatchResponse,
)
async def process_campaign_batch(
    campaign_id: int,
    payload: BroadcastCampaignProcessBatchRequest,
    actor: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[
        CustomerNotificationCampaignService,
        Depends(get_customer_campaign_service),
    ],
) -> BroadcastCampaignProcessBatchResponse:
    return await service.process_batch(campaign_id=campaign_id, actor=actor, payload=payload)


@router.get("/campaigns/{campaign_id}/deliveries", response_model=BroadcastDeliveryList)
async def list_campaign_deliveries(
    campaign_id: int,
    pagination: Annotated[PaginationParams, Depends()],
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[
        CustomerNotificationCampaignService,
        Depends(get_customer_campaign_service),
    ],
    status_filter: Annotated[
        BroadcastDeliveryStatus | None,
        Query(alias="status"),
    ] = None,
) -> BroadcastDeliveryList:
    return await service.list_deliveries(
        campaign_id=campaign_id,
        limit=pagination.limit,
        offset=pagination.offset,
        status_filter=status_filter,
    )


@router.get(
    "/campaigns/{campaign_id}/delivery-summary",
    response_model=BroadcastDeliverySummary,
)
async def get_campaign_delivery_summary(
    campaign_id: int,
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[
        CustomerNotificationCampaignService,
        Depends(get_customer_campaign_service),
    ],
) -> BroadcastDeliverySummary:
    return await service.get_delivery_summary(campaign_id)
