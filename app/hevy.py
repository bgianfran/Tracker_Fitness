import httpx
import os
from datetime import datetime

HEVY_BASE = "https://api.hevyapp.com/v1"


# ──────────────────────────────────────────────────────────────────────────
# Muscle group inference
#
# Hevy's workout endpoint only returns the exercise title (not the muscle
# group), so we infer the primary muscle group from the title using ordered
# keyword matching. Rules are checked top-to-bottom and the first match wins,
# so more specific patterns (e.g. "leg curl" → Isquios) must come before more
# generic ones (e.g. "curl" → Bíceps). Covers Hevy's default English titles
# plus common Spanish names. Unknown / custom exercises fall back to "Otro".
# ──────────────────────────────────────────────────────────────────────────
_MUSCLE_RULES = [
    ("Isquios", [
        "romanian deadlift", "rdl", "leg curl", "lying curl", "seated leg curl",
        "good morning", "femoral", "hamstring", "nordic", "isquio",
    ]),
    ("Glúteos", [
        "hip thrust", "glute", "gluteo", "glúteo", "hip abduction", "abductor",
        "kickback", "puente de glúteo", "puente de gluteo",
    ]),
    ("Gemelos", [
        "calf", "gemelo", "soleus", "soleo", "pantorrilla",
    ]),
    ("Cuádriceps", [
        "squat", "sentadilla", "leg press", "prensa", "lunge", "zancada",
        "leg extension", "extensión de cuád", "extension de cuad", "hack",
        "step up", "step-up", "bulgarian", "split squat", "pistol",
    ]),
    ("Antebrazos", [
        "wrist curl", "reverse curl", "forearm", "antebrazo", "wrist",
    ]),
    ("Tríceps", [
        "tricep", "tríceps", "pushdown", "push down", "skull", "press francés",
        "press frances", "overhead extension", "extensión de tríceps",
        "extension de triceps", "close grip", "press cerrado", "dip", "fondo",
    ]),
    ("Bíceps", [
        "bicep", "bíceps", "curl", "predicador", "preacher",
    ]),
    ("Hombros", [
        "shoulder press", "overhead press", "ohp", "military", "press militar",
        "lateral raise", "elevación lateral", "elevacion lateral", "front raise",
        "elevación frontal", "elevacion frontal", "rear delt", "deltoid",
        "deltoide", "face pull", "arnold", "upright row", "remo al mentón",
        "remo al menton", "hombro", "shoulder",
    ]),
    ("Espalda", [
        "row", "remo", "pulldown", "jalón", "jalon", "pull up", "pull-up",
        "pullup", "chin up", "chin-up", "chinup", "dominada", "lat ", "lat-",
        "pullover", "deadlift", "peso muerto", "shrug", "encogimiento",
        "trapecio", "back extension", "hiperext", "espalda", "back",
    ]),
    ("Pecho", [
        "bench press", "press de banca", "press banca", "chest press",
        "press de pecho", "chest fly", "apertura", "pec deck", "peck deck",
        "push up", "push-up", "pushup", "flexion", "flexión", "pecho", "chest",
        "incline press", "decline press", "press inclinado", "press declinado",
    ]),
    ("Abdominales", [
        "crunch", "plank", "plancha", "sit up", "sit-up", "abdominal", "ab wheel",
        "leg raise", "elevación de pierna", "elevacion de pierna", "russian twist",
        "oblicuo", "hollow", "core", "rueda abdominal",
    ]),
]


def infer_muscle_group(title: str) -> str:
    """Infer the primary muscle group from an exercise title (best effort)."""
    t = (title or "").lower()
    for muscle, keywords in _MUSCLE_RULES:
        for kw in keywords:
            if kw in t:
                return muscle
    return "Otro"


def get_headers(api_key: str = None):
    key = api_key or os.environ.get("HEVY_API_KEY", "")
    return {"api-key": key}


def fetch_recent_workouts(pages=3, api_key: str = None):
    """Fetch last ~pages*10 workouts. Returns list of workout dicts."""
    workouts = []
    try:
        for page in range(1, pages + 1):
            r = httpx.get(
                f"{HEVY_BASE}/workouts",
                headers=get_headers(api_key),
                params={"page": page, "pageSize": 10},
                timeout=10,
            )
            if r.status_code != 200:
                break
            data = r.json()
            workouts.extend(data.get("workouts", []))
            if page >= data.get("page_count", 1):
                break
    except Exception:
        pass
    return workouts


