"""
Nutritional data per 100g for common Argentine/Spanish foods.
Values: calories (kcal), protein (g), carbs (g), fat (g)
"""

FOOD_DATABASE = {
    # Proteínas animales
    "Pechuga de pollo": {"calories": 165, "protein": 31, "carbs": 0, "fat": 3.6},
    "Muslo de pollo": {"calories": 209, "protein": 26, "carbs": 0, "fat": 11},
    "Carne vacuna magra (nalga)": {"calories": 158, "protein": 28, "carbs": 0, "fat": 5},
    "Carne vacuna (asado)": {"calories": 289, "protein": 24, "carbs": 0, "fat": 21},
    "Carne picada (magra)": {"calories": 215, "protein": 26, "carbs": 0, "fat": 12},
    "Huevo entero": {"calories": 155, "protein": 13, "carbs": 1.1, "fat": 11},
    "Clara de huevo": {"calories": 52, "protein": 11, "carbs": 0.7, "fat": 0.2},
    "Atún en agua": {"calories": 116, "protein": 26, "carbs": 0, "fat": 1},
    "Salmón": {"calories": 208, "protein": 20, "carbs": 0, "fat": 13},
    "Merluza": {"calories": 82, "protein": 17, "carbs": 0, "fat": 1.2},
    "Proteína whey": {"calories": 380, "protein": 75, "carbs": 8, "fat": 5},
    "Proteína caseína": {"calories": 370, "protein": 72, "carbs": 10, "fat": 4},
    "Jamón crudo": {"calories": 250, "protein": 29, "carbs": 0, "fat": 15},
    "Jamón cocido": {"calories": 145, "protein": 19, "carbs": 2, "fat": 6},
    "Milanesa de pollo": {"calories": 220, "protein": 25, "carbs": 10, "fat": 8},
    # Lácteos
    "Leche descremada": {"calories": 35, "protein": 3.5, "carbs": 5, "fat": 0.1},
    "Leche entera": {"calories": 61, "protein": 3.2, "carbs": 4.8, "fat": 3.3},
    "Yogur griego": {"calories": 97, "protein": 9, "carbs": 4, "fat": 5},
    "Yogur descremado natural": {"calories": 56, "protein": 5.7, "carbs": 7.7, "fat": 0.4},
    "Queso cottage": {"calories": 98, "protein": 11, "carbs": 3.4, "fat": 4.3},
    "Queso fresco": {"calories": 264, "protein": 18, "carbs": 2, "fat": 21},
    "Queso cremoso": {"calories": 330, "protein": 22, "carbs": 2, "fat": 26},
    "Ricota": {"calories": 174, "protein": 11, "carbs": 3, "fat": 13},
    # Carbohidratos / Cereales
    "Arroz blanco cocido": {"calories": 130, "protein": 2.7, "carbs": 28, "fat": 0.3},
    "Arroz integral cocido": {"calories": 123, "protein": 2.7, "carbs": 26, "fat": 1},
    "Avena": {"calories": 389, "protein": 17, "carbs": 66, "fat": 7},
    "Pasta cocida": {"calories": 158, "protein": 5.8, "carbs": 31, "fat": 0.9},
    "Pan integral": {"calories": 247, "protein": 13, "carbs": 41, "fat": 4.2},
    "Pan blanco": {"calories": 265, "protein": 9, "carbs": 49, "fat": 3.2},
    "Papa cocida": {"calories": 86, "protein": 1.9, "carbs": 20, "fat": 0.1},
    "Batata cocida": {"calories": 90, "protein": 2, "carbs": 21, "fat": 0.1},
    "Lenteja cocida": {"calories": 116, "protein": 9, "carbs": 20, "fat": 0.4},
    "Garbanzo cocido": {"calories": 164, "protein": 8.9, "carbs": 27, "fat": 2.6},
    "Quinoa cocida": {"calories": 120, "protein": 4.4, "carbs": 22, "fat": 1.9},
    "Galletitas de arroz": {"calories": 381, "protein": 7.5, "carbs": 81, "fat": 3},
    # Frutas
    "Banana": {"calories": 89, "protein": 1.1, "carbs": 23, "fat": 0.3},
    "Manzana": {"calories": 52, "protein": 0.3, "carbs": 14, "fat": 0.2},
    "Naranja": {"calories": 47, "protein": 0.9, "carbs": 12, "fat": 0.1},
    "Frutilla": {"calories": 32, "protein": 0.7, "carbs": 7.7, "fat": 0.3},
    "Uva": {"calories": 69, "protein": 0.7, "carbs": 18, "fat": 0.2},
    "Sandía": {"calories": 30, "protein": 0.6, "carbs": 7.6, "fat": 0.2},
    "Kiwi": {"calories": 61, "protein": 1.1, "carbs": 15, "fat": 0.5},
    # Verduras
    "Lechuga": {"calories": 15, "protein": 1.4, "carbs": 2.9, "fat": 0.2},
    "Tomate": {"calories": 18, "protein": 0.9, "carbs": 3.9, "fat": 0.2},
    "Brócoli": {"calories": 34, "protein": 2.8, "carbs": 7, "fat": 0.4},
    "Zanahoria": {"calories": 41, "protein": 0.9, "carbs": 10, "fat": 0.2},
    "Espinaca": {"calories": 23, "protein": 2.9, "carbs": 3.6, "fat": 0.4},
    "Zapallo": {"calories": 26, "protein": 1, "carbs": 6.5, "fat": 0.1},
    "Pepino": {"calories": 15, "protein": 0.7, "carbs": 3.6, "fat": 0.1},
    "Cebolla": {"calories": 40, "protein": 1.1, "carbs": 9.3, "fat": 0.1},
    "Pimiento rojo": {"calories": 31, "protein": 1, "carbs": 6, "fat": 0.3},
    "Choclo cocido": {"calories": 96, "protein": 3.4, "carbs": 21, "fat": 1.5},
    # Grasas saludables
    "Aceite de oliva": {"calories": 884, "protein": 0, "carbs": 0, "fat": 100},
    "Palta (aguacate)": {"calories": 160, "protein": 2, "carbs": 9, "fat": 15},
    "Maní (crudo)": {"calories": 567, "protein": 26, "carbs": 16, "fat": 49},
    "Mantequilla de maní": {"calories": 588, "protein": 25, "carbs": 20, "fat": 50},
    "Almendras": {"calories": 579, "protein": 21, "carbs": 22, "fat": 50},
    "Nueces": {"calories": 654, "protein": 15, "carbs": 14, "fat": 65},
    "Semillas de chía": {"calories": 486, "protein": 17, "carbs": 42, "fat": 31},
    "Aceite de coco": {"calories": 892, "protein": 0, "carbs": 0, "fat": 100},
    # Otros
    "Chocolate amargo 70%": {"calories": 598, "protein": 7.8, "carbs": 46, "fat": 43},
    "Miel": {"calories": 304, "protein": 0.3, "carbs": 82, "fat": 0},
    "Dulce de leche": {"calories": 327, "protein": 7, "carbs": 55, "fat": 9},
}


def search_foods(query: str) -> list[dict]:
    """Return a list of foods matching the query string (case-insensitive)."""
    query_lower = query.lower().strip()
    if not query_lower:
        return []

    results = []
    for name, data in FOOD_DATABASE.items():
        if query_lower in name.lower():
            results.append({"name": name, **data})

    # Sort: exact matches first, then starts-with, then contains
    def sort_key(item):
        n = item["name"].lower()
        if n == query_lower:
            return 0
        if n.startswith(query_lower):
            return 1
        return 2

    results.sort(key=sort_key)
    return results[:15]


def get_food(name: str) -> dict | None:
    """Return nutritional data for a specific food by exact name."""
    return FOOD_DATABASE.get(name)
