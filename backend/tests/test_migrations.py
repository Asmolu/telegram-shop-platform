import importlib.util
from pathlib import Path


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
