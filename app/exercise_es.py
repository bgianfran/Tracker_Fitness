"""Deterministic English→Spanish translator for exercise names.

Ships with the app (no API needed) so the catalog reads in Spanish out of the
box. Strategy: pull the equipment word out (to a parenthetical suffix), move
leading qualifiers (incline / seated / standing…) to after the movement, and
translate known movement phrases + words. Unknown words are kept as-is. For
higher polish, scripts/translate_names.py can overwrite name_es with AI output.
"""
import re

# Equipment word(s) → Spanish suffix. Matched anywhere, longest first.
_EQUIP = [
    ("smith machine", "en multipower"),
    ("resistance band", "con banda"),
    ("ez-bar", "con barra Z"), ("ez bar", "con barra Z"),
    ("barbell", "con barra"),
    ("dumbbell", "con mancuerna"),
    ("kettlebell", "con pesa rusa"),
    ("cable", "en polea"),
    ("leverage", "en máquina"), ("lever", "en máquina"),
    ("machine", "en máquina"),
    ("smith", "en multipower"),
    ("band", "con banda"),
    ("bodyweight", "peso corporal"),
]

# Leading qualifiers → Spanish, moved to AFTER the movement. Longest first.
_QUALIFIERS = [
    ("bent over", "inclinado"), ("bent-over", "inclinado"), ("bent", "inclinado"),
    ("incline", "inclinado"), ("decline", "declinado"),
    ("seated", "sentado"), ("standing", "de pie"), ("lying", "acostado"),
    ("kneeling", "arrodillado"), ("prone", "boca abajo"),
    ("alternating", "alternado"), ("alternate", "alternado"),
    ("reverse grip", "agarre inverso"), ("reverse-grip", "agarre inverso"),
    ("reverse", "inverso"), ("weighted", "con peso"),
    ("single-arm", "a un brazo"), ("one-arm", "a un brazo"), ("single arm", "a un brazo"),
    ("single-leg", "a una pierna"), ("one-legged", "a una pierna"),
    ("wide-grip", "agarre abierto"), ("wide grip", "agarre abierto"),
    ("close-grip", "agarre cerrado"), ("close grip", "agarre cerrado"),
]

# Movement phrases (applied after equipment/qualifiers stripped). Longest first.
_PHRASES = [
    ("bench press", "press de banca"),
    ("shoulder press", "press de hombros"),
    ("overhead press", "press militar"), ("military press", "press militar"),
    ("chest press", "press de pecho"),
    ("leg press", "prensa de piernas"),
    ("leg curl", "curl femoral"),
    ("leg extension", "extensión de cuádriceps"),
    ("hanging leg raise", "elevación de piernas colgado"),
    ("leg raise", "elevación de piernas"),
    ("calf raise", "elevación de gemelos"), ("calf raises", "elevación de gemelos"),
    ("lateral raise", "elevación lateral"), ("lateral raises", "elevación lateral"),
    ("front raise", "elevación frontal"), ("front raises", "elevación frontal"),
    ("rear delt raise", "elevación posterior de hombro"),
    ("rear delt", "deltoides posterior"),
    ("lat pulldown", "jalón al pecho"),
    ("romanian deadlift", "peso muerto rumano"),
    ("stiff leg deadlift", "peso muerto piernas rígidas"),
    ("stiff-legged deadlift", "peso muerto piernas rígidas"),
    ("sumo deadlift", "peso muerto sumo"),
    ("deadlift", "peso muerto"),
    ("front squat", "sentadilla frontal"),
    ("full squat", "sentadilla profunda"),
    ("split squat", "sentadilla búlgara"),
    ("good morning", "buenos días"),
    ("hip thrust", "empuje de cadera"),
    ("face pull", "jalón a la cara"),
    ("push-up", "flexiones"), ("push up", "flexiones"), ("pushup", "flexiones"),
    ("push-ups", "flexiones"), ("pushups", "flexiones"),
    ("sit-up", "abdominales"), ("sit up", "abdominales"), ("situp", "abdominales"),
    ("sit-ups", "abdominales"),
    ("step-up", "subida al cajón"), ("step up", "subida al cajón"),
    ("triceps extension", "extensión de tríceps"), ("tricep extension", "extensión de tríceps"),
    ("triceps pushdown", "extensión de tríceps en polea"),
    ("tricep pushdown", "extensión de tríceps en polea"),
    ("hammer curl", "curl martillo"), ("hammer curls", "curl martillo"),
    ("preacher curl", "curl predicador"), ("preacher curls", "curl predicador"),
    ("concentration curl", "curl concentrado"),
    ("wrist curl", "curl de muñeca"), ("wrist curls", "curl de muñeca"),
    ("bicep curl", "curl de bíceps"), ("biceps curl", "curl de bíceps"),
    ("bicep curls", "curl de bíceps"), ("biceps curls", "curl de bíceps"),
    ("medium grip", "agarre medio"), ("wide grip", "agarre abierto"),
    ("close grip", "agarre cerrado"),
    ("leg raises", "elevación de piernas"),
    ("seated row", "remo sentado"), ("cable row", "remo en polea"),
    ("upright row", "remo al mentón"),
    ("cable crossover", "cruce en polea"), ("crossover", "cruce"),
    ("skull crusher", "rompecráneos"), ("skullcrusher", "rompecráneos"),
    ("pull-up", "dominada"), ("pull up", "dominada"), ("pullup", "dominada"),
    ("pull-ups", "dominadas"), ("pullups", "dominadas"),
    ("chin-up", "dominada supina"), ("chin up", "dominada supina"),
    ("russian twist", "giro ruso"),
    ("mountain climber", "escalador"),
    ("jumping jack", "saltos de tijera"),
    ("box jump", "salto al cajón"),
    ("clean and jerk", "cargada y envión"),
    ("hang clean", "cargada colgante"),
    ("power clean", "cargada de potencia"),
    ("calf press", "extensión de gemelos"),
]

