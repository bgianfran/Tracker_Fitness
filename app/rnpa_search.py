"""
Argentine food search backed by RNPA data.
Loads at startup: ~1,500 generics + ~57,000 branded products.
"""
import csv
import os
from pathlib import Path

_DATA_DIR = Path(__file__).parent.parent / "data"

_generics: list[dict] = []
_branded: list[dict] = []


def _load():
    global _generics, _branded

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

    rnpa_path = _DATA_DIR / "alimentos_rnpa.csv"
    if rnpa_path.exists():
        with open(rnpa_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if not row.get("calories"):
                    continue
                marca = row.get("marca", "").strip()
                name = row["name"].strip()
                _branded.append({
                    "name": name,
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
    """Search generics then branded RNPA products."""
    q = query.lower().strip()
    if not q:
        return []
    words = q.split()

    results = []

    # Generics first
    for item in _generics:
        s = _score(item["name"], words)
        if s:
            results.append((s + 1000, item))  # +1000 so generics always rank above branded

    # Branded RNPA
    for item in _branded:
        s = _score(item["name"], words)
        if s:
            results.append((s, item))

    results.sort(key=lambda x: -x[0])
    return [r[1] for r in results[:limit]]


# Load on import
_load()
