"""Rice observations from the production database.

AGMARKNET publishes Rice (and separately Paddy) mandi prices per market and
variety. Series are resolved dynamically from the database; nothing is pooled
across markets or varieties, and Rice is never merged with Paddy.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from apps.api.catalog import SeriesSpec, normalize_name
from cropmandi.db.models import Commodity, Grade, Market, PriceObservation, Source
from ml.datasets import rice_series_from_observation_rows


def _query_rice_rows(session: Session) -> list[tuple]:
    commodity = session.query(Commodity).filter_by(code="rice").one_or_none()
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


def rice_points(session: Session) -> dict[str, list[dict]]:
    rows = _query_rice_rows(session)
    series_map = rice_series_from_observation_rows(rows)
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


def rice_series_specs(session: Session) -> tuple[SeriesSpec, ...]:
    """Live AGMARKNET market+variety series available for Rice."""
    points_by_id = rice_points(session)
    specs: list[SeriesSpec] = []
    for sid in sorted(points_by_id):
        display_name = sid
        found = points_by_id[sid]
        if found:
            display_name = found[-1].get("display_name") or sid
        specs.append(
            SeriesSpec(
                "rice",
                sid,
                display_name,
                (normalize_name(display_name), normalize_name(sid)),
            )
        )
    return tuple(specs)


def rice_history(session: Session, spec: SeriesSpec, start: date | None, end: date | None) -> list[dict]:
    points = rice_points(session).get(spec.series_id, [])
    rows = []
    for point in points:
        d = point["observation_date"]
        if start and d < start:
            continue
        if end and d > end:
            continue
        rows.append(point)
    return rows


def rice_latest(session: Session, spec: SeriesSpec) -> dict | None:
    points = rice_points(session).get(spec.series_id, [])
    if not points:
        return None
    return points[-1]


def rice_payload_fields(spec: SeriesSpec, point: dict | None) -> dict:
    prov = (point or {}).get("provenance") or {}
    return {
        "commodity": "rice",
        "series": spec.display_name,
        "series_id": spec.series_id,
        "market": prov.get("market_name"),
        "grade": prov.get("grade_code"),
        "variety": prov.get("variety") or spec.display_name.split(" ", 1)[-1],
        "source": prov.get("source_name"),
        "source_code": prov.get("source_code"),
        "source_url": prov.get("source_url"),
        "publisher_source_label": prov.get("publisher_source_label"),
        "price_type": prov.get("price_type") or "modal_daily",
        "indicative": True,
        "experimental": False,
        "official": True,
        "guaranteed_transaction_price": False,
        "data_status": prov.get("data_status") or "AGMARKNET_INGESTED",
        "data_usage": prov.get("data_usage") or "EXPERIMENTAL_ML_ON_VALIDATED_OBSERVATIONS",
        "provenance": {k: v for k, v in prov.items() if k != "provenance"},
    }