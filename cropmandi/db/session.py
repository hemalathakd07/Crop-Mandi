from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from cropmandi.config import get_settings
from cropmandi.db.models import Base

_PAYMENT_COLUMNS = {
    "receipt": "VARCHAR(40)",
    "signature_verified": "BOOLEAN DEFAULT 0 NOT NULL",
    "webhook_verified": "BOOLEAN DEFAULT 0 NOT NULL",
    "failure_reason": "VARCHAR(255)",
    "paid_at": "DATETIME",
}

_OBSERVATION_COLUMNS = {
    "variety": "VARCHAR(128)",
}

# Must stay in sync with cropmandi.db.models.Commodity.
COMMODITY_CHECK_SQL = "code IN ('coffee', 'pepper', 'rice')"


def make_engine(url: str | None = None):
    database_url = url or get_settings().database_url
    connect_args = {}
    if database_url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
    return create_engine(database_url, future=True, connect_args=connect_args)


def make_session_factory(url: str | None = None):
    return sessionmaker(bind=make_engine(url), autoflush=False, autocommit=False, class_=Session)


def _ensure_payment_columns(engine) -> None:
    inspector = inspect(engine)
    if "payments" not in inspector.get_table_names():
        return
    existing = {col["name"] for col in inspector.get_columns("payments")}
    with engine.begin() as conn:
        for name, ddl in _PAYMENT_COLUMNS.items():
            if name not in existing:
                conn.execute(text(f"ALTER TABLE payments ADD COLUMN {name} {ddl}"))


def _ensure_observation_columns(engine) -> None:
    inspector = inspect(engine)
    if "price_observations" not in inspector.get_table_names():
        return
    existing = {col["name"] for col in inspector.get_columns("price_observations")}
    with engine.begin() as conn:
        for name, ddl in _OBSERVATION_COLUMNS.items():
            if name not in existing:
                conn.execute(text(f"ALTER TABLE price_observations ADD COLUMN {name} {ddl}"))


def _ensure_commodity_rice_constraint(engine) -> None:
    """Allow the 'rice' commodity code without dropping existing Coffee/Pepper rows."""
    inspector = inspect(engine)
    if "commodities" not in inspector.get_table_names():
        return

    if engine.dialect.name == "sqlite":
        with engine.connect() as conn:
            ddl = conn.execute(
                text("SELECT sql FROM sqlite_master WHERE type='table' AND name='commodities'")
            ).scalar()
        if not ddl or "'rice'" in ddl:
            return
        # SQLite has no ALTER for CHECK constraints. Rebuild the tiny table in
        # place, preserving every column value and id so FKs stay valid.
        rebuilt = (
            "CREATE TABLE commodities_new (\n"
            " id INTEGER NOT NULL,\n"
            " code VARCHAR(32) NOT NULL,\n"
            " name VARCHAR(128) NOT NULL,\n"
            " PRIMARY KEY (id),\n"
            f" CONSTRAINT ck_commodities_v1_codes CHECK ({COMMODITY_CHECK_SQL}),\n"
            " UNIQUE (code)\n"
            ")"
        )
        with engine.begin() as conn:
            conn.execute(text(rebuilt))
            conn.execute(
                text("INSERT INTO commodities_new (id, code, name) SELECT id, code, name FROM commodities")
            )
            conn.execute(text("DROP TABLE commodities"))
            conn.execute(text("ALTER TABLE commodities_new RENAME TO commodities"))
        return

    # PostgreSQL: swap the constraint in place.
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE commodities DROP CONSTRAINT ck_commodities_v1_codes"))
        conn.execute(
            text(
                "ALTER TABLE commodities ADD CONSTRAINT ck_commodities_v1_codes "
                f"CHECK ({COMMODITY_CHECK_SQL})"
            )
        )


def _sqlite_unique_index_has_variety(conn) -> bool:
    """Detect whether the observation unique index already includes variety."""
    for row in conn.execute(text("PRAGMA index_list('price_observations')")):
        if not row[2]:  # not a unique index
            continue
        index_name = row[1]
        for col in conn.execute(text(f"PRAGMA index_info('{index_name}')")):
            if col[2] == "variety":
                return True
    return False


def _ensure_price_observation_identity(engine) -> None:
    """Add 'variety' to the observation identity key so AGMARKNET rice rows with
    the same market + grade + date but different varieties stay distinct.
    """
    inspector = inspect(engine)
    if "price_observations" not in inspector.get_table_names():
        return

    if engine.dialect.name == "sqlite":
        with engine.connect() as conn:
            if _sqlite_unique_index_has_variety(conn):
                return

        from sqlalchemy.schema import CreateTable

        from cropmandi.db.models import PriceObservation

        compiled = str(
            CreateTable(PriceObservation.__table__).compile(dialect=engine.dialect)
        ).strip()
        with engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS price_observations_old"))
            conn.execute(text("ALTER TABLE price_observations RENAME TO price_observations_old"))
            conn.execute(text(compiled))
            columns = [
                row[1] for row in conn.execute(text("PRAGMA table_info('price_observations_old')"))
            ]
            col_list = ", ".join(f'"{c}"' for c in columns)
            conn.execute(
                text(
                    f"INSERT INTO price_observations ({col_list}) "
                    f"SELECT {col_list} FROM price_observations_old"
                )
            )
            conn.execute(text("DROP TABLE price_observations_old"))
        return

    # PostgreSQL: swap the unique constraint in place.
    with engine.begin() as conn:
        conn.execute(
            text("ALTER TABLE price_observations DROP CONSTRAINT uq_price_observation_identity")
        )
        conn.execute(
            text(
                "ALTER TABLE price_observations ADD CONSTRAINT uq_price_observation_identity "
                "UNIQUE (commodity_id, market_id, grade_id, market_date, price_type, unit, source_id, variety)"
            )
        )


def create_all(url: str | None = None) -> None:
    engine = make_engine(url)
    Base.metadata.create_all(engine)
    _ensure_payment_columns(engine)
    _ensure_observation_columns(engine)
    _ensure_price_observation_identity(engine)
    _ensure_commodity_rice_constraint(engine)
