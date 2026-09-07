from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode

import httpx

from cropmandi.config import get_settings
from ingest.rawstore import write_raw

BASE = (
    "https://www.indianspices.com/marketing/price/domestic/current-market-price.html"
)
USER_AGENT = "CropMandiAI/0.1 (research ingest; coffee-pepper prices)"


@dataclass
class DownloadResult:
    ok: bool
    url: str
    path: Path | None
    sha256: str | None
    error: str | None
    html: str | None = None


def fetch_pepper_page(state: str, dest_dir: Path) -> DownloadResult:
    params = {"filterSpice": "Pepper", "filterState": state}
    url = f"{BASE}?{urlencode(params)}"
    settings = get_settings()
    dest_dir.mkdir(parents=True, exist_ok=True)
    path = dest_dir / f"spices_board_pepper_{state.lower()}.html"
    try:
        with httpx.Client(
            timeout=settings.cropmandi_http_timeout,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
            follow_redirects=True,
        ) as client:
            response = client.get(url)
            response.raise_for_status()
            data = response.content
        encoding = response.encoding or "utf-8"
        checksum = write_raw(
            path,
            data,
            {"url": url, "http_status": 200, "state_filter": state},
        )
        return DownloadResult(
            ok=True,
            url=url,
            path=path,
            sha256=checksum,
            error=None,
            html=data.decode(encoding, errors="replace"),
        )
    except Exception as exc:  # noqa: BLE001 - connector must report failure, not invent data
        return DownloadResult(
            ok=False,
            url=url,
            path=None,
            sha256=None,
            error=str(exc),
        )


def download_pepper_sources(raw_root: Path) -> list[DownloadResult]:
    dest = raw_root / "spices_board_pepper"
    return [
        fetch_pepper_page("KERALA", dest),
        fetch_pepper_page("KARNATAKA", dest),
    ]
