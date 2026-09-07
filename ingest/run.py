from __future__ import annotations

import json
from pathlib import Path

from cropmandi.config import get_settings
from cropmandi.db.session import make_session_factory, create_all
from ingest.connectors.agmarknet_rice import download_rice_sources
from ingest.connectors.coffee_board import download_coffee_sources
from ingest.connectors.spices_board_pepper import download_pepper_sources
from ingest.load_prices import finish_run, insert_observations, start_run
from ingest.parsers.agmarknet_rice import parse_agmarknet_rice_file
from ingest.parsers.coffee_pdf import parse_coffee_pdf
from ingest.parsers.pepper_html import parse_pepper_html_file
from ingest.validate.price_validation import partition_valid


def _session():
    create_all()
    factory = make_session_factory()
    return factory()


def ingest_pepper(session) -> dict:
    settings = get_settings()
    raw_root = settings.data_dir / "raw"
    summary = {
        "connector": "spices_board_pepper",
        "downloads": [],
        "inserted": 0,
        "duplicate": 0,
        "rejected": 0,
        "parsed": 0,
        "failures": [],
    }
    for result in download_pepper_sources(raw_root):
        item = {
            "ok": result.ok,
            "url": result.url,
            "path": str(result.path) if result.path else None,
            "sha256": result.sha256,
            "error": result.error,
        }
        summary["downloads"].append(item)
        if not result.ok or result.path is None:
            summary["failures"].append(result.error or "download_failed")
            run = start_run(
                session,
                "spices_board_pepper",
                source_url=result.url,
                notes="download_failed",
            )
            finish_run(session, run, "failed", result.error)
            continue
        run = start_run(
            session,
            "spices_board_pepper",
            source_url=result.url,
            raw_path=str(result.path),
            raw_sha256=result.sha256,
        )
        parsed = parse_pepper_html_file(result.path, source_url=result.url)
        valid, rejected = partition_valid(parsed)
        run.rows_parsed = len(parsed)
        run.rows_rejected = len(rejected)
        inserted, dupes = insert_observations(session, run, valid)
        summary["parsed"] += len(parsed)
        summary["inserted"] += inserted
        summary["duplicate"] += dupes
        summary["rejected"] += len(rejected)
        finish_run(session, run, "success")
        session.commit()
    return summary


def ingest_coffee(session) -> dict:
    settings = get_settings()
    raw_root = settings.data_dir / "raw"
    summary = {
        "connector": "coffee_board",
        "downloads": [],
        "inserted": 0,
        "duplicate": 0,
        "rejected": 0,
        "parsed": 0,
        "failures": [],
        "pdfs_parsed": 0,
        "pdfs_without_clear_rows": 0,
    }
    downloads = download_coffee_sources(raw_root)
    seen: set[str] = set()
    for result in downloads:
        item = {
            "ok": result.ok,
            "url": result.url,
            "path": str(result.path) if result.path else None,
            "sha256": result.sha256,
            "error": result.error,
            "method": result.method,
        }
        summary["downloads"].append(item)
        if not result.ok:
            summary["failures"].append(f"{result.method}: {result.error}")
            run = start_run(
                session,
                "coffee_board",
                source_url=result.url,
                notes=result.method,
            )
            finish_run(session, run, "failed", result.error)
            session.commit()
            continue
        if result.path is None or result.path.suffix.lower() != ".pdf":
            continue
        if result.sha256 in seen:
            continue
        seen.add(result.sha256)
        run = start_run(
            session,
            "coffee_board",
            source_url=result.url,
            raw_path=str(result.path),
            raw_sha256=result.sha256,
            notes=result.method,
        )
        parsed = parse_coffee_pdf(result.path, source_url=result.url)
        valid, rejected = partition_valid(parsed)
        run.rows_parsed = len(parsed)
        run.rows_rejected = len(rejected)
        inserted, dupes = insert_observations(session, run, valid)
        summary["parsed"] += len(parsed)
        summary["inserted"] += inserted
        summary["duplicate"] += dupes
        summary["rejected"] += len(rejected)
        summary["pdfs_parsed"] += 1
        if not parsed:
            summary["pdfs_without_clear_rows"] += 1
        finish_run(session, run, "success" if parsed else "success_no_clear_rows")
        session.commit()
    return summary


def ingest_rice(session) -> dict:
    settings = get_settings()
    raw_root = settings.data_dir / "raw"
    summary = {
        "connector": "agmarknet_rice",
        "downloads": [],
        "inserted": 0,
        "duplicate": 0,
        "rejected": 0,
        "parsed": 0,
        "failures": [],
    }
    for result in download_rice_sources(raw_root):
        item = {
            "ok": result.ok,
            "url": result.url,
            "path": str(result.path) if result.path else None,
            "sha256": result.sha256,
            "error": result.error,
            "records_count": result.records_count,
        }
        summary["downloads"].append(item)
        if not result.ok or result.path is None:
            summary["failures"].append(result.error or "download_failed")
            run = start_run(
                session,
                "agmarknet_rice",
                source_url=result.url,
                notes="download_failed",
            )
            finish_run(session, run, "failed", result.error)
            session.commit()
            continue
        run = start_run(
            session,
            "agmarknet_rice",
            source_url=result.url,
            raw_path=str(result.path),
            raw_sha256=result.sha256,
        )
        parsed = parse_agmarknet_rice_file(result.path, source_url=result.url)
        valid, rejected = partition_valid(parsed)
        run.rows_parsed = len(parsed)
        run.rows_rejected = len(rejected)
        inserted, dupes = insert_observations(session, run, valid)
        summary["parsed"] += len(parsed)
        summary["inserted"] += inserted
        summary["duplicate"] += dupes
        summary["rejected"] += len(rejected)
        finish_run(session, run, "success")
        session.commit()
    return summary


def main() -> None:
    session = _session()
    try:
        pepper = ingest_pepper(session)
        coffee = ingest_coffee(session)
        rice = ingest_rice(session)
        report = {"pepper": pepper, "coffee": coffee, "rice": rice}
        out = get_settings().data_dir / "reports" / "ingestion_summary.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
    finally:
        session.close()


if __name__ == "__main__":
    main()
