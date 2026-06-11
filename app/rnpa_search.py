"""
Argentine food search.
Priority: básicos (curated, grass-fed) > RNPA genéricos > RNPA branded
Loads at startup: ~195 básicos + ~1,500 genéricos + ~57,000 branded.
"""
import csv
from pathlib import Path

_DATA_DIR = Path(__file__).parent.parent / "data"

_basics: list[dict] = []
_generics: list[dict] = []
_branded: list[dict] = []


def _load():
    global _basics, _generics, _branded

    # 1. Curated basic ingredients (highest priority)
    basics_path = _DATA_DIR / "ingredientes_basicos.csv"
    if basics_path.exists():
        with open(basics_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                _basics.append({
                    "name": row["name"],
                    "categoria": row["categoria"],
                    "calories": _f(row["calories"]),
                    "protein": _f(row["protein"]),
                    "carbs": _f(row["carbs"]),
                    "fat": _f(row["fat"]),
                    "fiber": _f(row.get("fiber")),
                    "source": row.get("source", "basico"),
                })

    # 2. RNPA generics (median of branded products)
    gen_path = _DATA_DIR / "alimentos_genericos.csv"
    if gen_path.exists():
        with open(gen_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                _generics.append({
                    "name": row["name"],
                    "categoria": row["categoria"],
                    "calories": _f(row["calories"]),
                    "protein": _f(row["protein"]),
                    "carbs": _f(row["carbs"]),
                    "fat": _f(row["fat"]),
                    "fiber": _f(row.get("fiber")),
                    "sodium": _f(row.get("sodium")),
                    "source": "rnpa_generic",
                    "n_productos": int(row.get("n_productos") or 0),
                })

    # 3. RNPA branded products
    rnpa_path = _DATA_DIR / "alimentos_rnpa.csv"
    if rnpa_path.exists():
        with open(rnpa_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if not row.get("calories"):
                    continue
                _branded.append({
                    "name": row["name"].strip(),
                    "marca": row.get("marca", "").strip(),
                    "categoria": row["categoria"],
                    "calories": _f(row["calories"]),
                    "protein": _f(row["protein"]),
                    "carbs": _f(row["carbs"]),
                    "fat": _f(row["fat"]),
                    "fiber": _f(row.get("fiber")),
                    "sodium": _f(row.get("sodium")),
                    "source": "rnpa",
                    "rnpa": row.get("rnpa", ""),
                })


def _f(val) -> float:
    try:
        return round(float(val), 1) if val else 0.0
    except (TypeError, ValueError):
        return 0.0


def _score(name: str, words: list[str]) -> int:
    """Return match score: higher is better. 0 = no match."""
    nl = name.lower()
    if not all(w in nl for w in words):
        return 0
    query = " ".join(words)
    if nl == query:
        return 100
    if nl.startswith(query):
        return 80
    if query in nl:
        return 60
    return 40


def search_rnpa(query: str, limit: int = 15) -> list[dict]:
    q = query.lower().strip()
    if not q:
        return []
    words = q.split()

    results = []

    # Básicos: highest priority (+2000)
    for item in _basics:
        s = _score(item["name"], words)
        if s:
            results.append((s + 2000, item))

    # RNPA generics: second (+1000)
    for item in _generics:
        s = _score(item["name"], words)
        if s:
            results.append((s + 1000, item))

    # RNPA branded: base score
    for item in _branded:
        s = _score(item["name"], words)
        if s:
            results.append((s, item))

    results.sort(key=lambda x: -x[0])
    return [r[1] for r in results[:limit]]


# Load on import
_load()
