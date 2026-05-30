from datetime import datetime

from fastapi import status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.cache import CacheService, banner_cache_patterns, public_banners_list_key
from app.common.pagination import PageMeta
from app.core.config import settings
from app.core.errors import AppError
from app.db.models import Banner, BannerTargetType
from app.modules.audit.service import AuditService, NoopAuditService
from app.modules.banners.repository import BannersRepository
from app.modules.banners.schemas import BannerCreate, BannerList, BannerRead, BannerUpdate

BANNER_AUDIT_FIELDS = (
    "title",
    "subtitle",
    "file_path",
    "target_type",
    "target_id",
    "external_url",
    "position",
    "is_active",
    "starts_at",
    "ends_at",
)


class BannersService:
    """Banner management endpoints."""

    def __init__(
        self,
        session: AsyncSession,
        audit_service: AuditService | None = None,
        cache: CacheService | None = None,
    ) -> None:
        self.session = session
        self.repository = BannersRepository(session)
        self.audit_service = audit_service or NoopAuditService()
        self.cache = cache

    async def list_public_banners(self, *, limit: int, offset: int) -> BannerList:
        cache_key = public_banners_list_key(limit=limit, offset=offset)
        if self.cache is not None:
            cached = await self.cache.get_model(cache_key, BannerList)
            if cached is not None:
                return cached

        items, total = await self.repository.list(
            limit=limit,
            offset=offset,
            active_only=True,
        )
        result = BannerList(
            items=[BannerRead.model_validate(item) for item in items],
            meta=PageMeta(limit=limit, offset=offset, total=total),
        )
        if self.cache is not None:
            await self.cache.set_model(cache_key, result, settings.cache_banners_ttl_seconds)
        return result

    async def list_banners(self, *, limit: int, offset: int) -> BannerList:
        items, total = await self.repository.list(limit=limit, offset=offset)
        return BannerList(
            items=[BannerRead.model_validate(item) for item in items],
            meta=PageMeta(limit=limit, offset=offset, total=total),
        )

    async def get_banner(self, banner_id: int) -> BannerRead:
        banner = await self._get_existing_banner(banner_id)
        return BannerRead.model_validate(banner)

    async def create_banner(
        self,
        payload: BannerCreate,
        actor_user_id: int | None = None,
    ) -> BannerRead:
        banner = Banner(
            title=payload.title,
            subtitle=payload.subtitle,
            file_path=payload.image_path,
            original_filename=payload.image_path.rsplit("/", 1)[-1],
            mime_type="",
            size_bytes=0,
            alt_text=payload.title,
            target_type=payload.target_type,
            target_id=payload.target_id,
            external_url=payload.external_url,
            position=payload.position,
            is_active=payload.is_active,
            starts_at=payload.starts_at,
            ends_at=payload.ends_at,
        )
        self.repository.add(banner)
        try:
            if banner.id is None:
                await self.session.flush()
            await self.audit_service.record_action(
                actor_user_id=actor_user_id,
                action="banner.created",
                entity_type="banner",
                entity_id=banner.id,
                before_data=None,
                after_data=self.audit_service.snapshot(banner, BANNER_AUDIT_FIELDS),
            )
            await self.session.commit()
            await self.session.refresh(banner)
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError("Banner create failed", status.HTTP_409_CONFLICT) from exc

        await self._invalidate_public_cache()
        return BannerRead.model_validate(banner)

    async def update_banner(
        self,
        banner_id: int,
        payload: BannerUpdate,
        actor_user_id: int | None = None,
    ) -> BannerRead:
        banner = await self._get_existing_banner(banner_id)
        before_data = self.audit_service.snapshot(banner, BANNER_AUDIT_FIELDS)
        data = payload.model_dump(exclude_unset=True)

        target_type = data.get("target_type", banner.target_type)
        target_id = data.get("target_id", banner.target_id)
        external_url = data.get("external_url", banner.external_url)
        starts_at = data.get("starts_at", banner.starts_at)
        ends_at = data.get("ends_at", banner.ends_at)
        is_active = data.get("is_active", banner.is_active)
        self._validate_banner_state(
            target_type=target_type,
            target_id=target_id,
            external_url=external_url,
            starts_at=starts_at,
            ends_at=ends_at,
            require_target=is_active,
        )

        image_path = data.pop("image_path", None)
        if image_path is not None:
            banner.file_path = image_path
            banner.original_filename = image_path.rsplit("/", 1)[-1]

        for field, value in data.items():
            setattr(banner, field, value)

        try:
            await self.audit_service.record_action(
                actor_user_id=actor_user_id,
                action="banner.updated",
                entity_type="banner",
                entity_id=banner.id,
                before_data=before_data,
                after_data=self.audit_service.snapshot(banner, BANNER_AUDIT_FIELDS),
            )
            await self.session.commit()
            await self.session.refresh(banner)
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError("Banner update failed", status.HTTP_409_CONFLICT) from exc

        await self._invalidate_public_cache()
        return BannerRead.model_validate(banner)

    async def set_banner_active(
        self,
        banner_id: int,
        is_active: bool,
        actor_user_id: int | None = None,
    ) -> BannerRead:
        banner = await self._get_existing_banner(banner_id)
        before_data = self.audit_service.snapshot(banner, BANNER_AUDIT_FIELDS)
        if is_active:
            self._validate_banner_state(
                target_type=banner.target_type,
                target_id=banner.target_id,
                external_url=banner.external_url,
                starts_at=banner.starts_at,
                ends_at=banner.ends_at,
                require_target=True,
            )
        banner.is_active = is_active
        try:
            await self.audit_service.record_action(
                actor_user_id=actor_user_id,
                action="banner.updated" if is_active else "banner.deactivated",
                entity_type="banner",
                entity_id=banner.id,
                before_data=before_data,
                after_data=self.audit_service.snapshot(banner, BANNER_AUDIT_FIELDS),
            )
            await self.session.commit()
            await self.session.refresh(banner)
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError("Banner update failed", status.HTTP_409_CONFLICT) from exc

        await self._invalidate_public_cache()
        return BannerRead.model_validate(banner)

    async def _get_existing_banner(self, banner_id: int) -> Banner:
        banner = await self.repository.get_by_id(banner_id)
        if banner is None:
            raise AppError("Banner not found", status.HTTP_404_NOT_FOUND)
        return banner

    def _validate_banner_state(
        self,
        *,
        target_type: BannerTargetType | None,
        target_id: int | None,
        external_url: str | None,
        starts_at: datetime | None,
        ends_at: datetime | None,
        require_target: bool,
    ) -> None:
        if target_type is None:
            if not require_target:
                if starts_at is not None and ends_at is not None and starts_at >= ends_at:
                    raise AppError("starts_at must be before ends_at", status.HTTP_400_BAD_REQUEST)
                return
            raise AppError("Banner target_type is required", status.HTTP_400_BAD_REQUEST)
        if target_type == BannerTargetType.EXTERNAL_URL:
            if not external_url:
                raise AppError("external_url is required", status.HTTP_400_BAD_REQUEST)
        elif target_id is None:
            raise AppError("target_id is required", status.HTTP_400_BAD_REQUEST)

        if starts_at is not None and ends_at is not None and starts_at >= ends_at:
            raise AppError("starts_at must be before ends_at", status.HTTP_400_BAD_REQUEST)

    async def _invalidate_public_cache(self) -> None:
        if self.cache is None:
            return
        await self.cache.delete_patterns(*banner_cache_patterns())
