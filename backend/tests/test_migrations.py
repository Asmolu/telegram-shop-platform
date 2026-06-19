import importlib.util
from pathlib import Path

from app.db.models import (
    Banner,
    BannerDisplayType,
    BannerTargetType,
    BroadcastCampaign,
    BroadcastCampaignStatus,
    BroadcastCampaignType,
    BroadcastDelivery,
    BroadcastDeliveryStatus,
    Category,
    CustomerTelegramSubscription,
    ManualPayment,
    ManualPaymentCurrency,
    ManualPaymentMethod,
    ManualPaymentStatus,
    Notification,
    NotificationChannel,
    NotificationStatus,
    NotificationTemplate,
    NotificationTemplateCategory,
    Order,
    OrderDeliveryMethod,
    OrderItem,
    PendingSellerRegistration,
    Product,
    ProductCategory,
    ProductImageBadgeColor,
    ProductImageBadgePosition,
    ProductImageBadgeType,
    ProductRelatedProduct,
    ProductSizeGrid,
    ProductVariant,
    SellerPaymentSettings,
    SellerRegistrationStatus,
    Tag,
    User,
)


def test_user_role_enum_migration_disables_implicit_type_creation() -> None:
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260527_0001_create_users.py"
    )
    spec = importlib.util.spec_from_file_location("create_users_migration", migration_path)
    assert spec is not None
    assert spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    assert migration.USER_ROLE_ENUM.name == "user_role"
    assert migration.USER_ROLE_ENUM.enums == ["USER", "SELLER", "ADMIN"]
    assert migration.USER_ROLE_ENUM.create_type is False


def test_product_status_enum_migration_disables_implicit_type_creation() -> None:
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260527_0002_create_product_catalog.py"
    )
    spec = importlib.util.spec_from_file_location(
        "create_product_catalog_migration",
        migration_path,
    )
    assert spec is not None
    assert spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    assert migration.PRODUCT_STATUS_ENUM.name == "product_status"
    assert migration.PRODUCT_STATUS_ENUM.enums == [
        "DRAFT",
        "ACTIVE",
        "OUT_OF_STOCK",
        "ARCHIVED",
    ]
    assert migration.PRODUCT_STATUS_ENUM.create_type is False


def test_product_variants_migration_adds_inventory_constraints() -> None:
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260527_0004_add_product_variants.py"
    )
    content = migration_path.read_text()

    assert "product_variants" in content
    assert "ck_product_variants_stock_non_negative" in content
    assert "ck_product_variants_reserved_non_negative" in content
    assert "ck_product_variants_reserved_not_above_stock" in content


def test_cart_migration_adds_cart_tables_and_constraints() -> None:
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260527_0005_add_cart_tables.py"
    )
    content = migration_path.read_text()

    assert "carts" in content
    assert "cart_items" in content
    assert "ck_cart_items_quantity_positive" in content
    assert "uq_cart_items_cart_variant" in content


def test_order_migration_adds_order_tables_status_enum_and_snapshot_constraints() -> None:
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260527_0006_add_order_tables.py"
    )
    spec = importlib.util.spec_from_file_location("add_order_tables_migration", migration_path)
    assert spec is not None
    assert spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    content = migration_path.read_text()

    assert migration.ORDER_STATUS_ENUM.name == "order_status"
    assert migration.ORDER_STATUS_ENUM.enums == [
        "NEW",
        "PROCESSING",
        "SHIPPED",
        "DELIVERED",
        "CANCELLED",
    ]
    assert migration.ORDER_STATUS_ENUM.create_type is False
    assert "orders" in content
    assert "order_items" in content
    assert "ck_order_items_quantity_positive" in content
    assert "product_name" in content
    assert "variant_sku" in content