# Single words (fallback, applied last).
_WORDS = {
    "press": "press", "curl": "curl", "curls": "curls",
    "row": "remo", "rows": "remo", "stretch": "estiramiento", "stretches": "estiramientos",
    "raise": "elevación", "raises": "elevaciones",
    "triceps": "de tríceps", "tricep": "de tríceps", "biceps": "de bíceps", "bicep": "de bíceps",
    "extension": "extensión", "extensions": "extensiones",
    "leg": "de pierna", "legs": "de piernas", "side": "lateral",
    "clean": "cargada", "chest": "de pecho", "calf": "de gemelos", "calves": "de gemelos",
    "jump": "salto", "jumps": "saltos", "overhead": "sobre la cabeza", "front": "frontal",
    "crunch": "abdominal", "crunches": "abdominales", "shoulder": "de hombros",
    "shoulders": "de hombros", "wrist": "de muñeca", "snatch": "arranque",
    "hip": "de cadera", "lateral": "lateral", "push": "empuje", "pull": "jalón",
    "pulldown": "jalón", "pushdown": "en polea", "hamstring": "de isquios",
    "hamstrings": "de isquios", "split": "split", "fly": "aperturas", "flyes": "aperturas",
    "flys": "aperturas", "flye": "aperturas", "lunge": "zancada", "lunges": "zancadas",
    "dip": "fondo", "dips": "fondos", "shrug": "encogimiento", "shrugs": "encogimientos",
    "plank": "plancha", "glute": "de glúteo", "glutes": "de glúteos", "quad": "de cuádriceps",
    "quads": "de cuádriceps", "adductor": "aductor", "abductor": "abductor", "twist": "giro",
    "squat": "sentadilla", "squats": "sentadillas", "thrust": "empuje", "swing": "swing",
    "pullover": "pullover", "row.": "remo", "kickback": "patada", "kickbacks": "patadas",
    "windmill": "molino", "rotation": "rotación", "circles": "círculos", "bridge": "puente",
    "raise.": "elevación", "extension.": "extensión", "rope": "con cuerda",
    "attachment": "", "v-bar": "con barra V", "to": "a", "the": "el", "with": "con",
    "and": "y", "on": "en",
}

_QUAL_SET = set()  # for fast removal detection


def _extract_equipment(text):
    equip = None
    for token, suffix in _EQUIP:
        if re.search(r"\b" + re.escape(token) + r"\b", text):
            if equip is None:
                equip = suffix
            text = re.sub(r"\b" + re.escape(token) + r"\b", " ", text)
    return re.sub(r"\s+", " ", text).strip(), equip


def _extract_leading_qualifiers(text):
    quals = []
    changed = True
    while changed:
        changed = False
        for en, es in _QUALIFIERS:
            if text == en or text.startswith(en + " "):
                quals.append(es)
                text = text[len(en):].strip()
                changed = True
                break
    return text, quals


def _translate_core(text):
    for en, es in _PHRASES:
        text = re.sub(r"\b" + re.escape(en) + r"\b", es, text)
    out = []
    for tok in text.split():
        key = tok.strip(".,").lower()
        val = _WORDS.get(key, tok)
        if val:  # allow dropping words (mapped to "")
            out.append(val)
    return " ".join(out).strip()


def translate_name(name_en):
    """Best-effort Spanish rendering of an English exercise name."""
    if not name_en:
        return name_en
    text = name_en.lower().strip()
    text, equip = _extract_equipment(text)
    text, quals = _extract_leading_qualifiers(text)
    core = _translate_core(text)
    parts = [p for p in [core, " ".join(quals)] if p]
    result = " ".join(parts)
    result = re.sub(r"\s+", " ", result).strip(" -")
    if equip:
        result = f"{result} ({equip})" if result else equip
    if not result:
        return name_en
    return result[0].upper() + result[1:]
