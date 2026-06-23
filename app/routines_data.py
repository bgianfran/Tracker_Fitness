"""Folders / routines helpers and folder-progression builder for the AI coach."""
from collections import defaultdict


def build_routines_context(db, user_id):
    """Return folders (each with their routines) + routines without a folder,
    plus how many logged sessions each folder has (to gate the AI button)."""
    from app.database import Folder, Routine, RoutineExercise, WorkoutSession

    folders = db.query(Folder).filter(Folder.user_id == user_id).order_by(Folder.created_at).all()
    routines = db.query(Routine).filter(Routine.user_id == user_id).order_by(Routine.created_at).all()
    rids = [r.id for r in routines]
    rexs = []
    if rids:
        rexs = (db.query(RoutineExercise)
                .filter(RoutineExercise.routine_id.in_(rids))
                .order_by(RoutineExercise.order, RoutineExercise.id).all())
    ex_by_routine = defaultdict(list)
    for rx in rexs:
        ex_by_routine[rx.routine_id].append({
            "name": rx.name, "muscle": rx.muscle,
            "target_sets": rx.target_sets, "target_reps": rx.target_reps,
        })

    # sessions logged per folder
    sess = (db.query(WorkoutSession.folder_id)
            .filter(WorkoutSession.user_id == user_id).all())
    sess_count = defaultdict(int)
    for (fid,) in sess:
        if fid is not None:
            sess_count[fid] += 1

    def routine_dict(r):
        exs = ex_by_routine.get(r.id, [])
        return {"id": r.id, "name": r.name, "notes": r.notes,
                "exercises": exs, "exercise_count": len(exs)}

    folder_list = [{
        "id": f.id, "name": f.name,
        "routines": [routine_dict(r) for r in routines if r.folder_id == f.id],
        "session_count": sess_count.get(f.id, 0),
    } for f in folders]
    loose = [routine_dict(r) for r in routines if not r.folder_id]
    return {"folders": folder_list, "loose_routines": loose}


def get_routine_prefill(db, user_id, routine_id):
    """Exercises (with target sets) to pre-fill the workout builder from a routine.
    Returns (prefill_list, folder_id) or (None, None) if not found/owned."""
    from app.database import Routine, RoutineExercise

    r = db.query(Routine).filter(Routine.id == routine_id, Routine.user_id == user_id).first()
    if not r:
        return None, None, None
    rexs = (db.query(RoutineExercise)
            .filter(RoutineExercise.routine_id == r.id)
            .order_by(RoutineExercise.order, RoutineExercise.id).all())
    prefill = [{
        "slug": rx.exercise_slug, "name": rx.name, "muscle": rx.muscle,
        "target_sets": rx.target_sets or 3, "target_reps": rx.target_reps or "",
    } for rx in rexs]
    return prefill, r.folder_id, r.name


def build_folder_progression(db, user_id, folder_id):
    """Aggregate every native session in a folder into a compact per-exercise
    progression payload for the AI coach. Returns (folder_name, payload) or
    (None, None) if the folder isn't found/owned."""
    from app.database import Folder, WorkoutSession, WorkoutExercise, WorkoutSet

    folder = db.query(Folder).filter(Folder.id == folder_id, Folder.user_id == user_id).first()
    if not folder:
        return None, None

    sessions = (db.query(WorkoutSession)
                .filter(WorkoutSession.user_id == user_id, WorkoutSession.folder_id == folder_id)
                .order_by(WorkoutSession.date).all())
    if not sessions:
        return folder.name, {"sesiones": 0, "ejercicios": []}

    sids = [s.id for s in sessions]
    wex = (db.query(WorkoutExercise)
           .filter(WorkoutExercise.session_id.in_(sids))
           .order_by(WorkoutExercise.order, WorkoutExercise.id).all())
    wex_ids = [w.id for w in wex]
    sets = []
    if wex_ids:
        sets = (db.query(WorkoutSet)
                .filter(WorkoutSet.workout_exercise_id.in_(wex_ids))
                .order_by(WorkoutSet.set_index).all())
    sets_by_wex = defaultdict(list)
    for st in sets:
        sets_by_wex[st.workout_exercise_id].append(st)
    date_by_session = {s.id: s.date.isoformat() for s in sessions}

    # exercise name -> list of {date, top_weight, top_reps, volume, sets}
    progression = defaultdict(list)
    muscle_by_ex = {}
    for w in wex:
        wsets = [x for x in sets_by_wex.get(w.id, []) if (x.type or "normal") != "warmup"]
        if not wsets:
            continue
        top = max(wsets, key=lambda x: (x.weight_kg or 0, x.reps or 0))
        volume = sum((x.weight_kg or 0) * (x.reps or 0) for x in wsets)
        muscle_by_ex[w.name] = w.muscle or "Otro"
        progression[w.name].append({
            "fecha": date_by_session.get(w.session_id),
            "peso_top": round(top.weight_kg or 0, 1),
            "reps_top": top.reps or 0,
            "series": len(wsets),
            "volumen": round(volume, 1),
        })

    ejercicios = [{
        "ejercicio": name,
        "grupo": muscle_by_ex.get(name, "Otro"),
        "historial": hist,
    } for name, hist in progression.items()]

    payload = {
        "carpeta": folder.name,
        "sesiones": len(sessions),
        "rango": f"{sessions[0].date.isoformat()} a {sessions[-1].date.isoformat()}",
        "ejercicios": ejercicios,
    }
    return folder.name, payload
