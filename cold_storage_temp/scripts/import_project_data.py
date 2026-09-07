"""
Generic Firebase/Firestore project-data importer.

Uploads CSV / JSON / JSONL files from a folder into Firebase.

Examples:

    python scripts/import_project_data.py \
        --data-dir incoming_data

    python scripts/import_project_data.py \
        --data-dir incoming_data \
        --collection market_history

Credentials:
    FIREBASE_SERVICE_ACCOUNT_JSON in .env, or
    firebase-service-account.json in project root.

The importer:
- does not overwrite unrelated collections
- creates deterministic document IDs
- uploads in Firestore batches
- records the source filename
- skips blank rows
- supports CSV, JSON arrays, JSON objects, and JSONL
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def get_firebase():
    import firebase_admin
    from firebase_admin import credentials, firestore

    if firebase_admin._apps:
        app = firebase_admin.get_app()
    else:
        configured = os.getenv(
            "FIREBASE_SERVICE_ACCOUNT_JSON",
            "",
        ).strip()

        path = (
            Path(configured)
            if configured
            else PROJECT_ROOT / "firebase-service-account.json"
        )

        if not path.is_absolute():
            path = PROJECT_ROOT / path

        if not path.exists():
            raise FileNotFoundError(
                f"Firebase service account not found: {path}"
            )

        app = firebase_admin.initialize_app(
            credentials.Certificate(str(path))
        )

    return firestore.client()


def clean(value):
    if isinstance(value, dict):
        return {
            str(k): clean(v)
            for k, v in value.items()
        }

    if isinstance(value, list):
        return [clean(v) for v in value]

    if value is None:
        return None

    text = str(value).strip()

    if text == "":
        return None

    # Preserve strings that look like IDs/dates.
    try:
        if "." in text:
            number = float(text)
            return number
        if text.isdigit():
            return int(text)
    except Exception:
        pass

    return text


def stable_id(record, source_file):
    payload = json.dumps(
        {
            "source_file":
                source_file,
            "record":
                record,
        },
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )

    return hashlib.sha256(
        payload.encode("utf-8")
    ).hexdigest()[:40]


def read_csv(path):
    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as f:
        return [
            clean(dict(row))
            for row in csv.DictReader(f)
        ]


def read_json(path):
    with path.open(
        "r",
        encoding="utf-8",
    ) as f:
        payload = json.load(f)

    if isinstance(payload, list):
        return [clean(x) for x in payload]

    if isinstance(payload, dict):
        # Common format: {"records": [...]}
        if isinstance(
            payload.get("records"),
            list,
        ):
            return [
                clean(x)
                for x in payload["records"]
            ]

        return [clean(payload)]

    return []


def read_jsonl(path):
    rows = []

    with path.open(
        "r",
        encoding="utf-8",
    ) as f:
        for line in f:
            line = line.strip()

            if not line:
                continue

            rows.append(
                clean(
                    json.loads(line)
                )
            )

    return rows


def read_file(path):
    suffix = path.suffix.lower()

    if suffix == ".csv":
        return read_csv(path)

    if suffix == ".json":
        return read_json(path)

    if suffix in {".jsonl", ".ndjson"}:
        return read_jsonl(path)

    return []


def collection_name(
    path: Path,
    override: str | None,
):
    if override:
        return override.strip()

    name = path.stem.strip().lower()

    aliases = {
        "cold_storages":
            "cold_storages",
        "cold_storage":
            "cold_storages",
        "coffee_prices":
            "coffee_prices",
        "pepper_prices":
            "pepper_prices",
        "cardamom_prices":
            "cardamom_prices",
    }

    return aliases.get(
        name,
        name.replace(
            " ",
            "_",
        ),
    )


def upload_collection(
    db,
    collection,
    rows,
    source_file,
):
    if not rows:
        return 0

    count = 0

    # Firestore batches have a practical operation limit.
    chunk_size = 400

    for start in range(
        0,
        len(rows),
        chunk_size,
    ):
        batch = db.batch()

        chunk = rows[
            start:
            start + chunk_size
        ]

        for row in chunk:
            if not isinstance(row, dict):
                continue

            row = {
                key: value
                for key, value in row.items()
                if value is not None
            }

            if not row:
                continue

            row["import_source_file"] = (
                source_file
            )

            document_id = stable_id(
                row,
                source_file,
            )

            ref = (
                db.collection(collection)
                .document(document_id)
            )

            batch.set(
                ref,
                row,
                merge=True,
            )

            count += 1

        batch.commit()

    return count


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--data-dir",
        required=True,
    )

    parser.add_argument(
        "--collection",
        default=None,
        help=(
            "Optional: upload every file "
            "to this one collection."
        ),
    )

    parser.add_argument(
        "--include",
        nargs="*",
        default=None,
        help=(
            "Optional filenames to import."
        ),
    )

    args = parser.parse_args()

    data_dir = Path(args.data_dir)

    if not data_dir.exists():
        raise SystemExit(
            f"Data directory does not exist: {data_dir}"
        )

    db = get_firebase()

    supported = {
        ".csv",
        ".json",
        ".jsonl",
        ".ndjson",
    }

    files = [
        path
        for path in sorted(
            data_dir.iterdir()
        )
        if path.is_file()
        and path.suffix.lower() in supported
    ]

    if args.include:
        allowed = set(args.include)
        files = [
            path
            for path in files
            if path.name in allowed
        ]

    if not files:
        raise SystemExit(
            "No CSV/JSON/JSONL files found."
        )

    grand_total = 0

    for path in files:
        rows = read_file(path)

        collection = collection_name(
            path,
            args.collection,
        )

        count = upload_collection(
            db,
            collection,
            rows,
            path.name,
        )

        grand_total += count

        print(
            f"{path.name}: "
            f"{count} upserts → "
            f"{collection}"
        )

    print(
        f"TOTAL: {grand_total} upserts"
    )


if __name__ == "__main__":
    main()
