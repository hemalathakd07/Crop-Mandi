"""Create users and payments tables for demo Razorpay orders."""

from alembic import op
import sqlalchemy as sa

revision = "0002_payments"
down_revision = "0001_data_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False, unique=True),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("is_demo", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("razorpay_order_id", sa.String(128), nullable=False, unique=True),
        sa.Column("razorpay_payment_id", sa.String(128), nullable=True),
        sa.Column("amount_paise", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False, server_default="INR"),
        sa.Column("crop", sa.String(64), nullable=False),
        sa.Column("quantity", sa.String(64), nullable=False),
        sa.Column("listing_id", sa.String(128), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="created"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("amount_paise > 0", name="ck_payments_amount_positive"),
    )


def downgrade() -> None:
    op.drop_table("payments")
    op.drop_table("users")
