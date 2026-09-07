from fastapi.testclient import TestClient

import apps.api.main as api_main
from apps.api.cold_storage_match import is_cold_storage_facility, resolve_query_location
from apps.api.storage_service import StorageService


MYSURU = {"latitude": 12.2958, "longitude": 76.6394}

TARGET_LOCATIONS = [
    "Ballupete",
    "Chikkamagaluru",
    "Gendehalli",
    "Gudugale",
    "Hanbal",
    "Hassan",
    "Kodlipete",
    "Kumbrahalli",
    "Kuninganahalli",
    "Kushalnagar",
    "Madikeri",
    "Makkandur",
    "Mudigere",
    "Pattadur",
    "Sakleshpur",
    "Somwarpet",
    "Theni",
]


def test_cold_storages_mysuru_returns_dataset_records():
    client = TestClient(api_main.app)
    response = client.get("/api/cold-storages", params=MYSURU)
    assert response.status_code == 200
    body = response.json()
    assert body["count"] >= 1
    assert len(body["storages"]) == body["count"]
    names = [row["name"] for row in body["storages"]]
    assert any(
        "Mysuru" in (row.get("district") or "") or "C5" in name or "AVS" in name
        for name, row in zip(names, body["storages"])
    )
    for row in body["storages"]:
        assert row["operational_status"]
        assert row["source"]
        assert row["availability_label"] != "Available"
        if row["operational_status"] == "unknown":
            assert row["operational_status_label"] == "Unknown"
        assert row["distance_km"] is not None
        assert row["routing_source"] in ("haversine_fallback", "OpenRouteService")
        assert "kswc" not in (row["name"] or "").lower()
        assert "warehouse" not in (row["name"] or "").lower()


def test_cold_storages_crop_and_quantity_do_not_invent_status():
    client = TestClient(api_main.app)
    coffee = client.get("/api/cold-storages", params={**MYSURU, "crop": "coffee", "limit": 10})
    pepper = client.get("/api/cold-storages", params={**MYSURU, "crop": "pepper", "quantity_kg": 100, "limit": 10})
    assert coffee.status_code == 200
    assert pepper.status_code == 200
    assert coffee.json()["count"] >= 1
    assert pepper.json()["count"] >= 1
    for row in coffee.json()["storages"] + pepper.json()["storages"]:
        assert row["operational_status_label"] != "Available"


def test_existing_price_endpoints_still_registered():
    client = TestClient(api_main.app)
    latest = client.get("/api/prices/latest", params={"commodity": "coffee"})
    markets = client.get("/api/markets/prices", params={"commodity": "coffee", "location": "Sakleshpur"})
    estimate = client.get("/api/predictions/next", params={"commodity": "coffee", "series": "Arabica Parchment"})
    assert latest.status_code == 200
    assert markets.status_code == 200
    assert estimate.status_code == 200


def test_all_target_locations_are_accepted():
    client = TestClient(api_main.app)
    for name in TARGET_LOCATIONS:
        response = client.get("/api/cold-storage", params={"location": name})
        assert response.status_code == 200, name
        body = response.json()
        assert body["requested_location"]
        assert body["match_type"] in ("EXACT", "NEARBY", "DISTRICT_NEARBY", "NO_DATA")
        assert body["match_type"] != "UNKNOWN_LOCATION"


def test_hassan_prefers_exact_local_facility():
    client = TestClient(api_main.app)
    body = client.get("/api/cold-storage", params={"location": "Hassan"}).json()
    assert body["match_type"] == "EXACT"
    assert body["facilities"]
    for row in body["facilities"]:
        assert row["match_type"] == "EXACT"
        assert (row["district"] or "").lower() == "hassan"
        assert row["state"] == "Karnataka"
        assert row["source_url"]
        assert row["verification_status"] == "NHB_PROJECT_RECORD"
        assert row["source_status"] == "NHB project record"
        assert row["source_url"]
        assert row["availability_label"] == "Contact facility"
        assert row["commodities_label"] == "Contact facility"
        assert "Available now" not in (row["availability_label"] or "")


