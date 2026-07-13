import re

from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.models import RouteAlias, RouteAliasEntityType
from app.modules.route_aliases.repository import RouteAliasesRepository

SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
_SLUG_RE = re.compile(SLUG_PATTERN)

_ENTITY_LABELS = {
    RouteAliasEntityType.PRODUCT: "Product",
    RouteAliasEntityType.CATEGORY: "Category",
    RouteAliasEntityType.LOOK: "Look",
}


class RouteAliasesService:
    def __init__(self, session: AsyncSession) -> None:
        self.repository = RouteAliasesRepository(session)

    async def ensure_slug_available(
        self,
        entity_type: RouteAliasEntityType,
        slug: str,
        *,
        entity_id: int | None = None,
        conflict_message: str | None = None,
    ) -> None:
        self._validate_slug(slug)
        alias = await self.repository.get_active_by_slug(entity_type, slug)
        if alias is not None and alias.entity_id != entity_id:
            raise AppError(
                conflict_message or self._conflict_message(entity_type),
                status.HTTP_409_CONFLICT,
            )

    async def create_alias_for_slug_change(
        self,
        entity_type: RouteAliasEntityType,
        *,
        entity_id: int,
        old_slug: str | None,
        new_slug: str,
        created_by_user_id: int | None = None,
        conflict_message: str | None = None,
    ) -> RouteAlias | None:
        if not old_slug or old_slug == new_slug:
            return None

        self._validate_slug(old_slug)
        alias = await self.repository.get_active_by_slug(entity_type, old_slug)
        if alias is not None:
            if alias.entity_id == entity_id:
                return alias
            raise AppError(
                conflict_message or self._conflict_message(entity_type),
                status.HTTP_409_CONFLICT,
            )

        route_alias = RouteAlias(
            entity_type=entity_type,
            entity_id=entity_id,
            alias_slug=old_slug,
            created_by_user_id=created_by_user_id,
        )
        self.repository.add(route_alias)
        return route_alias

    async def resolve_entity_id(
        self,
        entity_type: RouteAliasEntityType,
        slug: str,
    ) -> int | None:
        if not self.is_valid_slug(slug):
            return None
        alias = await self.repository.get_active_by_slug(entity_type, slug)
        return alias.entity_id if alias is not None else None

    def is_valid_slug(self, slug: str) -> bool:
        return _SLUG_RE.fullmatch(slug) is not None

    def _validate_slug(self, slug: str) -> None:
        if not self.is_valid_slug(slug):
            raise AppError("Route alias slug is invalid", status.HTTP_400_BAD_REQUEST)

    def _conflict_message(self, entity_type: RouteAliasEntityType) -> str:
        return f"{_ENTITY_LABELS[entity_type]} slug conflicts with an active route alias"
