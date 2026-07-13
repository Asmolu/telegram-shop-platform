from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.models import ReviewStatus


class ReviewCreate(BaseModel):
    rating: int = Field(ge=1, le=5)
    text: str = Field(min_length=1, max_length=5000)


class ReviewModerationUpdate(BaseModel):
    status: ReviewStatus

    @field_validator("status")
    @classmethod
    def validate_moderation_status(cls, value: ReviewStatus) -> ReviewStatus:
        if value == ReviewStatus.PENDING:
            raise ValueError("Moderation status must be APPROVED or REJECTED")
        return value


class ReviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    product_id: int
    order_id: int | None = None
    rating: int
    text: str
    status: ReviewStatus
    moderated_at: datetime | None = None
    moderated_by_id: int | None = None
    created_at: datetime
    updated_at: datetime


class ReviewList(BaseModel):
    items: list[ReviewRead]
