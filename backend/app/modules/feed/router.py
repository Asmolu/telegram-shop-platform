from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.deps import get_db_session
from app.common.http_cache import (
    PUBLIC_REVALIDATE_CACHE,
    is_not_modified,
    not_modified_response,
    set_cache_headers,
    stable_etag,
)
from app.common.pagination import PaginationParams
from app.modules.feed.schemas import FeedListResponse
from app.modules.feed.service import FeedService

router = APIRouter(prefix="/feed", tags=["feed"])


def get_feed_service(session: Annotated[AsyncSession, Depends(get_db_session)]) -> FeedService:
    return FeedService(session)


@router.get("", response_model=FeedListResponse)
async def list_public_feed(
    request: Request,
    response: Response,
    pagination: Annotated[PaginationParams, Depends()],
    service: Annotated[FeedService, Depends(get_feed_service)],
) -> FeedListResponse | Response:
    result = await service.list_public_feed(limit=pagination.limit, offset=pagination.offset)
    etag = stable_etag(result)
    if is_not_modified(request, etag):
        return not_modified_response(etag=etag, cache_control=PUBLIC_REVALIDATE_CACHE)
    set_cache_headers(response, etag=etag, cache_control=PUBLIC_REVALIDATE_CACHE)
    return result
