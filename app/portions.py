"""
Standard serving sizes (porciones) for foods.

get_portions(name, categoria, unidad) -> list[ {"label", "grams", "default"} ]

`grams` is the amount in the item's base unit (g for solids, ml for liquids).
Nutrition is scaled as  value_per_100 * grams / 100,  so it also works for ml.

Three layers, first match wins:
  1. Name patterns  — fresh produce, eggs, staples (precise, hand-tuned)
  2. Category rules — by RNPA / básico category (approximate)
  3. Fallback       — returns [] so the UI shows plain gram buttons

A "100 g" / "100 ml" reference chip is always appended.

Argentine household measures used (volume → typical weight):
  cucharada (sopera) ≈ 15 ml · cucharadita (de té) ≈ 5 ml
  taza ≈ 240 ml · tazón ≈ 350 ml · vaso ≈ 200 ml · pocillo ≈ 100 ml
"""
import re


def _norm(t: str) -> str:
    t = (t or "").lower()
    return t.translate(str.maketrans("áéíóúüñ", "aeiouun"))


def _p(label, grams, default=False):
    return {"label": label, "grams": float(grams), "default": default}


# ── 1. Name patterns ─────────────────────────────────────────────────────────
# Order matters: compound / specific names BEFORE generic ones.
_NAME_RULES_RAW: list[tuple[str, list]] = [

    # ---- Lácteos compuestos (antes de "leche") ----
    (r"dulce de leche",      [_p("1 cucharada", 20, True), _p("1 cucharadita", 7)]),
    (r"crema de leche",      [_p("1 cucharada", 15, True), _p("¼ taza", 60)]),

    # ---- Aceites (antes de coco / girasol / maíz) ----
    (r"\baceite\b",          [_p("1 cucharada", 14, True), _p("1 cucharadita", 5), _p("1 chorrito", 8)]),

    # ---- Huevos ----
    (r"clara de huevo",      [_p("1 unidad", 33, True), _p("2 unidades", 66)]),
    (r"yema de huevo",       [_p("1 unidad", 17, True), _p("2 unidades", 34)]),
    (r"\bhuevos?\b",         [_p("1 unidad", 60, True), _p("1 unidad grande", 70), _p("2 unidades", 120)]),

    # ---- Leche / yogur / quesos ----
    (r"\bleche\b",           [_p("1 vaso", 200, True), _p("1 taza", 245), _p("1 pocillo", 100)]),
    (r"yogur",               [_p("1 pote", 190, True), _p("1 taza", 245), _p("1 cucharada", 20)]),
    (r"ricota",              [_p("1 porción", 50, True), _p("1 cucharada", 30)]),
    (r"parmesano|rallado",   [_p("1 cucharada", 6, True), _p("1 cucharadita", 2)]),
    (r"mozzarella|cuartirolo|cremoso|port ?salut|\bqueso\b",
                             [_p("1 feta", 30, True), _p("1 porción", 40), _p("1 cucharada", 15)]),

    # ---- Suplementos ----
    (r"proteina|whey|caseina|caseín",
                             [_p("1 medida (scoop)", 30, True), _p("½ medida", 15)]),

    # ---- Frutos secos y semillas ----
    (r"almendras?",          [_p("1 puñado", 30, True), _p("1 unidad", 1.2), _p("1 cucharada", 15)]),
    (r"nueces|nuez",         [_p("1 puñado", 30, True), _p("1 mitad", 2)]),
    (r"\bmani\b|cacahuat",   [_p("1 puñado", 30, True), _p("1 cucharada", 12)]),
    (r"castaña.*caju|caju",  [_p("1 puñado", 30, True), _p("1 unidad", 1.5)]),
    (r"pistacho",            [_p("1 puñado", 30, True), _p("1 unidad", 0.7)]),
    (r"\bchia\b",            [_p("1 cucharada", 12, True), _p("1 cucharadita", 4)]),
    (r"\blino\b|linaza",     [_p("1 cucharada", 10, True), _p("1 cucharadita", 3)]),
    (r"semillas? de girasol",[_p("1 cucharada", 9, True), _p("1 puñado", 30)]),
    (r"sesamo",              [_p("1 cucharada", 9, True), _p("1 cucharadita", 3)]),

    # ---- Azúcares y dulces ----
    (r"azucar",              [_p("1 cucharada", 12, True), _p("1 cucharadita", 4), _p("1 sobre", 5)]),
    (r"\bmiel\b",            [_p("1 cucharada", 21, True), _p("1 cucharadita", 7)]),
    (r"mermelada",           [_p("1 cucharada", 20, True), _p("1 cucharadita", 7)]),

    # ---- Salsas y aderezos ----
    (r"salsa de tomate|pure de tomate|puré de tomate",
                             [_p("½ taza", 122, True), _p("1 cucharada", 16)]),
    (r"ketchup|mayonesa|mostaza|salsa de soja|salsa de soya",
                             [_p("1 cucharada", 15, True), _p("1 cucharadita", 5)]),
    (r"vinagre",             [_p("1 cucharada", 15, True), _p("1 cucharadita", 5)]),

    # ---- Condimentos ----
    (r"sal fina|\bsal\b",    [_p("1 cucharadita", 6, True), _p("1 pizca", 0.4)]),
    (r"caldo.*cubito|cubito|caldo en",
                             [_p("1 cubito", 10, True), _p("½ cubito", 5)]),

    # ---- Cereales, harinas, panes ----
    (r"arroz.*cocid",        [_p("1 taza", 160, True), _p("½ taza", 80), _p("1 tazón", 250)]),
    (r"\barroz\b",           [_p("1 taza", 185, True), _p("½ taza", 92), _p("1 cucharada", 12)]),
    (r"quinoa.*cocid",       [_p("1 taza", 185, True), _p("½ taza", 92)]),
    (r"quinoa",              [_p("¼ taza", 42, True), _p("1 cucharada", 11)]),
    (r"avena",               [_p("½ taza", 40, True), _p("1 taza", 80), _p("1 cucharada", 10)]),
    (r"harina",              [_p("1 taza", 120, True), _p("1 cucharada", 8)]),
    (r"fideos.*cocid",       [_p("1 plato", 220, True), _p("1 taza", 140)]),
    (r"\bfideos\b|\bpastas?\b",[_p("1 porción", 80, True), _p("1 plato", 100)]),
    (r"pan lactal|pan de molde",
                             [_p("1 rebanada", 25, True), _p("2 rebanadas", 50)]),
    (r"pan integral",        [_p("1 rebanada", 28, True), _p("2 rebanadas", 56)]),
    (r"pan frances|mignon|felipe|pan de viena",
                             [_p("1 unidad", 60, True), _p("½ unidad", 30)]),
    (r"\bpan\b",             [_p("1 porción", 50, True), _p("1 rebanada", 25)]),

    # ---- Legumbres ----
    (r"lenteja.*cocid",      [_p("1 taza", 198, True), _p("½ taza", 99)]),
    (r"lenteja",             [_p("1 taza", 192, True), _p("½ taza", 96)]),
    (r"garbanzo.*cocid",     [_p("1 taza", 164, True), _p("½ taza", 82)]),
    (r"garbanzo",            [_p("1 taza", 200, True), _p("½ taza", 100)]),
    (r"poroto.*cocid|frijol.*cocid",
                             [_p("1 taza", 172, True), _p("½ taza", 86)]),
    (r"poroto|frijol",       [_p("1 taza", 194, True), _p("½ taza", 97)]),
    (r"soja.*cocid|soya.*cocid",
                             [_p("1 taza", 172, True), _p("½ taza", 86)]),

    # ---- Carnes / pescados (específicas) ----
    (r"pechuga.*pollo",      [_p("1 porción", 150, True), _p("1 pechuga", 200), _p("1 porción chica", 100)]),
    (r"atun.*(lata|al agua|en aceite)|\blata.*atun",
                             [_p("1 lata", 120, True), _p("½ lata", 60)]),
    (r"langostino|camaron",  [_p("1 porción", 100, True), _p("1 unidad", 10)]),

    # ---- Frutas (por unidad) ----
    (r"\bbanana\b|platano",  [_p("1 unidad", 120, True), _p("½ unidad", 60), _p("1 rodaja", 8)]),
    (r"manzana(?!.*(deshidr|chips))",
                             [_p("1 unidad", 150, True), _p("½ unidad", 75), _p("1 rodaja", 20)]),
    (r"\bnaranjas?\b",       [_p("1 unidad", 180, True), _p("½ unidad", 90)]),
    (r"mandarina",           [_p("1 unidad", 90, True), _p("2 unidades", 180)]),
    (r"\blimon\b",           [_p("1 unidad", 100, True), _p("1 cucharada (jugo)", 15)]),
    (r"\blima\b",            [_p("1 unidad", 67, True)]),
    (r"pomelo",              [_p("1 unidad", 230, True), _p("½ unidad", 115)]),
    (r"frutilla",            [_p("1 taza", 150, True), _p("1 unidad", 12)]),
    (r"\buvas?\b",           [_p("1 taza", 150, True), _p("1 grano", 5)]),
    (r"\bpera\b",            [_p("1 unidad", 160, True), _p("½ unidad", 80)]),
    (r"durazno",             [_p("1 unidad", 150, True), _p("½ unidad", 75)]),
    (r"sandia",              [_p("1 taza", 150, True), _p("1 rodaja", 200)]),
    (r"\bmelon\b",           [_p("1 taza", 150, True), _p("1 rodaja", 160)]),
    (r"\bkiwi\b",            [_p("1 unidad", 75, True), _p("2 unidades", 150)]),
    (r"anana|piña|ananas",   [_p("1 rodaja", 80, True), _p("1 taza", 165)]),
    (r"ciruela",             [_p("1 unidad", 65, True), _p("2 unidades", 130)]),
    (r"cereza",              [_p("1 taza", 140, True), _p("1 unidad", 8)]),
    (r"\bmango\b",           [_p("1 unidad", 200, True), _p("½ unidad", 100)]),
    (r"papaya|mamon",        [_p("1 taza", 145, True), _p("½ unidad", 150)]),
    (r"\bhigos?\b",          [_p("1 unidad", 50, True), _p("2 unidades", 100)]),
    (r"granada",             [_p("1 unidad", 180, True), _p("½ unidad", 90)]),
    (r"frambuesa",           [_p("1 taza", 125, True), _p("1 puñado", 30)]),
    (r"arandano",            [_p("1 taza", 145, True), _p("1 puñado", 30)]),
    (r"\bmoras?\b",          [_p("1 taza", 145, True), _p("1 puñado", 30)]),
    (r"maracuya",            [_p("1 unidad", 18, True), _p("2 unidades", 36)]),
    (r"coco fresco|\bcoco\b",[_p("1 trozo", 45, True), _p("1 taza rallado", 80)]),
    (r"damasco|albaricoq",   [_p("1 unidad", 35, True), _p("2 unidades", 70)]),
    (r"membrillo",           [_p("1 unidad", 90, True)]),
    (r"nispero",             [_p("1 unidad", 40, True)]),
    (r"\btuna\b",            [_p("1 unidad", 100, True)]),
    (r"guayaba",             [_p("1 unidad", 55, True)]),

    # ---- Verduras y hortalizas ----
    (r"\bpapas?\b(?!.*(frit|chips|prefrit|noisette))",
                             [_p("1 unidad", 150, True), _p("1 unidad chica", 90)]),
    (r"batata|boniato",      [_p("1 unidad", 130, True), _p("½ unidad", 65)]),
    (r"tomate cherry|cherry",[_p("1 taza", 150, True), _p("1 unidad", 15)]),
    (r"\btomates?\b(?!.*(triturad|pure|pelad|seco|deshidr|salsa|extracto|concentr))",
                             [_p("1 unidad", 120, True), _p("1 rodaja", 20)]),
    (r"lechuga",             [_p("1 plato", 60, True), _p("1 taza", 35), _p("1 hoja", 10)]),
    (r"zanahoria",           [_p("1 unidad", 70, True), _p("1 taza rallada", 110)]),
    (r"cebolla de verdeo",   [_p("1 tallo", 15, True), _p("2 tallos", 30)]),
    (r"\bcebollas?\b",       [_p("1 unidad", 110, True), _p("½ unidad", 55)]),
    (r"\bajo\b",             [_p("1 diente", 3, True), _p("3 dientes", 9)]),
    (r"morron|pimiento|aji ",[_p("1 unidad", 120, True), _p("½ unidad", 60)]),
    (r"zapallo",             [_p("1 taza", 116, True), _p("1 porción", 150)]),
    (r"zucchini|zapallito",  [_p("1 unidad", 200, True), _p("1 taza", 124)]),
    (r"brocoli",             [_p("1 taza", 90, True), _p("1 porción", 150)]),
    (r"coliflor",            [_p("1 taza", 100, True), _p("1 porción", 150)]),
    (r"espinaca",            [_p("1 taza", 30, True), _p("1 porción cocida", 90)]),
    (r"acelga",              [_p("1 taza", 36, True), _p("1 porción cocida", 90)]),
    (r"choclo.*(cocid|desgran)|granos? de choclo",
                             [_p("1 taza", 145, True), _p("½ taza", 72)]),
    (r"\bchoclos?\b",        [_p("1 unidad", 100, True), _p("½ unidad", 50)]),
    (r"\bapio\b",            [_p("1 tallo", 40, True), _p("1 taza", 100)]),
    (r"pepino",              [_p("1 unidad", 200, True), _p("1 rodaja", 7)]),
    (r"berenjena",           [_p("1 unidad", 250, True), _p("1 taza", 82)]),
    (r"remolacha",           [_p("1 unidad", 80, True), _p("1 taza", 136)]),
    (r"puerro",              [_p("1 unidad", 90, True)]),
    (r"champignon|champiñon|hongo|seta",
                             [_p("1 taza", 70, True), _p("1 unidad", 18)]),
    (r"\bpalta\b|aguacate",  [_p("1 unidad", 150, True), _p("½ unidad", 75)]),
    (r"alcaucil|alcachofa",  [_p("1 unidad", 128, True)]),
    (r"chaucha",             [_p("1 taza", 110, True), _p("1 porción", 90)]),
    (r"arvejas?",            [_p("1 taza", 145, True), _p("1 cucharada", 12)]),
    (r"\bhabas?\b",          [_p("1 taza", 150, True)]),
    (r"\bnabo\b",            [_p("1 unidad", 120, True)]),
    (r"rabanito|rabano",     [_p("1 unidad", 5, True), _p("1 taza", 116)]),
    (r"\bberro\b",           [_p("1 puñado", 25, True), _p("1 taza", 20)]),
    (r"rucula",              [_p("1 puñado", 25, True), _p("1 taza", 20)]),
    (r"repollo",             [_p("1 taza", 90, True), _p("1 hoja", 15)]),
    (r"\bkale\b",            [_p("1 taza", 20, True), _p("1 puñado", 25)]),
    (r"hinojo",              [_p("1 unidad", 230, True), _p("½ unidad", 115)]),
    (r"endibia|endivia",     [_p("1 unidad", 50, True)]),
    (r"esparrago",           [_p("1 atado", 150, True), _p("1 unidad", 18)]),
]

