"""Seed / refresh the Exercise catalog from the public-domain free-exercise-db.

Usage:
    python -m scripts.import_exercises                 # fetch from CDN
    python -m scripts.import_exercises --file ex.json   # use a local JSON file
    python -m scripts.import_exercises --dry-run        # parse only, don't write

The dataset (https://github.com/yuhonas/free-exercise-db) is public domain.
Images are NOT downloaded: we store CDN (jsDelivr) URLs and hot-link them.
Muscle / equipment / category vocabularies are normalised to our Spanish
taxonomy so the analysis tab works natively. The script is idempotent
(upsert by slug), so it's safe to re-run.
"""
import argparse
import json
import os
import sys
import urllib.request

# Make `app` importable when run as a plain script.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal, Exercise, Base, engine  # noqa: E402

DATA_URL = "https://raw.githubusercontent.com/yuhonas/free-exercise-db/main/dist/exercises.json"
IMG_BASE = "https://cdn.jsdelivr.net/gh/yuhonas/free-exercise-db@main/exercises/"
SOURCE = "free-exercise-db"
LICENSE = "Public Domain (Unlicense)"

# free-exercise-db muscle vocab → our canonical Spanish groups (same taxonomy
# used by the analysis tab in app/hevy.py).
MUSCLE_ES = {
    "chest": "Pecho", "serratus anterior": "Pecho",
    "lats": "Espalda", "middle back": "Espalda", "lower back": "Espalda",
    "traps": "Espalda", "neck": "Espalda",
    "shoulders": "Hombros",
    "biceps": "Bíceps", "brachialis": "Bíceps",
    "triceps": "Tríceps",
    "forearms": "Antebrazos",
    "abdominals": "Abdominales", "obliques": "Abdominales",
    "quadriceps": "Cuádriceps",
    "hamstrings": "Isquios",
    "glutes": "Glúteos", "abductors": "Glúteos",
    "adductors": "Aductores",
    "calves": "Gemelos", "soleus": "Gemelos",
}

EQUIPMENT_ES = {
    "barbell": "Barra", "dumbbell": "Mancuerna", "body only": "Peso corporal",
    "cable": "Polea", "machine": "Máquina", "kettlebells": "Pesa rusa",
    "bands": "Bandas", "medicine ball": "Balón medicinal",
    "exercise ball": "Pelota de ejercicio", "foam roll": "Rodillo",
    "e-z curl bar": "Barra Z", "other": "Otro", None: "Sin equipo",
}

CATEGORY_ES = {
    "strength": "Fuerza", "stretching": "Estiramiento", "plyometrics": "Pliometría",
    "powerlifting": "Powerlifting", "olympic weightlifting": "Halterofilia",
    "strongman": "Strongman", "cardio": "Cardio",
}


def to_es_list(muscles):
    """Map a list of EN muscle names to canonical ES groups (deduped, ordered)."""
    out = []
    for m in muscles or []:
        es = MUSCLE_ES.get(m, "Otro")
        if es not in out:
            out.append(es)
    return out


def load_data(file_path=None):
    if file_path:
        with open(file_path, encoding="utf-8") as f:
            return json.load(f)
    with urllib.request.urlopen(DATA_URL, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def build_row(rec):
    primary_raw = rec.get("primaryMuscles", []) or []
    secondary_raw = rec.get("secondaryMuscles", []) or []
    primary_es = to_es_list(primary_raw)
    images = [IMG_BASE + p for p in (rec.get("images") or [])]
    return {
        "slug": (rec.get("id") or rec.get("name", "")).strip().lower(),
        "name_en": rec.get("name", ""),
        "category": rec.get("category"),
        "category_es": CATEGORY_ES.get(rec.get("category"), rec.get("category")),
        "equipment": rec.get("equipment"),
        "equipment_es": EQUIPMENT_ES.get(rec.get("equipment"), rec.get("equipment") or "Sin equipo"),
        "force": rec.get("force"),
        "level": rec.get("level"),
        "mechanic": rec.get("mechanic"),
        "primary_muscle": primary_es[0] if primary_es else "Otro",
        "primary_muscles_raw": primary_raw,
        "secondary_muscles_es": to_es_list(secondary_raw),
        "secondary_muscles_raw": secondary_raw,
        "instructions": rec.get("instructions") or [],
        "images": images,
        "source": SOURCE,
        "license": LICENSE,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", help="Local JSON file instead of fetching from CDN")
    ap.add_argument("--dry-run", action="store_true", help="Parse only; no DB writes")
    args = ap.parse_args()

    data = load_data(args.file)
    rows = [build_row(r) for r in data]
    print(f"Parsed {len(rows)} exercises from {'file' if args.file else DATA_URL}")

    if args.dry_run:
        print("Dry run — sample:")
        print(json.dumps(rows[0], ensure_ascii=False, indent=2))
        return

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    created = updated = 0
    try:
        existing = {e.slug: e for e in db.query(Exercise).all()}
        for row in rows:
            ex = existing.get(row["slug"])
            if ex:
                for k, v in row.items():
                    setattr(ex, k, v)
                updated += 1
            else:
                db.add(Exercise(**row))
                created += 1
        db.commit()
    finally:
        db.close()
    print(f"Done. created={created} updated={updated}")


if __name__ == "__main__":
    main()
