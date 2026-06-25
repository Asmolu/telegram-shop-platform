import asyncio
import json
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


EXPECTED_COLUMNS = {
    "event_version",
    "telemetry_session_id",
    "client_event_id",
    "request_id",
    "route",
    "endpoint_scope",
    "http_method",
    "http_status",
    "duration_ms",
    "metric_value",
    "error_category",
    "platform",
    "app_version",
    "network_state",
    "connection_type",
}


async def insert_legacy() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                INSERT INTO analytics_events (event_name, metadata, created_at)
                VALUES ('legacy.event', '{"legacy": true}'::jsonb, now())
                """
            )
        )
    await engine.dispose()


async def verify_head() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    async with engine.begin() as conn:
        columns = {
            row[0]
            for row in (
                await conn.execute(
                    text(
                        """
                        SELECT column_name
                        FROM information_schema.columns
                        WHERE table_name = 'analytics_events'
                        """
                    )
                )
            )
        }
        missing = sorted(EXPECTED_COLUMNS - columns)
        legacy_count = (
            await conn.execute(
                text("SELECT count(*) FROM analytics_events WHERE event_name = 'legacy.event'")
            )
        ).scalar_one()
        await conn.execute(
            text(
                """
                INSERT INTO analytics_events (
                    event_name,
                    event_version,
                    telemetry_session_id,
                    client_event_id,
                    request_id,
                    route,
                    endpoint_scope,
                    http_method,
                    http_status,
                    duration_ms,
                    metric_value,
                    error_category,
                    platform,
                    app_version,
                    network_state,
                    connection_type,
                    metadata,
                    created_at
                )
                VALUES (
                    'route.rendered',
                    1,
                    'session-test',
                    'event-test',
                    'request-test',
                    '/products/_id',
                    '/products/_id',
                    'GET',
                    200,
                    42,
                    42.5,
                    NULL,
                    'web',
                    'local-test',
                    'online',
                    '4g',
                    '{"viewport_class": "medium"}'::jsonb,
                    now()
                )
                """
            )
        )
        telemetry_count = (
            await conn.execute(
                text(
                    """
                    SELECT count(*)
                    FROM analytics_events
                    WHERE telemetry_session_id = 'session-test'
                    """
                )
            )
        ).scalar_one()
    await engine.dispose()
    print(
        json.dumps(
            {
                "missing_columns": missing,
                "legacy_count": legacy_count,
                "telemetry_count": telemetry_count,
            },
            sort_keys=True,
        )
    )
    if missing or legacy_count != 1 or telemetry_count != 1:
        raise SystemExit(1)


async def main() -> None:
    mode = sys.argv[1]
    if mode == "insert-legacy":
        await insert_legacy()
        return
    if mode == "verify-head":
        await verify_head()
        return
    raise SystemExit(f"unknown mode: {mode}")


asyncio.run(main())
