"""Cold-storage nearby search payload. Does not invent availability or status."""

from __future__ import annotations

from typing import Any

from apps.api.errors import ApiError
from apps.api.storage_service import StorageService

_service: StorageService | None = None


def get_storage_service() -> StorageService:
    global _service
    if _service is None:
        _service = StorageService()
    return _service


def _source_label(source: str, notes: str) -> str:
    text = (source or "").strip()
    lower = text.lower()
    if "nhb" in lower:
        return "NHB project record"
    if "project dataset" in lower:
        return "Project dataset"
    if notes and "nhb" in notes.lower():
        return "NHB project record"
    return text or "Unknown source"


def _status_label(status: str) -> str:
    value = (status or "unknown").strip().lower()
    if value in ("", "unknown"):
        return "Unknown"
    if value in ("operational", "operating", "active"):
        return "Operational"
    if value in ("non_operational", "non-operational", "closed", "inactive"):
        return "Not operational"
    return status.strip()


def _availability_label(record: dict[str, Any]) -> str:
    kg = record.get("current_availability_kg")
    if kg in (None, ""):
        return "Contact facility"
    return str(kg) + " kg reported in dataset"


def _source_status(record: dict[str, Any]) -> str:
    status = str(record.get("verification_status") or "").strip()
    if status == "REGISTERED_NHB":
        return "NHB registered"
    if status == "NHB_PROJECT_RECORD":
        return "NHB project record"
    if status == "UNVERIFIED":
        return "Unverified"
    source = str(record.get("source") or "").lower()
    if "nhb" in source:
        return "NHB project record"
    return status or "Unverified"


def _commodities_label(record: dict[str, Any]) -> str:
    crops = str(record.get("supported_crops") or "").strip()
    if not crops:
        return "Contact facility"
    return crops


def _public_record(record: dict[str, Any]) -> dict[str, Any]:
    source = str(record.get("source") or "unknown")
    notes = str(record.get("notes") or "")
    status = str(record.get("operational_status") or "unknown")
    routing_source = record.get("routing_source")
    lat = record.get("latitude")
    lon = record.get("longitude")
    maps_url = None
    if lat is not None and lon is not None:
        maps_url = f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=14/{lat}/{lon}"
    return {
        "id": record.get("id") or record.get("document_id"),
        "name": record.get("name") or "",
        "village": record.get("village") or "",
        "taluk": record.get("taluk") or "",
        "district": record.get("district") or "",
        "state": record.get("state") or "",
        "location": record.get("facility_location")
        or ", ".join(part for part in (record.get("district"), record.get("state")) if part),
        "address": record.get("address") or "",
        "capacity_mt": record.get("capacity_mt"),
        "storage_type": record.get("storage_type") or "",
        "supported_crops": record.get("supported_crops") or "",
        "commodities_supported": record.get("supported_crops") or "",
        "commodities_label": _commodities_label(record),
        "contact": record.get("contact") or "",
        "phone": record.get("contact") or "",
        "email": record.get("email") or "",
        "latitude": lat,
        "longitude": lon,
        "distance_km": record.get("distance_km"),
        "road_distance_km": record.get("road_distance_km"),
        "eta_minutes": record.get("eta_minutes"),
        "routing_source": routing_source,
        "routing_note": record.get("routing_note"),
        "match_type": record.get("match_type"),
        "operational_status": status,
        "operational_status_label": _status_label(status),
        "operational_checked_at": record.get("operational_checked_at"),
        "current_availability_kg": record.get("current_availability_kg"),
        "availability": record.get("availability") or _availability_label(record),
        "availability_label": _availability_label(record),
        "source": source,
        "source_name": record.get("source_name") or source,
        "source_url": record.get("source_url") or "",
        "source_type": record.get("source_type") or "",
        "source_status": _source_status(record),
        "source_label": _source_label(source, notes),
        "verification_status": record.get("verification_status") or "",
        "last_verified_at": record.get("last_verified_at") or "",
        "directions_url": maps_url,
        "coordinates_source": record.get("coordinates_source"),
        "notes": notes,
    }


def nearby_payload(
    latitude: float,
    longitude: float,
    crop: str | None = None,
    quantity_kg: float | None = None,
    district: str | None = None,
    max_distance_km: float = 100,
    limit: int = 5,
) -> dict[str, Any]:
    if latitude < -90 or latitude > 90:
        raise ApiError(400, "invalid_latitude", "latitude must be between -90 and 90")
    if longitude < -180 or longitude > 180:
        raise ApiError(400, "invalid_longitude", "longitude must be between -180 and 180")

    rows = get_storage_service().find_nearby_storages(
        latitude=latitude,
        longitude=longitude,
        crop=crop,
        quantity_kg=quantity_kg,
        district=district,
        max_distance_km=max_distance_km,
        limit=limit,
    )
    public = [_public_record(row) for row in rows]
    routing_sources = sorted({row.get("routing_source") or "" for row in public if row.get("routing_source")})
    return {
        "count": len(public),
        "farmer_location": {
            "latitude": latitude,
            "longitude": longitude,
            "label": "Mysuru demo location" if abs(latitude - 12.2958) < 0.0002 and abs(longitude - 76.6394) < 0.0002 else None,
        },
        "filters": {
            "crop": crop or None,
            "quantity_kg": quantity_kg,
            "district": district or None,
            "max_distance_km": max_distance_km,
            "limit": limit,
        },
        "routing_sources": routing_sources,
        "disclaimer": (
            "Unknown operational status is not the same as currently operating. "
            "NHB project/sanction records are not verified operating facilities. "
            "Availability is shown only when the dataset reports it."
        ),
        "storages": public,
    }


def location_payload(location: str, limit: int = 5) -> dict[str, Any]:
    result = get_storage_service().find_for_location(location, limit=limit)
    facilities = [_public_record(row) for row in result.get("facilities") or []]
    resolved = result.get("resolved_location") or {}
    return {
        "requested_location": result.get("requested_location"),
        "matched_location": facilities[0]["location"] if facilities else None,
        "match_type": result.get("match_type"),
        "distance_km": facilities[0]["distance_km"] if facilities else None,
        "query_state": resolved.get("state"),
        "query_district": resolved.get("district"),
        "query_coordinates_precision": resolved.get("coordinates_precision"),
        "message": result.get("message"),
        "disclaimer": (
            "Nearby facilities are not located in the selected village. "
            "NHB project/sanction records list facilities; they do not by themselves prove current operation. "
            "Availability and crop compatibility are shown only when a source reports them."
        ),
        "count": len(facilities),
        "facilities": facilities,
    }
