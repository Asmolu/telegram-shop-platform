from datetime import datetime
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from app.common.pagination import PageMeta


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    actor_user_id: int | None = None
    action: str
    entity_type: str
    entity_id: int | None = None
    before_data: dict[str, Any] | None = None
    after_data: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = Field(
        default=None,
        validation_alias=AliasChoices("audit_metadata", "metadata"),
    )
    created_at: datetime


class AuditLogList(BaseModel):
    items: list[AuditLogRead]
    meta: PageMeta
