from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Commodity(Base):
    __tablename__ = "commodities"
    __table_args__ = (
        CheckConstraint("code IN ('coffee', 'pepper', 'rice')", name="ck_commodities_v1_codes"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)

    grades: Mapped[list["Grade"]] = relationship(back_populates="commodity")
    observations: Mapped[list["PriceObservation"]] = relationship(back_populates="commodity")


class Market(Base):
    __tablename__ = "markets"
    __table_args__ = (
        UniqueConstraint("name", "kind", "district", "state", name="uq_markets_identity"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False, default="unknown")
    district: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    taluk: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    state: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    country: Mapped[str] = mapped_column(String(64), nullable=False, default="India")


class Grade(Base):
    __tablename__ = "grades"
    __table_args__ = (
        UniqueConstraint("commodity_id", "code", name="uq_grades_commodity_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    commodity_id: Mapped[int] = mapped_column(ForeignKey("commodities.id"), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)

    commodity: Mapped[Commodity] = relationship(back_populates="grades")


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    publisher: Mapped[str] = mapped_column(String(255), nullable=False)
    homepage_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    classification: Mapped[str] = mapped_column(String(64), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    connector: Mapped[str] = mapped_column(String(128), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    raw_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    raw_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rows_parsed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_inserted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_duplicate: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_rejected: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    observations: Mapped[list["PriceObservation"]] = relationship(back_populates="ingestion_run")


class PriceObservation(Base):
    __tablename__ = "price_observations"
    __table_args__ = (
        UniqueConstraint(
            "commodity_id",
            "market_id",
            "grade_id",
            "market_date",
            "price_type",
            "unit",
            "source_id",
            "variety",
            name="uq_price_observation_identity",
        ),
        CheckConstraint("price > 0", name="ck_price_positive"),
        CheckConstraint(
            "price_min IS NULL OR price_min > 0",
            name="ck_price_min_positive",
        ),
        CheckConstraint(
            "price_max IS NULL OR price_max > 0",
            name="ck_price_max_positive",
        ),
        CheckConstraint(
            "price_avg IS NULL OR price_avg > 0",
            name="ck_price_avg_positive",
        ),
        CheckConstraint(
            "price_min IS NULL OR price_max IS NULL OR price_min <= price_max",
            name="ck_price_min_le_max",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    commodity_id: Mapped[int] = mapped_column(ForeignKey("commodities.id"), nullable=False)
    market_id: Mapped[int] = mapped_column(ForeignKey("markets.id"), nullable=False)
    grade_id: Mapped[int] = mapped_column(ForeignKey("grades.id"), nullable=False)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), nullable=False)
    ingestion_run_id: Mapped[int] = mapped_column(
        ForeignKey("ingestion_runs.id"), nullable=False
    )

    market_date: Mapped[date] = mapped_column(Date, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    price_min: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    price_max: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    price_avg: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    variety: Mapped[str | None] = mapped_column(String(128), nullable=True)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    price_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    raw_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    raw_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    publisher_source_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    commodity: Mapped[Commodity] = relationship(back_populates="observations")
    market: Mapped[Market] = relationship()
    grade: Mapped[Grade] = relationship()
    source: Mapped[Source] = relationship()
    ingestion_run: Mapped[IngestionRun] = relationship(back_populates="observations")


class User(Base):
    """App identity row. The seeded demo farmer is NOT production authentication."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    payments: Mapped[list["Payment"]] = relationship(back_populates="user")


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount_paise > 0", name="ck_payments_amount_positive"),
        Index("uq_payments_razorpay_payment_id", "razorpay_payment_id", unique=True),
        Index("ix_payments_user_id", "user_id"),
        Index("ix_payments_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    receipt: Mapped[str | None] = mapped_column(String(40), unique=True, nullable=True)
    razorpay_order_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    razorpay_payment_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    amount_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="INR")
    crop: Mapped[str] = mapped_column(String(64), nullable=False)
    quantity: Mapped[str] = mapped_column(String(64), nullable=False)
    listing_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="CREATED")
    signature_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    webhook_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    failure_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped[User] = relationship(back_populates="payments")


class PaymentWebhookEvent(Base):
    __tablename__ = "payment_webhook_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    razorpay_order_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
