"""
Argentine food search.
Priority: básicos (curated, grass-fed) > RNPA genéricos > RNPA branded
Loads at startup: ~195 básicos + ~1,500 genéricos + ~57,000 branded.
"""
import csv
import re
from pathlib import Path

from app.portions import get_portions

_DATA_DIR = Path(__file__).parent.parent / "data"

_basics: list[dict] = []
_generics: list[dict] = []
_branded: list[dict] = []

# Removes trailing (Brand Name) from RNPA product names
_PAREN_BRAND = re.compile(r"\s*\([^)]+\)\s*$")

# Leading legal/category prefixes to strip  (order matters: longer first)
_LEADING_NOISE = re.compile(
    r"^(snack\.|postre congelado|producto de confiter[ií]a[^,]*,|producto de copet[ií]n[^,]*,|"
    r"producto alimenticio[^,]*,|alimento[^,]*,|conserva de|preparado[^,]*,)\s*",
    re.IGNORECASE,
)

# Verbose phrases → compact equivalents  (applied in order)
_SUBSTITUTIONS: list[tuple[re.Pattern, str]] = [
    # "con relleno sabor a X" / "relleno con sabor a X" / "con relleno de X"
    (re.compile(r"con relleno sabor a\s+", re.I), "relleno "),
    (re.compile(r"rellenos? con sabor a\s+", re.I), "relleno "),
    (re.compile(r"con relleno de\s+", re.I), "relleno "),
    # "con sabor a X" / "sabor a X"
    (re.compile(r"con sabor a\s+", re.I), "sabor "),
    (re.compile(r"sabor a\s+", re.I), "sabor "),
    # "a base de" → "de" (keeps the ingredient, removes the legal phrase)
    (re.compile(r"\ba base de\b\s*", re.I), "de "),
    # "adicionado/enriquecido/vitaminizado con X" at end or before comma → drop
    (re.compile(r",?\s*(adicionad[ao]|enriquecid[ao]|vitaminizad[ao]|fortif?icad[ao]) con [^,]+", re.I), ""),
    # "de mesa. " prefix remnants
    (re.compile(r"^de mesa\.\s*", re.I), ""),
    # "dulces?" adjacent to galletitas / bizcochos → redundant
    (re.compile(r"\bdulces?\s+(?=galletitas?|bizcochos?|obleas?|cereales?)", re.I), ""),
    (re.compile(r"(galletitas?)\s+dulces?\b", re.I), r"\1"),
    # "con relleno sabor X" (without "a")
    (re.compile(r"con relleno sabor\s+", re.I), "relleno "),
    # "producto de" as standalone prefix
    (re.compile(r"^producto de\s+", re.I), ""),
    # "cubierto/bañado/recubierto con baño de repostería X" → "bañado X"
    (re.compile(r",?\s*(cubierto|bañado|recubierto) con baño de repostería?\s*", re.I), " bañado "),
    (re.compile(r",?\s*(cubierto|bañado|recubierto) con baño\s+", re.I), " bañado "),
    (re.compile(r",?\s*(cubierto|bañado|recubierto) con\s+", re.I), " bañado "),
    # "bañado de repostería X" / "bañado en X" → keep just "bañado X"
    (re.compile(r"\bbañado de repostería?\s*", re.I), "bañado "),
    (re.compile(r"\bbañado en\s+", re.I), "bañado "),
    # trailing "recubierto/a con X" descriptions (candy coatings, etc.)
    (re.compile(r",?\s*recubiertos? con .+$", re.I), ""),
    # "con trozos/chips/pedacitos de X" → "con X"
    (re.compile(r"con (trozos?|chips?|pedacitos?|copos?) de\s+", re.I), "con "),
    # trailing long flavor lists: "sabores a X, Y, Z..."
    (re.compile(r",?\s*sabores? (surtidos?|a\s+\w+(?:,\s*\w+){2,}).*$", re.I), ""),
    # trailing "sabores surtidos"
    (re.compile(r",?\s*sabores? surtidos?.*$", re.I), ""),
    # collapse multiple spaces / stray commas / trailing punctuation
    (re.compile(r",\s*,"), ","),
    (re.compile(r",\s*$"), ""),
    (re.compile(r"\s{2,}"), " "),
]


_MAX_NAME_LEN = 60


