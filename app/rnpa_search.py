"""
Argentine food search.
Priority: básicos (curated, grass-fed) > RNPA genéricos > RNPA branded
Loads at startup: ~195 básicos + ~1,500 genéricos + ~57,000 branded.
"""
import csv
import re
from pathlib import Path

_DATA_DIR = Path(__file__).parent.parent / "data"

_basics: list[dict] = []
_generics: list[dict] = []
_branded: list[dict] = []

# Removes trailing (Brand Name) from RNPA product names
_PAREN_BRAND = re.compile(r"\s*\([^)]+\)\s*$")


def _clean_name(raw: str) -> str:
    """Remove trailing (brand) from name and convert to title case."""
    return _PAREN_BRAND.sub("", raw).strip().title()


def _load():
    global _basics, _generics, _branded

    # 1. Curated basic ingredients (highest priority)
    basics_path = _DATA_DIR / "ingredientes_basicos.csv"
    if basics_path.exists():
        seen = set()
        with open(basics_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row["name"] in seen:
                    continue
                seen.add(row["name"])
                _basics.append({
                    "name": row["name"],
                    "marca": "",
                    "categoria": row["categoria"],
                    "calories": _f(row["calories"]),
                    "protein": _f(row["protein"]),
                    "carbs": _f(row["carbs"]),
                    "fat": _f(row["fat"]),
                    "fiber": _f(row.get("fiber")),
                    "source": row.get("source", "basico"),
                    "unidad": "g",
                })

    # 2. RNPA generics (median of branded products)
    gen_path = _DATA_DIR / "alimentos_genericos.csv"
    if gen_path.exists():
        with open(gen_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                _generics.append({
                    "name": row["name"],
                    "marca": "",
                    "categoria": row["categoria"],
                    "calories": _f(row["calories"]),
                    "protein": _f(row["protein"]),
                    "carbs": _f(row["carbs"]),
                    "fat": _f(row["fat"]),
                    "fiber": _f(row.get("fiber")),
                    "sodium": _f(row.get("sodium")),
                    "source": "rnpa_generic",
                    "n_productos": int(row.get("n_productos") or 0),
                    "unidad": "g",
                })

    # 3. RNPA branded products
    rnpa_path = _DATA_DIR / "alimentos_rnpa.csv"
    if rnpa_path.exists():
        with open(rnpa_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if not row.get("calories"):
                    continue
                unidad = row.get("unidad", "g").strip().lower()
                marca = row.get("marca", "").strip().title()
                _branded.append({
                    "name": _clean_name(row["name"]),
                    "marca": marca,
                    "categoria": row["categoria"],
                    "calories": _f(row["calories"]),
                    "protein": _f(row["protein"]),
                    "carbs": _f(row["carbs"]),
                    "fat": _f(row["fat"]),
                    "fiber": _f(row.get("fiber")),
                    "sodium": _f(row.get("sodium")),
                    "source": "rnpa",
                    "rnpa": row.get("rnpa", ""),
                    "unidad": "ml" if unidad == "ml" else "g",
                })


def _f(val) -> float:
    try:
        return round(float(val), 1) if val else 0.0
    except (TypeError, ValueError):
        return 0.0


def _normalize(text: str) -> str:
    """Lowercase, strip accents and special punctuation for fuzzy matching."""
    t = text.lower()
    t = t.translate(str.maketrans("áéíóúüñäëïöü", "aeiouunaeiou"))
    # Remove apostrophes/accents used as punctuation (e.g. LAY´S → lays)
    t = t.translate(str.maketrans("", "", "´`'"))
    return t


def _score(name: str, marca: str, words: list[str]) -> int:
    """Return match score: higher is better. 0 = no match.

    Searches both product name and brand. Brand-only matches are scored
    lower so food-name searches rank above brand-only hits.
    """
    nl = _normalize(name)
    ml = _normalize(marca)
    combined = nl + " " + ml  # search space

    # All words must appear somewhere in name+brand
    if not all(w in combined for w in words):
        return 0

    query = " ".join(words)

    # Exact name match
    if nl == query:
        return 100
    # Name starts with query
    if nl.startswith(query):
        return 80
    # Query is a substring of name
    if query in nl:
        return 60
    # All words in name (any order)
    if all(w in nl for w in words):
        return 40
    # Match only via brand field — brand search
    if query in ml or all(w in ml for w in words):
        return 20
    # Partial cross-match (some words in name, rest in brand)
    return 10


_MAX_GENERICS = 3  # cap generic (no-brand) entries per search


def search_rnpa(query: str, limit: int = 15) -> list[dict]:
    q = _normalize(query.strip())
    if not q:
        return []
    words = q.split()

    basics_hits: list[tuple[int, dict]] = []
    generic_hits: list[tuple[int, dict]] = []
    branded_hits: list[tuple[int, dict]] = []

    for item in _basics:
        s = _score(item["name"], item["marca"], words)
        if s:
            basics_hits.append((s + 2000, item))

    for item in _generics:
        s = _score(item["name"], item["marca"], words)
        if s:
            generic_hits.append((s + 1000, item))

    for item in _branded:
        s = _score(item["name"], item["marca"], words)
        if s:
            branded_hits.append((s, item))

    basics_hits.sort(key=lambda x: -x[0])
    generic_hits.sort(key=lambda x: -x[0])
    branded_hits.sort(key=lambda x: -x[0])

    # Always include all basics, cap generics, fill remainder with branded
    combined = basics_hits + generic_hits[:_MAX_GENERICS] + branded_hits
    combined.sort(key=lambda x: -x[0])
    return [r[1] for r in combined[:limit]]


# Load on import
_load()
