from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from pypdf import PdfReader

from ingest.types import ParsedObservation

COFFEE_BOARD_URL = "https://coffeeboard.gov.in/Market_Info.aspx"

GRADE_PATTERNS = [
    (re.compile(r"arabica\s*parchment", re.I), "ARABICA_PARCHMENT"),
    (re.compile(r"arabica\s*cherry", re.I), "ARABICA_CHERRY"),
    (re.compile(r"robusta\s*parchment", re.I), "ROBUSTA_PARCHMENT"),
    (re.compile(r"robusta\s*cherry", re.I), "ROBUSTA_CHERRY"),
]

UNIT_PATTERNS = [
    (re.compile(r"rs\.?\s*/\s*50\s*kgs?", re.I), "INR_PER_50KG"),
    (re.compile(r"rs\.?\s*/\s*50\s*kg", re.I), "INR_PER_50KG"),
    (re.compile(r"rs\.?\s*/\s*quintal", re.I), "INR_PER_QUINTAL"),
    (re.compile(r"rs\.?\s*/\s*qtl", re.I), "INR_PER_QUINTAL"),
    (re.compile(r"rs\.?\s*/\s*kg", re.I), "INR_PER_KG"),
]

DATE_PATTERNS = [
    re.compile(r"(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})"),
    re.compile(r"(\d{1,2}[-/][A-Za-z]{3}[-/]\d{4})"),
    re.compile(r"(\d{1,2}[-/]\d{1,2}[-/]\d{4})"),
]


def _decimal(text: str) -> Decimal | None:
    cleaned = text.replace(",", "").strip()
    if not re.fullmatch(r"\d+(\.\d+)?", cleaned):
        return None
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        return None
    return value if value > 0 else None


def detect_unit(text: str) -> str | None:
    for pattern, unit in UNIT_PATTERNS:
        if pattern.search(text):
            return unit
    return None


def detect_grade(text: str) -> str | None:
    for pattern, code in GRADE_PATTERNS:
        if pattern.search(text):
            return code
    return None


def detect_report_date(text: str, fallback_filename: str | None = None) -> date | None:
    for pattern in DATE_PATTERNS:
        match = pattern.search(text[:2500])
        if match:
            raw = match.group(1)
            for fmt in ("%d %B %Y", "%d %b %Y", "%d-%b-%Y", "%d/%m/%Y", "%d-%m-%Y"):
                try:
                    return datetime.strptime(raw.replace(",", ""), fmt).date()
                except ValueError:
                    continue
    if fallback_filename:
        match = re.search(r"(\d{1,2})[-_](\d{1,2})[-_](\d{4})", fallback_filename)
        if match:
            day, month, year = match.groups()
            try:
                return date(int(year), int(month), int(day))
            except ValueError:
                return None
    return None


def _looks_like_centre(name: str) -> bool:
    lowered = name.lower()
    if len(name) < 3 or len(name) > 80:
        return False
    banned = ("ice", "london", "new york", "nybot", "liffe", "ico", "page")
    if any(word in lowered for word in banned):
        return False
    return bool(re.search(r"[A-Za-z]", name))


ROW_RE = re.compile(
    r"(?P<centre>[A-Za-z][A-Za-z0-9 .,&'/-]{2,60})\s+"
    r"(?P<grade>Arabica Parchment|Arabica Cherry|Robusta Parchment|Robusta Cherry)\s+"
    r"(?P<price>\d{3,6}(?:\.\d{1,2})?)\b(?!\s*-\s*\d)",
    re.I,
)


def parse_coffee_report_text(
    text: str,
    *,
    source_url: str = COFFEE_BOARD_URL,
    raw_name: str | None = None,
) -> list[ParsedObservation]:
    """Parse only clearly labelled Indian grade + centre + price rows.

    Ambiguous numbers, ranges (10000-12000), and international futures are skipped.
    """
    unit = detect_unit(text)
    report_date = detect_report_date(text, raw_name)
    if unit is None or report_date is None:
        return []

    observations: list[ParsedObservation] = []
    for match in ROW_RE.finditer(text):
        after = text[match.end() : match.end() + 12]
        if re.match(r"\s*-\s*\d", after):
            continue
        if re.search(r"\d\s*-\s*\d", match.group(0)):
            continue
        centre = re.sub(r"\s+", " ", match.group("centre")).strip(" -")
        if not _looks_like_centre(centre):
            continue
        grade = detect_grade(match.group("grade"))
        price = _decimal(match.group("price"))
        if grade is None or price is None:
            continue
        observations.append(
            ParsedObservation(
                commodity_code="coffee",
                market_name=centre,
                market_kind="unknown",
                market_state=None,
                market_district=None,
                grade_code=grade,
                market_date=report_date,
                price=price,
                price_min=None,
                price_max=None,
                price_avg=price,
                unit=unit,
                price_type="reported_average",
                source_code="coffee_board_of_india",
                source_url=source_url,
                publisher_source_label="Coffee Board of India Daily Market Report",
                notes=(
                    "Market kind left as unknown unless the report explicitly names "
                    "the venue type. Not assumed to be a curing-centre quote."
                ),
            )
        )
    return observations


def parse_coffee_pdf(
    path: Path,
    *,
    source_url: str = COFFEE_BOARD_URL,
) -> list[ParsedObservation]:
    reader = PdfReader(str(path))
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    text = "\n".join(pages)
    return parse_coffee_report_text(text, source_url=source_url, raw_name=path.name)
