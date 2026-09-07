"""Rice (AGMARKNET / data.gov.in) tests.

Covers the integration of the AGMARKNET Rice provider into the existing
CropMandi-AI architecture without touching Coffee/Pepper behaviour.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from cropmandi.db.seed import seed_reference_data
from cropmandi.db.session import create_all, make_session_factory
from ingest.connectors.agmarknet_rice import (
    DAILY_RESOURCE_ID,
    HISTORICAL_RESOURCE_ID,
)
from ingest.load_prices import insert_observations, start_run
from ingest.parsers.agmarknet_rice import parse_agmarknet_rice_json
from ingest.types import ParsedObservation
from ingest.validate.price_validation import partition_valid, validate_observation
import apps.api.main as api_main


def _rice_obs(
    *,
    variety: str = "IR_64",
    market: str = "Mangalore",
    day: date = date(2026, 9, 5),
    price: str = "3300",
    price_min: str | None = "3200",
    price_max: str | None = "3400",
    grade: str = "FAQ",
    unit: str = "INR_PER_QUINTAL",
    state: str = "Karnataka",
    district: str = "Dakshina Kannada",
) -> ParsedObservation:
    values = dict(
        commodity_code="rice",
        market_name=market,
        market_kind="mandi",
        market_state=state,
        market_district=district,
        grade_code=grade,
        variety=variety,
        market_date=day,
        price=Decimal(price),
        price_min=Decimal(price_min) if price_min is not None else None,
        price_max=Decimal(price_max) if price_max is not None else None,
        price_avg=Decimal(price),
        unit=unit,
        price_type="modal_daily",
        source_code="agmarknet_data_gov_in",
        source_url="https://data.gov.in/resource/current-daily-price-various-commodities-various-markets-mandi",
        publisher_source_label="DMI, Ministry of Agriculture and Farmers Welfare",
    )
    return ParsedObservation(**values)


def _sample_payload() -> dict:
    return {
        "total": 4,
        "records": [
            {
                "State": "Karnataka",
                "District": "Dakshina Kannada",
                "Market": "Mangalore",
                "Commodity": "Rice",
                "Variety": "IR-64",
                "Grade": "FAQ",
                "Arrival_Date": "05/09/2026",
                "Min_Price": "3200",
                "Max_Price": "3400",
                "Modal_Price": "3300",
            },
            {
                "State": "Karnataka",
                "District": "Hassan",
                "Market": "Hassan",
                "Commodity": "Rice",
                "Variety": "Ponni",
                "Grade": "SUPERFINE",
                "Arrival_Date": "05/09/2026",
                "Min_Price": "3000",
                "Max_Price": "3100",
                "Modal_Price": "3050",
            },
            {
                "State": "Kerala",
                "District": "Ernakulam",
                "Market": "Ernakulam",
                "Commodity": "Rice",
                "Variety": "Ponni",
                "Grade": "FAQ",
                "Arrival_Date": "05/09/2026",
                "Min_Price": "2900",
                "Max_Price": "3000",
                "Modal_Price": "2950",
            },
            {
                "State": "Karnataka",
                "District": "Mandya",
                "Market": "Mandya",
                "Commodity": "Paddy",
                "Variety": "Jaya",
                "Grade": "FAQ",
                "Arrival_Date": "05/09/2026",
                "Min_Price": "2200",
                "Max_Price": "2400",
                "Modal_Price": "2300",
            },
        ],
    }


# ---------------------------------------------------------------- provider


def test_provider_resource_ids_match_agmarknet_package():
    assert HISTORICAL_RESOURCE_ID == "35985678-0d79-46b4-9ed6-6f13308a1d24"
    assert DAILY_RESOURCE_ID == "9ef84268-d588-465a-a308-a864a43d0070"


def test_provider_requires_api_key(monkeypatch):
    import ingest.connectors.agmarknet_rice as connector

    monkeypatch.delenv("DATA_GOV_API_KEY", raising=False)
    monkeypatch.setattr(connector, "get_settings", lambda: SimpleNamespace(data_gov_api_key=""))
    with pytest.raises(ValueError, match="DATA_GOV_API_KEY"):
        connector._get_api_key()


def test_provider_api_key_reads_from_settings(monkeypatch):
    import ingest.connectors.agmarknet_rice as connector

    monkeypatch.delenv("DATA_GOV_API_KEY", raising=False)
    monkeypatch.setattr(
        connector, "get_settings", lambda: SimpleNamespace(data_gov_api_key="rzp-not-a-key")
    )
    assert connector._get_api_key() == "rzp-not-a-key"


def test_provider_download_reports_missing_key_without_payload(tmp_path, monkeypatch):
    """Without an API key the provider returns ok=False rather than fake data."""
    import ingest.connectors.agmarknet_rice as connector

    monkeypatch.delenv("DATA_GOV_API_KEY", raising=False)
    monkeypatch.setattr(connector, "get_settings", lambda: SimpleNamespace(data_gov_api_key=""))
    result = connector.fetch_agmarknet_rice(HISTORICAL_RESOURCE_ID, dest_dir=tmp_path)
    assert result.ok is False
    assert result.path is None
    assert result.error and "DATA_GOV_API_KEY" in result.error


# ---------------------------------------------------------------- parsing


def test_parse_keeps_karnataka_rice_and_preserves_variety():
    parsed = parse_agmarknet_rice_json(_sample_payload())
    # 2 valid (Karnataka Rice); Kerala and Paddy rows dropped.
    assert len(parsed) == 2
    ir64 = next(p for p in parsed if p.variety == "IR_64")
    assert ir64.market_name == "Mangalore"
    assert ir64.market_state == "Karnataka"
    assert ir64.market_district == "Dakshina Kannada"
    assert ir64.grade_code == "FAQ"
    assert ir64.price == Decimal("3300")
    assert ir64.price_min == Decimal("3200")
    assert ir64.price_max == Decimal("3400")
    assert ir64.unit == "INR_PER_QUINTAL"
    assert ir64.price_type == "modal_daily"
    assert ir64.extras["raw_commodity"] == "Rice"
    assert ir64.extras["data_source"] == "AGMARKNET / data.gov.in"


def test_parse_filters_out_paddy_and_non_karnataka():
    parsed = parse_agmarknet_rice_json(_sample_payload())
    commodities = {p.extras["raw_commodity"] for p in parsed}
    assert commodities == {"Rice"}
    assert all(p.market_state == "Karnataka" for p in parsed)


def test_parse_rejects_invalid_dates_and_missing_modal():
    payload = {
        "records": [
            {
                "State": "Karnataka",
                "District": "X",
                "Market": "Y",
                "Commodity": "Rice",
                "Variety": "IR-64",
                "Grade": "FAQ",
                "Arrival_Date": "not-a-date",
                "Min_Price": "1",
                "Max_Price": "2",
                "Modal_Price": "3",
            },
            {
                "State": "Karnataka",
                "District": "X",
                "Market": "Y",
                "Commodity": "Rice",
                "Variety": "IR-64",
                "Grade": "FAQ",
                "Arrival_Date": "05/09/2026",
                "Min_Price": "1",
                "Max_Price": "2",
                "Modal_Price": "",
            },
        ]
    }
    parsed = parse_agmarknet_rice_json(payload)
    assert parsed == []


def test_parse_handles_missing_or_malformed_json():
    assert parse_agmarknet_rice_json(json.dumps({})) == []
    assert parse_agmarknet_rice_json("{not json") == []
    assert parse_agmarknet_rice_json({"records": []}) == []


def test_parse_marks_missing_variety_as_none_not_fabricated():
    payload = {
        "records": [
            {
                "State": "Karnataka",
                "District": "X",
                "Market": "Y",
                "Commodity": "Rice",
                "Grade": "FAQ",
                "Arrival_Date": "05/09/2026",
                "Min_Price": "1",
                "Max_Price": "2",
                "Modal_Price": "3",
            }
        ]
    }
    (parsed,) = parse_agmarknet_rice_json(payload)
    assert parsed.variety is None


# ---------------------------------------------------------------- validation


def test_rice_validation_accepts_valid_row():
    obs = _rice_obs()
    assert validate_observation(obs) == []


def test_rice_validation_rejects_bad_records():
    cases = {
        "missing_market": _rice_obs(market=""),
        "invalid_date": _rice_obs(day=date(1960, 1, 1)),
        "invalid_price": _rice_obs(price="0"),
        "missing_modal_as_zero": _rice_obs(price="0.00"),
        "missing_variety": _rice_obs(variety=None),
        "min_greater_than_modal": _rice_obs(price_min="3400", price="3300", price_max="3500"),
        "modal_greater_than_max": _rice_obs(price="3500", price_min="3200", price_max="3400"),
        "min_greater_than_max": _rice_obs(price_min="3400", price_max="3200", price="3300"),
        "wrong_unit": _rice_obs(unit="INR_PER_KG"),
    }
    for reason, obs in cases.items():
        errors = validate_observation(obs)
        assert errors, f"expected rejection for {reason}"


def test_rice_validation_allows_live_agmarknet_grades():
    obs = _rice_obs(grade="SUPERFINE")
    assert validate_observation(obs) == []
    obs2 = _rice_obs(grade="OTHER")
    assert validate_observation(obs2) == []


def test_partition_valid_counts_rejections_and_keeps_source():
    valid, rejected = partition_valid([_rice_obs(), _rice_obs(variety=None)])
    assert len(valid) == 1
    assert len(rejected) == 1
    assert "missing_variety" in rejected[0].reason
    assert valid[0].source_code == "agmarknet_data_gov_in"


# ---------------------------------------------------------------- DB + API


def _setup_db(tmp_path: Path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'rice_api.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    create_all(url)
    factory = make_session_factory(url)
    api_main.SessionLocal = factory
    return factory


def test_rice_latest_and_history_via_api(tmp_path, monkeypatch):
    factory = _setup_db(tmp_path, monkeypatch)
    client = TestClient(api_main.app)

    # No rice data yet -> honest 404 no-observations, never fabricated prices.
    missing = client.get("/api/prices/latest", params={"commodity": "rice"})
    assert missing.status_code == 404
    assert missing.json()["available"] is False

    session = factory()
    seed_reference_data(session)
    run = start_run(session, "agmarknet_rice")
    insert_observations(
        session,
        run,
        [
            _rice_obs(variety="IR_64", market="Mangalore", day=date(2026, 9, 4), price="3250"),
            _rice_obs(variety="IR_64", market="Mangalore", day=date(2026, 9, 5), price="3300"),
            _rice_obs(variety="Ponni", market="Hassan", day=date(2026, 9, 5), price="3050"),
        ],
    )
    session.commit()
    session.close()

    latest = client.get("/api/prices/latest", params={"commodity": "rice"})
    assert latest.status_code == 200
    body = latest.json()
    assert body["available"] is True
    assert body["commodity"] == "rice"
    by_series = {row["series"]: row for row in body["observations"]}
    assert set(by_series) == {"Mangalore IR 64", "Hassan Ponni"}

    mangalore = by_series["Mangalore IR 64"]
    assert mangalore["price"] == 3300
    assert mangalore["unit"] == "INR_PER_QUINTAL"
    assert mangalore["price_type"] == "modal_daily"
    assert mangalore["source_code"] == "agmarknet_data_gov_in"
    assert mangalore["market"] == "Mangalore"
    assert mangalore["variety"] == "IR_64"
    assert mangalore["data_status"] == "AGMARKNET_INGESTED"
    assert mangalore["official"] is True
    assert mangalore["guaranteed_transaction_price"] is False

    history = client.get(
        "/api/prices/history",
        params={"commodity": "rice", "series": "Mangalore IR 64"},
    )
    assert history.status_code == 200
    hbody = history.json()
    assert hbody["count"] == 2
    assert hbody["observations"][-1]["price"] == 3300

    # Variety/market filtering via an unknown series must 400, not fabricate.
    unknown = client.get(
        "/api/prices/history",
        params={"commodity": "rice", "series": "Mysuru Jaya"},
    )
    assert unknown.status_code == 400
    assert unknown.json()["error"] == "unsupported_series"


def test_rice_market_locations_via_api(tmp_path, monkeypatch):
    factory = _setup_db(tmp_path, monkeypatch)
    client = TestClient(api_main.app)
    session = factory()
    seed_reference_data(session)
    run = start_run(session, "agmarknet_rice")
    insert_observations(
        session,
        run,
        [
            _rice_obs(variety="IR_64", market="Mangalore", day=date(2026, 9, 5), price="3300"),
            _rice_obs(variety="Ponni", market="Hassan", day=date(2026, 9, 5), price="3050"),
        ],
    )
    session.commit()
    session.close()

    markets = client.get("/api/markets", params={"commodity": "rice"})
    assert markets.status_code == 200
    names = {loc["name"] for loc in markets.json()["locations"]}
    assert names == {"Mangalore", "Hassan"}

    prices = client.get(
        "/api/markets/prices",
        params={"commodity": "rice", "location": "Mangalore"},
    )
    assert prices.status_code == 200
    assert prices.json()["count"] == 1
    assert prices.json()["unit"] == "INR_PER_QUINTAL"


def test_rice_series_never_pools_markets_or_varieties(tmp_path, monkeypatch):
    factory = _setup_db(tmp_path, monkeypatch)
    session = factory()
    seed_reference_data(session)
    run = start_run(session, "agmarknet_rice")
    insert_observations(
        session,
        run,
        [
            _rice_obs(variety="IR_64", market="Mangalore", day=date(2026, 9, 5), price="3300"),
            _rice_obs(variety="IR_64", market="Hassan", day=date(2026, 9, 5), price="3400"),
            _rice_obs(variety="Ponni", market="Mangalore", day=date(2026, 9, 5), price="2900"),
        ],
    )
    session.commit()

    from apps.api.rice_data import rice_points

    points = rice_points(session)
    # Distinct market+variety series: 3 series from 3 rows.
    assert len(points) == 3
    session.close()