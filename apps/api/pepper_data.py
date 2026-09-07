"""Pepper observations from the production database. Does not mix markets or grades."""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from apps.api.catalog import SeriesSpec
from cropmandi.db.models import Commodity, Grade, Market, PriceObservation, Source
from ml.datasets import pepper_series_from_observation_rows


def _query_pepper_rows(session: Session) -> list[tuple]:
    commodity = session.query(Commodity).filter_by(code="pepper").one_or_none()
    if commodity is None:
        return []
    return (
        session.query(PriceObservation, Market, Grade, Source)
        .join(Market, PriceObservation.market_id == Market.id)
        .join(Grade, PriceObservation.grade_id == Grade.id)
        .join(Source, PriceObservation.source_id == Source.id)
        .filter(PriceObservation.commodity_id == commodity.id)
        .order_by(PriceObservation.market_date.asc(), PriceObservation.id.asc())
        .all()
    )


def pepper_points(session: Session) -> dict[str, list[dict]]:
    rows = _query_pepper_rows(session)
    series_map = pepper_series_from_observation_rows(rows)
    # Attach last-row publisher fields from the grouped series provenance.
    out: dict[str, list[dict]] = {}
    for sid, series in series_map.items():
        points = []
        for d, p in zip(series.dates, series.prices):
            points.append(
                {
                    "observation_date": d,
                    "price": p,
                    "unit": series.unit,
                    "display_name": series.display_name,
                    "provenance": series.provenance,
                }
            )
        out[sid] = points
    return out


def pepper_history(session: Session, spec: SeriesSpec, start: date | None, end: date | None) -> list[dict]:
    points = pepper_points(session).get(spec.series_id, [])
    rows = []
    for point in points:
        d = point["observation_date"]
        if start and d < start:
            continue
        if end and d > end:
            continue
        rows.append(point)
    return rows


def pepper_latest(session: Session, spec: SeriesSpec) -> dict | None:
    points = pepper_points(session).get(spec.series_id, [])
    if not points:
        return None
    return points[-1]


def pepper_payload_fields(spec: SeriesSpec, point: dict | None) -> dict:
    prov = (point or {}).get("provenance") or {}
    return {
        "commodity": "pepper",
        "series": spec.display_name,
        "series_id": spec.series_id,
        "market": prov.get("market_name"),
        "grade": prov.get("grade_code"),
        "source": prov.get("source_name"),
        "source_code": prov.get("source_code"),
        "source_url": prov.get("source_url"),
        "publisher_source_label": prov.get("publisher_source_label"),
        "price_type": prov.get("price_type") or "indicative_daily_average",
        "indicative": True,
        "experimental": False,
        "official": False,
        "guaranteed_transaction_price": False,
        "data_status": prov.get("data_status") or "SPICES_BOARD_INGESTED",
        "data_usage": prov.get("data_usage") or "EXPERIMENTAL_ML_ON_VALIDATED_OBSERVATIONS",
        "provenance": {k: v for k, v in prov.items() if k != "provenance"},
    }
