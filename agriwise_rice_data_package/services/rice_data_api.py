"""Clients for Government OGD/AGMARKNET rice-price extraction."""
from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

import requests


class DataGovError(RuntimeError):
    pass


class DataGovAgmarknetClient:
    """Paginated client for api.data.gov.in AGMARKNET resources."""

    def __init__(self, api_key: str, resource_id: str, timeout: int = 60,
                 delay: float = 0.8, max_retries: int = 6, page_size: int = 1000):
        if not api_key:
            raise DataGovError("DATA_GOV_API_KEY is missing")
        self.api_key = api_key
        self.resource_id = resource_id
        self.base_url = f"https://api.data.gov.in/resource/{resource_id}"
        self.timeout = timeout
        self.delay = delay
        self.max_retries = max_retries
        self.page_size = page_size
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "AgriWise-Rice-Data-Pipeline/1.0"})

    def fetch_page(self, offset: int = 0, filters: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            "api-key": self.api_key,
            "format": "json",
            "limit": self.page_size,
            "offset": offset,
        }
        for key, value in (filters or {}).items():
            params[f"filters[{key}]"] = value

        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries):
            try:
                response = self.session.get(self.base_url, params=params, timeout=self.timeout)
                if response.status_code == 429 or response.status_code >= 500:
                    raise requests.HTTPError(f"HTTP {response.status_code}: {response.text[:300]}")
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise DataGovError("Unexpected API response format")
                return payload
            except Exception as exc:  # network/API transient errors
                last_error = exc
                if attempt == self.max_retries - 1:
                    break
                sleep_for = min(30, 2 ** attempt)
                time.sleep(sleep_for)
        raise DataGovError(f"AGMARKNET API request failed after retries: {last_error}")

    def fetch_all(self, filters: Optional[Dict[str, str]] = None,
                  max_rows: Optional[int] = None) -> List[Dict[str, Any]]:
        records: List[Dict[str, Any]] = []
        offset = 0
        while True:
            payload = self.fetch_page(offset=offset, filters=filters)
            page = payload.get("records") or []
            if not page:
                break
            records.extend(page)
            total = payload.get("total")
            print(f"Fetched offset={offset:,}, rows={len(page):,}, cumulative={len(records):,}"
                  + (f", reported_total={total:,}" if isinstance(total, int) else ""))
            if max_rows and len(records) >= max_rows:
                return records[:max_rows]
            if len(page) < self.page_size:
                break
            offset += self.page_size
            time.sleep(self.delay)
        return records


def get_client(resource_id: Optional[str] = None) -> DataGovAgmarknetClient:
    return DataGovAgmarknetClient(
        api_key=os.getenv("DATA_GOV_API_KEY", ""),
        resource_id=resource_id or os.getenv("DATA_GOV_HISTORICAL_RESOURCE_ID",
                                              "35985678-0d79-46b4-9ed6-6f13308a1d24"),
        timeout=int(os.getenv("REQUEST_TIMEOUT", "60")),
        delay=float(os.getenv("REQUEST_DELAY_SECONDS", "0.8")),
        max_retries=int(os.getenv("MAX_RETRIES", "6")),
        page_size=int(os.getenv("PAGE_SIZE", "1000")),
    )