def test_promo_code_migration_adds_discount_enum_tables_and_order_snapshot() -> None:
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260527_0007_add_promo_code_tables.py"
    )
    spec = importlib.util.spec_from_file_location("add_promo_code_tables_migration", migration_path)
    assert spec is not None
    assert spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    content = migration_path.read_text()

    assert migration.DISCOUNT_TYPE_ENUM.name == "discount_type"
    assert migration.DISCOUNT_TYPE_ENUM.enums == ["PERCENT", "FIXED"]
    assert migration.DISCOUNT_TYPE_ENUM.create_type is False
    assert "promo_codes" in content
    assert "coupon_usages" in content
    assert "promo_code_code" in content
    assert "ck_promo_codes_discount_value_positive" in content
    assert "uq_coupon_usages_promo_order" in content


def test_reviews_favorites_migration_adds_review_status_enum_and_constraints() -> None:
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260527_0008_add_reviews_and_favorites.py"
    )
    spec = importlib.util.spec_from_file_location(
        "add_reviews_and_favorites_migration",
        migration_path,
    )
    assert spec is not None
    assert spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    content = migration_path.read_text()

    assert migration.REVIEW_STATUS_ENUM.name == "review_status"
    assert migration.REVIEW_STATUS_ENUM.enums == ["PENDING", "APPROVED", "REJECTED"]
    assert migration.REVIEW_STATUS_ENUM.create_type is False
    assert "reviews" in content
    assert "favorites" in content
    assert "ck_reviews_rating_range" in content
    assert "uq_reviews_user_product" in content
    assert "uq_favorites_user_product" in content


def test_sprint_9_banner_migration_adds_management_fields() -> None:
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260527_0009_extend_banners_for_seller_panel.py"
    )
    spec = importlib.util.spec_from_file_location("extend_banners_migration", migration_path)
    assert spec is not None
    assert spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    content = migration_path.read_text()

    assert migration.BANNER_TARGET_TYPE_ENUM.name == "banner_target_type"
    assert migration.BANNER_TARGET_TYPE_ENUM.enums == [
        "product",
        "category",
        "promo",
        "external_url",
    ]
    assert migration.BANNER_TARGET_TYPE_ENUM.create_type is False
    assert "target_type" in content
    assert "external_url" in content
    assert "is_active" in content


def test_sprint_10_notification_migration_adds_status_and_channel_enums() -> None:
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260527_0010_add_notifications.py"
    )
    spec = importlib.util.spec_from_file_location("add_notifications_migration", migration_path)
    assert spec is not None
    assert spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    content = migration_path.read_text()

    assert migration.NOTIFICATION_CHANNEL_ENUM.name == "notification_channel"
    assert migration.NOTIFICATION_CHANNEL_ENUM.enums == ["telegram", "internal"]
    assert migration.NOTIFICATION_CHANNEL_ENUM.create_type is False
    assert migration.NOTIFICATION_STATUS_ENUM.name == "notification_status"
    assert migration.NOTIFICATION_STATUS_ENUM.enums == ["pending", "sent", "failed"]
    assert migration.NOTIFICATION_STATUS_ENUM.create_type is False
    assert "notifications" in content
    assert "payload" in content
    assert "error_message" in content
    assert "sent_at" in content


def test_sprint_11_migration_adds_analytics_and_audit_tables() -> None:
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260529_0011_add_analytics_and_audit.py"
    )
    content = migration_path.read_text()

    assert "analytics_events" in content
    assert "audit_logs" in content
    assert "event_name" in content
    assert "actor_user_id" in content
    assert "before_data" in content
    assert "after_data" in content
    assert "metadata" in content


def test_sprint_14_migration_adds_missing_production_indexes() -> None:
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260530_0012_add_sprint14_indexes.py"
    )
    content = migration_path.read_text()

    assert "CREATE INDEX IF NOT EXISTS ix_products_created_at" in content
    assert "CREATE INDEX IF NOT EXISTS ix_orders_created_at" in content
    assert "CREATE INDEX IF NOT EXISTS ix_notifications_created_at" in content


