from fastapi.testclient import TestClient

import apps.api.main as api_main
from apps.api.market_centres import is_unmapped, mappings_for, resolve_location


client = TestClient(api_main.app)


def test_coffee_markets_endpoint():
    response = client.get("/api/markets", params={"commodity": "coffee"})
    assert response.status_code == 200
    body = response.json()
    assert body["commodity"] == "coffee"
    assert body["source_workbook"] == "coffee_market_price.xlsx"
    assert body["data_status"] == "UNVERIFIED_LOCAL_DATA"
    names = [row["name"] for row in body["locations"]]
    assert "Sakleshpur" in names
    assert "Sakleshpura" not in names
    assert "Chikkamagaluru" in names
    sakleshpur = next(row for row in body["locations"] if row["name"] == "Sakleshpur")
    assert sakleshpur["raw_variants"] == ["Sakleshpura", "Sakleshpur", "SAKLESHPUR"]
    assert "PAI COMM0DITY" in body["unmapped_raw_centres"]
    assert "WESTERN COFFEE CURERS EXPORTS PVT LIMITED" in body["unmapped_raw_centres"]
    assert "GOLDEN COFFEE AGENCIES" in body["unmapped_raw_centres"]


def test_pepper_markets_endpoint():
    response = client.get("/api/markets", params={"commodity": "pepper"})
    assert response.status_code == 200
    body = response.json()
    assert body["commodity"] == "pepper"
    assert body["source_workbook"] == "pepper_market_price.xlsx"
    names = [row["name"] for row in body["locations"]]
    assert "Balupet" in names
    assert "Ballupete" not in names
    assert "Chikmagalur" in names
    assert "Chikkamagaluru" not in names
    balupet = next(row for row in body["locations"] if row["name"] == "Balupet")
    assert balupet["raw_variants"] == ["Balupet"]
    chik = next(row for row in body["locations"] if row["name"] == "Chikmagalur")
    assert chik["raw_variants"] == ["Chikmagalur"]


def test_sakleshpur_location_mapping():
    coffee = client.get(
        "/api/markets/centres",
        params={"commodity": "coffee", "location": "Sakleshpur"},
    )
    assert coffee.status_code == 200
    coffee_raw = {row["raw_market_centre"] for row in coffee.json()["centres"]}
    assert "LIKITHA COFFEE SAKLESHPURA" in coffee_raw
    assert "GAIN COFEE SAKLESHPURA" in coffee_raw
    assert "NASIR TRADERS SAKLESHPURA" in coffee_raw
    assert any("KUMBARAHALLI SAKLESHPUR" in name for name in coffee_raw)

    pepper = client.get(
        "/api/markets/centres",
        params={"commodity": "pepper", "location": "Sakleshpur"},
    )
    assert pepper.status_code == 200
    pepper_raw = {row["raw_market_centre"] for row in pepper.json()["centres"]}
    assert "Sakleshpur-Gain Coffee Traders" in pepper_raw
    assert any(name.startswith("Sakleshpur-") for name in pepper_raw)


def test_coffee_sakleshpura_alias():
    by_canonical = client.get(
        "/api/markets/centres",
        params={"commodity": "coffee", "location": "Sakleshpur"},
    ).json()
    by_alias = client.get(
        "/api/markets/centres",
        params={"commodity": "coffee", "location": "Sakleshpura"},
    ).json()
    assert by_alias["location"] == "Sakleshpur"
    assert by_alias["centres"] == by_canonical["centres"]
    assert resolve_location("coffee", "SAKLESHPUR") == "Sakleshpur"


def test_pepper_balupet_spelling():
    response = client.get(
        "/api/markets/centres",
        params={"commodity": "pepper", "location": "Balupet"},
    )
    assert response.status_code == 200
    raw = {row["raw_market_centre"] for row in response.json()["centres"]}
    assert raw == {
        "Balupet-Coffee Agencies",
        "Balupet-Geetha Coffee Trading",
        "Balupet-Nanjundeshwara Coffee Agency",
    }
    wrong = client.get(
        "/api/markets/centres",
        params={"commodity": "pepper", "location": "Ballupete"},
    )
    assert wrong.status_code == 404
    assert wrong.json()["error"] == "unknown_location"