def format_workout_summary(workout):
    """Return a compact text summary of a workout for the AI context."""
    start = workout.get("start_time", "")[:10]
    title = workout.get("title", "Entrenamiento")
    duration_mins = 0
    if workout.get("start_time") and workout.get("end_time"):
        try:
            s = datetime.fromisoformat(workout["start_time"].replace("Z", "+00:00"))
            e = datetime.fromisoformat(workout["end_time"].replace("Z", "+00:00"))
            duration_mins = int((e - s).total_seconds() / 60)
        except Exception:
            pass

    exercises = []
    for ex in workout.get("exercises", []):
        sets = ex.get("sets", [])
        normal_sets = [s for s in sets if s.get("type") == "normal" and s.get("weight_kg")]
        if normal_sets:
            max_w = max(s["weight_kg"] for s in normal_sets)
            total_reps = sum(s.get("reps", 0) or 0 for s in normal_sets)
            exercises.append(
                f"{ex['title']}: {len(normal_sets)}x (max {max_w}kg, {total_reps} reps)"
            )
        else:
            exercises.append(f"{ex['title']}: {len(sets)} series")

    return f"[{start}] {title} ({duration_mins}min): " + " | ".join(exercises[:6])


def get_workout_display_data(workout):
    """Return structured data for rendering a workout card and for analysis.

    Includes per-exercise stats (max weight, sets, reps, volume, inferred
    muscle group) and per-workout aggregates (total volume, muscle breakdown).
    """
    start = workout.get("start_time", "")
    title = workout.get("title", "Entrenamiento")
    duration_mins = 0
    duration_seconds = 0

    date_str = start[:10] if start else ""
    time_str = ""
    if start:
        try:
            dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
            date_str = dt.strftime("%d/%m/%Y")
            time_str = dt.strftime("%H:%M")
        except Exception:
            pass

    if workout.get("start_time") and workout.get("end_time"):
        try:
            s = datetime.fromisoformat(workout["start_time"].replace("Z", "+00:00"))
            e = datetime.fromisoformat(workout["end_time"].replace("Z", "+00:00"))
            duration_seconds = int((e - s).total_seconds())
            duration_mins = duration_seconds // 60
        except Exception:
            pass

    exercises = []
    total_volume = 0.0
    muscle_volume = {}
    muscle_sets = {}
    for ex in workout.get("exercises", []):
        ex_title = ex.get("title", "")
        muscle = infer_muscle_group(ex_title)
        sets = ex.get("sets", [])
        # Count every set that isn't an explicit warmup as a working set.
        working = [s for s in sets if s.get("type") != "warmup"]
        weighted = [s for s in working if s.get("weight_kg")]

        ex_volume = 0.0
        max_w = 0.0
        total_reps = 0
        for s in working:
            w = s.get("weight_kg") or 0
            r = s.get("reps") or 0
            ex_volume += w * r
            total_reps += r
            if w > max_w:
                max_w = w

        total_volume += ex_volume
        muscle_volume[muscle] = muscle_volume.get(muscle, 0.0) + ex_volume
        muscle_sets[muscle] = muscle_sets.get(muscle, 0) + len(working)

        if weighted:
            detail = f"{len(working)} series · máx {max_w:g}kg · {total_reps} reps"
        else:
            detail = f"{len(sets)} series"

        exercises.append({
            "name": ex_title,
            "detail": detail,
            "muscle": muscle,
            "max_weight": round(max_w, 1),
            "sets": len(working),
            "reps": total_reps,
            "volume": round(ex_volume, 1),
        })

    raw_date = start[:10] if start else ""  # ISO date YYYY-MM-DD for sorting

    return {
        "title": title,
        "date": date_str,
        "sort_date": raw_date,
        "time": time_str,
        "duration_mins": duration_mins,
        "duration_seconds": duration_seconds,
        "exercise_count": len(exercises),
        "total_volume_kg": round(total_volume, 1),
        "muscle_volume": {k: round(v, 1) for k, v in muscle_volume.items()},
        "muscle_sets": muscle_sets,
        "exercises": exercises,
        "start_time": start,
    }
