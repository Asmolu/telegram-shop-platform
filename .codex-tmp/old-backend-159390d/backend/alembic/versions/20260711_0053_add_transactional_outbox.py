"""Add transactional outbox and durable notification consumption keys.

Revision ID: 20260711_0053
Revises: 20260710_0052
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260711_0053"
down_revision: str | None = "20260710_0052"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OUTBOX_STATUS_ENUM = postgresql.ENUM(
    "PENDING", "PROCESSING", "PROCESSED", "FAILED", name="outbox_status", create_type=False
)
OUTBOX_DELIVERY_STATUS_ENUM = postgresql.ENUM(
    "PENDING", "PROCESSED", "FAILED", name="outbox_delivery_status", create_type=False
)


def upgrade() -> None:
    bind = op.get_bind()
    postgresql.ENUM("PENDING", "PROCESSING", "PROCESSED", "FAILED", name="outbox_status").create(
        bind, checkfirst=True
    )
    postgresql.ENUM("PENDING", "PROCESSED", "FAILED", name="outbox_delivery_status").create(
        bind, checkfirst=True
    )

    op.create_table(
        "outbox_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_name", sa.String(length=100), nullable=False),
        sa.Column("aggregate_type", sa.String(length=100), nullable=False),
        sa.Column("aggregate_id", sa.String(length=255), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", OUTBOX_STATUS_ENUM, server_default="PENDING", nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.String(length=255), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("attempt_count >= 0", name="ck_outbox_events_attempt_count"),
        sa.CheckConstraint("max_attempts > 0", name="ck_outbox_events_max_attempts"),
        sa.UniqueConstraint("event_id", name="uq_outbox_events_event_id"),
    )
    op.create_index(
        "ix_outbox_events_poll", "outbox_events", ["status", "next_attempt_at", "created_at"]
    )
    op.create_index("ix_outbox_events_locked", "outbox_events", ["status", "locked_at"])
    op.create_index(
        "ix_outbox_events_aggregate", "outbox_events", ["aggregate_type", "aggregate_id"]
    )

    op.create_table(
        "outbox_deliveries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "outbox_event_id",
            sa.Integer(),
            sa.ForeignKey("outbox_events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("consumer", sa.String(length=50), nullable=False),
        sa.Column("status", OUTBOX_DELIVERY_STATUS_ENUM, server_default="PENDING", nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("attempt_count >= 0", name="ck_outbox_deliveries_attempt_count"),
        sa.UniqueConstraint("outbox_event_id", "consumer", name="uq_outbox_delivery_consumer"),
    )
    op.create_index(
        "ix_outbox_deliveries_event_status", "outbox_deliveries", ["outbox_event_id", "status"]
    )

    for table, constraint in (
        ("notifications", "uq_notifications_source_event_consumer"),
        (
            "customer_service_notification_deliveries",
            "uq_customer_service_deliveries_source_event_consumer",
        ),
    ):
        op.add_column(
            table, sa.Column("source_event_id", postgresql.UUID(as_uuid=True), nullable=True)
        )
        op.add_column(table, sa.Column("source_consumer", sa.String(length=50), nullable=True))
        op.create_unique_constraint(constraint, table, ["source_event_id", "source_consumer"])


def downgrade() -> None:
    for table, constraint in (
        (
            "customer_service_notification_deliveries",
            "uq_customer_service_deliveries_source_event_consumer",
        ),
        ("notifications", "uq_notifications_source_event_consumer"),
    ):
        op.drop_constraint(constraint, table, type_="unique")
        op.drop_column(table, "source_consumer")
        op.drop_column(table, "source_event_id")
    op.drop_index("ix_outbox_deliveries_event_status", table_name="outbox_deliveries")
    op.drop_table("outbox_deliveries")
    op.drop_index("ix_outbox_events_aggregate", table_name="outbox_events")
    op.drop_index("ix_outbox_events_locked", table_name="outbox_events")
    op.drop_index("ix_outbox_events_poll", table_name="outbox_events")
    op.drop_table("outbox_events")
    postgresql.ENUM(name="outbox_delivery_status").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="outbox_status").drop(op.get_bind(), checkfirst=True)