def test_pepper_chikmagalur_spelling():
    response = client.get(
        "/api/markets/centres",
        params={"commodity": "pepper", "location": "Chikmagalur"},
    )
    assert response.status_code == 200
    raw = {row["raw_market_centre"] for row in response.json()["centres"]}
    assert all(name.startswith("Chikmagalur-") for name in raw)
    assert len(raw) == 5
    coffee_spelling = client.get(
        "/api/markets/centres",
        params={"commodity": "pepper", "location": "Chikkamagaluru"},
    )
    assert coffee_spelling.status_code == 404


def test_kumbarahalli_kept_separate():
    coffee = client.get(
        "/api/markets/centres",
        params={"commodity": "coffee", "location": "Kumbarahalli"},
    )
    assert coffee.status_code == 200
    coffee_raw = {row["raw_market_centre"] for row in coffee.json()["centres"]}
    assert any("KUMBARAHALLI" in name for name in coffee_raw)
    md = next(row for row in coffee.json()["centres"] if "KUMBARAHALLI" in row["raw_market_centre"])
    assert md["ambiguous"] is True
    assert "Sakleshpur" in md["also_mapped_to"]

    pepper = client.get(
        "/api/markets/available",
        params={"commodity": "pepper", "location": "Kumbarahalli"},
    )
    assert pepper.status_code == 200
    pepper_raw = {row["raw_market_centre"] for row in pepper.json()["centres"]}
    assert "MD COFFEE KUMBARAHALLI SAKLESHPUR-8495875252" in pepper_raw
    assert pepper.json()["unit"] is None


def test_unmapped_pai_commodity():
    assert is_unmapped("coffee", "PAI COMM0DITY")
    coffee = client.get("/api/markets", params={"commodity": "coffee"}).json()
    mapped = []
    for location in coffee["locations"]:
        centres = client.get(
            "/api/markets/centres",
            params={"commodity": "coffee", "location": location["name"]},
        ).json()["centres"]
        mapped.extend(row["raw_market_centre"] for row in centres)
    assert "PAI COMM0DITY" not in mapped
    assert "PAI COMM0DITY" in coffee["unmapped_raw_centres"]


def test_unmapped_western_coffee_curers():
    assert is_unmapped("coffee", "WESTERN COFFEE CURERS EXPORTS PVT LIMITED")
    names = []
    for mapping in mappings_for("coffee"):
        names.append(mapping.raw_market_centre)
    assert "WESTERN COFFEE CURERS EXPORTS PVT LIMITED" not in names
    available = client.get(
        "/api/markets/available",
        params={"commodity": "coffee", "location": "Sakleshpur"},
    )
    assert available.status_code == 200
    assert available.json()["unit"] == "Rs./50 Kg"
    raw = {row["raw_market_centre"] for row in available.json()["centres"]}
    assert "WESTERN COFFEE CURERS EXPORTS PVT LIMITED" not in raw
    likitha = next(
        row for row in available.json()["centres"] if row["raw_market_centre"] == "LIKITHA COFFEE SAKLESHPURA"
    )
    assert "ARABICA PARCHMENT" in likitha["types"]
    assert likitha["observation_count"] == 4
    assert "price" not in likitha
    assert "observations" not in available.json()


