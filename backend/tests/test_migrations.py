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
