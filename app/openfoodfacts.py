import httpx
from typing import Optional

OFF_SEARCH_URL = "https://world.openfoodfacts.org/cgi/search.pl"
OFF_PRODUCT_URL = "https://world.openfoodfacts.org/api/v0/product/{barcode}.json"

_FIELDS = "product_name,brands,nutriments,quantity,image_front_small_url,countries_tags"


def search_openfoodfacts(query: str, limit: int = 10) -> list[dict]:
    """Search Open Food Facts, prioritizing Argentine products."""
    results = []

    # First try: Argentina-specific search
    ar_results = _search(query, country="ar", limit=limit)
    results.extend(ar_results)

    # Fill up with world results if needed
    if len(results) < limit:
        world_results = _search(query, country=None, limit=limit - len(results))
        seen_codes = {r["barcode"] for r in results}
        for r in world_results:
            if r["barcode"] not in seen_codes:
                results.append(r)

    return results[:limit]


def _search(query: str, country: Optional[str], limit: int) -> list[dict]:
    params = {
        "search_terms": query,
        "search_simple": 1,
        "action": "process",
        "json": 1,
        "page_size": limit,
        "fields": _FIELDS,
    }
    if country:
        params["tagtype_0"] = "countries"
        params["tag_contains_0"] = "contains"
        params["tag_0"] = country

    try:
        resp = httpx.get(OFF_SEARCH_URL, params=params, timeout=8)
        resp.raise_for_status()
        data = resp.json()
        return [_parse_product(p) for p in data.get("products", []) if _has_nutrition(p)]
    except Exception:
        return []


def get_by_barcode(barcode: str) -> Optional[dict]:
    try:
        resp = httpx.get(OFF_PRODUCT_URL.format(barcode=barcode), timeout=8)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") == 1:
            return _parse_product(data["product"])
    except Exception:
        pass
    return None


def _has_nutrition(product: dict) -> bool:
    n = product.get("nutriments", {})
    return bool(n.get("energy-kcal_100g") or n.get("energy_100g"))


def _parse_product(product: dict) -> dict:
    n = product.get("nutriments", {})
    calories = n.get("energy-kcal_100g") or (n.get("energy_100g", 0) / 4.184)
    name = product.get("product_name", "").strip()
    brand = product.get("brands", "").split(",")[0].strip()
    display_name = f"{name} ({brand})" if brand and brand.lower() not in name.lower() else name

    # Flag if it's an Argentine product
    countries = product.get("countries_tags", [])
    is_ar = any("argentina" in c.lower() for c in countries)

    return {
        "barcode": product.get("code", ""),
        "name": display_name or "Producto sin nombre",
        "calories": round(float(calories or 0), 1),
        "protein": round(float(n.get("proteins_100g", 0) or 0), 1),
        "carbs": round(float(n.get("carbohydrates_100g", 0) or 0), 1),
        "fat": round(float(n.get("fat_100g", 0) or 0), 1),
        "quantity": product.get("quantity", ""),
        "image": product.get("image_front_small_url", ""),
        "is_ar": is_ar,
        "source": "openfoodfacts",
    }
