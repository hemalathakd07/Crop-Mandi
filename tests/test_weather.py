from unittest.mock import Mock

from fastapi.testclient import TestClient

import apps.api.main as api_main
import apps.api.weather as weather_mod


def test_weather_requires_location():
    client = TestClient(api_main.app)
    response = client.get("/api/weather")
    assert response.status_code == 400


def test_weather_returns_live_payload_for_catalog_location(monkeypatch):
    def fake_get(url, params=None, headers=None, timeout=None):
        response = Mock()
        response.raise_for_status = Mock()
        if "open-meteo" in url:
            response.json.return_value = {
                "current": {
                    "temperature_2m": 23.4,
                    "relative_humidity_2m": 61,
                    "weather_code": 0,
                }
            }
        else:
            response.json.return_value = []
        return response

    monkeypatch.setattr(weather_mod.requests, "get", fake_get)
    client = TestClient(api_main.app)
    response = client.get("/api/weather", params={"location": "Sakleshpur"})
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is True
    assert body["location"] == "Sakleshpur"
    assert body["temperature_c"] == 23.4
    assert body["humidity_percent"] == 61
    assert body["description"] == "Clear"


def test_weather_unavailable_when_fetch_fails(monkeypatch):
    def fake_get(url, params=None, headers=None, timeout=None):
        raise RuntimeError("network down")

    monkeypatch.setattr(weather_mod.requests, "get", fake_get)
    monkeypatch.setattr(weather_mod, "resolve_query_location", lambda _name: None)
    client = TestClient(api_main.app)
    response = client.get("/api/weather", params={"location": "UnknownPlaceXYZ"})
    assert response.status_code == 503
    assert response.json()["error"] == "weather_unavailable"