def test_seller_auth_migration_adds_credentials_and_pending_registration_tables() -> None:
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260601_0013_add_seller_auth_tables.py"
    )
    spec = importlib.util.spec_from_file_location("add_seller_auth_tables", migration_path)
    assert spec is not None
    assert spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    content = migration_path.read_text()

    assert migration.SELLER_REGISTRATION_STATUS_ENUM.name == "seller_registration_status"
    assert migration.SELLER_REGISTRATION_STATUS_ENUM.enums == [
        "pending",
        "verified",
        "expired",
        "rejected",
    ]
    assert migration.SELLER_REGISTRATION_STATUS_ENUM.create_type is False
    assert "seller_credentials" in content
    assert "pending_seller_registrations" in content
    assert "password_hash" in content
    assert "bot_start_token_hash" in content
    assert "verification_code_hash" in content


def test_seller_registration_status_model_matches_head_migration() -> None:
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260602_0015_add_seller_registration_approval_flow.py"
    )
    spec = importlib.util.spec_from_file_location(
        "add_seller_registration_approval_flow",
        migration_path,
    )
    assert spec is not None
    assert spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    content = migration_path.read_text()

    expected_values = [status.value for status in SellerRegistrationStatus]
    status_type = PendingSellerRegistration.__table__.c.status.type

    assert expected_values == [
        "PENDING",
        "AWAITING_APPROVAL",
        "APPROVED",
        "VERIFIED",
        "EXPIRED",
        "REJECTED",
    ]
    assert status_type.name == "seller_registration_status"
    assert status_type.enums == expected_values
    assert migration.CANONICAL_SELLER_REGISTRATION_STATUS_VALUES == tuple(expected_values)
    assert "approval_expires_at" in content
    assert "AWAITING_APPROVAL" in content
    assert "APPROVED" in content
    assert "status::text" in content
    assert "ALTER COLUMN status DROP DEFAULT" in content
    assert "ALTER COLUMN status SET DEFAULT" in content


def test_model_enums_bind_database_values_not_member_names() -> None:
    assert Banner.__table__.c.target_type.type.enums == [
        BannerTargetType.PRODUCT.value,
        BannerTargetType.CATEGORY.value,
        BannerTargetType.PROMO.value,
        BannerTargetType.EXTERNAL_URL.value,
    ]
    assert Banner.__table__.c.display_type.type.enums == [
        BannerDisplayType.HORIZONTAL.value,
        BannerDisplayType.VERTICAL.value,
        BannerDisplayType.POPUP.value,
        BannerDisplayType.AGGRESSIVE_POPUP.value,
    ]
    assert Notification.__table__.c.channel.type.enums == [
        NotificationChannel.TELEGRAM.value,
        NotificationChannel.INTERNAL.value,
    ]
    assert Notification.__table__.c.status.type.enums == [
        NotificationStatus.PENDING.value,
        NotificationStatus.SENT.value,
        NotificationStatus.FAILED.value,
    ]


def test_customer_notifications_migration_adds_subscription_registry() -> None:
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260604_0016_add_customer_telegram_subscriptions.py"
    )
    content = migration_path.read_text()

    assert "customer_telegram_subscriptions" in content
    assert "telegram_user_id" in content
    assert "telegram_chat_id" in content
    assert "service_opt_in" in content
    assert "marketing_opt_in" in content
    assert "uq_customer_telegram_subscriptions_user_id" in content
    assert "uq_customer_telegram_subscriptions_telegram_user_id" in content


def test_customer_subscription_model_has_unique_user_and_telegram_constraints() -> None:
    table = CustomerTelegramSubscription.__table__
    constraint_names = {constraint.name for constraint in table.constraints}

    assert "uq_customer_telegram_subscriptions_user_id" in constraint_names
    assert "uq_customer_telegram_subscriptions_telegram_user_id" in constraint_names
    assert table.c.telegram_user_id.index is True
    assert table.c.telegram_chat_id.index is True


