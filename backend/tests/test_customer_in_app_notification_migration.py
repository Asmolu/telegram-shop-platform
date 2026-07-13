import os

import pytest
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine

from app.db.models import CustomerInAppNotification

MIGRATED_POSTGRES_URL = os.getenv("TEST_MIGRATED_POSTGRES_URL")


@pytest.mark.skipif(
    not MIGRATED_POSTGRES_URL,
    reason="TEST_MIGRATED_POSTGRES_URL is required",
)
@pytest.mark.asyncio
async def test_real_migrated_notification_indexes_match_sqlalchemy_metadata() -> None:
    engine = create_async_engine(MIGRATED_POSTGRES_URL)
    try:
        async with engine.connect() as connection:
            indexes, unique_constraints = await connection.run_sync(_notification_contract)
    finally:
        await engine.dispose()

    expected_indexes = {index.name for index in CustomerInAppNotification.__table__.indexes}
    actual_indexes = {
        index["name"]
        for index in indexes
        if index.get("duplicates_constraint") is None
    }
    assert actual_indexes == expected_indexes
    assert {constraint["name"] for constraint in unique_constraints} == {
        "uq_customer_in_app_notifications_source_key"
    }


def _notification_contract(connection):
    inspector = inspect(connection)
    return (
        inspector.get_indexes("customer_in_app_notifications"),
        inspector.get_unique_constraints("customer_in_app_notifications"),
    )
