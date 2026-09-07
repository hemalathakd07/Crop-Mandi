from __future__ import annotations

import json
from collections import defaultdict
from statistics import mean, median, pstdev

from sqlalchemy.orm import Session

from cropmandi.config import get_settings
from cropmandi.db.models import Commodity, Grade, Market, PriceObservation, Source
from cropmandi.db.session import make_session_factory, create_all

MIN_SESSIONS_FOR_NEXT_SESSION_MODEL = 60


def _series_key(obs, market, grade, source) -> str:
    return f"{market.name}|{grade.code}|{obs.unit}|{obs.price_type}|{source.code}"


def readiness_report(session: Session) -> dict:
    report: dict = {"commodities": {}, "ml_ready": False, "notes": []}
    for code in ("coffee", "pepper", "rice"):
        commodity = session.query(Commodity).filter_by(code=code).one_or_none()
        if commodity is None:
            report["commodities"][code] = {"observations": 0}
            continue
        rows = (
            session.query(PriceObservation, Market, Grade, Source)
            .join(Market, PriceObservation.market_id == Market.id)
            .join(Grade, PriceObservation.grade_id == Grade.id)
            .join(Source, PriceObservation.source_id == Source.id)
            .filter(PriceObservation.commodity_id == commodity.id)
            .all()
        )
        by_series: dict[str, list] = defaultdict(list)
        prices = []
        dates = []
        for obs, market, grade, source in rows:
            by_series[_series_key(obs, market, grade, source)].append(obs)
            prices.append(float(obs.price))
            dates.append(obs.market_date)
        series_reports = []
        for key, items in sorted(by_series.items()):
            items = sorted(items, key=lambda o: o.market_date)
            unique_dates = sorted({o.market_date for o in items})
            gaps = []
            for i in range(1, len(unique_dates)):
                delta = (unique_dates[i] - unique_dates[i - 1]).days
                if delta > 1:
                    gaps.append(delta - 1)
            n = len(items)
            series_reports.append(
                {
                    "series": key,
                    "observations": n,
                    "unique_dates": len(unique_dates),
                    "earliest": str(unique_dates[0]) if unique_dates else None,
                    "latest": str(unique_dates[-1]) if unique_dates else None,
                    "gap_days_total": sum(gaps),
                    "max_gap_days": max(gaps) if gaps else 0,
                    "enough_history_for_next_session_attempt": n >= MIN_SESSIONS_FOR_NEXT_SESSION_MODEL,
                    "prediction_target": "next_published_market_session",
                }
            )
        report["commodities"][code] = {
            "observations": len(rows),
            "unique_dates": len(set(dates)),
            "unique_series": len(by_series),
            "earliest": str(min(dates)) if dates else None,
            "latest": str(max(dates)) if dates else None,
            "missing_min": sum(1 for obs, *_ in rows if obs.price_min is None),
            "missing_max": sum(1 for obs, *_ in rows if obs.price_max is None),
            "duplicate_identity_blocked_by_constraint": True,
            "price_min": min(prices) if prices else None,
            "price_max": max(prices) if prices else None,
            "price_mean": round(mean(prices), 4) if prices else None,
            "price_median": round(median(prices), 4) if prices else None,
            "price_stdev": round(pstdev(prices), 4) if len(prices) > 1 else None,
            "series": series_reports,
            "series_with_enough_history": [
                s["series"] for s in series_reports if s["enough_history_for_next_session_attempt"]
            ],
        }
    coffee_ready = report["commodities"].get("coffee", {}).get("series_with_enough_history") or []
    pepper_ready = report["commodities"].get("pepper", {}).get("series_with_enough_history") or []
    report["ml_ready"] = False
    report["notes"].append(
        "No production models are trained in this phase. "
        f"Pepper series meeting the {MIN_SESSIONS_FOR_NEXT_SESSION_MODEL}-session floor: {pepper_ready}. "
        f"Coffee series meeting the floor: {coffee_ready}."
    )
    return report


def main() -> None:
    create_all()
    session = make_session_factory()()
    try:
        report = readiness_report(session)
        out = get_settings().data_dir / "reports" / "data_readiness.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
    finally:
        session.close()


if __name__ == "__main__":
    main()
