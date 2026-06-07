import httpx
import os
from datetime import datetime

HEVY_BASE = "https://api.hevyapp.com/v1"


def get_headers():
    return {"api-key": os.environ.get("HEVY_API_KEY", "")}


def fetch_recent_workouts(pages=3):
    """Fetch last ~pages*10 workouts. Returns list of workout dicts."""
    workouts = []
    try:
        for page in range(1, pages + 1):
            r = httpx.get(
                f"{HEVY_BASE}/workouts",
                headers=get_headers(),
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
    """Return structured data for rendering a workout card."""
    start = workout.get("start_time", "")
    title = workout.get("title", "Entrenamiento")
    duration_mins = 0

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
            exercises.append({
                "name": ex.get("title", ""),
                "detail": f"{len(normal_sets)} series · max {max_w}kg · {total_reps} reps",
            })
        else:
            exercises.append({
                "name": ex.get("title", ""),
                "detail": f"{len(sets)} series",
            })

    raw_date = start[:10] if start else ""  # ISO date YYYY-MM-DD for sorting

    return {
        "title": title,
        "date": date_str,
        "sort_date": raw_date,
        "time": time_str,
        "duration_mins": duration_mins,
        "exercises": exercises,
        "start_time": start,
    }