def test_customer_campaign_migration_adds_phase_2_tables_and_enums() -> None:
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260605_0018_add_customer_campaign_tables.py"
    )
    spec = importlib.util.spec_from_file_location("add_customer_campaign_tables", migration_path)
    assert spec is not None
    assert spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    content = migration_path.read_text()

    assert migration.NOTIFICATION_TEMPLATE_CATEGORY_ENUM.enums == ["service", "marketing"]
    assert migration.BROADCAST_CAMPAIGN_TYPE_ENUM.enums == ["service", "marketing"]
    assert migration.BROADCAST_CAMPAIGN_STATUS_ENUM.enums == [
        "draft",
        "scheduled",
        "sending",
        "paused",
        "completed",
        "cancelled",
        "failed",
    ]
    assert migration.BROADCAST_DELIVERY_STATUS_ENUM.enums == [
        "pending",
        "sending",
        "sent",
        "failed",
        "skipped",
        "blocked",
        "rate_limited",
    ]
    assert "notification_templates" in content
    assert "broadcast_campaigns" in content
    assert "broadcast_deliveries" in content
    assert "uq_broadcast_deliveries_campaign_subscription" in content
    assert "ix_broadcast_deliveries_status_next_attempt_at" in content


def test_customer_campaign_models_bind_database_values_and_constraints() -> None:
    template_table = NotificationTemplate.__table__
    campaign_table = BroadcastCampaign.__table__
    delivery_table = BroadcastDelivery.__table__
    delivery_constraints = {constraint.name for constraint in delivery_table.constraints}

    assert template_table.c.category.type.enums == [
        NotificationTemplateCategory.SERVICE.value,
        NotificationTemplateCategory.MARKETING.value,
    ]
    assert campaign_table.c.type.type.enums == [
        BroadcastCampaignType.SERVICE.value,
        BroadcastCampaignType.MARKETING.value,
    ]
    assert campaign_table.c.status.type.enums == [
        status.value for status in BroadcastCampaignStatus
    ]
    assert delivery_table.c.status.type.enums == [
        status.value for status in BroadcastDeliveryStatus
    ]
    assert "uq_broadcast_deliveries_campaign_subscription" in delivery_constraints


def test_order_item_color_and_banner_display_type_migration() -> None:
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260607_0019_add_order_item_color_and_banner_display_type.py"
    )
    spec = importlib.util.spec_from_file_location(
        "add_order_item_color_and_banner_display_type",
        migration_path,
    )
    assert spec is not None
    assert spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    content = migration_path.read_text()

    assert migration.BANNER_DISPLAY_TYPE_ENUM.name == "banner_display_type"
    assert migration.BANNER_DISPLAY_TYPE_ENUM.enums == [
        "horizontal",
        "vertical",
        "popup",
        "aggressive_popup",
    ]
    assert "variant_color" in content
    assert "display_type" in content
    assert "ix_banners_display_type" in content


def test_product_search_foundation_migration_and_model_constraints() -> None:
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260608_0020_add_product_search_foundation.py"
    )
    content = migration_path.read_text()
    table = Product.__table__
    constraint_names = {constraint.name for constraint in table.constraints}

    assert "CREATE EXTENSION IF NOT EXISTS pg_trgm" in content
    assert "old_price" in content
    assert "search_priority" in content
    assert "search_aliases" in content
    assert "ix_products_search_priority" in content
    assert "ix_products_name_trgm" in content
    assert "ix_products_search_aliases_trgm" in content
    assert "ck_products_old_price_above_base_price" in constraint_names
    assert "ck_products_search_priority_range" in constraint_names
    assert table.c.old_price.nullable is True
    assert table.c.search_priority.default.arg == 2


def test_product_category_assignments_migration_and_model_constraints() -> None:
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260609_0021_add_product_category_assignments.py"
    )
    content = migration_path.read_text()
    table = ProductCategory.__table__
    constraint_names = {constraint.name for constraint in table.constraints}
    index_names = {index.name for index in table.indexes}

    assert "product_categories" in content
    assert "INSERT INTO product_categories" in content
    assert "WHERE category_id IS NOT NULL" in content
    assert "ck_product_categories_priority_range" in constraint_names
    assert "uq_product_categories_product_category" in constraint_names
    assert "uq_product_categories_product_priority" in constraint_names
    assert "ix_product_categories_category_priority" in index_names
    assert table.c.priority.nullable is False


