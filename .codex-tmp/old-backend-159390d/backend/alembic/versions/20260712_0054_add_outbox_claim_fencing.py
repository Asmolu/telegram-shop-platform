"""Add immutable claim fencing to the transactional outbox.

Revision ID: 20260712_0054
Revises: 20260711_0053
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260712_0054"
down_revision: str | None = "20260711_0053"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "outbox_events",
        sa.Column("claim_token", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "outbox_deliveries",
        sa.Column("last_claim_token", postgresql.UUID(as_uuid=True), nullable=True),
    )


def downgrade() -> None:
    # Downgrade intentionally discards transient lease ownership and acknowledgement
    # deduplication state. It is suitable for disposable validation, not a normal
    # production rollback while workers are active.
    op.drop_column("outbox_deliveries", "last_claim_token")
    op.drop_column("outbox_events", "claim_token")
