from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from cropmandi.config import get_settings
from ingest.rawstore import sha256_file, write_raw

DATA_GOV_API_BASE = "https://api.data.gov.in/resource"
USER_AGENT = "CropMandiAI/0.1 (research ingest; AGMARKNET rice prices)"

# AGMARKNET resource IDs from the Rice package
HISTORICAL_RESOURCE_ID = "35985678-0d79-46b4-9ed6-6f13308a1d24"
DAILY_RESOURCE_ID = "9ef84268-d588-465a-a308-a864a43d0070"


@dataclass
class AgmarknetDownload:
    ok: bool
    url: str
    path: Path | None
    sha256: str | None
    error: str | None
    records_count: int | None = None
    metadata: dict | None = None


def _get_api_key() -> str:
    """Get DATA_GOV_API_KEY from environment or settings."""
    # Try environment variable first
    api_key = os.getenv("DATA_GOV_API_KEY")
    if api_key:
        return api_key
    
    # Try settings
    settings = get_settings()
    if hasattr(settings, 'data_gov_api_key') and settings.data_gov_api_key:
        return settings.data_gov_api_key
    
    raise ValueError("DATA_GOV_API_KEY not found in environment or settings")


def fetch_agmarknet_rice(
    resource_id: str,
    state: str = "Karnataka",
    commodity: str = "Rice",
    max_rows: int | None = None,
    dest_dir: Path | None = None,
) -> AgmarknetDownload:
    """Fetch Rice mandi prices from AGMARKNET via data.gov.in API."""
    settings = get_settings()
    dest = dest_dir or (settings.data_dir / "raw" / "agmarknet_rice")
    dest.mkdir(parents=True, exist_ok=True)
    
    try:
        api_key = _get_api_key()
        base_url = f"{DATA_GOV_API_BASE}/{resource_id}"
        
        params = {
            "api-key": api_key,
            "format": "json",
            "limit": 1000,
            "offset": 0,
        }
        
        # Add filters for state and commodity
        params["filters[State]"] = state
        params["filters[Commodity]"] = commodity
        
        all_records: List[Dict[str, Any]] = []
        offset = 0
        total_fetched = 0
        
        with httpx.Client(
            timeout=settings.cropmandi_http_timeout,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        ) as client:
            while True:
                params["offset"] = offset
                response = client.get(base_url, params=params)
                response.raise_for_status()
                
                payload = response.json()
                records = payload.get("records", [])
                
                if not records:
                    break
                
                all_records.extend(records)
                total_fetched = len(all_records)
                
                # Check if we've hit max_rows limit
                if max_rows and total_fetched >= max_rows:
                    all_records = all_records[:max_rows]
                    break
                
                # Check if we've fetched all available records
                if len(records) < params["limit"]:
                    break
                
                offset += params["limit"]
                time.sleep(0.8)  # Rate limiting as per Rice package
        
        # Save raw data as JSON
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"agmarknet_rice_{state.lower()}_{timestamp}.json"
        path = dest / filename
        
        data_to_save = {
            "source": "AGMARKNET/data.gov.in",
            "resource_id": resource_id,
            "filters": {"State": state, "Commodity": commodity},
            "records": all_records,
            "fetch_timestamp": timestamp,
        }
        
        json_data = json.dumps(data_to_save, indent=2)
        checksum = write_raw(
            path,
            json_data.encode("utf-8"),
            {
                "url": base_url,
                "resource_id": resource_id,
                "state": state,
                "commodity": commodity,
                "records_count": len(all_records),
            },
        )
        
        metadata = {
            "source": "AGMARKNET/data.gov.in",
            "resource_id": resource_id,
            "state": state,
            "commodity": commodity,
            "records_count": len(all_records),
            "fetch_timestamp": timestamp,
        }
        
        return AgmarknetDownload(
            ok=True,
            url=base_url,
            path=path,
            sha256=checksum,
            error=None,
            records_count=len(all_records),
            metadata=metadata,
        )
        
    except Exception as exc:  # noqa: BLE001 - connector must report failure, not invent data
        return AgmarknetDownload(
            ok=False,
            url=f"{DATA_GOV_API_BASE}/{resource_id}",
            path=None,
            sha256=None,
            error=str(exc),
            records_count=None,
            metadata=None,
        )


def download_rice_sources(raw_root: Path, max_rows: int | None = None) -> list[AgmarknetDownload]:
    """Download Rice sources from AGMARKNET.

    Uses both the official daily and historical data.gov.in resources. A failed
    resource is reported (ok=False) rather than silently skipped, so an ingest
    run can record exactly what was and was not fetched.
    """
    results: list[AgmarknetDownload] = []

    historical_result = fetch_agmarknet_rice(
        HISTORICAL_RESOURCE_ID,
        state="Karnataka",
        commodity="Rice",
        max_rows=max_rows,
        dest_dir=raw_root / "agmarknet_rice",
    )
    results.append(historical_result)

    daily_result = fetch_agmarknet_rice(
        DAILY_RESOURCE_ID,
        state="Karnataka",
        commodity="Rice",
        max_rows=max_rows,
        dest_dir=raw_root / "agmarknet_rice",
    )
    results.append(daily_result)

    return results