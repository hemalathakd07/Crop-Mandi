from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from bs4 import BeautifulSoup

from ingest.types import ParsedObservation

SOURCE_URL = (
    "https://www.indianspices.com/marketing/price/domestic/current-market-price.html"
)
PRICE_TYPE = "indicative_daily_average"
UNIT = "INR_PER_KG"


def parse_price(value: str | None) -> Decimal | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if text in {"", "-", "–", "—", "NA", "N/A", "00.00", "0", "0.00", "0.0"}:
        return None
    if re.search(r"[^0-9.]", text):
        return None
    try:
        number = Decimal(text)
    except InvalidOperation:
        return None
    if number <= 0:
        return None
    return number


def parse_market_date(value: str) -> date | None:
    text = str(value).strip()
    for fmt in ("%d-%b-%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def normalize_grade(value: str | None) -> str:
    text = (value or "").strip().upper()
    text = text.replace(" ", "")
    mapping = {
        "GARBLED": "GARBLED",
        "UNGARBLED": "UNGARBLED",
        "UNGARBALED": "UNGARBLED",
        "UNGRADED": "UNGRADED",
        "WHITE": "WHITE",
        "-": "UNSPECIFIED",
        "": "UNSPECIFIED",
    }
    if text in mapping:
        return mapping[text]
    return None


def parse_pepper_html(
    html: str,
    *,
    source_url: str = SOURCE_URL,
) -> list[ParsedObservation]:
    soup = BeautifulSoup(html, "lxml")
    observations: list[ParsedObservation] = []
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue
        header_cells = [c.get_text(" ", strip=True).lower() for c in rows[0].find_all(["th", "td"])]
        header_blob = " ".join(header_cells)
        if "spice" not in header_blob or "market" not in header_blob:
            continue
        for row in rows[1:]:
            cells = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
            if len(cells) < 7:
                continue
            # Expected: Date, Spice, Market, State, Grade, Source, Min, Max, Avg
            # Some pages omit min/max as '-' in the same columns.
            date_text, spice, market, state, grade, publisher = cells[:6]
            if spice.strip().lower() != "pepper":
                continue
            numeric_cells = cells[6:]
            min_price = parse_price(numeric_cells[0] if len(numeric_cells) > 0 else None)
            max_price = parse_price(numeric_cells[1] if len(numeric_cells) > 1 else None)
            avg_price = parse_price(numeric_cells[2] if len(numeric_cells) > 2 else None)
            if avg_price is None and len(numeric_cells) == 1:
                avg_price = parse_price(numeric_cells[0])
            price = avg_price or min_price or max_price
            market_date = parse_market_date(date_text)
            grade_code = normalize_grade(grade)
            if (
                price is None
                or market_date is None
                or grade_code is None
                or not market.strip()
            ):
                continue
            kind = "apmc" if "apmc" in publisher.lower() else "indicative_market"
            observations.append(
                ParsedObservation(
                    commodity_code="pepper",
                    market_name=market.strip(),
                    market_kind=kind,
                    market_state=state.strip() or None,
                    market_district=None,
                    grade_code=grade_code,
                    market_date=market_date,
                    price=price,
                    price_min=min_price,
                    price_max=max_price,
                    price_avg=avg_price,
                    unit=UNIT,
                    price_type=PRICE_TYPE,
                    source_code="spices_board_india",
                    source_url=source_url,
                    publisher_source_label=publisher.strip() or None,
                    notes=(
                        "Spices Board publishes these as indicative daily averages, "
                        "not guaranteed transaction prices."
                    ),
                )
            )
    return observations


def parse_pepper_html_file(path: Path, source_url: str = SOURCE_URL) -> list[ParsedObservation]:
    return parse_pepper_html(path.read_text(encoding="utf-8", errors="replace"), source_url=source_url)
