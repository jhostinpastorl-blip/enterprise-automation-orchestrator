"""Create durable automation state and audit tables."""

from alembic import op
import sqlalchemy as sa

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "automation_requests",
        sa.Column("request_id", sa.String(), nullable=False),
        sa.Column("idempotency_key", sa.String(), nullable=True),
        sa.Column("process", sa.String(), nullable=False),
        sa.Column("target", sa.String(), nullable=False),
        sa.Column("execution_channel", sa.String(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.String(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("request_id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index(
        "idx_automation_requests_status_next_attempt",
        "automation_requests",
        ["status", "next_attempt_at"],
        unique=False,
    )
    op.create_table(
        "automation_events",
        sa.Column("event_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("request_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["request_id"], ["automation_requests.request_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index("idx_automation_events_request_id", "automation_events", ["request_id"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_automation_events_request_id", table_name="automation_events")
    op.drop_table("automation_events")
    op.drop_index("idx_automation_requests_status_next_attempt", table_name="automation_requests")
    op.drop_table("automation_requests")