_NAME_RULES = [(re.compile(p), ports) for p, ports in _NAME_RULES_RAW]


# ── 2. Category rules ────────────────────────────────────────────────────────
# Keyed by normalized category. Values are functions of unit ("g"/"ml").
def _cat_aceites(u):   return [_p("1 cucharada", 14, True), _p("1 cucharadita", 5)]
def _cat_bebidas(u):   return [_p("1 vaso", 200, True), _p("1 lata", 354), _p("1 botella", 500)]
def _cat_jugos(u):     return [_p("1 vaso", 200, True), _p("1 caja", 200), _p("1 botella", 500)]
def _cat_infusiones(u):return [_p("1 taza", 200, True), _p("1 pocillo", 100)]
def _cat_cafe(u):
    return ([_p("1 taza", 200, True), _p("1 pocillo", 100)] if u == "ml"
            else [_p("1 cucharadita", 2, True), _p("1 cucharada", 6)])
def _cat_aguas(u):     return [_p("1 vaso", 200, True), _p("1 botella", 500)]
def _cat_azucares(u):  return [_p("1 cucharada", 12, True), _p("1 cucharadita", 4), _p("1 sobre", 5)]
def _cat_jarabes(u):   return [_p("1 cucharada", 20, True), _p("1 cucharadita", 7)]
def _cat_salsas(u):    return [_p("1 cucharada", 15, True), _p("1 cucharadita", 5)]
def _cat_quesos(u):    return [_p("1 feta", 30, True), _p("1 porción", 40), _p("1 cucharada", 15)]
def _cat_galletitas(u):return [_p("1 porción", 30, True), _p("1 galletita", 8), _p("1 barra", 30)]
def _cat_golosinas(u): return [_p("1 porción", 30, True), _p("1 unidad", 5)]
def _cat_chocolate(u): return [_p("1 porción", 30, True), _p("1 fila", 20), _p("1 barra", 100)]
def _cat_alfajores(u): return [_p("1 unidad", 50, True), _p("½ unidad", 25)]
def _cat_helados(u):   return [_p("1 bocha", 65, True), _p("1 porción", 100), _p("1 vasito", 90)]
def _cat_confituras(u):return [_p("1 cucharada", 20, True), _p("1 cucharadita", 7)]
def _cat_panaderia(u): return [_p("1 unidad", 60, True), _p("1 porción", 50)]
def _cat_pastas(u):    return [_p("1 porción", 100, True), _p("1 plato", 220)]
def _cat_carnes(u):    return [_p("1 porción", 150, True), _p("1 porción chica", 100), _p("1 porción grande", 200), _p("1 feta", 15)]
def _cat_preparadas(u):return [_p("1 porción", 250, True), _p("1 plato", 350)]
def _cat_postres(u):   return [_p("1 pote", 100, True), _p("1 porción", 120)]
def _cat_reposteria(u):return [_p("1 porción", 60, True)]
def _cat_cereales(u):  return [_p("1 taza", 40, True), _p("1 porción", 30), _p("1 cucharada", 8)]
def _cat_vegfrutas(u): return [_p("1 porción", 100, True), _p("1 taza", 120)]
def _cat_secos(u):     return [_p("1 puñado", 30, True), _p("1 cucharada", 12)]
def _cat_huevos(u):    return [_p("1 unidad", 60, True), _p("2 unidades", 120)]
def _cat_lacteos(u):
    return ([_p("1 vaso", 200, True), _p("1 taza", 245)] if u == "ml"
            else [_p("1 pote", 190, True), _p("1 cucharada", 20)])
