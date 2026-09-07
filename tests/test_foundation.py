from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError

from cropmandi.db.models import Commodity, PriceObservation
from cropmandi.db.seed import seed_reference_data
from cropmandi.db.session import create_all, make_session_factory
from ingest.load_prices import insert_observations, start_run
from ingest.parsers.coffee_pdf import parse_coffee_report_text
from ingest.parsers.pepper_html import parse_pepper_html
from ingest.types import ParsedObservation
from ingest.validate.price_validation import validate_observation


@pytest.fixture()
def session(tmp_path: Path):
    url = f"sqlite:///{tmp_path / 'test.db'}"
    create_all(url)
    factory = make_session_factory(url)
    db = factory()
    seed_reference_data(db)
    db.commit()
    try:
        yield db
    finally:
        db.close()


def _pepper_obs(**overrides) -> ParsedObservation:
    data = dict(
        commodity_code="pepper",
        market_name="Cochin",
        market_kind="indicative_market",
        market_state="Kerala",
        market_district="",
        grade_code="GARBLED",
        market_date=date(2026, 9, 3),
        price=Decimal("722"),
        price_min=None,
        price_max=None,
        price_avg=Decimal("722"),
        unit="INR_PER_KG",
        price_type="indicative_daily_average",
        source_code="spices_board_india",
        source_url="https://www.indianspices.com/marketing/price/domestic/current-market-price.html",
        publisher_source_label="IPSTA",
    )
    data.update(overrides)
    return ParsedObservation(**data)


def test_schema_rejects_cardamom_commodity(session):
    session.add(Commodity(code="cardamom", name="Cardamom"))
    with pytest.raises(IntegrityError):
        session.flush()


def test_duplicate_observation_prevented(session):
    run = start_run(session, "test")
    obs = _pepper_obs()
    inserted, dupes = insert_observations(session, run, [obs])
    assert inserted == 1
    inserted2, dupes2 = insert_observations(session, run, [obs])
    assert inserted2 == 0
    assert dupes2 == 1
    assert session.query(PriceObservation).count() == 1


def test_invalid_date():
    errors = validate_observation(_pepper_obs(market_date=date(1960, 1, 1)))
    assert "invalid_date" in errors


def test_invalid_price():
    errors = validate_observation(_pepper_obs(price=Decimal("0")))
    assert "invalid_price" in errors


def test_missing_market():
    errors = validate_observation(_pepper_obs(market_name=""))
    assert "missing_market" in errors


def test_missing_commodity():
    errors = validate_observation(_pepper_obs(commodity_code=""))
    assert "unsupported_or_missing_commodity" in errors


def test_missing_unit():
    errors = validate_observation(_pepper_obs(unit=""))
    assert "missing_unit" in errors


def test_unknown_unit_not_converted():
    errors = validate_observation(_pepper_obs(unit="BAG"))
    assert "unknown_unit_not_converted" in errors


def test_source_url_required_for_official():
    errors = validate_observation(_pepper_obs(source_url=None))
    assert "missing_source_url" in errors


def test_pepper_parser_skips_non_pepper():
    html = """
    <table>
      <tr><th>Date</th><th>Spice</th><th>Market Centre</th><th>State</th><th>Grade</th><th>Source</th><th>Min</th><th>Max</th><th>Avg</th></tr>
      <tr><td>03-Sep-2026</td><td>Pepper</td><td>Cochin</td><td>KERALA</td><td>Garbled</td><td>IPSTA</td><td>-</td><td>-</td><td>722.00</td></tr>
      <tr><td>03-Sep-2026</td><td>Clove</td><td>Cochin</td><td>KERALA</td><td>-</td><td>Daily News Paper</td><td>-</td><td>-</td><td>875.00</td></tr>
    </table>
    """
    rows = parse_pepper_html(html)
    assert len(rows) == 1
    assert rows[0].commodity_code == "pepper"
    assert rows[0].price_type == "indicative_daily_average"
    assert rows[0].unit == "INR_PER_KG"


def test_coffee_parser_requires_clear_rows():
    text = """
    Daily Coffee Market Report 01 September 2026
    Prices in Rs./50 kg
    Sangam Curing Arabica Parchment 25650
    ICE New York 340.50
    """
    rows = parse_coffee_report_text(text)
    assert len(rows) == 1
    assert rows[0].grade_code == "ARABICA_PARCHMENT"
    assert rows[0].unit == "INR_PER_50KG"
    assert rows[0].market_kind == "unknown"


def test_coffee_parser_rejects_ranges():
    text = """
    01 September 2026 Rs./50 kg
    Mystery Centre Arabica Parchment 10000-12000
    """
    assert parse_coffee_report_text(text) == []
