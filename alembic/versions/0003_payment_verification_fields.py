"""Add payment verification columns and webhook event table."""

from alembic import op
import sqlalchemy as sa

revision = "0003_payment_verification"
down_revision = "0002_payments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("payments", sa.Column("receipt", sa.String(40), nullable=True))
    op.add_column(
        "payments",
        sa.Column("signature_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "payments",
        sa.Column("webhook_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("payments", sa.Column("failure_reason", sa.String(255), nullable=True))
    op.add_column("payments", sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("uq_payments_receipt", "payments", ["receipt"], unique=True)
    op.create_index("uq_payments_razorpay_payment_id", "payments", ["razorpay_payment_id"], unique=True)
    op.create_index("ix_payments_user_id", "payments", ["user_id"])
    op.create_index("ix_payments_status", "payments", ["status"])
    op.create_table(
        "payment_webhook_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.String(128), nullable=False, unique=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("razorpay_order_id", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("payment_webhook_events")
    op.drop_index("ix_payments_status", table_name="payments")
    op.drop_index("ix_payments_user_id", table_name="payments")
    op.drop_index("uq_payments_razorpay_payment_id", table_name="payments")
    op.drop_index("uq_payments_receipt", table_name="payments")
    op.drop_column("payments", "paid_at")
    op.drop_column("payments", "failure_reason")
    op.drop_column("payments", "webhook_verified")
    op.drop_column("payments", "signature_verified")
    op.drop_column("payments", "receipt")
