"""Live weather for a farmer location. Uses catalog coordinates, then Open-Meteo."""

from __future__ import annotations

from typing import Any

import requests

from apps.api.cold_storage_match import resolve_query_location
from apps.api.errors import ApiError

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

WMO_DESCRIPTIONS = {
    0: "Clear",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Rime fog",
    51: "Light drizzle",
    53: "Drizzle",
    55: "Dense drizzle",
    56: "Freezing drizzle",
    57: "Freezing drizzle",
    61: "Slight rain",
    63: "Rain",
    65: "Heavy rain",
    66: "Freezing rain",
    67: "Freezing rain",
    71: "Slight snow",
    73: "Snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Rain showers",
    81: "Rain showers",
    82: "Violent rain showers",
    85: "Snow showers",
    86: "Snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm",
    99: "Thunderstorm",
}


def _unavailable(message: str = "Weather unavailable") -> ApiError:
    return ApiError(503, "weather_unavailable", message, {"available": False})


def _geocode_name(location: str) -> tuple[float, float, str] | None:
    resolved = resolve_query_location(location)
    if resolved and resolved.get("latitude") is not None and resolved.get("longitude") is not None:
        return (
            float(resolved["latitude"]),
            float(resolved["longitude"]),
            str(resolved.get("name") or location),
        )
    try:
        response = requests.get(
            NOMINATIM_URL,
            params={
                "q": f"{location}, India",
                "format": "jsonv2",
                "limit": 1,
                "countrycodes": "in",
            },
            headers={"User-Agent": "CropMandiAI-Weather/1.0"},
            timeout=8,
        )
        response.raise_for_status()
        results = response.json()
        if not results:
            return None
        return float(results[0]["lat"]), float(results[0]["lon"]), location
    except Exception:
        return None


def _fetch_current(lat: float, lon: float) -> dict[str, Any] | None:
    try:
        response = requests.get(
            OPEN_METEO_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,relative_humidity_2m,weather_code",
                "timezone": "auto",
            },
            timeout=8,
        )
        response.raise_for_status()
        return response.json()
    except Exception:
        return None


def weather_payload(location: str) -> dict[str, Any]:
    place = (location or "").strip()
    if not place:
        raise ApiError(400, "missing_location", "location is required")
    coords = _geocode_name(place)
    if coords is None:
        raise _unavailable()
    lat, lon, name = coords
    payload = _fetch_current(lat, lon)
    current = (payload or {}).get("current") or {}
    temp = current.get("temperature_2m")
    humidity = current.get("relative_humidity_2m")
    code = current.get("weather_code")
    if temp is None:
        raise _unavailable()
    description = WMO_DESCRIPTIONS.get(int(code) if code is not None else -1, "Current conditions")
    return {
        "available": True,
        "location": name,
        "temperature_c": temp,
        "humidity_percent": humidity,
        "description": description,
        "weather_code": code,
    }
