from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

from cropmandi.config import get_settings
from ingest.rawstore import sha256_file, write_raw

MARKET_INFO_URL = "https://coffeeboard.gov.in/Market_Info.aspx"
USER_AGENT = "CropMandiAI/0.1 (research ingest; coffee-pepper prices)"


@dataclass
class CoffeeDownload:
    ok: bool
    url: str
    path: Path | None
    sha256: str | None
    error: str | None
    method: str


def _copy_local_pdfs(dest: Path, extra_dir: str | None) -> list[CoffeeDownload]:
    dest.mkdir(parents=True, exist_ok=True)
    results: list[CoffeeDownload] = []
    search_dirs = [dest]
    if extra_dir:
        extra = Path(extra_dir)
        if extra.is_dir():
            search_dirs.append(extra)

    seen: set[str] = set()
    for folder in search_dirs:
        for pdf in sorted(folder.glob("*.pdf")):
            if folder != dest and not looks_like_coffee_market_report(pdf.name):
                continue
            if folder != dest:
                target = dest / pdf.name
                if not target.exists():
                    shutil.copy2(pdf, target)
                pdf = target
            checksum = sha256_file(pdf)
            if checksum in seen:
                continue
            seen.add(checksum)
            results.append(
                CoffeeDownload(
                    ok=True,
                    url=MARKET_INFO_URL,
                    path=pdf,
                    sha256=checksum,
                    error=None,
                    method="local_official_pdf_copy",
                )
            )
    return results


def _try_postback_pdf(dest: Path) -> CoffeeDownload:
    dest.mkdir(parents=True, exist_ok=True)
    settings = get_settings()
    try:
        with httpx.Client(
            timeout=settings.cropmandi_http_timeout,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        ) as client:
            page = client.get(MARKET_INFO_URL)
            page.raise_for_status()
            soup = BeautifulSoup(page.text, "lxml")
            form = soup.find("form")
            payload = {}
            if form:
                for inp in form.find_all("input"):
                    name = inp.get("name")
                    if name:
                        payload[name] = inp.get("value", "")
            payload["__EVENTTARGET"] = "lbnmarketinfo"
            payload["__EVENTARGUMENT"] = ""
            response = client.post(
                MARKET_INFO_URL,
                data=payload,
                headers={
                    "User-Agent": USER_AGENT,
                    "Referer": MARKET_INFO_URL,
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
            content_type = response.headers.get("content-type", "").lower()
            if response.status_code != 200:
                return CoffeeDownload(
                    False,
                    MARKET_INFO_URL,
                    None,
                    None,
                    f"HTTP {response.status_code}",
                    "aspnet_postback",
                )
            if "pdf" not in content_type and not response.content.startswith(b"%PDF"):
                snippet = response.text[:200].replace("\n", " ")
                return CoffeeDownload(
                    False,
                    MARKET_INFO_URL,
                    None,
                    None,
                    (
                        "Postback did not return a PDF. "
                        f"content-type={content_type!r} body_start={snippet!r}"
                    ),
                    "aspnet_postback",
                )
            path = dest / "coffee_board_latest_market_info.pdf"
            checksum = write_raw(
                path,
                response.content,
                {"url": MARKET_INFO_URL, "event_target": "lbnmarketinfo"},
            )
            return CoffeeDownload(
                True,
                MARKET_INFO_URL,
                path,
                checksum,
                None,
                "aspnet_postback",
            )
    except Exception as exc:  # noqa: BLE001
        return CoffeeDownload(
            False, MARKET_INFO_URL, None, None, str(exc), "aspnet_postback"
        )


def _try_archives(dest: Path) -> CoffeeDownload:
    """Archives are another ASP.NET postback; record failure honestly if not a PDF."""
    settings = get_settings()
    try:
        with httpx.Client(
            timeout=settings.cropmandi_http_timeout,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        ) as client:
            page = client.get(MARKET_INFO_URL)
            page.raise_for_status()
            soup = BeautifulSoup(page.text, "lxml")
            form = soup.find("form")
            payload = {}
            if form:
                for inp in form.find_all("input"):
                    name = inp.get("name")
                    if name:
                        payload[name] = inp.get("value", "")
            payload["__EVENTTARGET"] = "lbnarchives"
            payload["__EVENTARGUMENT"] = ""
            response = client.post(MARKET_INFO_URL, data=payload)
            content_type = response.headers.get("content-type", "").lower()
            if "pdf" in content_type or response.content.startswith(b"%PDF"):
                path = dest / "coffee_board_archives.pdf"
                checksum = write_raw(
                    path,
                    response.content,
                    {"url": MARKET_INFO_URL, "event_target": "lbnarchives"},
                )
                return CoffeeDownload(
                    True, MARKET_INFO_URL, path, checksum, None, "aspnet_archives"
                )
            # HTML archive listing is not historical prices by itself.
            listing = dest / "coffee_board_archives.html"
            write_raw(
                listing,
                response.content,
                {"url": MARKET_INFO_URL, "event_target": "lbnarchives"},
            )
            return CoffeeDownload(
                False,
                MARKET_INFO_URL,
                listing,
                None,
                (
                    "Archives postback returned HTML, not a downloadable historical "
                    "price file. Direct PDF URLs were not published on Market_Info.aspx."
                ),
                "aspnet_archives",
            )
    except Exception as exc:  # noqa: BLE001
        return CoffeeDownload(
            False, MARKET_INFO_URL, None, None, str(exc), "aspnet_archives"
        )


def download_coffee_sources(raw_root: Path) -> list[CoffeeDownload]:
    dest = raw_root / "coffee_board"
    settings = get_settings()
    results: list[CoffeeDownload] = []
    results.append(_try_postback_pdf(dest))
    results.append(_try_archives(dest))
    results.extend(_copy_local_pdfs(dest, settings.cropmandi_coffee_pdf_dir or None))
    return results


def looks_like_coffee_market_report(name: str) -> bool:
    return bool(re.search(r"coffee\s*market\s*report", name, re.I))
