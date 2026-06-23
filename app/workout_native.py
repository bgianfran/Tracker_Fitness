"""Build display / analysis data from natively-logged gym workouts.

Returns dicts in the SAME shape as app.hevy.get_workout_display_data so native
sessions plug straight into the Entrenos timeline and the Data analysis tab —
but with accurate muscle groups (taken from the logged exercise, not inferred
from a title).
"""


def build_native_sessions(db, user_id):
    """Return a list of display dicts for a user's native workout sessions,
    newest first. One efficient pass (no N+1)."""
    from app.database import WorkoutSession, WorkoutExercise, WorkoutSet

    sessions = (
        db.query(WorkoutSession)
        .filter(WorkoutSession.user_id == user_id)
        .order_by(WorkoutSession.date.desc(), WorkoutSession.id.desc())
        .all()
    )
    if not sessions:
        return []

    session_ids = [s.id for s in sessions]
    wex = (
        db.query(WorkoutExercise)
        .filter(WorkoutExercise.session_id.in_(session_ids))
        .order_by(WorkoutExercise.order, WorkoutExercise.id)
        .all()
    )
    wex_ids = [w.id for w in wex]
    sets = []
    if wex_ids:
        sets = (
            db.query(WorkoutSet)
            .filter(WorkoutSet.workout_exercise_id.in_(wex_ids))
            .order_by(WorkoutSet.set_index)
            .all()
        )

    sets_by_wex = {}
    for st in sets:
        sets_by_wex.setdefault(st.workout_exercise_id, []).append(st)
    wex_by_session = {}
    for w in wex:
        wex_by_session.setdefault(w.session_id, []).append(w)

    months_es = ["ene", "feb", "mar", "abr", "may", "jun",
                 "jul", "ago", "sep", "oct", "nov", "dic"]

    out = []
    for s in sessions:
        exercises = []
        total_volume = 0.0
        muscle_volume = {}
        muscle_sets = {}
        for w in wex_by_session.get(s.id, []):
            wsets = sets_by_wex.get(w.id, [])
            working = [x for x in wsets if (x.type or "normal") != "warmup"]
            ex_volume = 0.0
            max_w = 0.0
            total_reps = 0
            for x in working:
                wt = x.weight_kg or 0
                rp = x.reps or 0
                ex_volume += wt * rp
                total_reps += rp
                if wt > max_w:
                    max_w = wt
            total_volume += ex_volume
            muscle = w.muscle or "Otro"
            muscle_volume[muscle] = muscle_volume.get(muscle, 0.0) + ex_volume
            muscle_sets[muscle] = muscle_sets.get(muscle, 0) + len(working)
            exercises.append({
                "name": w.name,
                "muscle": muscle,
                "max_weight": round(max_w, 1),
                "sets": len(working),
                "reps": total_reps,
                "volume": round(ex_volume, 1),
            })

        out.append({
            "id": s.id,
            "source": "app",
            "date": s.date.isoformat(),
            "sort_date": s.date.isoformat(),
            "date_label": f"{s.date.day} {months_es[s.date.month - 1]} {s.date.year}",
            "title": s.title or "Entreno de gym",
            "notes": s.notes,
            "duration_min": s.duration_min or 0,
            "duration_seconds": (s.duration_min or 0) * 60,
            "exercise_count": len(exercises),
            "total_volume_kg": round(total_volume, 1),
            "volume_kg": round(total_volume, 1),
            "calories": 0,
            "muscle_volume": {k: round(v, 1) for k, v in muscle_volume.items()},
            "muscle_sets": muscle_sets,
            "exercises": exercises,
        })
    return out
