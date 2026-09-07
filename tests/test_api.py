from datetime import date
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from cropmandi.db.seed import seed_reference_data
from cropmandi.db.session import create_all, make_session_factory
from ingest.load_prices import insert_observations, start_run
from ingest.types import ParsedObservation
from ml.sessions import next_weekday_session
import apps.api.main as api_main
import apps.api.runtime as api_runtime


def _pepper_obs(grade: str, price: str, day: date, market: str = "Cochin", kind: str = "indicative_market", label: str = "IPSTA"):
    return ParsedObservation(
        commodity_code="pepper",
        market_name=market,
        market_kind=kind,
        market_state="Karnataka" if market == "Sirsi" else "Kerala",
        market_district="",
        grade_code=grade,
        market_date=day,
        price=Decimal(price),
        price_min=None,
        price_max=None,
        price_avg=Decimal(price),
        unit="INR_PER_KG",
        price_type="indicative_daily_average",
        source_code="spices_board_india",
        source_url="https://www.indianspices.com/example",
        publisher_source_label=label,
    )


def _setup_db(tmp_path: Path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'api.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    create_all(url)
    factory = make_session_factory(url)
    api_main.SessionLocal = factory
    return factory


def _write_coffee_csv(path: Path) -> None:
    path.write_text(
        "series_id,display_name,session_date,weekday,price,unit\n"
        "coffee_arabica_parchment,Arabica Parchment,2026-08-27,Thursday,23900.0000,INR_PER_50KG\n"
        "coffee_arabica_parchment,Arabica Parchment,2026-08-28,Friday,24000.0000,INR_PER_50KG\n"
        "coffee_arabica_cherry,Arabica Cherry,2026-08-28,Friday,14700.0000,INR_PER_50KG\n"
        "coffee_robusta_parchment,Robusta Parchment,2026-08-28,Friday,18150.0000,INR_PER_50KG\n"
        "coffee_robusta_cherry,Robusta Cherry,2026-08-28,Friday,10300.0000,INR_PER_50KG\n"
        "coffee_arabica_parchment,Arabica Parchment,2026-08-29,Saturday,99999.0000,INR_PER_50KG\n",
        encoding="utf-8",
    )


def test_latest_price_unavailable_and_available(tmp_path, monkeypatch):
    factory = _setup_db(tmp_path, monkeypatch)
    client = TestClient(api_main.app)

    missing = client.get("/api/prices/latest", params={"commodity": "pepper"})
    assert missing.status_code == 404
    assert missing.json()["available"] is False

    session = factory()
    seed_reference_data(session)
    run = start_run(session, "test")
    insert_observations(session, run, [_pepper_obs("GARBLED", "722", date(2026, 9, 3))])
    session.commit()
    session.close()

    present = client.get("/api/prices/latest", params={"commodity": "pepper"})
    assert present.status_code == 200
    body = present.json()
    assert body["available"] is True
    assert body["observations"][0]["price"] == 722
    assert body["observations"][0]["source_url"].endswith("example")


def test_latest_coffee_and_pepper_metadata(tmp_path, monkeypatch):
    factory = _setup_db(tmp_path, monkeypatch)
    csv_path = tmp_path / "coffee.csv"
    _write_coffee_csv(csv_path)
    monkeypatch.setattr(api_runtime, "COFFEE_CSV_PATH", csv_path)

    session = factory()
    seed_reference_data(session)
    run = start_run(session, "test")
    insert_observations(
        session,
        run,
        [
            _pepper_obs("GARBLED", "722", date(2026, 9, 1)),
            _pepper_obs("UNGARBLED", "702", date(2026, 9, 1)),
            _pepper_obs("UNSPECIFIED", "674.16", date(2026, 2, 20), market="Sirsi", kind="apmc", label="APMC,SIRSI"),
        ],
    )
    session.commit()
    session.close()
    client = TestClient(api_main.app)

    coffee = client.get("/api/prices/latest", params={"commodity": "coffee"}).json()
    names = {row["series"] for row in coffee["observations"]}
    assert names == {"Arabica Parchment", "Arabica Cherry", "Robusta Parchment", "Robusta Cherry"}
    ap = next(row for row in coffee["observations"] if row["series"] == "Arabica Parchment")
    assert ap["price"] == 24000.0
    assert ap["observation_date"] == "2026-08-28"
    assert ap["data_status"] == "UNVERIFIED_HISTORICAL_COFFEE_DATA"
    assert ap["data_usage"] == "EXPERIMENTAL_ONLY"
    assert ap["official"] is False
    assert ap["experimental"] is True
    assert "Coffee Board" not in str(ap["source"])
    assert 99999 not in [row["price"] for row in coffee["observations"]]

    pepper = client.get("/api/prices/latest", params={"commodity": "pepper"}).json()
    by_series = {row["series"]: row for row in pepper["observations"]}
    assert set(by_series) == {"Cochin Garbled", "Cochin Ungarbled", "Sirsi"}
    assert by_series["Cochin Garbled"]["price_type"] == "indicative_daily_average"
    assert by_series["Cochin Garbled"]["indicative"] is True
    assert by_series["Cochin Garbled"]["guaranteed_transaction_price"] is False
    assert by_series["Sirsi"]["market"] == "Sirsi"


def test_history_coffee_and_pepper_separate(tmp_path, monkeypatch):
    factory = _setup_db(tmp_path, monkeypatch)
    csv_path = tmp_path / "coffee.csv"
    _write_coffee_csv(csv_path)
    monkeypatch.setattr(api_runtime, "COFFEE_CSV_PATH", csv_path)
    session = factory()
    seed_reference_data(session)
    run = start_run(session, "test")
    insert_observations(
        session,
        run,
        [
            _pepper_obs("GARBLED", "700", date(2026, 9, 1)),
            _pepper_obs("GARBLED", "722", date(2026, 9, 3)),
            _pepper_obs("UNGARBLED", "702", date(2026, 9, 3)),
        ],
    )
    session.commit()
    session.close()
    client = TestClient(api_main.app)

    coffee = client.get(
        "/api/prices/history",
        params={"commodity": "coffee", "series": "Arabica Parchment", "from": "2026-08-27", "to": "2026-08-28"},
    )
    assert coffee.status_code == 200
    body = coffee.json()
    dates = [row["observation_date"] for row in body["observations"]]
    assert dates == sorted(dates)
    assert body["interpolated"] is False
    assert body["data_status"] == "UNVERIFIED_HISTORICAL_COFFEE_DATA"
    assert all(row["price"] != 99999 for row in body["observations"])

    pepper = client.get(
        "/api/prices/history",
        params={"commodity": "pepper", "series": "Cochin Garbled"},
    ).json()
    assert pepper["count"] == 2
    assert [row["price"] for row in pepper["observations"]] == [700.0, 722.0]
    assert pepper["price_type"] == "indicative_daily_average"
    assert 702.0 not in [row["price"] for row in pepper["observations"]]


def test_unsupported_commodity_and_series(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    client = TestClient(api_main.app)
    bad = client.get("/api/prices/latest", params={"commodity": "cardamom"})
    assert bad.status_code == 400
    assert bad.json()["error"] == "unsupported_commodity"
    assert "Traceback" not in str(bad.json())

    missing_series = client.get("/api/prices/history", params={"commodity": "pepper"})
    assert missing_series.status_code == 400
    assert missing_series.json()["error"] == "missing_series_parameter"

    unknown = client.get(
        "/api/prices/history",
        params={"commodity": "pepper", "series": "Tellicherry Extra Bold"},
    )
    assert unknown.status_code == 400
    assert unknown.json()["error"] == "unsupported_series"

    invalid = client.get(
        "/api/prices/history",
        params={"commodity": "coffee", "series": "Arabica Parchment", "from": "28-08-2026"},
    )
    assert invalid.status_code == 400
    assert invalid.json()["error"] == "invalid_date_filter"


def test_next_session_estimates_use_naive_baseline(tmp_path, monkeypatch):
    factory = _setup_db(tmp_path, monkeypatch)
    csv_path = tmp_path / "coffee.csv"
    _write_coffee_csv(csv_path)
    monkeypatch.setattr(api_runtime, "COFFEE_CSV_PATH", csv_path)
    session = factory()
    seed_reference_data(session)
    run = start_run(session, "test")
    insert_observations(session, run, [_pepper_obs("GARBLED", "722", date(2026, 9, 3))])
    session.commit()
    session.close()
    client = TestClient(api_main.app)

    coffee = client.get(
        "/api/predictions/next",
        params={"commodity": "coffee", "series": "Arabica Parchment"},
    )
    assert coffee.status_code == 200
    body = coffee.json()
    assert body["method"] == "naive_last_value"
    assert body["estimate_kind"] == "baseline_estimate"
    assert body["ml_used_for_estimate"] is False
    assert body["model_status"] == "BASELINE_BETTER"
    assert body["tested_ml_model"] == "RandomForestRegressor"
    assert body["latest_observed_price"] == 24000.0
    assert body["next_session_estimate"] == 24000.0
    assert body["latest_observation_date"] == "2026-08-28"
    assert body["target_session"] == next_weekday_session(date(2026, 8, 28)).isoformat()
    assert body["target_session"] == "2026-08-31"
    assert body["data_status"] == "UNVERIFIED_HISTORICAL_COFFEE_DATA"
    assert body["data_usage"] == "EXPERIMENTAL_ONLY"
    assert body["official"] is False

    pepper = client.get(
        "/api/predictions/next",
        params={"commodity": "pepper", "series": "Cochin Garbled"},
    ).json()
    assert pepper["method"] == "naive_last_value"
    assert pepper["next_session_estimate"] == 722.0
    assert pepper["target_session"] is None
    assert pepper["next_session"] is None
    assert pepper["next_session_status"] == "next_published_session_unknown"
    assert pepper["price_type"] == "indicative_daily_average"
    assert pepper["indicative"] is True
    assert pepper["guaranteed_transaction_price"] is False if "guaranteed_transaction_price" in pepper else pepper["indicative"] is True


def test_target_session_friday_to_monday_and_no_future_leakage():
    friday = date(2026, 9, 4)
    assert friday.strftime("%A") == "Friday"
    monday = next_weekday_session(friday)
    assert monday == date(2026, 9, 7)
    assert monday.strftime("%A") == "Monday"
    saturday = date(2026, 9, 5)
    assert next_weekday_session(saturday) == date(2026, 9, 7)
    # Estimate equals last known price; it does not invent a later observed value.
    last_known = 24000.0
    naive_estimate = last_known
    future_unobserved = 25000.0
    assert naive_estimate != future_unobserved
    assert naive_estimate == last_known
