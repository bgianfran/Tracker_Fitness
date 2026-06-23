"""Seed / refresh the Exercise catalog from the public-domain free-exercise-db.

Usage:
    python -m scripts.import_exercises                 # use bundled data/exercises_free.json
    python -m scripts.import_exercises --cdn            # fetch latest from CDN
    python -m scripts.import_exercises --file ex.json   # use a specific local file
    python -m scripts.import_exercises --dry-run        # parse only, don't write

The dataset (https://github.com/yuhonas/free-exercise-db) is public domain.
Images are NOT downloaded: we store CDN (jsDelivr) URLs and hot-link them.
The script is idempotent (upsert by slug), so it's safe to re-run.
"""
import argparse
import json
import os
import sys

# Make `app` importable when run as a plain script.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal, Base, engine  # noqa: E402
from app import exercise_catalog as cat  # noqa: E402

CDN_URL = "https://raw.githubusercontent.com/yuhonas/free-exercise-db/main/dist/exercises.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", help="Local JSON file")
    ap.add_argument("--cdn", action="store_true", help="Fetch latest from CDN")
    ap.add_argument("--dry-run", action="store_true", help="Parse only; no DB writes")
    args = ap.parse_args()

    records = cat.load_records(
        file_path=args.file,
        url=CDN_URL if args.cdn else None,
    )
    src = args.file or (CDN_URL if args.cdn else cat.BUNDLED_PATH)
    print(f"Loaded {len(records)} exercises from {src}")

    if args.dry_run:
        print(json.dumps(cat.build_row(records[0]), ensure_ascii=False, indent=2))
        return

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        created, updated = cat.upsert_exercises(db, records)
    finally:
        db.close()
    print(f"Done. created={created} updated={updated}")


if __name__ == "__main__":
    main()
