from alembic import op
import sqlalchemy as sa

revision = "0001_data_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "commodities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(32), nullable=False, unique=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.CheckConstraint("code IN ('coffee', 'pepper')", name="ck_commodities_v1_codes"),
    )
    op.create_table(
        "markets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("district", sa.String(128), nullable=False, server_default=""),
        sa.Column("taluk", sa.String(128), nullable=False, server_default=""),
        sa.Column("state", sa.String(128), nullable=False, server_default=""),
        sa.Column("country", sa.String(64), nullable=False, server_default="India"),
        sa.UniqueConstraint("name", "kind", "district", "state", name="uq_markets_identity"),
    )
    op.create_table(
        "grades",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("commodity_id", sa.Integer(), sa.ForeignKey("commodities.id"), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.UniqueConstraint("commodity_id", "code", name="uq_grades_commodity_code"),
    )
    op.create_table(
        "sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("publisher", sa.String(255), nullable=False),
        sa.Column("homepage_url", sa.String(500), nullable=True),
        sa.Column("classification", sa.String(64), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
    )
    op.create_table(
        "ingestion_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("connector", sa.String(128), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="running"),
        sa.Column("source_url", sa.String(1000), nullable=True),
        sa.Column("raw_path", sa.String(1000), nullable=True),
        sa.Column("raw_sha256", sa.String(64), nullable=True),
        sa.Column("rows_parsed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_inserted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_duplicate", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_rejected", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
    )
    op.create_table(
        "price_observations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("commodity_id", sa.Integer(), sa.ForeignKey("commodities.id"), nullable=False),
        sa.Column("market_id", sa.Integer(), sa.ForeignKey("markets.id"), nullable=False),
        sa.Column("grade_id", sa.Integer(), sa.ForeignKey("grades.id"), nullable=False),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("sources.id"), nullable=False),
        sa.Column("ingestion_run_id", sa.Integer(), sa.ForeignKey("ingestion_runs.id"), nullable=False),
        sa.Column("market_date", sa.Date(), nullable=False),
        sa.Column("price", sa.Numeric(14, 4), nullable=False),
        sa.Column("price_min", sa.Numeric(14, 4), nullable=True),
        sa.Column("price_max", sa.Numeric(14, 4), nullable=True),
        sa.Column("price_avg", sa.Numeric(14, 4), nullable=True),
        sa.Column("unit", sa.String(32), nullable=False),
        sa.Column("price_type", sa.String(64), nullable=False),
        sa.Column("source_url", sa.String(1000), nullable=True),
        sa.Column("raw_path", sa.String(1000), nullable=True),
        sa.Column("raw_sha256", sa.String(64), nullable=True),
        sa.Column("publisher_source_label", sa.String(255), nullable=True),
        sa.Column("ingested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.CheckConstraint("price > 0", name="ck_price_positive"),
        sa.CheckConstraint("price_min IS NULL OR price_min > 0", name="ck_price_min_positive"),
        sa.CheckConstraint("price_max IS NULL OR price_max > 0", name="ck_price_max_positive"),
        sa.CheckConstraint("price_avg IS NULL OR price_avg > 0", name="ck_price_avg_positive"),
        sa.CheckConstraint(
            "price_min IS NULL OR price_max IS NULL OR price_min <= price_max",
            name="ck_price_min_le_max",
        ),
        sa.UniqueConstraint(
            "commodity_id",
            "market_id",
            "grade_id",
            "market_date",
            "price_type",
            "unit",
            "source_id",
            name="uq_price_observation_identity",
        ),
    )


def downgrade() -> None:
    op.drop_table("price_observations")
    op.drop_table("ingestion_runs")
    op.drop_table("sources")
    op.drop_table("grades")
    op.drop_table("markets")
    op.drop_table("commodities")