def _cat_condimentos(u):return [_p("1 cucharadita", 2, True), _p("1 pizca", 0.4)]
def _cat_sal(u):       return [_p("1 cucharadita", 6, True), _p("1 pizca", 0.4)]
def _cat_caldos(u):
    return ([_p("1 taza", 250, True), _p("1 plato", 350)] if u == "ml"
            else [_p("1 cubito", 10, True), _p("1 cucharada", 12)])
def _cat_pescadolata(u):return [_p("1 lata", 120, True), _p("½ lata", 60)]
def _cat_vinagres(u):  return [_p("1 cucharada", 15, True), _p("1 cucharadita", 5)]
def _cat_suplementos(u):return [_p("1 medida (scoop)", 30, True), _p("½ medida", 15)]

_CATEGORY_RULES = {
    # RNPA / genérico categories
    "aceites y grasas": _cat_aceites,
    "bebidas analcoholicas": _cat_bebidas,
    "bebidas alcoholicas": _cat_bebidas,
    "jugos": _cat_jugos,
    "te e infusiones": _cat_infusiones,
    "cafe y sucedaneos": _cat_cafe,
    "aguas": _cat_aguas,
    "azucares y edulcorantes": _cat_azucares,
    "jarabes y siropes": _cat_jarabes,
    "salsas y aderezos": _cat_salsas,
    "quesos": _cat_quesos,
    "galletitas y barras": _cat_galletitas,
    "caramelos y golosinas": _cat_golosinas,
    "cacao y chocolate": _cat_chocolate,
    "alfajores": _cat_alfajores,
    "helados": _cat_helados,
    "confituras y dulces": _cat_confituras,
    "masas y panaderia": _cat_panaderia,
    "reposteria y confiteria": _cat_reposteria,
    "pastas": _cat_pastas,
    "carnes y chacinados": _cat_carnes,
    "comidas preparadas": _cat_preparadas,
    "postres": _cat_postres,
    "cereales y harinas": _cat_cereales,
    "vegetales y frutas": _cat_vegfrutas,
    "semillas y frutos secos": _cat_secos,
    "huevos": _cat_huevos,
    "lacteos": _cat_lacteos,
    "condimentos y especias": _cat_condimentos,
    "sal y sales": _cat_sal,
    "caldos y sopas": _cat_caldos,
    "conservas de pescado y mar": _cat_pescadolata,
    "vinagres": _cat_vinagres,
    "hongos": lambda u: [_p("1 taza", 70, True), _p("1 unidad", 18)],
    "suplementos y dieteticos": _cat_suplementos,
    # básico categories (fallback if a básico misses every name rule)
    "frutas": lambda u: [_p("1 unidad", 120, True), _p("½ unidad", 60)],
    "verduras y hortalizas": lambda u: [_p("1 unidad", 100, True), _p("1 taza", 100)],
    "carnes y pescados": _cat_carnes,
    "huevos y lacteos": _cat_lacteos,
    "frutos secos": _cat_secos,
    "legumbres": lambda u: [_p("1 taza", 180, True), _p("½ taza", 90)],
    "azucares y endulzantes": _cat_azucares,
    "condimentos": _cat_condimentos,
    "suplementos": _cat_suplementos,
}


def _finalize(ports: list, u: str) -> list:
    """Dedupe, guarantee a single default, append a 100 g/ml reference chip."""
    out, seen = [], set()
    has_default = any(p.get("default") for p in ports)
    for i, p in enumerate(ports):
        g = round(float(p["grams"]), 1)
        key = (p["label"], g)
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "label": p["label"],
            "grams": g,
            "default": bool(p.get("default")) or (not has_default and i == 0),
        })
    # keep only the first default
    seen_def = False
    for p in out:
        if p["default"] and not seen_def:
            seen_def = True
        elif p["default"]:
            p["default"] = False
    # always offer a per-100 reference
    if not any(abs(p["grams"] - 100) < 0.01 for p in out):
        out.append({"label": f"100 {u}", "grams": 100.0, "default": not seen_def})
    return out


def get_portions(name: str, categoria: str = "", unidad: str = "g") -> list:
    """Return available portions for a food, or [] if none apply."""
    u = "ml" if str(unidad).strip().lower() == "ml" else "g"
    n = _norm(name)

    for rx, ports in _NAME_RULES:
        if rx.search(n):
            return _finalize(ports, u)

    rule = _CATEGORY_RULES.get(_norm(categoria))
    if rule:
        return _finalize(rule(u), u)

    return []
