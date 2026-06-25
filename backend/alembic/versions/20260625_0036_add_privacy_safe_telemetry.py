"""add privacy safe telemetry fields

Revision ID: 20260625_0036
Revises: 20260624_0035
Create Date: 2026-06-25 02:40:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260625_0036"
down_revision: str | None = "20260624_0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("analytics_events", sa.Column("event_version", sa.Integer(), nullable=True))
    op.add_column(
        "analytics_events",
        sa.Column("telemetry_session_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "analytics_events",
        sa.Column("client_event_id", sa.String(length=64), nullable=True),
    )
    op.add_column("analytics_events", sa.Column("request_id", sa.String(length=64), nullable=True))
    op.add_column("analytics_events", sa.Column("route", sa.String(length=160), nullable=True))
    op.add_column(
        "analytics_events",
        sa.Column("endpoint_scope", sa.String(length=160), nullable=True),
    )
    op.add_column(
        "analytics_events",
        sa.Column("http_method", sa.String(length=10), nullable=True),
    )
    op.add_column("analytics_events", sa.Column("http_status", sa.Integer(), nullable=True))
    op.add_column("analytics_events", sa.Column("duration_ms", sa.Integer(), nullable=True))
    op.add_column("analytics_events", sa.Column("metric_value", sa.Float(), nullable=True))
    op.add_column(
        "analytics_events",
        sa.Column("error_category", sa.String(length=64), nullable=True),
    )
    op.add_column("analytics_events", sa.Column("platform", sa.String(length=32), nullable=True))
    op.add_column("analytics_events", sa.Column("app_version", sa.String(length=80), nullable=True))
    op.add_column(
        "analytics_events",
        sa.Column("network_state", sa.String(length=24), nullable=True),
    )
    op.add_column(
        "analytics_events",
        sa.Column("connection_type", sa.String(length=24), nullable=True),
    )
    op.create_index(
        "ix_analytics_events_telemetry_session",
        "analytics_events",
        ["telemetry_session_id"],
    )
    op.create_index("ix_analytics_events_request_id", "analytics_events", ["request_id"])
    op.create_index(
        "ix_analytics_events_created_event",
        "analytics_events",
        ["created_at", "event_name"],
    )
    op.create_unique_constraint(
        "uq_analytics_events_telemetry_client_event",
        "analytics_events",
        ["telemetry_session_id", "client_event_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_analytics_events_telemetry_client_event",
        "analytics_events",
        type_="unique",
    )
    op.drop_index("ix_analytics_events_created_event", table_name="analytics_events")
    op.drop_index("ix_analytics_events_request_id", table_name="analytics_events")
    op.drop_index("ix_analytics_events_telemetry_session", table_name="analytics_events")
    op.drop_column("analytics_events", "connection_type")
    op.drop_column("analytics_events", "network_state")
    op.drop_column("analytics_events", "app_version")
    op.drop_column("analytics_events", "platform")
    op.drop_column("analytics_events", "error_category")
    op.drop_column("analytics_events", "metric_value")
    op.drop_column("analytics_events", "duration_ms")
    op.drop_column("analytics_events", "http_status")
    op.drop_column("analytics_events", "http_method")
    op.drop_column("analytics_events", "endpoint_scope")
    op.drop_column("analytics_events", "route")
    op.drop_column("analytics_events", "request_id")
    op.drop_column("analytics_events", "client_event_id")
    op.drop_column("analytics_events", "telemetry_session_id")
    op.drop_column("analytics_events", "event_version")
