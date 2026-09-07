from sqlalchemy.orm import Session

from cropmandi.db.models import Commodity, Grade, Market, Source

COFFEE_GRADES = [
    ("UNSPECIFIED", "Unspecified"),
    ("ARABICA_PARCHMENT", "Arabica Parchment"),
    ("ARABICA_CHERRY", "Arabica Cherry"),
    ("ROBUSTA_PARCHMENT", "Robusta Parchment"),
    ("ROBUSTA_CHERRY", "Robusta Cherry"),
]

PEPPER_GRADES = [
    ("UNSPECIFIED", "Unspecified"),
    ("GARBLED", "Garbled"),
    ("UNGARBLED", "Ungarbled"),
    ("UNGRADED", "Ungraded"),
    ("WHITE", "White"),
]

RICE_GRADES = [
    ("UNSPECIFIED", "Unspecified"),
]

SOURCES = [
    {
        "code": "coffee_board_of_india",
        "name": "Coffee Board of India Daily Market Report",
        "publisher": "Coffee Board of India",
        "homepage_url": "https://coffeeboard.gov.in/Market_Info.aspx",
        "classification": "official_government",
        "notes": "Daily Coffee Market Report PDFs. Parser stores only clearly identifiable rows.",
    },
    {
        "code": "spices_board_india",
        "name": "Spices Board of India Current Market Price",
        "publisher": "Spices Board India",
        "homepage_url": (
            "https://www.indianspices.com/marketing/price/domestic/current-market-price.html"
        ),
        "classification": "official_government",
        "notes": (
            "Published as indicative daily averages, not guaranteed transaction prices. "
            "Underlying publisher labels such as IPSTA or APMC are stored separately."
        ),
    },
    {
        "code": "agmarknet_data_gov_in",
        "name": "AGMARKNET Daily Market Prices via data.gov.in",
        "publisher": "Directorate of Marketing & Inspection (DMI), Ministry of Agriculture and Farmers Welfare, Government of India",
        "homepage_url": "https://data.gov.in/resource/current-daily-price-various-commodities-various-markets-mandi",
        "classification": "official_government",
        "notes": (
            "Daily mandi prices from AGMARKNET. Includes min, max, and modal prices in Rs/quintal. "
            "Filtered to Karnataka and Rice commodities."
        ),
    },
    {
        "code": "unverified_local_data",
        "name": "Unverified local spreadsheet",
        "publisher": "Unknown / team spreadsheet",
        "homepage_url": None,
        "classification": "UNVERIFIED_LOCAL_DATA",
        "notes": "Must not be labelled Coffee Board or Spices Board.",
    },
]


def get_or_create(session: Session, model, **kwargs):
    instance = session.query(model).filter_by(**kwargs).one_or_none()
    if instance is not None:
        return instance
    instance = model(**kwargs)
    session.add(instance)
    session.flush()
    return instance


def seed_reference_data(session: Session) -> None:
    coffee = get_or_create(session, Commodity, code="coffee", name="Coffee")
    pepper = get_or_create(session, Commodity, code="pepper", name="Black Pepper")
    rice = get_or_create(session, Commodity, code="rice", name="Rice")

    for code, name in COFFEE_GRADES:
        get_or_create(session, Grade, commodity_id=coffee.id, code=code, name=name)
    for code, name in PEPPER_GRADES:
        get_or_create(session, Grade, commodity_id=pepper.id, code=code, name=name)
    for code, name in RICE_GRADES:
        get_or_create(session, Grade, commodity_id=rice.id, code=code, name=name)

    get_or_create(
        session,
        Market,
        name="Cochin",
        kind="indicative_market",
        district="",
        state="Kerala",
    )
    get_or_create(
        session,
        Market,
        name="Sirsi",
        kind="apmc",
        district="Uttara Kannada",
        state="Karnataka",
    )

    for source in SOURCES:
        existing = session.query(Source).filter_by(code=source["code"]).one_or_none()
        if existing is None:
            session.add(Source(**source))
    session.flush()
