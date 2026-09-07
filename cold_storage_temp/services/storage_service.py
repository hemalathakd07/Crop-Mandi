"""
AgriWise AI - Cold Storage Service

Compatible with:
GET /api/cold-storages?latitude=...&longitude=...

Expected public method:
    find_nearby_storages(
        latitude,
        longitude,
        crop=None,
        quantity_kg=None,
        district=None,
        max_distance_km=100,
        limit=5,
    )

Data source:
    CSV files in datasets/:
      - nhb_karnataka_cold_storages.csv
      - cold_storages.csv
      - demo_project_cold_storages.csv

Routing:
    OpenRouteService if ORS_API_KEY / OPENROUTESERVICE_API_KEY is configured.
    Falls back to haversine distance with an explicit routing_source flag.
"""

from __future__ import annotations

import csv
import math
import os
import time
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATASETS_DIR = PROJECT_ROOT / "datasets"

load_dotenv(PROJECT_ROOT / ".env")


class StorageService:
    def __init__(self, data_path: str | Path | None = None):
        self.data_path = Path(data_path) if data_path else DATASETS_DIR / "cold_storages.csv"
        self.storages: list[dict[str, Any]] = []
        self._load_data()

        self.ors_api_key = (
            os.getenv("ORS_API_KEY", "").strip()
            or os.getenv("OPENROUTESERVICE_API_KEY", "").strip()
        )

        self.nominatim_enabled = (
            os.getenv("COLD_STORAGE_ENABLE_GEOCODING", "true").strip().lower()
            in {"1", "true", "yes", "on"}
        )

        self._load_extra_sources()

    # ------------------------------------------------------------
    # DATA
    # ------------------------------------------------------------

    def _load_csv(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []

        try:
            with path.open("r", encoding="utf-8-sig", newline="") as f:
                rows = list(csv.DictReader(f))
        except Exception as exc:
            print(f"[StorageService] CSV read failed: {path}: {exc}")
            return []

        result = []
        for row in rows:
            result.append(self._normalize_storage(row))
        return result

    def _load_data(self):
        self.storages = self._load_csv(self.data_path)

    def _load_extra_sources(self):
        candidates = [
            DATASETS_DIR / "nhb_karnataka_cold_storages.csv",
            DATASETS_DIR / "demo_project_cold_storages.csv",
        ]

        by_key: dict[tuple[str, str], dict[str, Any]] = {}

        for record in self.storages:
            key = (
                self._norm(record.get("name")),
                self._norm(record.get("address")),
            )
            by_key[key] = record

        for path in candidates:
            if not path.exists():
                continue

            for record in self._load_csv(path):
                key = (
                    self._norm(record.get("name")),
                    self._norm(record.get("address")),
                )

                if key in by_key:
                    existing = by_key[key]
                    for field in (
                        "latitude",
                        "longitude",
                        "capacity_mt",
                        "district",
                        "address",
                        "source",
                    ):
                        if self._empty(existing.get(field)) and not self._empty(record.get(field)):
                            existing[field] = record[field]
                else:
                    by_key[key] = record

        self.storages = list(by_key.values())

        print(
            f"[StorageService] Loaded "
            f"{len(self.storages)} cold-storage records."
        )

    @staticmethod
    def _norm(value: Any) -> str:
        return " ".join(str(value or "").strip().lower().split())

    @staticmethod
    def _empty(value: Any) -> bool:
        return value in (None, "")

    def _normalize_storage(self, row: dict[str, Any]) -> dict[str, Any]:
        def number(value):
            try:
                if value in (None, ""):
                    return None
                return float(value)
            except (TypeError, ValueError):
                return None

        latitude = number(
            row.get("latitude")
            or row.get("lat")
        )

        longitude = number(
            row.get("longitude")
            or row.get("lng")
            or row.get("lon")
        )

        capacity = number(
            row.get("capacity_mt")
            or row.get("capacity")
        )

        return {
            "id": row.get("id") or row.get("document_id"),
            "document_id": row.get("document_id") or row.get("id"),
            "name": str(
                row.get("name")
                or row.get("cold_storage_name")
                or ""
            ).strip(),
            "district": str(
                row.get("district")
                or ""
            ).strip(),
            "state": str(
                row.get("state")
                or "Karnataka"
            ).strip(),
            "address": str(
                row.get("address")
                or ""
            ).strip(),
            "capacity_mt": capacity,
            "supported_crops": str(
                row.get("supported_crops")
                or row.get("crops")
                or ""
            ).strip(),
            "storage_cost_per_kg_day": number(
                row.get("storage_cost_per_kg_day")
            ),
            "contact": str(
                row.get("contact")
                or ""
            ).strip(),
            "latitude": latitude,
            "longitude": longitude,
            "current_availability_kg": number(
                row.get("current_availability_kg")
            ),
            "source": str(
                row.get("source")
                or row.get("data_source")
                or "unknown"
            ).strip(),
            "operational_status": str(
                row.get("operational_status")
                or "unknown"
            ).strip().lower(),
            "operational_checked_at": row.get(
                "operational_checked_at"
            ),
            "coordinates_source": row.get(
                "coordinates_source"
            ),
            "notes": row.get("notes") or "",
        }

    # ------------------------------------------------------------
    # GEOCODING
    # ------------------------------------------------------------

    def _geocode(self, record: dict[str, Any]) -> bool:
        if not self.nominatim_enabled:
            return False

        if (
            record.get("latitude") is not None
            and record.get("longitude") is not None
        ):
            return True

        address = record.get("address") or ""
        district = record.get("district") or ""
        state = record.get("state") or "Karnataka"

        query = ", ".join(
            part for part in [
                address,
                district,
                state,
                "India",
            ]
            if part
        )

        if not query.strip():
            return False

        try:
            response = requests.get(
                "https://nominatim.openstreetmap.org/search",
                params={
                    "q": query,
                    "format": "jsonv2",
                    "limit": 1,
                    "countrycodes": "in",
                },
                headers={
                    "User-Agent":
                        "AgriWiseAI-ColdStorage/1.0"
                },
                timeout=8,
            )

            response.raise_for_status()

            results = response.json()

            if not results:
                return False

            record["latitude"] = float(
                results[0]["lat"]
            )

            record["longitude"] = float(
                results[0]["lon"]
            )

            record["coordinates_source"] = (
                "OpenStreetMap Nominatim"
            )

            time.sleep(1)

            return True

        except Exception as exc:
            print(
                f"[StorageService] Geocoding failed "
                f"for {record.get('name')}: {exc}"
            )
            return False

    # ------------------------------------------------------------
    # DISTANCE / ROUTING
    # ------------------------------------------------------------

    @staticmethod
    def haversine_km(
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float,
    ) -> float:
        radius = 6371.0088

        p1 = math.radians(lat1)
        p2 = math.radians(lat2)

        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)

        a = (
            math.sin(dlat / 2) ** 2
            +
            math.cos(p1)
            * math.cos(p2)
            * math.sin(dlon / 2) ** 2
        )

        return radius * (
            2 * math.atan2(
                math.sqrt(a),
                math.sqrt(1 - a),
            )
        )

    def _route_ors(
        self,
        origin_lat: float,
        origin_lon: float,
        destination_lat: float,
        destination_lon: float,
    ) -> tuple[float | None, float | None]:
        if not self.ors_api_key:
            return None, None

        try:
            response = requests.get(
                "https://api.openrouteservice.org/v2/directions/driving-car",
                params={
                    "api_key": self.ors_api_key,
                    "start": f"{origin_lon},{origin_lat}",
                    "end": f"{destination_lon},{destination_lat}",
                },
                timeout=15,
            )

            response.raise_for_status()

            data = response.json()

            summary = (
                data.get("features", [{}])[0]
                .get("properties", {})
                .get("summary", {})
            )

            distance_km = (
                float(summary["distance"]) / 1000
                if summary.get("distance") is not None
                else None
            )

            eta_minutes = (
                float(summary["duration"]) / 60
                if summary.get("duration") is not None
                else None
            )

            return distance_km, eta_minutes

        except Exception as exc:
            print(
                "[StorageService] ORS routing failed:",
                exc,
            )
            return None, None

    # ------------------------------------------------------------
    # PUBLIC API
    # ------------------------------------------------------------

    def find_nearby_storages(
        self,
        latitude: float,
        longitude: float,
        crop: str | None = None,
        quantity_kg: float | None = None,
        district: str | None = None,
        max_distance_km: float = 100,
        limit: int = 5,
    ) -> list[dict[str, Any]]:

        max_distance_km = max(
            1,
            min(float(max_distance_km), 500),
        )

        limit = max(
            1,
            min(int(limit), 20),
        )

        crop_norm = self._norm(crop)
        district_norm = self._norm(district)

        candidates = []

        for record in self.storages:
            if district_norm:
                if self._norm(record.get("district")) != district_norm:
                    continue

            if crop_norm:
                supported = self._norm(
                    record.get("supported_crops")
                )

                if (
                    supported
                    and "multi" not in supported
                    and crop_norm not in supported
                ):
                    continue

            available_kg = record.get(
                "current_availability_kg"
            )

            if (
                quantity_kg is not None
                and available_kg is not None
                and float(available_kg) < float(quantity_kg)
            ):
                continue

            if not self._geocode(record):
                continue

            if (
                record.get("latitude") is None
                or record.get("longitude") is None
            ):
                continue

            straight_distance = self.haversine_km(
                latitude,
                longitude,
                record["latitude"],
                record["longitude"],
            )

            # Pre-filter using straight-line distance.
            # Road distance will be calculated afterwards.
            if straight_distance > max_distance_km:
                continue

            candidates.append(
                (
                    straight_distance,
                    record,
                )
            )

        candidates.sort(
            key=lambda item: item[0]
        )

        results = []

        for straight_distance, record in candidates[
            : max(limit * 2, limit)
        ]:

            road_distance, eta_minutes = self._route_ors(
                latitude,
                longitude,
                record["latitude"],
                record["longitude"],
            )

            if road_distance is None:
                road_distance = straight_distance
                routing_source = "haversine_fallback"
                routing_note = (
                    "Road routing unavailable; "
                    "distance is straight-line estimate."
                )
            else:
                routing_source = "OpenRouteService"
                routing_note = (
                    "Road distance and ETA from routing service."
                )

            if (
                road_distance > max_distance_km
            ):
                continue

            result = dict(record)

            result.update(
                {
                    "distance_km": round(
                        road_distance,
                        2,
                    ),
                    "road_distance_km": round(
                        road_distance,
                        2,
                    ),
                    "eta_minutes": (
                        round(
                            eta_minutes,
                            1,
                        )
                        if eta_minutes is not None
                        else None
                    ),
                    "routing_source":
                        routing_source,
                    "routing_note":
                        routing_note,
                    "availability":
                        (
                            "Available"
                            if record.get(
                                "current_availability_kg"
                            )
                            not in (None, "")
                            else "Availability not reported"
                        ),
                }
            )

            results.append(result)

            if len(results) >= limit:
                break

        return results