def _clean_name(raw: str) -> str:
    """Strip legal boilerplate from an RNPA product name and title-case it."""
    name = _PAREN_BRAND.sub("", raw).strip()
    name = _LEADING_NOISE.sub("", name)
    for pattern, repl in _SUBSTITUTIONS:
        name = pattern.sub(repl, name)
    name = name.strip()
    # Hard cap: trim at last word boundary before _MAX_NAME_LEN
    if len(name) > _MAX_NAME_LEN:
        cut = name[:_MAX_NAME_LEN].rsplit(" ", 1)[0].rstrip(",")
        name = cut + "…"
    return name.title()


def _short_desc(name: str) -> str:
    """Return a compact descriptor for branded items: drop the main noun group,
    keep flavor/variant info (≤ 60 chars)."""
    # After _clean_name the name is already simplified; just trim to 60 chars
    return name[:60].strip()


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

# Categories allowed per meal_type filter (RNPA category names, uppercase)
_MEAL_CATEGORIES: dict[str, set[str]] = {
    "drink": {
        "BEBIDAS ANALCOHÓLICAS", "BEBIDAS ALCOHOLICAS", "BEBIDAS ALCOHÓLICAS",
        "JUGOS", "TÉ E INFUSIONES", "CAFÉ Y SUCEDÁNEOS", "AGUAS",
        "JARABES Y SIROPES",
    },
    "snack": {
        "GALLETITAS Y BARRAS", "CARAMELOS Y GOLOSINAS", "CACAO Y CHOCOLATE",
        "ALFAJORES", "CONFITURAS Y DULCES", "REPOSTERÍA Y CONFITERÍA",
        "MASAS Y PANADERÍA", "HELADOS", "POSTRES",
        "AZÚCARES Y EDULCORANTES",
    },
}

# Categories that belong to basics/generics (used for mapping básicos)
_DRINK_NAMES = {"bebida", "jugo", "agua", "gaseosa", "té", "cafe", "infusion", "cerveza", "vino", "alcohol"}
_SNACK_NAMES = {"galletita", "chocolate", "alfajor", "caramelo", "golosina", "helado", "postre", "dulce", "oblea", "barrita"}


def _item_matches_meal(item: dict, meal_type: str) -> bool:
    """Return True if the item is appropriate for the given meal type."""
    if not meal_type or meal_type not in _MEAL_CATEGORIES:
        return True

    allowed_cats = _MEAL_CATEGORIES[meal_type]
    cat = item.get("categoria", "").strip().upper()

    # RNPA items: filter strictly by category
    if item["source"] == "rnpa":
        return cat in allowed_cats

    # Generics: also by category
    if item["source"] == "rnpa_generic":
        return cat in allowed_cats

    # Basics: use name heuristic (they have human category names)
    name_l = item["name"].lower()
    if meal_type == "drink":
        return any(w in name_l for w in _DRINK_NAMES)
    if meal_type == "snack":
        return any(w in name_l for w in _SNACK_NAMES)

    return True


def search_rnpa(query: str, limit: int = 15, meal_type: str = "") -> list[dict]:
    q = _normalize(query.strip())
    if not q:
        return []
    words = q.split()

    basics_hits: list[tuple[int, dict]] = []
    generic_hits: list[tuple[int, dict]] = []
    branded_hits: list[tuple[int, dict]] = []

    for item in _basics:
        if not _item_matches_meal(item, meal_type):
            continue
        s = _score(item["name"], item["marca"], words)
        if s:
            basics_hits.append((s + 2000, item))

    for item in _generics:
        if not _item_matches_meal(item, meal_type):
            continue
        s = _score(item["name"], item["marca"], words)
        if s:
            generic_hits.append((s + 1000, item))

    for item in _branded:
        if not _item_matches_meal(item, meal_type):
            continue
        s = _score(item["name"], item["marca"], words)
        if s:
            branded_hits.append((s, item))

    basics_hits.sort(key=lambda x: -x[0])
    generic_hits.sort(key=lambda x: -x[0])
    branded_hits.sort(key=lambda x: -x[0])

    # Always include all basics, cap generics, fill remainder with branded
    combined = basics_hits + generic_hits[:_MAX_GENERICS] + branded_hits
    combined.sort(key=lambda x: -x[0])

    results = []
    for _, item in combined[:limit]:
        it = dict(item)
        it["portions"] = get_portions(it["name"], it.get("categoria", ""), it.get("unidad", "g"))
        results.append(it)
    return results


# Load on import
_load()
