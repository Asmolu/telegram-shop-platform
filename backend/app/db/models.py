from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

product_tags = Table(
    "product_tags",
    Base.metadata,
    Column(
        "product_id",
        ForeignKey("products.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "tag_id",
        ForeignKey("tags.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class UserRole(StrEnum):
    USER = "USER"
    SELLER = "SELLER"
    ADMIN = "ADMIN"


class ProductStatus(StrEnum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    OUT_OF_STOCK = "OUT_OF_STOCK"
    ARCHIVED = "ARCHIVED"


class LookStatus(StrEnum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class ProductSizeGrid(StrEnum):
    CLOTHING_ALPHA = "clothing_alpha"
    SHOES_EU = "shoes_eu"
    SHOES_RU = "shoes_ru"


class ProductImageBadgeType(StrEnum):
    NONE = "none"
    NEW = "new"
    SALE = "sale"
    HIT = "hit"
    EXCLUSIVE = "exclusive"
    CUSTOM = "custom"


class ProductImageBadgeColor(StrEnum):
    PURPLE = "purple"
    PINK = "pink"
    RED = "red"
    ORANGE = "orange"
    BLUE = "blue"
    GREEN = "green"
    BLACK = "black"
    WHITE = "white"


class ProductImageBadgePosition(StrEnum):
    TOP_LEFT = "top-left"
    TOP_RIGHT = "top-right"
    BOTTOM_LEFT = "bottom-left"
    BOTTOM_RIGHT = "bottom-right"


class OrderStatus(StrEnum):
    NEW = "NEW"
    PROCESSING = "PROCESSING"
    SHIPPED = "SHIPPED"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"


class OrderDeliveryMethod(StrEnum):
    ROUTE_TAXI = "ROUTE_TAXI"
    CITY_DELIVERY = "CITY_DELIVERY"
    OZON = "OZON"
    WB = "WB"
    CDEK = "CDEK"


class ManualPaymentMethod(StrEnum):
    SBP_PHONE = "SBP_PHONE"


class ManualPaymentCurrency(StrEnum):
    RUB = "RUB"


class ManualPaymentStatus(StrEnum):
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class ReviewStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class ReturnRequestStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class ReturnRefundStatus(StrEnum):
    PENDING = "PENDING"
    RECORDED = "RECORDED"


class DiscountType(StrEnum):
    PERCENT = "PERCENT"
    FIXED = "FIXED"


class BannerTargetType(StrEnum):
    PRODUCT = "product"
    CATEGORY = "category"
    PROMO = "promo"
    EXTERNAL_URL = "external_url"


class BannerDisplayType(StrEnum):
    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"
    POPUP = "popup"
    AGGRESSIVE_POPUP = "aggressive_popup"


class NotificationChannel(StrEnum):
    TELEGRAM = "telegram"
    INTERNAL = "internal"


class NotificationStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


class CustomerServiceNotificationDeliveryStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


class NotificationTemplateCategory(StrEnum):
    SERVICE = "service"
    MARKETING = "marketing"


class BroadcastCampaignType(StrEnum):
    SERVICE = "service"
    MARKETING = "marketing"


class BroadcastCampaignStatus(StrEnum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    SENDING = "sending"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class BroadcastDeliveryStatus(StrEnum):
    PENDING = "pending"
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"
    RATE_LIMITED = "rate_limited"


class SellerRegistrationStatus(StrEnum):
    PENDING = "PENDING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    VERIFIED = "VERIFIED"
    EXPIRED = "EXPIRED"
    REJECTED = "REJECTED"


def _enum_values(enum_cls: type[StrEnum]) -> list[str]:
    return [item.value for item in enum_cls]


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    recipient_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    city: Mapped[str | None] = mapped_column(String(255), nullable=True)
    height_cm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    telegram_username: Mapped[str | None] = mapped_column(String(32), nullable=True)
    persistent_comment: Mapped[str | None] = mapped_column(String(500), nullable=True)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", values_callable=_enum_values),
        nullable=False,
        default=UserRole.USER,
        server_default=UserRole.USER.value,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    cart: Mapped["Cart | None"] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
    )
    orders: Mapped[list["Order"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="Order.id",
    )
    coupon_usages: Mapped[list["CouponUsage"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="CouponUsage.id",
    )
    reviews: Mapped[list["Review"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        foreign_keys="Review.user_id",
        order_by="Review.id",
    )
    moderated_reviews: Mapped[list["Review"]] = relationship(
        back_populates="moderated_by",
        foreign_keys="Review.moderated_by_id",
        order_by="Review.id",
    )
    favorites: Mapped[list["Favorite"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="Favorite.id",
    )
    notifications: Mapped[list["Notification"]] = relationship(
        back_populates="user",
        order_by="Notification.id",
    )
    seller_credential: Mapped["SellerCredential | None"] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
    )
    customer_telegram_subscription: Mapped["CustomerTelegramSubscription | None"] = relationship(
        back_populates="user",
        uselist=False,
    )
    return_requests: Mapped[list["ReturnRequest"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        foreign_keys="ReturnRequest.user_id",
        order_by="ReturnRequest.id",
    )
    decided_return_requests: Mapped[list["ReturnRequest"]] = relationship(
        back_populates="decided_by",
        foreign_keys="ReturnRequest.decided_by_user_id",
        order_by="ReturnRequest.id",
    )
    completed_return_requests: Mapped[list["ReturnRequest"]] = relationship(
        back_populates="completed_by",
        foreign_keys="ReturnRequest.completed_by_user_id",
        order_by="ReturnRequest.id",
    )
    cancelled_return_requests: Mapped[list["ReturnRequest"]] = relationship(
        back_populates="cancelled_by",
        foreign_keys="ReturnRequest.cancelled_by_user_id",
        order_by="ReturnRequest.id",
    )
    processed_return_refunds: Mapped[list["ReturnRefund"]] = relationship(
        back_populates="processed_by",
        foreign_keys="ReturnRefund.processed_by_user_id",
        order_by="ReturnRefund.id",
    )
    restocked_return_items: Mapped[list["ReturnRequestItem"]] = relationship(
        back_populates="restocked_by",
        foreign_keys="ReturnRequestItem.restocked_by_user_id",
        order_by="ReturnRequestItem.id",
    )


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "scope",
            "key",
            name="uq_idempotency_records_user_scope_key",
        ),
        CheckConstraint(
            "status IN ('PROCESSING', 'SUCCEEDED')",
            name="ck_idempotency_records_status",
        ),
        Index("ix_idempotency_records_expires_at", "expires_at"),
        Index("ix_idempotency_records_user_scope", "user_id", "scope"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    scope: Mapped[str] = mapped_column(String(100), nullable=False)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="PROCESSING",
        server_default="PROCESSING",
    )
    response_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class CustomerTelegramSubscription(Base):
    __tablename__ = "customer_telegram_subscriptions"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_customer_telegram_subscriptions_user_id"),
        UniqueConstraint(
            "telegram_user_id",
            name="uq_customer_telegram_subscriptions_telegram_user_id",
        ),
        Index(
            "ix_customer_telegram_subscriptions_consent",
            "has_chat",
            "service_opt_in",
            "marketing_opt_in",
        ),
        Index(
            "ix_customer_telegram_subscriptions_write_access",
            "write_access_granted",
            "service_opt_in",
        ),
        Index("ix_customer_telegram_subscriptions_blocked_at", "blocked_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    telegram_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    telegram_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    telegram_first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    telegram_last_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    chat_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="unknown",
        server_default="unknown",
    )
    has_chat: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    service_opt_in: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    marketing_opt_in: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    opt_in_source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    marketing_opted_in_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    marketing_opted_out_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    service_opted_out_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    write_access_granted: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    write_access_granted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    write_access_denied_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    write_access_source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_stop_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_settings_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    blocked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_delivery_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped[User | None] = relationship(back_populates="customer_telegram_subscription")


class TelegramChannel(Base):
    __tablename__ = "telegram_channels"
    __table_args__ = (
        UniqueConstraint("chat_id", name="uq_telegram_channels_chat_id"),
        Index("ix_telegram_channels_active_created", "is_active", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    chat_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
    last_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_check_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_check_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    entry_messages: Mapped[list["TelegramChannelEntryMessage"]] = relationship(
        back_populates="channel",
        order_by="TelegramChannelEntryMessage.created_at",
    )


class TelegramChannelEntryMessage(Base):
    __tablename__ = "telegram_channel_entry_messages"
    __table_args__ = (
        Index(
            "ix_telegram_channel_entry_messages_created",
            "created_at",
            "id",
        ),
        Index(
            "ix_telegram_channel_entry_messages_channel_created",
            "channel_id",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    channel_id: Mapped[int | None] = mapped_column(
        ForeignKey("telegram_channels.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    chat_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    button_text: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="Открыть",
        server_default="Открыть",
    )
    button_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    is_pinned: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pinned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    channel: Mapped[TelegramChannel | None] = relationship(back_populates="entry_messages")


class SellerCredential(Base):
    __tablename__ = "seller_credentials"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    telegram_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    telegram_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped[User] = relationship(back_populates="seller_credential")


class PendingSellerRegistration(Base):
    __tablename__ = "pending_seller_registrations"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    telegram_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    telegram_first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    telegram_last_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    telegram_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    bot_start_token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    verification_code_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    verification_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    approval_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    approval_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    approval_decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[SellerRegistrationStatus] = mapped_column(
        Enum(
            SellerRegistrationStatus,
            name="seller_registration_status",
            values_callable=_enum_values,
        ),
        nullable=False,
        default=SellerRegistrationStatus.PENDING,
        server_default=SellerRegistrationStatus.PENDING.value,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    products: Mapped[list["Product"]] = relationship(back_populates="category")
    product_categories: Mapped[list["ProductCategory"]] = relationship(
        back_populates="category",
        cascade="all, delete-orphan",
        order_by="ProductCategory.priority",
    )

    @property
    def image_url(self) -> str | None:
        return f"/uploads/{self.image_path}" if self.image_path else None


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    image_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    products: Mapped[list["Product"]] = relationship(
        secondary=product_tags,
        back_populates="tags",
    )

    @property
    def image_url(self) -> str | None:
        return f"/uploads/{self.image_path}" if self.image_path else None


class ProductCategory(Base):
    __tablename__ = "product_categories"
    __table_args__ = (
        CheckConstraint(
            "priority IN (1, 2, 3)",
            name="ck_product_categories_priority_range",
        ),
        UniqueConstraint(
            "product_id",
            "category_id",
            name="uq_product_categories_product_category",
        ),
        UniqueConstraint(
            "product_id",
            "priority",
            name="uq_product_categories_product_priority",
        ),
        Index("ix_product_categories_category_priority", "category_id", "priority"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    product: Mapped["Product"] = relationship(back_populates="product_categories")
    category: Mapped[Category] = relationship(back_populates="product_categories")


class ProductRelatedProduct(Base):
    __tablename__ = "product_related_products"
    __table_args__ = (
        CheckConstraint(
            "product_id <> related_product_id",
            name="ck_product_related_products_not_self",
        ),
        CheckConstraint(
            "position >= 0",
            name="ck_product_related_products_position_non_negative",
        ),
        UniqueConstraint(
            "product_id",
            "related_product_id",
            name="uq_product_related_products_pair",
        ),
        UniqueConstraint(
            "product_id",
            "position",
            name="uq_product_related_products_position",
        ),
        Index(
            "ix_product_related_products_product_position",
            "product_id",
            "position",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    related_product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    product: Mapped["Product"] = relationship(
        back_populates="related_product_links",
        foreign_keys=[product_id],
    )
    related_product: Mapped["Product"] = relationship(
        back_populates="related_from_links",
        foreign_keys=[related_product_id],
    )


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint(
            "old_price IS NULL OR old_price > base_price",
            name="ck_products_old_price_above_base_price",
        ),
        CheckConstraint(
            "search_priority IN (1, 2, 3)",
            name="ck_products_search_priority_range",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    brand: Mapped[str | None] = mapped_column(String(120), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    base_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    old_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    search_priority: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=2,
        server_default="2",
        index=True,
    )
    search_aliases: Mapped[str | None] = mapped_column(Text, nullable=True)
    size_grid: Mapped[ProductSizeGrid] = mapped_column(
        Enum(ProductSizeGrid, name="product_size_grid", values_callable=_enum_values),
        nullable=False,
        default=ProductSizeGrid.CLOTHING_ALPHA,
        server_default=ProductSizeGrid.CLOTHING_ALPHA.value,
    )
    image_badge_type: Mapped[ProductImageBadgeType] = mapped_column(
        Enum(
            ProductImageBadgeType,
            name="product_image_badge_type",
            values_callable=_enum_values,
        ),
        nullable=False,
        default=ProductImageBadgeType.NONE,
        server_default=ProductImageBadgeType.NONE.value,
    )
    image_badge_text: Mapped[str | None] = mapped_column(String(20), nullable=True)
    image_badge_color: Mapped[ProductImageBadgeColor | None] = mapped_column(
        Enum(
            ProductImageBadgeColor,
            name="product_image_badge_color",
            values_callable=_enum_values,
        ),
        nullable=True,
    )
    image_badge_position: Mapped[ProductImageBadgePosition | None] = mapped_column(
        Enum(
            ProductImageBadgePosition,
            name="product_image_badge_position",
            values_callable=_enum_values,
        ),
        nullable=True,
    )
    status: Mapped[ProductStatus] = mapped_column(
        Enum(ProductStatus, name="product_status", values_callable=_enum_values),
        nullable=False,
        default=ProductStatus.DRAFT,
        server_default=ProductStatus.DRAFT.value,
        index=True,
    )
    is_listed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        index=True,
    )
    is_returnable: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    category: Mapped[Category | None] = relationship(back_populates="products")
    product_categories: Mapped[list[ProductCategory]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="ProductCategory.priority",
    )
    images: Mapped[list["ProductImage"]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="ProductImage.position",
    )
    tags: Mapped[list[Tag]] = relationship(
        secondary=product_tags,
        back_populates="products",
    )
    variants: Mapped[list["ProductVariant"]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="ProductVariant.id",
    )
    related_product_links: Mapped[list[ProductRelatedProduct]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        foreign_keys="ProductRelatedProduct.product_id",
        order_by="ProductRelatedProduct.position",
    )
    related_from_links: Mapped[list[ProductRelatedProduct]] = relationship(
        back_populates="related_product",
        cascade="all, delete-orphan",
        foreign_keys="ProductRelatedProduct.related_product_id",
    )
    cart_items: Mapped[list["CartItem"]] = relationship(back_populates="product")
    order_items: Mapped[list["OrderItem"]] = relationship(back_populates="product")
    reviews: Mapped[list["Review"]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="Review.id",
    )
    favorites: Mapped[list["Favorite"]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="Favorite.id",
    )
    look_items: Mapped[list["LookItem"]] = relationship(back_populates="product")

    @property
    def is_available(self) -> bool:
        return any(
            variant.is_active and variant.available_quantity > 0 for variant in self.variants
        )

    @property
    def primary_image(self) -> "ProductImage | None":
        primary = next((image for image in self.images if image.is_primary), None)
        return primary or (self.images[0] if self.images else None)

    @property
    def image_url(self) -> str | None:
        image = self.primary_image
        if image is None:
            return None
        return image.card_url or image.thumbnail_url or image.url

    @property
    def thumbnail_image_url(self) -> str | None:
        image = self.primary_image
        if image is None:
            return None
        return image.thumbnail_url or image.card_url or image.url

    @property
    def categories(self) -> list[ProductCategory]:
        return self.product_categories

    @property
    def related_product_ids(self) -> list[int]:
        return [link.related_product_id for link in self.related_product_links]

    @property
    def related_products(self) -> list["Product"]:
        return [link.related_product for link in self.related_product_links]


class ProductVariant(Base):
    __tablename__ = "product_variants"
    __table_args__ = (
        CheckConstraint("stock_quantity >= 0", name="ck_product_variants_stock_non_negative"),
        CheckConstraint(
            "reserved_quantity >= 0",
            name="ck_product_variants_reserved_non_negative",
        ),
        CheckConstraint(
            "reserved_quantity <= stock_quantity",
            name="ck_product_variants_reserved_not_above_stock",
        ),
        Index(
            "ix_product_variants_size_active_product",
            "size",
            "is_active",
            "product_id",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    size: Mapped[str] = mapped_column(String(64), nullable=False)
    color: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sku: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    stock_quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    reserved_quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    product: Mapped[Product] = relationship(back_populates="variants")
    cart_items: Mapped[list["CartItem"]] = relationship(back_populates="product_variant")
    order_items: Mapped[list["OrderItem"]] = relationship(back_populates="product_variant")

    @property
    def available_quantity(self) -> int:
        return self.stock_quantity - self.reserved_quantity


class Cart(Base):
    __tablename__ = "carts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped[User] = relationship(back_populates="cart")
    items: Mapped[list["CartItem"]] = relationship(
        back_populates="cart",
        cascade="all, delete-orphan",
        order_by="CartItem.id",
    )


class CartItem(Base):
    __tablename__ = "cart_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_cart_items_quantity_positive"),
        Index("ix_cart_items_source_group_id", "source_group_id"),
        Index("ix_cart_items_source_look_id", "source_look_id"),
        Index(
            "uq_cart_items_normal_cart_variant",
            "cart_id",
            "product_variant_id",
            unique=True,
            postgresql_where=text("source_type IS NULL AND source_group_id IS NULL"),
            sqlite_where=text("source_type IS NULL AND source_group_id IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    cart_id: Mapped[int] = mapped_column(
        ForeignKey("carts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_variant_id: Mapped[int] = mapped_column(
        ForeignKey("product_variants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    is_selected: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
    source_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_look_id: Mapped[int | None] = mapped_column(
        ForeignKey("looks.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_look_slug: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_look_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_look_image_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    source_group_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    cart: Mapped[Cart] = relationship(back_populates="items")
    product: Mapped[Product] = relationship(back_populates="cart_items")
    product_variant: Mapped[ProductVariant] = relationship(back_populates="cart_items")


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_number: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus, name="order_status", values_callable=_enum_values),
        nullable=False,
        default=OrderStatus.NEW,
        server_default=OrderStatus.NEW.value,
        index=True,
    )
    subtotal_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default="0.00",
    )
    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default="0.00",
    )
    promo_code_id: Mapped[int | None] = mapped_column(
        ForeignKey("promo_codes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    promo_code_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    contact_name: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_phone: Mapped[str] = mapped_column(String(32), nullable=False)
    delivery_method: Mapped[OrderDeliveryMethod | None] = mapped_column(
        Enum(
            OrderDeliveryMethod,
            name="order_delivery_method",
            values_callable=_enum_values,
        ),
        nullable=True,
    )
    delivery_address: Mapped[str] = mapped_column(Text, nullable=False)
    delivery_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped[User] = relationship(back_populates="orders")
    promo_code: Mapped["PromoCode | None"] = relationship(back_populates="orders")
    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="OrderItem.id",
    )
    coupon_usages: Mapped[list["CouponUsage"]] = relationship(back_populates="order")
    reviews: Mapped[list["Review"]] = relationship(back_populates="order")
    manual_payment: Mapped["ManualPayment | None"] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        uselist=False,
    )
    return_request: Mapped["ReturnRequest | None"] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        uselist=False,
    )


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_order_items_quantity_positive"),
        CheckConstraint("unit_price >= 0", name="ck_order_items_unit_price_non_negative"),
        CheckConstraint("subtotal >= 0", name="ck_order_items_subtotal_non_negative"),
        Index("ix_order_items_source_group_id", "source_group_id"),
        Index("ix_order_items_source_look_id", "source_look_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    product_variant_id: Mapped[int] = mapped_column(
        ForeignKey("product_variants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    variant_size: Mapped[str] = mapped_column(String(64), nullable=False)
    variant_size_grid: Mapped[ProductSizeGrid] = mapped_column(
        Enum(ProductSizeGrid, name="product_size_grid", values_callable=_enum_values),
        nullable=False,
        default=ProductSizeGrid.CLOTHING_ALPHA,
        server_default=ProductSizeGrid.CLOTHING_ALPHA.value,
    )
    variant_color: Mapped[str | None] = mapped_column(String(64), nullable=True)
    variant_sku: Mapped[str] = mapped_column(String(100), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    is_returnable: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
    source_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_look_id: Mapped[int | None] = mapped_column(
        ForeignKey("looks.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_look_slug: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_look_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_look_image_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    source_group_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    order: Mapped[Order] = relationship(back_populates="items")
    product: Mapped[Product] = relationship(back_populates="order_items")
    product_variant: Mapped[ProductVariant] = relationship(back_populates="order_items")
    return_request_items: Mapped[list["ReturnRequestItem"]] = relationship(
        back_populates="order_item",
        cascade="all, delete-orphan",
        order_by="ReturnRequestItem.id",
    )


class ReturnRequest(Base):
    __tablename__ = "return_requests"
    __table_args__ = (
        UniqueConstraint("order_id", name="uq_return_requests_order_id"),
        Index("ix_return_requests_order_id", "order_id"),
        Index("ix_return_requests_user_id", "user_id"),
        Index("ix_return_requests_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    return_number: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[ReturnRequestStatus] = mapped_column(
        Enum(ReturnRequestStatus, name="return_request_status", values_callable=_enum_values),
        nullable=False,
        default=ReturnRequestStatus.PENDING,
        server_default=ReturnRequestStatus.PENDING.value,
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    decision_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    completion_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    cancellation_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    order: Mapped[Order] = relationship(back_populates="return_request")
    user: Mapped[User] = relationship(
        back_populates="return_requests",
        foreign_keys=[user_id],
    )
    decided_by: Mapped[User | None] = relationship(
        back_populates="decided_return_requests",
        foreign_keys=[decided_by_user_id],
    )
    completed_by: Mapped[User | None] = relationship(
        back_populates="completed_return_requests",
        foreign_keys=[completed_by_user_id],
    )
    cancelled_by: Mapped[User | None] = relationship(
        back_populates="cancelled_return_requests",
        foreign_keys=[cancelled_by_user_id],
    )
    items: Mapped[list["ReturnRequestItem"]] = relationship(
        back_populates="return_request",
        cascade="all, delete-orphan",
        order_by="ReturnRequestItem.id",
    )
    attachments: Mapped[list["ReturnRequestAttachment"]] = relationship(
        back_populates="return_request",
        cascade="all, delete-orphan",
        order_by="ReturnRequestAttachment.position",
    )
    refund: Mapped["ReturnRefund | None"] = relationship(
        back_populates="return_request",
        cascade="all, delete-orphan",
        uselist=False,
    )

    @property
    def order_number(self) -> str | None:
        return self.order.order_number if self.order is not None else None

    @property
    def order_status(self) -> OrderStatus | None:
        return self.order.status if self.order is not None else None

    @property
    def customer_name(self) -> str | None:
        return self.order.contact_name if self.order is not None else None

    @property
    def customer_phone(self) -> str | None:
        return self.order.contact_phone if self.order is not None else None


class ReturnRequestItem(Base):
    __tablename__ = "return_request_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_return_request_items_quantity_positive"),
        CheckConstraint(
            "unit_price >= 0",
            name="ck_return_request_items_unit_price_non_negative",
        ),
        CheckConstraint(
            "restocked_quantity >= 0",
            name="ck_return_request_items_restocked_quantity_non_negative",
        ),
        CheckConstraint(
            "restocked_quantity <= quantity",
            name="ck_return_request_items_restocked_quantity_not_above_quantity",
        ),
        UniqueConstraint(
            "return_request_id",
            "order_item_id",
            name="uq_return_request_items_request_order_item",
        ),
        Index("ix_return_request_items_return_request_id", "return_request_id"),
        Index("ix_return_request_items_product_variant_id", "product_variant_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    return_request_id: Mapped[int] = mapped_column(
        ForeignKey("return_requests.id", ondelete="CASCADE"),
        nullable=False,
    )
    order_item_id: Mapped[int] = mapped_column(
        ForeignKey("order_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id: Mapped[int | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
    )
    product_variant_id: Mapped[int | None] = mapped_column(
        ForeignKey("product_variants.id", ondelete="SET NULL"),
        nullable=True,
    )
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    product_brand: Mapped[str | None] = mapped_column(String(120), nullable=True)
    sku: Mapped[str | None] = mapped_column(String(100), nullable=True)
    size: Mapped[str | None] = mapped_column(String(64), nullable=True)
    color: Mapped[str | None] = mapped_column(String(64), nullable=True)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    restocked_quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    restocked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    restocked_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    return_request: Mapped[ReturnRequest] = relationship(back_populates="items")
    order_item: Mapped[OrderItem] = relationship(back_populates="return_request_items")
    restocked_by: Mapped[User | None] = relationship(
        back_populates="restocked_return_items",
        foreign_keys=[restocked_by_user_id],
    )

    @property
    def remaining_restockable_quantity(self) -> int:
        if self.product_variant_id is None:
            return 0
        return max(self.quantity - (self.restocked_quantity or 0), 0)

    @property
    def can_restock(self) -> bool:
        return self.remaining_restockable_quantity > 0


class ReturnRequestAttachment(Base):
    __tablename__ = "return_request_attachments"
    __table_args__ = (
        CheckConstraint(
            "media_type IN ('image', 'video')",
            name="ck_return_request_attachments_media_type",
        ),
        CheckConstraint(
            "size_bytes >= 0",
            name="ck_return_request_attachments_size_non_negative",
        ),
        CheckConstraint(
            "position >= 0",
            name="ck_return_request_attachments_position_non_negative",
        ),
        Index("ix_return_request_attachments_return_request_id", "return_request_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    return_request_id: Mapped[int] = mapped_column(
        ForeignKey("return_requests.id", ondelete="CASCADE"),
        nullable=False,
    )
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    media_type: Mapped[str] = mapped_column(String(20), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    return_request: Mapped[ReturnRequest] = relationship(back_populates="attachments")


class ReturnRefund(Base):
    __tablename__ = "return_refunds"
    __table_args__ = (
        UniqueConstraint(
            "return_request_id",
            name="uq_return_refunds_return_request_id",
        ),
        CheckConstraint("amount >= 0", name="ck_return_refunds_amount_non_negative"),
        CheckConstraint(
            "status IN ('PENDING', 'RECORDED')",
            name="ck_return_refunds_status",
        ),
        Index("ix_return_refunds_processed_by_user_id", "processed_by_user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    return_request_id: Mapped[int] = mapped_column(
        ForeignKey("return_requests.id", ondelete="CASCADE"),
        nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="RUB",
        server_default="RUB",
    )
    method: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[ReturnRefundStatus] = mapped_column(
        String(32),
        nullable=False,
        default=ReturnRefundStatus.PENDING,
        server_default=ReturnRefundStatus.PENDING.value,
    )
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    processed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    return_request: Mapped[ReturnRequest] = relationship(back_populates="refund")
    processed_by: Mapped[User | None] = relationship(
        back_populates="processed_return_refunds",
        foreign_keys=[processed_by_user_id],
    )


class SellerPaymentSettings(Base):
    __tablename__ = "seller_payment_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    seller_phone_e164: Mapped[str | None] = mapped_column(String(16), nullable=True)
    seller_phone_display: Mapped[str | None] = mapped_column(String(24), nullable=True)
    seller_bank_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    seller_recipient_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_manual_sbp_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    updated_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ManualPayment(Base):
    __tablename__ = "manual_payments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_manual_payments_amount_positive"),
        Index(
            "ix_manual_payments_status_expires_at",
            "status",
            "expires_at",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    method: Mapped[ManualPaymentMethod] = mapped_column(
        Enum(
            ManualPaymentMethod,
            name="manual_payment_method",
            values_callable=_enum_values,
        ),
        nullable=False,
        default=ManualPaymentMethod.SBP_PHONE,
        server_default=ManualPaymentMethod.SBP_PHONE.value,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[ManualPaymentCurrency] = mapped_column(
        Enum(
            ManualPaymentCurrency,
            name="manual_payment_currency",
            values_callable=_enum_values,
        ),
        nullable=False,
        default=ManualPaymentCurrency.RUB,
        server_default=ManualPaymentCurrency.RUB.value,
    )
    seller_phone_e164: Mapped[str] = mapped_column(String(16), nullable=False)
    seller_phone_display: Mapped[str] = mapped_column(String(24), nullable=False)
    seller_bank_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    seller_recipient_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    payment_comment: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[ManualPaymentStatus] = mapped_column(
        Enum(
            ManualPaymentStatus,
            name="manual_payment_status",
            values_callable=_enum_values,
        ),
        nullable=False,
        default=ManualPaymentStatus.PENDING,
        server_default=ManualPaymentStatus.PENDING.value,
        index=True,
    )
    receipt_image_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    seller_telegram_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    seller_telegram_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reject_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    stock_released_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    order: Mapped[Order] = relationship(back_populates="manual_payment")


class ProductImage(Base):
    __tablename__ = "product_images"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    thumbnail_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    card_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    detail_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    alt_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    is_primary: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    product: Mapped[Product] = relationship(back_populates="images")

    @property
    def url(self) -> str:
        return f"/uploads/{self.file_path}"

    @property
    def image_url(self) -> str:
        return self.url

    @property
    def thumbnail_url(self) -> str | None:
        return f"/uploads/{self.thumbnail_path}" if self.thumbnail_path else None

    @property
    def card_url(self) -> str | None:
        return f"/uploads/{self.card_path}" if self.card_path else None

    @property
    def detail_url(self) -> str | None:
        return f"/uploads/{self.detail_path}" if self.detail_path else None

    @property
    def image_variants(self) -> dict[str, str | None]:
        return {
            "thumbnail": self.thumbnail_url,
            "card": self.card_url,
            "detail": self.detail_url,
        }


class Look(Base):
    __tablename__ = "looks"
    __table_args__ = (
        CheckConstraint(
            "search_priority IN (1, 2, 3)",
            name="ck_looks_search_priority_range",
        ),
        Index(
            "ix_looks_public_listing",
            "status",
            "is_listed",
            "search_priority",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[LookStatus] = mapped_column(
        Enum(LookStatus, name="look_status", values_callable=_enum_values),
        nullable=False,
        default=LookStatus.DRAFT,
        server_default=LookStatus.DRAFT.value,
        index=True,
    )
    is_listed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        index=True,
    )
    search_priority: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    images: Mapped[list["LookImage"]] = relationship(
        back_populates="look",
        cascade="all, delete-orphan",
        order_by="LookImage.position",
    )
    items: Mapped[list["LookItem"]] = relationship(
        back_populates="look",
        cascade="all, delete-orphan",
        order_by="LookItem.position",
    )

    @property
    def primary_image(self) -> "LookImage | None":
        primary = next((image for image in self.images if image.is_primary), None)
        return primary or (self.images[0] if self.images else None)

    @property
    def image_url(self) -> str | None:
        image = self.primary_image
        return image.url if image is not None else None


class LookImage(Base):
    __tablename__ = "look_images"
    __table_args__ = (
        CheckConstraint("position >= 0", name="ck_look_images_position_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    look_id: Mapped[int] = mapped_column(
        ForeignKey("looks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    alt_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    is_primary: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    look: Mapped[Look] = relationship(back_populates="images")

    @property
    def url(self) -> str:
        return f"/uploads/{self.file_path}"

    @property
    def image_url(self) -> str:
        return self.url


class LookItem(Base):
    __tablename__ = "look_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_look_items_quantity_positive"),
        UniqueConstraint("look_id", "product_id", name="uq_look_items_look_product"),
        Index("ix_look_items_look_position", "look_id", "position"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    look_id: Mapped[int] = mapped_column(
        ForeignKey("looks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    is_default_selected: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    look: Mapped[Look] = relationship(back_populates="items")
    product: Mapped[Product] = relationship(back_populates="look_items")


class Banner(Base):
    __tablename__ = "banners"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    subtitle: Mapped[str | None] = mapped_column(String(500), nullable=True)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    alt_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    target_type: Mapped[BannerTargetType | None] = mapped_column(
        Enum(BannerTargetType, name="banner_target_type", values_callable=_enum_values),
        nullable=True,
        index=True,
    )
    target_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    external_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    display_type: Mapped[BannerDisplayType] = mapped_column(
        Enum(BannerDisplayType, name="banner_display_type", values_callable=_enum_values),
        nullable=False,
        default=BannerDisplayType.HORIZONTAL,
        server_default=BannerDisplayType.HORIZONTAL.value,
        index=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        index=True,
    )
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    @property
    def url(self) -> str:
        return f"/uploads/{self.file_path}"

    @property
    def image_path(self) -> str:
        return self.file_path

    @property
    def image_url(self) -> str:
        return self.url


class PromoCode(Base):
    __tablename__ = "promo_codes"
    __table_args__ = (
        CheckConstraint("discount_value > 0", name="ck_promo_codes_discount_value_positive"),
        CheckConstraint(
            "usage_limit IS NULL OR usage_limit > 0",
            name="ck_promo_codes_usage_limit_positive",
        ),
        CheckConstraint(
            "per_user_limit IS NULL OR per_user_limit > 0",
            name="ck_promo_codes_per_user_limit_positive",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    discount_type: Mapped[DiscountType] = mapped_column(
        Enum(DiscountType, name="discount_type", values_callable=_enum_values),
        nullable=False,
    )
    discount_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    usage_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    per_user_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    orders: Mapped[list[Order]] = relationship(back_populates="promo_code")
    usages: Mapped[list["CouponUsage"]] = relationship(
        back_populates="promo_code",
        cascade="all, delete-orphan",
        order_by="CouponUsage.id",
    )


class CouponUsage(Base):
    __tablename__ = "coupon_usages"
    __table_args__ = (
        UniqueConstraint("promo_code_id", "order_id", name="uq_coupon_usages_promo_order"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    promo_code_id: Mapped[int] = mapped_column(
        ForeignKey("promo_codes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    promo_code: Mapped[PromoCode] = relationship(back_populates="usages")
    user: Mapped[User] = relationship(back_populates="coupon_usages")
    order: Mapped[Order | None] = relationship(back_populates="coupon_usages")


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (
        CheckConstraint("rating >= 1 AND rating <= 5", name="ck_reviews_rating_range"),
        UniqueConstraint("user_id", "product_id", name="uq_reviews_user_product"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ReviewStatus] = mapped_column(
        Enum(ReviewStatus, name="review_status", values_callable=_enum_values),
        nullable=False,
        default=ReviewStatus.PENDING,
        server_default=ReviewStatus.PENDING.value,
        index=True,
    )
    moderated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    moderated_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped[User] = relationship(
        back_populates="reviews",
        foreign_keys=[user_id],
    )
    product: Mapped[Product] = relationship(back_populates="reviews")
    order: Mapped[Order | None] = relationship(back_populates="reviews")
    moderated_by: Mapped[User | None] = relationship(
        back_populates="moderated_reviews",
        foreign_keys=[moderated_by_id],
    )


class Favorite(Base):
    __tablename__ = "favorites"
    __table_args__ = (
        UniqueConstraint("user_id", "product_id", name="uq_favorites_user_product"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    user: Mapped[User] = relationship(back_populates="favorites")
    product: Mapped[Product] = relationship(back_populates="favorites")


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    channel: Mapped[NotificationChannel] = mapped_column(
        Enum(NotificationChannel, name="notification_channel", values_callable=_enum_values),
        nullable=False,
        default=NotificationChannel.INTERNAL,
        server_default=NotificationChannel.INTERNAL.value,
        index=True,
    )
    status: Mapped[NotificationStatus] = mapped_column(
        Enum(NotificationStatus, name="notification_status", values_callable=_enum_values),
        nullable=False,
        default=NotificationStatus.PENDING,
        server_default=NotificationStatus.PENDING.value,
        index=True,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped[User | None] = relationship(back_populates="notifications")


class CustomerServiceNotificationDelivery(Base):
    __tablename__ = "customer_service_notification_deliveries"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    subscription_id: Mapped[int | None] = mapped_column(
        ForeignKey("customer_telegram_subscriptions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    event_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    channel: Mapped[NotificationChannel] = mapped_column(
        Enum(NotificationChannel, name="notification_channel", values_callable=_enum_values),
        nullable=False,
        default=NotificationChannel.TELEGRAM,
        server_default=NotificationChannel.TELEGRAM.value,
        index=True,
    )
    status: Mapped[CustomerServiceNotificationDeliveryStatus] = mapped_column(
        Enum(
            CustomerServiceNotificationDeliveryStatus,
            name="customer_service_notification_delivery_status",
            values_callable=_enum_values,
        ),
        nullable=False,
        default=CustomerServiceNotificationDeliveryStatus.PENDING,
        server_default=CustomerServiceNotificationDeliveryStatus.PENDING.value,
        index=True,
    )
    telegram_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_after_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class NotificationTemplate(Base):
    __tablename__ = "notification_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(150), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[NotificationTemplateCategory] = mapped_column(
        Enum(
            NotificationTemplateCategory,
            name="notification_template_category",
            values_callable=_enum_values,
        ),
        nullable=False,
        index=True,
    )
    channel: Mapped[NotificationChannel] = mapped_column(
        Enum(NotificationChannel, name="notification_channel", values_callable=_enum_values),
        nullable=False,
        default=NotificationChannel.TELEGRAM,
        server_default=NotificationChannel.TELEGRAM.value,
        index=True,
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    body_template: Mapped[str] = mapped_column(Text, nullable=False)
    parse_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    allowed_variables: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        index=True,
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    updated_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class BroadcastCampaign(Base):
    __tablename__ = "broadcast_campaigns"
    __table_args__ = (
        Index("ix_broadcast_campaigns_status_type", "status", "type"),
        Index("ix_broadcast_campaigns_scheduled_at", "scheduled_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    template_id: Mapped[int | None] = mapped_column(
        ForeignKey("notification_templates.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[BroadcastCampaignType] = mapped_column(
        Enum(BroadcastCampaignType, name="broadcast_campaign_type", values_callable=_enum_values),
        nullable=False,
        index=True,
    )
    status: Mapped[BroadcastCampaignStatus] = mapped_column(
        Enum(
            BroadcastCampaignStatus,
            name="broadcast_campaign_status",
            values_callable=_enum_values,
        ),
        nullable=False,
        default=BroadcastCampaignStatus.DRAFT,
        server_default=BroadcastCampaignStatus.DRAFT.value,
        index=True,
    )
    audience_filter: Mapped[dict[str, object]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    recipient_count_estimate: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    recipient_count_final: Mapped[int | None] = mapped_column(Integer, nullable=True)
    message_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    message_body: Mapped[str] = mapped_column(Text, nullable=False)
    parse_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    image_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    image_original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    image_mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    image_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    approved_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    cancelled_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    template: Mapped[NotificationTemplate | None] = relationship()

    @property
    def image_url(self) -> str | None:
        return f"/uploads/{self.image_path}" if self.image_path else None


class BroadcastDelivery(Base):
    __tablename__ = "broadcast_deliveries"
    __table_args__ = (
        UniqueConstraint(
            "campaign_id",
            "subscription_id",
            name="uq_broadcast_deliveries_campaign_subscription",
        ),
        Index("ix_broadcast_deliveries_campaign_status", "campaign_id", "status"),
        Index("ix_broadcast_deliveries_status_next_attempt_at", "status", "next_attempt_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("broadcast_campaigns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    subscription_id: Mapped[int] = mapped_column(
        ForeignKey("customer_telegram_subscriptions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    telegram_chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[BroadcastDeliveryStatus] = mapped_column(
        Enum(
            BroadcastDeliveryStatus,
            name="broadcast_delivery_status",
            values_callable=_enum_values,
        ),
        nullable=False,
        default=BroadcastDeliveryStatus.PENDING,
        server_default=BroadcastDeliveryStatus.PENDING.value,
        index=True,
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    telegram_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_after_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    campaign: Mapped[BroadcastCampaign] = relationship()
    subscription: Mapped[CustomerTelegramSubscription] = relationship()


class AnalyticsEvent(Base):
    __tablename__ = "analytics_events"
    __table_args__ = (
        Index("ix_analytics_events_telemetry_session", "telemetry_session_id"),
        Index("ix_analytics_events_request_id", "request_id"),
        Index("ix_analytics_events_created_event", "created_at", "event_name"),
        UniqueConstraint(
            "telemetry_session_id",
            "client_event_id",
            name="uq_analytics_events_telemetry_client_event",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    event_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    event_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    telemetry_session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    client_event_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    route: Mapped[str | None] = mapped_column(String(160), nullable=True)
    endpoint_scope: Mapped[str | None] = mapped_column(String(160), nullable=True)
    http_method: Mapped[str | None] = mapped_column(String(10), nullable=True)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metric_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    platform: Mapped[str | None] = mapped_column(String(32), nullable=True)
    app_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    network_state: Mapped[str | None] = mapped_column(String(24), nullable=True)
    connection_type: Mapped[str | None] = mapped_column(String(24), nullable=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    product_id: Mapped[int | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    promo_code_id: Mapped[int | None] = mapped_column(
        ForeignKey("promo_codes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    banner_id: Mapped[int | None] = mapped_column(
        ForeignKey("banners.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    event_metadata: Mapped[dict[str, object] | None] = mapped_column(
        "metadata",
        JSON,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    before_data: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    after_data: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    audit_metadata: Mapped[dict[str, object] | None] = mapped_column(
        "metadata",
        JSON,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )
