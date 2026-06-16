"""
Open Food Facts barcode lookup.

Public API, no key required. Returns nutrition per 100 g / 100 ml in the same
shape used across the app, or None if the product is missing or has no usable
nutrition data.
"""
import httpx

_URL = "https://world.openfoodfacts.org/api/v2/product/{}.json"
_FIELDS = ",".join([
    "product_name", "product_name_es", "generic_name_es", "generic_name",
    "brands", "nutriments", "quantity", "categories_tags",
])
_HEADERS = {"User-Agent": "FitTracker/1.0 (https://fittracker.app)"}


def _f(val) -> float:
    try:
        return round(float(val), 1) if val is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def lookup(barcode: str) -> dict | None:
    """Look up a barcode on Open Food Facts. Returns a food dict or None."""
    try:
        r = httpx.get(_URL.format(barcode), params={"fields": _FIELDS},
                      timeout=8.0, headers=_HEADERS)
        data = r.json()
    except Exception:
        return None

    if data.get("status") != 1:
        return None

    p = data.get("product", {})
    n = p.get("nutriments", {})

    # Energy: prefer kcal, fall back to kJ → kcal
    kcal = n.get("energy-kcal_100g")
    if kcal is None:
        kj = n.get("energy_100g")
        kcal = round(kj / 4.184, 1) if kj else None
    if kcal is None:
        return None  # no usable nutrition

    name = (p.get("product_name_es") or p.get("product_name")
            or p.get("generic_name_es") or p.get("generic_name") or "").strip()
    if not name:
        return None

    # Drinks → unit "ml" so the portion engine offers vaso / lata
    tags = p.get("categories_tags", []) or []
    is_drink = any(any(k in t for k in ("beverage", "drink", "boisson", "bebida"))
                   for t in tags)

    return {
        "barcode": str(barcode),
        "name": name.title(),
        "marca": (p.get("brands") or "").split(",")[0].strip().title(),
        "categoria": "",
        "calories": _f(kcal),
        "protein": _f(n.get("proteins_100g")),
        "carbs": _f(n.get("carbohydrates_100g")),
        "fat": _f(n.get("fat_100g")),
        "fiber": _f(n.get("fiber_100g")),
        "sodium": round(_f(n.get("sodium_100g")) * 1000, 1),  # g → mg, like RNPA
        "unidad": "ml" if is_drink else "g",
        "source": "openfoodfacts",
    }
