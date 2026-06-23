"""Exercise catalog data helpers: EN→ES mapping, row building and seeding.

Shared by scripts/import_exercises.py (manual/CDN import) and the app startup
(auto-seed from the bundled data/exercises_free.json when the table is empty),
so the mapping logic lives in exactly one place.
"""
import json
import os

from app.exercise_es import translate_name

IMG_BASE = "https://cdn.jsdelivr.net/gh/yuhonas/free-exercise-db@main/exercises/"
SOURCE = "free-exercise-db"
LICENSE = "Public Domain (Unlicense)"

# Bundled dataset shipped with the repo (public domain), used for auto-seed.
BUNDLED_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "exercises_free.json",
)

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


def build_row(rec):
    """Turn a free-exercise-db record into kwargs for the Exercise model."""
    primary_raw = rec.get("primaryMuscles", []) or []
    secondary_raw = rec.get("secondaryMuscles", []) or []
    primary_es = to_es_list(primary_raw)
    images = [IMG_BASE + p for p in (rec.get("images") or [])]
    return {
        "slug": (rec.get("id") or rec.get("name", "")).strip().lower(),
        "name_en": rec.get("name", ""),
        "name_es": translate_name(rec.get("name", "")),
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


def load_records(file_path=None, url=None):
    """Load raw free-exercise-db records from a file or URL (file wins)."""
    if file_path:
        with open(file_path, encoding="utf-8") as f:
            return json.load(f)
    if url:
        import urllib.request
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    # default: the bundled dataset
    with open(BUNDLED_PATH, encoding="utf-8") as f:
        return json.load(f)


def upsert_exercises(db, records):
    """Idempotently insert/update Exercise rows. Returns (created, updated)."""
    from app.database import Exercise
    existing = {e.slug: e for e in db.query(Exercise).all()}
    created = updated = 0
    for rec in records:
        row = build_row(rec)
        ex = existing.get(row["slug"])
        if ex:
            for k, v in row.items():
                setattr(ex, k, v)
            updated += 1
        else:
            db.add(Exercise(**row))
            created += 1
    db.commit()
    return created, updated


def seed_if_empty(db):
    """Auto-seed the catalog from the bundled dataset when the table is empty.
    Safe to call on every startup; no-ops once populated."""
    from app.database import Exercise
    try:
        if db.query(Exercise.id).first() is not None:
            return 0
        records = load_records()
        created, _ = upsert_exercises(db, records)
        return created
    except Exception:
        # Never let seeding break app startup.
        return 0


def ensure_name_es(db):
    """Backfill Spanish names for catalogs seeded before translation existed.
    Cheap, deterministic, no network. Returns how many rows were updated."""
    from app.database import Exercise
    try:
        rows = db.query(Exercise).filter(Exercise.name_es.is_(None)).all()
        for e in rows:
            e.name_es = translate_name(e.name_en)
        if rows:
            db.commit()
        return len(rows)
    except Exception:
        db.rollback()
        return 0
