from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from cropmandi.db.models import (
    Commodity,
    Grade,
    IngestionRun,
    Market,
    PriceObservation,
    Source,
)
from cropmandi.db.seed import seed_reference_data
from ingest.types import ParsedObservation


def start_run(
    session: Session,
    connector: str,
    *,
    source_url: str | None = None,
    raw_path: str | None = None,
    raw_sha256: str | None = None,
    notes: str | None = None,
) -> IngestionRun:
    seed_reference_data(session)
    run = IngestionRun(
        connector=connector,
        source_url=source_url,
        raw_path=raw_path,
        raw_sha256=raw_sha256,
        status="running",
        notes=notes,
    )
    session.add(run)
    session.flush()
    return run


def finish_run(session: Session, run: IngestionRun, status: str, error: str | None = None) -> None:
    run.status = status
    run.finished_at = datetime.now(timezone.utc)
    run.error_message = error
    session.flush()


def _resolve_refs(session: Session, obs: ParsedObservation):
    commodity = session.query(Commodity).filter_by(code=obs.commodity_code).one()
    source = session.query(Source).filter_by(code=obs.source_code).one()
    grade = session.query(Grade).filter_by(
        commodity_id=commodity.id, code=obs.grade_code
    ).one_or_none()
    if grade is None:
        grade = Grade(
            commodity_id=commodity.id,
            code=obs.grade_code,
            name=obs.grade_code.replace("_", " ").title(),
        )
        session.add(grade)
        session.flush()
    market = (
        session.query(Market)
        .filter_by(
            name=obs.market_name,
            kind=obs.market_kind,
            state=obs.market_state or "",
            district=obs.market_district or "",
        )
        .one_or_none()
    )
    if market is None:
        market = Market(
            name=obs.market_name,
            kind=obs.market_kind,
            state=obs.market_state or "",
            district=obs.market_district or "",
        )
        session.add(market)
        session.flush()
    return commodity, market, grade, source


def _existing_identity(
    session: Session,
    commodity,
    market,
    grade,
    source,
    obs: ParsedObservation,
) -> bool:
    """NULL-safe duplicate check mirroring uq_price_observation_identity.

    Coffee/Pepper rows have variety NULL, and SQL databases treat NULLs as
    distinct in UNIQUE indexes, so the DB constraint alone cannot deduplicate
    those legacy rows. AGMARKNET Rice rows carry a real variety and are caught
    by the constraint as well as by this pre-check.
    """
    query = session.query(PriceObservation.id).filter(
        PriceObservation.commodity_id == commodity.id,
        PriceObservation.market_id == market.id,
        PriceObservation.grade_id == grade.id,
        PriceObservation.source_id == source.id,
        PriceObservation.market_date == obs.market_date,
        PriceObservation.price_type == obs.price_type,
        PriceObservation.unit == obs.unit,
    )
    if obs.variety is None:
        query = query.filter(PriceObservation.variety.is_(None))
    else:
        query = query.filter(PriceObservation.variety == obs.variety)
    return session.query(query.exists()).scalar() is True


def insert_observations(
    session: Session,
    run: IngestionRun,
    observations: list[ParsedObservation],
) -> tuple[int, int]:
    inserted = 0
    duplicates = 0
    for obs in observations:
        commodity, market, grade, source = _resolve_refs(session, obs)
        if _existing_identity(session, commodity, market, grade, source, obs):
            duplicates += 1
            continue
        row = PriceObservation(
            commodity_id=commodity.id,
            market_id=market.id,
            grade_id=grade.id,
            source_id=source.id,
            ingestion_run_id=run.id,
            market_date=obs.market_date,
            price=obs.price,
            price_min=obs.price_min,
            price_max=obs.price_max,
            price_avg=obs.price_avg,
            variety=obs.variety,
            unit=obs.unit,
            price_type=obs.price_type,
            source_url=obs.source_url,
            raw_path=run.raw_path,
            raw_sha256=run.raw_sha256,
            publisher_source_label=obs.publisher_source_label,
            notes=obs.notes,
        )
        try:
            with session.begin_nested():
                session.add(row)
                session.flush()
            inserted += 1
        except IntegrityError:
            duplicates += 1
    run.rows_inserted = (run.rows_inserted or 0) + inserted
    run.rows_duplicate = (run.rows_duplicate or 0) + duplicates
    return inserted, duplicates