def test_product_size_grid_migration_and_model_contract() -> None:
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260611_0022_add_product_size_grids.py"
    )
    content = migration_path.read_text()
    product_table = Product.__table__
    order_item_table = OrderItem.__table__
    variant_index_names = {index.name for index in ProductVariant.__table__.indexes}

    assert "product_size_grid" in content
    assert "clothing_alpha" in content
    assert "shoes_ru" in content
    assert Product.__table__.c.size_grid.type.enums == [
        ProductSizeGrid.CLOTHING_ALPHA.value,
        ProductSizeGrid.SHOES_EU.value,
        ProductSizeGrid.SHOES_RU.value,
    ]
    assert product_table.c.size_grid.nullable is False
    assert product_table.c.size_grid.default.arg == ProductSizeGrid.CLOTHING_ALPHA
    assert order_item_table.c.variant_size_grid.nullable is False
    assert order_item_table.c.variant_size_grid.default.arg == ProductSizeGrid.CLOTHING_ALPHA
    assert "ix_product_variants_size_active_product" in variant_index_names


def test_eu_footwear_size_grid_migration_is_additive() -> None:
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260619_0033_add_eu_footwear_size_grid.py"
    )
    content = migration_path.read_text()

    assert "ALTER TYPE product_size_grid ADD VALUE IF NOT EXISTS 'shoes_eu'" in content
    assert "UPDATE products" not in content
    assert "UPDATE order_items" not in content


def test_related_products_and_image_badges_migration_contract() -> None:
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260612_0023_add_related_products_and_image_badges.py"
    )
    spec = importlib.util.spec_from_file_location(
        "add_related_products_and_image_badges",
        migration_path,
    )
    assert spec is not None
    assert spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    content = migration_path.read_text()
    related_table = ProductRelatedProduct.__table__
    constraint_names = {constraint.name for constraint in related_table.constraints}
    index_names = {index.name for index in related_table.indexes}

    assert migration.PRODUCT_IMAGE_BADGE_TYPE_ENUM.enums == [
        "none",
        "new",
        "sale",
        "hit",
        "exclusive",
        "custom",
    ]
    assert "product_related_products" in content
    assert Product.__table__.c.image_badge_type.default.arg == ProductImageBadgeType.NONE
    assert Product.__table__.c.image_badge_text.type.length == 20
    assert "ck_product_related_products_not_self" in constraint_names
    assert "uq_product_related_products_pair" in constraint_names
    assert "uq_product_related_products_position" in constraint_names
    assert "ix_product_related_products_product_position" in index_names


def test_configurable_product_image_badges_migration_contract() -> None:
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260618_0031_configurable_product_image_badges.py"
    )
    spec = importlib.util.spec_from_file_location(
        "configurable_product_image_badges",
        migration_path,
    )
    assert spec is not None
    assert spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    product_table = Product.__table__

    assert migration.down_revision == "20260618_0030"
    assert migration.PRODUCT_IMAGE_BADGE_COLOR_ENUM.enums == [
        "purple",
        "pink",
        "red",
        "orange",
        "blue",
        "green",
        "black",
        "white",
    ]
    assert migration.PRODUCT_IMAGE_BADGE_POSITION_ENUM.enums == [
        "top-left",
        "top-right",
        "bottom-left",
        "bottom-right",
    ]
    assert product_table.c.image_badge_color.nullable is True
    assert product_table.c.image_badge_position.nullable is True
    assert product_table.c.image_badge_color.type.enum_class == ProductImageBadgeColor
    assert product_table.c.image_badge_position.type.enum_class == ProductImageBadgePosition


def test_tag_images_migration_and_model_contract() -> None:
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260613_0024_add_tag_images.py"
    )
    spec = importlib.util.spec_from_file_location("add_tag_images", migration_path)
    assert spec is not None
    assert spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    content = migration_path.read_text()

    assert migration.down_revision == "20260612_0023"
    assert "image_path" in content
    assert Tag.__table__.c.image_path.nullable is True
    assert Tag.__table__.c.image_path.type.length == 1024


