"""Add durable customer in-app status notifications.

Revision ID: 20260713_0056
Revises: 20260712_0055
Create Date: 2026-07-13 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260713_0056"
down_revision: str | None = "20260712_0055"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    category = postgresql.ENUM(
        "order",
        "payment",
        "return",
        name="customer_in_app_notification_category",
        create_type=False,
    )
    variant = postgresql.ENUM(
        "standard",
        "approved_payment",
        name="customer_in_app_notification_variant",
        create_type=False,
    )
    action_mode = postgresql.ENUM(
        "continue_only",
        "continue_with_contacts",
        name="customer_in_app_notification_action_mode",
        create_type=False,
    )
    category.create(op.get_bind(), checkfirst=True)
    variant.create(op.get_bind(), checkfirst=True)
    action_mode.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "customer_in_app_notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("category", category, nullable=False),
        sa.Column("event_code", sa.String(length=64), nullable=False),
        sa.Column("variant", variant, nullable=False),
        sa.Column("action_mode", action_mode, nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=True),
        sa.Column("manual_payment_id", sa.Integer(), nullable=True),
        sa.Column("return_request_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_key", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["manual_payment_id"], ["manual_payments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["return_request_id"], ["return_requests.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("source_key", name="uq_customer_in_app_notifications_source_key"),
    )
    op.create_index(
        "ix_customer_in_app_notifications_user_unseen",
        "customer_in_app_notifications",
        ["user_id", "seen_at", "occurred_at", "id"],
    )
    op.create_index(
        "ix_customer_in_app_notifications_user_chronological",
        "customer_in_app_notifications",
        ["user_id", "occurred_at", "id"],
    )
    for column in ("order_id", "manual_payment_id", "return_request_id"):
        op.create_index(
            f"ix_customer_in_app_notifications_{column}",
            "customer_in_app_notifications",
            [column],
        )


def downgrade() -> None:
    op.drop_table("customer_in_app_notifications")
    bind = op.get_bind()
    for name in (
        "customer_in_app_notification_action_mode",
        "customer_in_app_notification_variant",
        "customer_in_app_notification_category",
    ):
        sa.Enum(name=name).drop(bind, checkfirst=True)
