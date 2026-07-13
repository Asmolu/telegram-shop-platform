from __future__ import annotations

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from app.core.config import settings
from app.db import models  # noqa: F401 - required for Alembic metadata discovery
from app.db.base import Base

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# These PostgreSQL expression/partial indexes are intentionally owned by their
# hand-written migrations. They cannot be represented portably in the shared
# SQLite/PostgreSQL ORM metadata, so autogenerate must leave them intact.
MIGRATION_MANAGED_INDEXES = {
    "ix_products_description_trgm",
    "ix_products_name_trgm",
    "ix_products_search_aliases_trgm",
    "ix_products_slug_trgm",
    "uq_user_blocks_active_telegram_id",
    "uq_user_blocks_active_user_id",
    "uq_user_blocks_active_username",
}


def include_object(object_, name, type_, reflected, compare_to) -> bool:
    del object_
    if (
        type_ == "index"
        and reflected
        and compare_to is None
        and name in MIGRATION_MANAGED_INDEXES
    ):
        return False
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = settings.database_url

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
