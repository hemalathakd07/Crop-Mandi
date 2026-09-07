"""
Verify current cold-storage operational/open status.

Preferred source:
Google Places API (New), if GOOGLE_MAPS_API_KEY is configured.

This distinguishes:
- OPERATIONAL: business is operating, but not necessarily open right now
- CLOSED_TEMPORARILY
- CLOSED_PERMANENTLY
- FUTURE_OPENING
- OPEN_NOW / CLOSED_NOW when opening hours are returned
- UNKNOWN when Google has no usable match or no API key is configured

Usage:
    python scripts/check_cold_storage_status.py \
        --csv data/nhb_karnataka_cold_storages.csv \
        --output data/nhb_karnataka_cold_storages_status.csv

Environment:
    GOOGLE_MAPS_API_KEY=...
"""

from __future__ import annotations

import argparse
import csv
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

API_URL = "https://places.googleapis.com/v1/places:searchText"


def search_place(name: str, address: str, api_key: str):
    payload = {
        "textQuery": f"{name}, {address}, Karnataka, India",
        "maxResultCount": 1,
        "regionCode": "IN",
    }

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": (
            "places.id,"
            "places.displayName,"
            "places.formattedAddress,"
            "places.businessStatus,"
            "places.currentOpeningHours,"
            "places.googleMapsUri"
        ),
    }

    response = requests.post(
        API_URL,
        json=payload,
        headers=headers,
        timeout=20,
    )

    response.raise_for_status()

    places = response.json().get("places", [])

    if not places:
        return None

    return places[0]


def determine_status(place):
    if not place:
        return {
            "operational_status": "unknown",
            "open_now": "",
            "status_reason":
                "No confident Google Places match.",
            "google_place_id": "",
            "google_maps_url": "",
        }

    status = (
        place.get("businessStatus")
        or "BUSINESS_STATUS_UNSPECIFIED"
    )

    hours = place.get(
        "currentOpeningHours"
    ) or {}

    open_now = hours.get("openNow")

    if status == "OPERATIONAL":
        if open_now is True:
            operational_status = "open_now"
        elif open_now is False:
            operational_status = "closed_now"
        else:
            operational_status = "operational_hours_unknown"
    elif status == "CLOSED_TEMPORARILY":
        operational_status = "closed_temporarily"
    elif status == "CLOSED_PERMANENTLY":
        operational_status = "closed_permanently"
    elif status == "FUTURE_OPENING":
        operational_status = "future_opening"
    else:
        operational_status = "unknown"

    return {
        "operational_status":
            operational_status,
        "open_now":
            "" if open_now is None else str(open_now).lower(),
        "status_reason":
            status,
        "google_place_id":
            place.get("id", ""),
        "google_maps_url":
            place.get("googleMapsUri", ""),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--csv",
        required=True,
    )
    parser.add_argument(
        "--output",
        required=True,
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="0 = all records",
    )

    args = parser.parse_args()

    api_key = os.getenv(
        "GOOGLE_MAPS_API_KEY",
        "",
    ).strip()

    if not api_key:
        raise SystemExit(
            "GOOGLE_MAPS_API_KEY is not configured. "
            "Set it before running this verifier."
        )

    input_path = Path(args.csv)
    output_path = Path(args.output)
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with input_path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as f:
        rows = list(csv.DictReader(f))

    if args.limit > 0:
        rows = rows[: args.limit]

    checked_at = datetime.now(
        timezone.utc
    ).isoformat()

    for index, row in enumerate(rows, start=1):
        name = row.get("name", "").strip()
        address = row.get("address", "").strip()

        print(
            f"[{index}/{len(rows)}] Checking: {name}"
        )

        try:
            place = search_place(
                name,
                address,
                api_key,
            )

            status = determine_status(place)

            row.update(status)
            row["operational_checked_at"] = checked_at

        except Exception as exc:
            row.update(
                {
                    "operational_status": "unknown",
                    "open_now": "",
                    "status_reason":
                        f"Verification error: {exc}",
                    "google_place_id": "",
                    "google_maps_url": "",
                    "operational_checked_at":
                        checked_at,
                }
            )

        # Be gentle with external APIs.
        time.sleep(0.2)

    fieldnames = list(
        dict.fromkeys(
            key
            for row in rows
            for key in row.keys()
        )
    )

    with output_path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
        )
        writer.writeheader()
        writer.writerows(rows)

    print(
        f"Done. Wrote {len(rows)} records to {output_path}"
    )


if __name__ == "__main__":
    main()
