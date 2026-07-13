"""Add analytics and audit tables

Revision ID: 20260529_0011
Revises: 20260527_0010
Create Date: 2026-05-29 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260529_0011"
down_revision: str | None = "20260527_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "analytics_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_name", sa.String(length=100), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("order_id", sa.Integer(), nullable=True),
        sa.Column("promo_code_id", sa.Integer(), nullable=True),
        sa.Column("banner_id", sa.Integer(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["promo_code_id"], ["promo_codes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["banner_id"], ["banners.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_analytics_events_event_name"),
        "analytics_events",
        ["event_name"],
        unique=False,
    )
    op.create_index(op.f("ix_analytics_events_user_id"), "analytics_events", ["user_id"])
    op.create_index(op.f("ix_analytics_events_product_id"), "analytics_events", ["product_id"])
    op.create_index(op.f("ix_analytics_events_order_id"), "analytics_events", ["order_id"])
    op.create_index(
        op.f("ix_analytics_events_promo_code_id"),
        "analytics_events",
        ["promo_code_id"],
    )
    op.create_index(op.f("ix_analytics_events_banner_id"), "analytics_events", ["banner_id"])
    op.create_index(op.f("ix_analytics_events_created_at"), "analytics_events", ["created_at"])

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("entity_type", sa.String(length=100), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("before_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_audit_logs_actor_user_id"), "audit_logs", ["actor_user_id"])
    op.create_index(op.f("ix_audit_logs_action"), "audit_logs", ["action"])
    op.create_index(op.f("ix_audit_logs_entity_type"), "audit_logs", ["entity_type"])
    op.create_index(op.f("ix_audit_logs_entity_id"), "audit_logs", ["entity_id"])
    op.create_index(op.f("ix_audit_logs_created_at"), "audit_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index(op.f("ix_audit_logs_created_at"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_entity_id"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_entity_type"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_action"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_actor_user_id"), table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_index(op.f("ix_analytics_events_created_at"), table_name="analytics_events")
    op.drop_index(op.f("ix_analytics_events_banner_id"), table_name="analytics_events")
    op.drop_index(op.f("ix_analytics_events_promo_code_id"), table_name="analytics_events")
    op.drop_index(op.f("ix_analytics_events_order_id"), table_name="analytics_events")
    op.drop_index(op.f("ix_analytics_events_product_id"), table_name="analytics_events")
    op.drop_index(op.f("ix_analytics_events_user_id"), table_name="analytics_events")
    op.drop_index(op.f("ix_analytics_events_event_name"), table_name="analytics_events")
    op.drop_table("analytics_events")