def test_customer_personal_data_migration_and_model_contract() -> None:
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260613_0025_add_customer_personal_data.py"
    )
    spec = importlib.util.spec_from_file_location("add_customer_personal_data", migration_path)
    assert spec is not None
    assert spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    content = migration_path.read_text()
    table = User.__table__

    assert migration.down_revision == "20260613_0024"
    for column_name in (
        "recipient_name",
        "contact_phone",
        "city",
        "height_cm",
        "weight_kg",
        "telegram_username",
        "persistent_comment",
    ):
        assert column_name in content
        assert table.c[column_name].nullable is True
    assert table.c.recipient_name.type.length == 255
    assert table.c.contact_phone.type.length == 32
    assert table.c.city.type.length == 255
    assert table.c.weight_kg.type.precision == 6
    assert table.c.weight_kg.type.scale == 2
    assert table.c.telegram_username.type.length == 32
    assert table.c.persistent_comment.type.length == 500


def test_category_images_migration_and_model_contract() -> None:
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260613_0026_add_category_images.py"
    )
    spec = importlib.util.spec_from_file_location("add_category_images", migration_path)
    assert spec is not None
    assert spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    content = migration_path.read_text()

    assert migration.down_revision == "20260613_0025"
    assert "image_path" in content
    assert Category.__table__.c.image_path.nullable is True
    assert Category.__table__.c.image_path.type.length == 1024


def test_manual_sbp_payment_migration_and_model_contract() -> None:
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260614_0027_add_manual_sbp_payments.py"
    )
    spec = importlib.util.spec_from_file_location("add_manual_sbp_payments", migration_path)
    assert spec is not None
    assert spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    content = migration_path.read_text()

    assert migration.down_revision == "20260613_0026"
    assert migration.MANUAL_PAYMENT_METHOD_ENUM.enums == [ManualPaymentMethod.SBP_PHONE.value]
    assert migration.MANUAL_PAYMENT_CURRENCY_ENUM.enums == [ManualPaymentCurrency.RUB.value]
    assert migration.MANUAL_PAYMENT_STATUS_ENUM.enums == [
        status.value for status in ManualPaymentStatus
    ]
    assert "seller_payment_settings" in content
    assert "manual_payments" in content
    assert "stock_released_at" in content
    assert "ix_manual_payments_status_expires_at" in content
    assert SellerPaymentSettings.__table__.c.seller_phone_e164.nullable is True
    assert ManualPayment.__table__.c.order_id.unique is True
    assert ManualPayment.__table__.c.receipt_image_path.type.length == 1024


def test_order_delivery_method_migration_and_model_contract() -> None:
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260615_0028_add_order_delivery_method.py"
    )
    spec = importlib.util.spec_from_file_location("add_order_delivery_method", migration_path)
    assert spec is not None
    assert spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    assert migration.down_revision == "20260614_0027"
    assert migration.ORDER_DELIVERY_METHOD_ENUM.enums == [
        method.value for method in OrderDeliveryMethod
    ]
    assert migration.ORDER_DELIVERY_METHOD_ENUM.create_type is False
    assert Order.__table__.c.delivery_method.nullable is True


def test_manual_payment_telegram_message_refs_migration_and_model_contract() -> None:
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260615_0029_add_manual_payment_telegram_message_refs.py"
    )
    spec = importlib.util.spec_from_file_location("add_manual_payment_message_refs", migration_path)
    assert spec is not None
    assert spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    assert migration.down_revision == "20260615_0028"
    assert ManualPayment.__table__.c.seller_telegram_chat_id.nullable is True
    assert ManualPayment.__table__.c.seller_telegram_message_id.nullable is True


def test_product_brand_migration_and_model_contract() -> None:
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260618_0030_add_product_brand.py"
    )
    spec = importlib.util.spec_from_file_location("add_product_brand", migration_path)
    assert spec is not None
    assert spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    content = migration_path.read_text()

    assert migration.down_revision == "20260615_0029"
    assert "brand" in content
    assert Product.__table__.c.brand.nullable is True
    assert Product.__table__.c.brand.type.length == 120