def test_coffee_hassan_market_prices():
    response = client.get(
        "/api/markets/prices",
        params={"commodity": "coffee", "location": "Hassan"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["commodity"] == "coffee"
    assert body["location"] == "Hassan"
    assert body["source_workbook"] == "coffee_market_price.xlsx"
    assert body["data_status"] == "UNVERIFIED_LOCAL_DATA"
    assert body["unit"] == "Rs./50 Kg"
    assert body["official"] is False
    assert body["count"] == len(body["observations"])
    assert body["count"] >= 1
    prices = body["observations"]
    for row in prices:
        assert row["commodity"] == "coffee"
        assert row["location"] == "Hassan"
        assert isinstance(row["price"], (int, float))
        assert row["price"] not in (0, "-", "—", None)
        assert row["unit"] == "Rs./50 Kg"
        assert row["official"] is False
        assert row["data_status"] == "UNVERIFIED_LOCAL_DATA"
        assert row["source"] == "coffee_market_price.xlsx"
        assert row["date"]
    lakshmi_parchment = next(
        row
        for row in prices
        if row["market_centre"] == "Lakshmi Coffee Curing Works-Hassan-9901124342"
        and row["type"] == "ARABICA PARCHMENT"
    )
    assert lakshmi_parchment["price"] == 25500
    lakshmi_cherry = next(
        row
        for row in prices
        if row["market_centre"] == "Lakshmi Coffee Curing Works-Hassan-9901124342"
        and row["type"] == "ARABICA CHERRY"
    )
    assert lakshmi_cherry["price"] == 13500
    nkg = next(
        row
        for row in prices
        if row["market_centre"] == "NKG-Hassan-8884418803" and row["type"] == "ARABICA PARCHMENT"
    )
    assert nkg["price"] == 25650
    dates = [row["date"] for row in prices]
    assert dates == sorted(dates, reverse=True)
    assert not any(row["type"] == "ROBUSTA PARCHMENT" for row in prices)


def test_coffee_sakleshpur_market_prices():
    response = client.get(
        "/api/markets/prices",
        params={"commodity": "coffee", "location": "Sakleshpur"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["location"] == "Sakleshpur"
    prices = body["observations"]
    assert prices
    likitha = next(
        row
        for row in prices
        if row["market_centre"] == "LIKITHA COFFEE SAKLESHPURA" and row["type"] == "ARABICA PARCHMENT"
    )
    assert likitha["price"] == 25400
    assert all(isinstance(row["price"], (int, float)) for row in prices)


def test_pepper_sakleshpur_market_prices():
    response = client.get(
        "/api/markets/prices",
        params={"commodity": "pepper", "location": "Sakleshpur"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["location"] == "Sakleshpur"
    assert body["unit"] is None
    assert body["official"] is False
    assert body["data_status"] == "UNVERIFIED_LOCAL_DATA"
    prices = body["observations"]
    assert prices
    gain = next(row for row in prices if row["market_centre"] == "Sakleshpur-Gain Coffee Traders")
    assert gain["type"] == "UnGarbaled"
    assert gain["price"] == 680
    assert gain["unit"] is None
    assert gain["official"] is False
    assert all(row["unit"] is None for row in prices)
    assert all(row["type"] in {"UnGarbaled", "White"} for row in prices)


def test_market_prices_exclude_non_numeric_values():
    response = client.get(
        "/api/markets/prices",
        params={"commodity": "coffee", "location": "Ballupete"},
    )
    assert response.status_code == 200
    prices = response.json()["observations"]
    assert prices
    assert all(isinstance(row["price"], (int, float)) for row in prices)
    assert not any(row["price"] in (0, "-", "—") for row in prices)
    types = {row["type"] for row in prices}
    assert "ROBUSTA CHERRY (383 OT)" not in types
    assert "ARABICA CHERRY (517 OT)" not in types
    assert "ROBUSTA CHERRY (385 OT)" not in types
    assert "ARABICA CHERRY (522 OT)" not in types
    hanbalu = client.get(
        "/api/markets/prices",
        params={"commodity": "coffee", "location": "Hanbalu"},
    )
    assert hanbalu.status_code == 200
    assert hanbalu.json()["observations"] == []
    assert hanbalu.json()["count"] == 0


def test_market_prices_invalid_commodity_and_unknown_location():
    bad = client.get(
        "/api/markets/prices",
        params={"commodity": "cardamom", "location": "Hassan"},
    )
    assert bad.status_code == 400
    assert bad.json()["error"] == "unsupported_commodity"

    unknown = client.get(
        "/api/markets/prices",
        params={"commodity": "coffee", "location": "NotAMappedPlace"},
    )
    assert unknown.status_code == 404
    assert unknown.json()["error"] == "unknown_location"
    assert "Traceback" not in str(unknown.json())