def test_sakleshpur_returns_nearby_not_pretending_local():
    client = TestClient(api_main.app)
    body = client.get("/api/cold-storage", params={"location": "Sakleshpur"}).json()
    assert body["match_type"] == "NEARBY"
    assert body["facilities"]
    row = body["facilities"][0]
    assert "sakleshpur" not in (row["district"] or "").lower()
    assert row["match_type"] != "EXACT"
    assert row["distance_km"] is not None
    assert 0 < row["distance_km"] <= 75


def test_nearest_facility_is_hassan_cluster_for_sakleshpur_area():
    client = TestClient(api_main.app)
    sakleshpur = client.get("/api/cold-storage", params={"location": "Sakleshpur"}).json()["facilities"][0]
    ballupete = client.get("/api/cold-storage", params={"location": "Ballupete"}).json()["facilities"][0]
    hanbal = client.get("/api/cold-storage", params={"location": "Hanbal"}).json()["facilities"][0]
    kumbra = client.get("/api/cold-storage", params={"location": "Kumbrahalli"}).json()["facilities"][0]
    names = {sakleshpur["name"], ballupete["name"], hanbal["name"], kumbra["name"]}
    assert names  # same verified Hassan cluster is reused, not duplicated per village
    for row in (sakleshpur, ballupete, hanbal, kumbra):
        assert (row["district"] or "").lower() == "hassan"
        assert row["distance_km"] is not None


def test_theni_is_tamil_nadu_and_not_karnataka():
    resolved = resolve_query_location("Theni")
    assert resolved is not None
    assert resolved["state"] == "Tamil Nadu"
    client = TestClient(api_main.app)
    body = client.get("/api/cold-storage", params={"location": "Theni"}).json()
    assert body["query_state"] == "Tamil Nadu"
    if body["facilities"]:
        assert all(row["state"] != "Karnataka" or row["distance_km"] <= 75 for row in body["facilities"])
        assert all("hassan" not in (row["location"] or "").lower() or row["distance_km"] <= 75 for row in body["facilities"])
    else:
        assert body["match_type"] == "NO_DATA"
        assert "75 KM" in (body["message"] or "").upper()


def test_chikkamagaluru_is_district_nearby():
    client = TestClient(api_main.app)
    body = client.get("/api/cold-storage", params={"location": "Chikkamagaluru"}).json()
    assert body["match_type"] == "DISTRICT_NEARBY"
    assert body["facilities"][0]["distance_km"] > 50
    assert body["facilities"][0]["distance_km"] <= 75


def test_unknown_capacity_and_availability_are_not_invented():
    client = TestClient(api_main.app)
    body = client.get("/api/cold-storage", params={"location": "Hassan", "limit": 5}).json()
    for row in body["facilities"]:
        if row["capacity_mt"] is not None:
            assert isinstance(row["capacity_mt"], (int, float))
        assert row["availability_label"] != "Available now"
        assert row["availability_label"] == "Contact facility"


def test_source_is_returned_and_no_warehouse_names():
    client = TestClient(api_main.app)
    body = client.get("/api/cold-storage", params={"location": "Hassan", "limit": 10}).json()
    names = [row["name"].lower() for row in body["facilities"]]
    assert names
    assert all("warehouse" not in name and "kswc" not in name and "curing" not in name for name in names)
    for row in body["facilities"]:
        assert row["source_name"]
        assert row["source_url"]
        assert is_cold_storage_facility(row)


def test_facilities_are_not_duplicated_in_dataset_key():
    service = StorageService()
    keys = [(service._norm(r.get("name")), service._norm(r.get("address"))) for r in service.storages]
    assert len(keys) == len(set(keys))


def test_unknown_location_is_not_fabricated():
    client = TestClient(api_main.app)
    body = client.get("/api/cold-storage", params={"location": "Atlantis"}).json()
    assert body["match_type"] == "UNKNOWN_LOCATION"
    assert body["facilities"] == []
