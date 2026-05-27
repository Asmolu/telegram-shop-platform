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
