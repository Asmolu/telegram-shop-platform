from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import RouteAlias, RouteAliasEntityType


class RouteAliasesRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_active_by_slug(
        self,
        entity_type: RouteAliasEntityType,
        alias_slug: str,
    ) -> RouteAlias | None:
        result = await self.session.execute(
            select(RouteAlias).where(
                RouteAlias.entity_type == entity_type,
                RouteAlias.alias_slug == alias_slug,
                RouteAlias.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def get_active_for_entity_slug(
        self,
        entity_type: RouteAliasEntityType,
        entity_id: int,
        alias_slug: str,
    ) -> RouteAlias | None:
        result = await self.session.execute(
            select(RouteAlias).where(
                RouteAlias.entity_type == entity_type,
                RouteAlias.entity_id == entity_id,
                RouteAlias.alias_slug == alias_slug,
                RouteAlias.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def list_active_alias_slugs(self, entity_type: RouteAliasEntityType) -> list[str]:
        result = await self.session.execute(
            select(RouteAlias.alias_slug).where(
                RouteAlias.entity_type == entity_type,
                RouteAlias.is_active.is_(True),
            )
        )
        return list(result.scalars().all())

    def add(self, route_alias: RouteAlias) -> None:
        self.session.add(route_alias)
