from fastapi import FastAPI, Request, Depends, Form, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date, timedelta, datetime
import os
import base64
import json

from app.database import get_db, init_db, FoodEntry, UserProfile, DayScore, ChatMessage, BodyMeasurement, ManualWorkout, StravaToken
from app.food_data import search_foods, get_food, FOOD_DATABASE
from app.hevy import fetch_recent_workouts, format_workout_summary, get_workout_display_data
from app.strava_api import get_auth_url, exchange_code, get_valid_token, fetch_activities, format_activity


def calculate_score(cal_pct: float, protein_pct: float, wellbeing: str) -> int:
    """Calcula puntaje 1-5 según cumplimiento de objetivos y bienestar."""
    # Base por calorías
    if cal_pct > 130:
        base = 1
    elif cal_pct > 115:
        base = 2
    elif cal_pct > 105 or cal_pct < 70:
        base = 3
    elif cal_pct > 100 or cal_pct < 80:
        base = 4
    else:  # 80-100% → zona ideal de déficit
        base = 5

    # Ajuste por proteínas
    if protein_pct < 70:
        base -= 1
    elif protein_pct < 85:
        base -= 0

    # Ajuste por bienestar
    if wellbeing == "overate":
        base -= 1
    elif wellbeing == "good":
        base += 0.5

    return max(1, min(5, round(base)))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

app = FastAPI(title="Fitness Tracker")
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")


@app.get("/manifest.json")
def manifest():
    import json
    with open(os.path.join(BASE_DIR, "static", "manifest.json")) as f:
        return JSONResponse(content=json.load(f))


@app.on_event("startup")
def on_startup():
    init_db()


# ─── API ────────────────────────────────────────────────────────────────────

@app.get("/api/search")
def api_search(q: str = ""):
    results = search_foods(q)
    return JSONResponse(content=results)


@app.get("/api/food/{name}")
def api_food(name: str):
    data = get_food(name)
    if not data:
        raise HTTPException(status_code=404, detail="Alimento no encontrado")
    return JSONResponse(content=data)


# ─── Dashboard ──────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    today = date.today()
    profile = db.query(UserProfile).first()

    entries = db.query(FoodEntry).filter(FoodEntry.date == today).all()

    totals = {"calories": 0.0, "protein": 0.0, "carbs": 0.0, "fat": 0.0}
    meals: dict[str, list] = {"Desayuno": [], "Almuerzo": [], "Cena": [], "Merienda/Snack": []}
    meal_map = {
        "breakfast": "Desayuno",
        "lunch": "Almuerzo",
        "dinner": "Cena",
        "snack": "Merienda/Snack",
    }

    for e in entries:
        totals["calories"] += e.calories
        totals["protein"] += e.protein
        totals["carbs"] += e.carbs
        totals["fat"] += e.fat
        meal_label = meal_map.get(e.meal_type, e.meal_type)
        meals[meal_label].append(e)

    # Round totals
    totals = {k: round(v, 1) for k, v in totals.items()}

    # Progress percentages (capped display at 110%)
    def pct(consumed, target):
        if target == 0:
            return 0
        return min(round((consumed / target) * 100, 1), 110)

    progress = {
        "calories": pct(totals["calories"], profile.target_calories),
        "protein": pct(totals["protein"], profile.target_protein),
        "carbs": pct(totals["carbs"], profile.target_carbs),
        "fat": pct(totals["fat"], profile.target_fat),
    }

    days_es = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    months_es = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
                 "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
    today_str = f"{days_es[today.weekday()]}, {today.day} de {months_es[today.month - 1]} de {today.year}"

    # Score for today
    today_score = db.query(DayScore).filter(DayScore.date == today).first()

    # Weekly score (last 7 days)
    week_start = today - timedelta(days=6)
    week_scores = db.query(DayScore).filter(DayScore.date >= week_start).all()
    weekly_total = sum(s.score for s in week_scores)
    weekly_goal = 30  # 7 days × ~4.3 average

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "profile": profile,
        "totals": totals,
        "progress": progress,
        "meals": meals,
        "today_str": today_str,
        "today": today,
        "today_score": today_score,
        "weekly_total": weekly_total,
        "weekly_goal": weekly_goal,
        "scored_days": len(week_scores),
    })


# ─── Food Log ───────────────────────────────────────────────────────────────

@app.get("/log", response_class=HTMLResponse)
def log_page(request: Request, db: Session = Depends(get_db)):
    profile = db.query(UserProfile).first()
    food_names = sorted(FOOD_DATABASE.keys())
    return templates.TemplateResponse("log.html", {
        "request": request,
        "profile": profile,
        "food_names": food_names,
    })


@app.post("/api/analyze-food")
async def analyze_food(
    description: str = Form(""),
    file: UploadFile = File(None),
):
    """Analiza descripción de texto o imagen de comida con Claude y devuelve macros estimados."""
    import anthropic as _anthropic
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY no configurada")

    client = _anthropic.Anthropic(api_key=api_key)

    system = """Sos un nutricionista experto. Analizás platos de comida y estimás sus macronutrientes.
Devolvé SOLO un JSON con estas claves exactas (sin texto extra, solo el JSON):
{
  "nombre": "nombre descriptivo del plato",
  "cantidad_g": número (porción estimada en gramos),
  "calorias": número (kcal por la porción),
  "proteinas": número (gramos por la porción),
  "carbohidratos": número (gramos por la porción),
  "grasas": número (gramos por la porción),
  "confianza": "alta" | "media" | "baja",
  "nota": "breve aclaración si es necesaria"
}
Sé conservador y realista. Si hay ingredientes inciertos, asumí preparación casera estándar argentina."""

    if file and file.filename:
        contents = await file.read()
        img_b64 = base64.b64encode(contents).decode()
        media_type = file.content_type or "image/jpeg"
        messages = [{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": img_b64}},
                {"type": "text", "text": f"Analizá este plato y estimá los macronutrientes.{' Contexto adicional: ' + description if description else ''}"}
            ]
        }]
    else:
        messages = [{"role": "user", "content": f"Analizá este plato y estimá los macronutrientes: {description}"}]

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            system=system,
            messages=messages,
        )
        raw = response.content[0].text.strip()
        # Extraer JSON si viene con texto extra
        start = raw.find("{")
        end = raw.rfind("}") + 1
        data = json.loads(raw[start:end])
        return JSONResponse(content=data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al analizar: {str(e)}")


@app.post("/log")
def add_food(
    request: Request,
    db: Session = Depends(get_db),
    meal_type: str = Form(...),
    entry_mode: str = Form("search"),
    food_name: str = Form(""),
    quantity_g: float = Form(...),
    manual_name: str = Form(""),
    manual_calories: float = Form(0),
    manual_protein: float = Form(0),
    manual_carbs: float = Form(0),
    manual_fat: float = Form(0),
):
    today = date.today()

    if entry_mode == "search" and food_name:
        data = get_food(food_name)
        if not data:
            raise HTTPException(status_code=400, detail="Alimento no encontrado")
        factor = quantity_g / 100.0
        entry = FoodEntry(
            date=today,
            meal_type=meal_type,
            food_name=food_name,
            quantity_g=quantity_g,
            calories=round(data["calories"] * factor, 1),
            protein=round(data["protein"] * factor, 1),
            carbs=round(data["carbs"] * factor, 1),
            fat=round(data["fat"] * factor, 1),
        )
    else:
        # Manual entry
        factor = quantity_g / 100.0
        entry = FoodEntry(
            date=today,
            meal_type=meal_type,
            food_name=manual_name or "Alimento personalizado",
            quantity_g=quantity_g,
            calories=round(manual_calories * factor, 1),
            protein=round(manual_protein * factor, 1),
            carbs=round(manual_carbs * factor, 1),
            fat=round(manual_fat * factor, 1),
        )

    db.add(entry)
    db.commit()
    return RedirectResponse(url="/", status_code=303)


@app.delete("/log/{entry_id}")
def delete_entry(entry_id: int, db: Session = Depends(get_db)):
    entry = db.query(FoodEntry).filter(FoodEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Entrada no encontrada")
    db.delete(entry)
    db.commit()
    return JSONResponse(content={"success": True})


# ─── History ────────────────────────────────────────────────────────────────

@app.get("/history", response_class=HTMLResponse)
def history(request: Request, db: Session = Depends(get_db)):
    profile = db.query(UserProfile).first()
    today = date.today()

    days_data = []
    days_es = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
    months_es = ["ene", "feb", "mar", "abr", "may", "jun",
                 "jul", "ago", "sep", "oct", "nov", "dic"]

    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        entries = db.query(FoodEntry).filter(FoodEntry.date == day).all()
        cals = round(sum(e.calories for e in entries), 1)
        protein = round(sum(e.protein for e in entries), 1)
        carbs = round(sum(e.carbs for e in entries), 1)
        fat = round(sum(e.fat for e in entries), 1)

        score_obj = db.query(DayScore).filter(DayScore.date == day).first()
        label = f"{days_es[day.weekday()]} {day.day}/{months_es[day.month - 1]}"
        days_data.append({
            "date": day,
            "label": label,
            "is_today": day == today,
            "calories": cals,
            "protein": protein,
            "carbs": carbs,
            "fat": fat,
            "cal_pct": min(round((cals / profile.target_calories) * 100), 150) if cals else 0,
            "protein_pct": min(round((protein / profile.target_protein) * 100), 150) if protein else 0,
            "score": score_obj.score if score_obj else None,
            "score_notes": score_obj.notes if score_obj else "",
        })

    chart_labels = [d["label"] for d in days_data]
    chart_calories = [d["calories"] for d in days_data]
    chart_protein = [d["protein"] for d in days_data]

    return templates.TemplateResponse("history.html", {
        "request": request,
        "profile": profile,
        "days_data": days_data,
        "chart_labels": chart_labels,
        "chart_calories": chart_calories,
        "chart_protein": chart_protein,
    })


# ─── Score ──────────────────────────────────────────────────────────────────

@app.post("/score")
def save_score(
    db: Session = Depends(get_db),
    wellbeing: str = Form("good"),
    notes: str = Form(""),
    score_date: str = Form(""),
):
    target_date = date.fromisoformat(score_date) if score_date else date.today()
    profile = db.query(UserProfile).first()

    # Calcular % cumplimiento del día
    entries = db.query(FoodEntry).filter(FoodEntry.date == target_date).all()
    total_cal = sum(e.calories for e in entries)
    total_protein = sum(e.protein for e in entries)
    cal_pct = round((total_cal / profile.target_calories) * 100, 1) if profile.target_calories else 0
    protein_pct = round((total_protein / profile.target_protein) * 100, 1) if profile.target_protein else 0

    score = calculate_score(cal_pct, protein_pct, wellbeing)

    existing = db.query(DayScore).filter(DayScore.date == target_date).first()
    if existing:
        existing.score = score
        existing.cal_pct = cal_pct
        existing.protein_pct = protein_pct
        existing.wellbeing = wellbeing
        existing.notes = notes
    else:
        db.add(DayScore(date=target_date, score=score, cal_pct=cal_pct,
                        protein_pct=protein_pct, wellbeing=wellbeing, notes=notes))
    db.commit()
    return RedirectResponse(url="/", status_code=303)


@app.get("/api/score/preview")
def api_score_preview(db: Session = Depends(get_db), wellbeing: str = "good"):
    today = date.today()
    profile = db.query(UserProfile).first()
    entries = db.query(FoodEntry).filter(FoodEntry.date == today).all()
    total_cal = sum(e.calories for e in entries)
    total_protein = sum(e.protein for e in entries)
    cal_pct = round((total_cal / profile.target_calories) * 100, 1) if profile.target_calories else 0
    protein_pct = round((total_protein / profile.target_protein) * 100, 1) if profile.target_protein else 0
    score = calculate_score(cal_pct, protein_pct, wellbeing)
    return JSONResponse(content={"score": score, "cal_pct": cal_pct, "protein_pct": protein_pct})


@app.get("/api/scores/week")
def api_week_scores(db: Session = Depends(get_db)):
    today = date.today()
    week_start = today - timedelta(days=6)
    scores = db.query(DayScore).filter(DayScore.date >= week_start).all()
    return JSONResponse(content={str(s.date): s.score for s in scores})


# ─── Reminders ──────────────────────────────────────────────────────────────

@app.get("/reminders", response_class=HTMLResponse)
def reminders_page(request: Request, db: Session = Depends(get_db)):
    profile = db.query(UserProfile).first()
    return templates.TemplateResponse("reminders.html", {
        "request": request,
        "profile": profile,
    })


# ─── Profile ────────────────────────────────────────────────────────────────

# ─── Coach ──────────────────────────────────────────────────────────────────

@app.get("/coach", response_class=HTMLResponse)
def coach_page(request: Request, db: Session = Depends(get_db)):
    profile = db.query(UserProfile).first()

    # Last 20 chat messages
    messages = (
        db.query(ChatMessage)
        .order_by(ChatMessage.created_at.asc())
        .limit(20)
        .all()
    )

    # Recent workouts from Hevy
    hevy_error = None
    recent_workouts_display = []
    hevy_key = os.environ.get("HEVY_API_KEY", "")
    if hevy_key:
        try:
            raw = fetch_recent_workouts(pages=1)
            recent_workouts_display = [get_workout_display_data(w) for w in raw[:5]]
        except Exception as e:
            hevy_error = str(e)
    else:
        hevy_error = "HEVY_API_KEY no configurada"

    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")

    return templates.TemplateResponse("coach.html", {
        "request": request,
        "profile": profile,
        "messages": messages,
        "recent_workouts": recent_workouts_display,
        "hevy_error": hevy_error,
        "anthropic_configured": bool(anthropic_key),
    })


@app.post("/coach/chat")
async def coach_chat(
    request: Request,
    db: Session = Depends(get_db),
    message: str = Form(...),
):
    import anthropic as anthropic_sdk

    profile = db.query(UserProfile).first()
    user_message = message.strip()
    if not user_message:
        return RedirectResponse(url="/coach", status_code=303)

    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not anthropic_key:
        # Save user message anyway, return error as assistant
        db.add(ChatMessage(role="user", content=user_message))
        db.add(ChatMessage(
            role="assistant",
            content="Error: ANTHROPIC_API_KEY no está configurada. Configurá la variable de entorno para usar el coach.",
        ))
        db.commit()
        return RedirectResponse(url="/coach", status_code=303)

    # Save user message
    db.add(ChatMessage(role="user", content=user_message))
    db.commit()

    # Today's nutrition
    today = date.today()
    today_entries = db.query(FoodEntry).filter(FoodEntry.date == today).all()
    today_calories = sum(e.calories for e in today_entries)
    today_protein = sum(e.protein for e in today_entries)

    # Recent workouts for context
    workout_summaries = []
    try:
        raw_workouts = fetch_recent_workouts(pages=2)
        workout_summaries = [format_workout_summary(w) for w in raw_workouts[:10]]
    except Exception:
        pass

    # Recent manual workouts for context
    manual_workouts = db.query(ManualWorkout).order_by(ManualWorkout.date.desc()).limit(10).all()
    manual_summaries = [
        f"[{mw.date}] {mw.activity_type}{' (' + mw.custom_type + ')' if mw.custom_type else ''} ({mw.duration_min or '?'}min, {mw.intensity or 'sin intensidad'}, {mw.calories_burned or '?'} kcal)"
        for mw in manual_workouts
    ]

    system = f"""Sos un coach deportivo y nutricional personalizado.
Trabajás con un atleta con este perfil:
- Nombre: {profile.name}, {profile.age} años, {profile.weight_kg}kg, {profile.height_cm}cm
- Objetivo: {profile.goal}
- Nivel de actividad: {profile.activity_level}
- Objetivos diarios: {profile.target_calories} kcal, {profile.target_protein}g proteína, {profile.target_carbs}g carbs, {profile.target_fat}g grasa

Actividades recientes (Hevy - gimnasio):
{chr(10).join(workout_summaries) if workout_summaries else 'Sin datos de Hevy disponibles'}

Actividades recientes (manual - fútbol, MMA, cardio, etc.):
{chr(10).join(manual_summaries) if manual_summaries else 'Sin actividades manuales registradas'}

Nutrición de hoy: {today_calories:.0f} kcal / {profile.target_calories} kcal, proteína: {today_protein:.0f}g / {profile.target_protein}g

Respondé siempre en español. Sé directo, práctico y conciso. No más de 3-4 párrafos por respuesta.
Podés sugerir ajustes de nutrición, planificar entrenamientos, recomendar cargas, recetas, o responder dudas."""

    # Build message history (last 10 for context)
    history = (
        db.query(ChatMessage)
        .order_by(ChatMessage.created_at.desc())
        .limit(11)
        .all()
    )
    history.reverse()
    # Exclude the very last one (user msg we just saved) - it's already in history
    api_messages = [{"role": m.role, "content": m.content} for m in history]

    try:
        client = anthropic_sdk.Anthropic(api_key=anthropic_key)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            system=system,
            messages=api_messages,
        )
        assistant_reply = response.content[0].text
    except Exception as e:
        assistant_reply = f"Error al contactar al coach: {str(e)}"

    db.add(ChatMessage(role="assistant", content=assistant_reply))
    db.commit()

    return RedirectResponse(url="/coach", status_code=303)


@app.post("/coach/clear")
def coach_clear(db: Session = Depends(get_db)):
    db.query(ChatMessage).delete()
    db.commit()
    return RedirectResponse(url="/coach", status_code=303)


@app.get("/api/workouts/recent")
def api_recent_workouts():
    hevy_key = os.environ.get("HEVY_API_KEY", "")
    if not hevy_key:
        return JSONResponse(content={"error": "HEVY_API_KEY no configurada", "workouts": []})
    try:
        raw = fetch_recent_workouts(pages=1)
        workouts = [get_workout_display_data(w) for w in raw[:10]]
        return JSONResponse(content={"workouts": workouts})
    except Exception as e:
        return JSONResponse(content={"error": str(e), "workouts": []})


@app.get("/profile", response_class=HTMLResponse)
def profile_page(request: Request, db: Session = Depends(get_db)):
    profile = db.query(UserProfile).first()
    # Calculate BMI
    height_m = profile.height_cm / 100
    bmi = round(profile.weight_kg / (height_m ** 2), 1)
    # Calculate BMR (Mifflin-St Jeor)
    bmr = round(10 * profile.weight_kg + 6.25 * profile.height_cm - 5 * profile.age + 5)
    tdee = round(bmr * 1.9)  # Very active multiplier

    return templates.TemplateResponse("profile.html", {
        "request": request,
        "profile": profile,
        "bmi": bmi,
        "bmr": bmr,
        "tdee": tdee,
    })


# ─── Body Measurements ──────────────────────────────────────────────────────

_MEASUREMENT_FLOAT_FIELDS = [
    "peso_kg", "agua_corporal_l", "proteinas_kg", "minerales_kg",
    "masa_grasa_corporal_kg", "masa_musculoesqueletica_kg", "imc", "pgc",
    "magro_brazo_derecho_kg", "magro_brazo_izquierdo_kg", "magro_tronco_kg",
    "magro_pierna_derecha_kg", "magro_pierna_izquierda_kg",
    "grasa_brazo_derecho_kg", "grasa_brazo_izquierdo_kg", "grasa_tronco_kg",
    "grasa_pierna_derecha_kg", "grasa_pierna_izquierda_kg",
    "control_peso_kg", "control_grasa_kg", "control_musculo_kg",
    "relacion_cintura_cadera",
    "pliegue_triceps_mm", "pliegue_subescapular_mm", "pliegue_suprailiaco_mm",
    "pliegue_abdominal_mm", "pliegue_muslo_mm",
]
_MEASUREMENT_INT_FIELDS = ["nivel_grasa_visceral", "puntuacion_inbody"]


def _parse_optional_float(v: str):
    try:
        return float(v) if v and v.strip() else None
    except (ValueError, TypeError):
        return None


def _parse_optional_int(v: str):
    try:
        return int(v) if v and v.strip() else None
    except (ValueError, TypeError):
        return None


@app.get("/measurements", response_class=HTMLResponse)
def measurements_page(request: Request, db: Session = Depends(get_db)):
    profile = db.query(UserProfile).first()
    measurements = (
        db.query(BodyMeasurement)
        .order_by(BodyMeasurement.fecha_medicion.desc())
        .all()
    )
    return templates.TemplateResponse("measurements.html", {
        "request": request,
        "profile": profile,
        "measurements": measurements,
        "now": datetime.today,
    })


@app.post("/measurements")
async def save_measurement(
    request: Request,
    db: Session = Depends(get_db),
):
    form = await request.form()

    fecha_str = form.get("fecha_medicion", "")
    if not fecha_str:
        raise HTTPException(status_code=400, detail="fecha_medicion es requerida")
    fecha = date.fromisoformat(fecha_str)

    kwargs = {"fecha_medicion": fecha, "notas": form.get("notas", "") or None}
    for field in _MEASUREMENT_FLOAT_FIELDS:
        kwargs[field] = _parse_optional_float(form.get(field, ""))
    for field in _MEASUREMENT_INT_FIELDS:
        kwargs[field] = _parse_optional_int(form.get(field, ""))

    m = BodyMeasurement(**kwargs)
    db.add(m)
    db.commit()
    return RedirectResponse(url="/measurements", status_code=303)


@app.get("/measurements/{measurement_id}", response_class=HTMLResponse)
def measurement_detail(measurement_id: int, request: Request, db: Session = Depends(get_db)):
    profile = db.query(UserProfile).first()
    m = db.query(BodyMeasurement).filter(BodyMeasurement.id == measurement_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Medición no encontrada")
    return templates.TemplateResponse("measurement_detail.html", {
        "request": request,
        "profile": profile,
        "m": m,
    })


@app.delete("/measurements/{measurement_id}")
def delete_measurement(measurement_id: int, db: Session = Depends(get_db)):
    m = db.query(BodyMeasurement).filter(BodyMeasurement.id == measurement_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Medición no encontrada")
    db.delete(m)
    db.commit()
    return JSONResponse(content={"success": True})


STRAVA_REDIRECT_URI = "https://trackerfitness-production.up.railway.app/strava/callback"


@app.get("/strava/connect")
def strava_connect():
    url = get_auth_url(STRAVA_REDIRECT_URI)
    return RedirectResponse(url=url)


@app.get("/strava/callback")
def strava_callback(
    code: str = "",
    error: str = "",
    db: Session = Depends(get_db),
):
    if error or not code:
        return RedirectResponse(url="/workouts?strava_error=denied", status_code=303)
    try:
        data = exchange_code(code, STRAVA_REDIRECT_URI)
        athlete_id = data.get("athlete", {}).get("id", 0)
        existing = db.query(StravaToken).first()
        if existing:
            existing.athlete_id = athlete_id
            existing.access_token = data["access_token"]
            existing.refresh_token = data["refresh_token"]
            existing.expires_at = data["expires_at"]
        else:
            db.add(StravaToken(
                athlete_id=athlete_id,
                access_token=data["access_token"],
                refresh_token=data["refresh_token"],
                expires_at=data["expires_at"],
            ))
        db.commit()
        return RedirectResponse(url="/workouts?strava_connected=1", status_code=303)
    except Exception as e:
        return RedirectResponse(url=f"/workouts?strava_error=1", status_code=303)


@app.post("/strava/disconnect")
def strava_disconnect(db: Session = Depends(get_db)):
    db.query(StravaToken).delete()
    db.commit()
    return RedirectResponse(url="/workouts", status_code=303)


@app.get("/workouts", response_class=HTMLResponse)
def workouts_page(request: Request, db: Session = Depends(get_db)):
    profile = db.query(UserProfile).first()
    today = date.today()
    week_start = today - timedelta(days=today.weekday())  # Monday of current week

    # Hevy workouts
    hevy_workouts = []
    hevy_error = None
    hevy_key = os.environ.get("HEVY_API_KEY", "")
    if hevy_key:
        try:
            raw = fetch_recent_workouts(pages=3)
            hevy_workouts = [get_workout_display_data(w) for w in raw]
        except Exception as e:
            hevy_error = str(e)
    else:
        hevy_error = "HEVY_API_KEY no configurada. Solo se muestran actividades manuales."

    # Manual workouts
    manual_workouts = db.query(ManualWorkout).order_by(ManualWorkout.date.desc()).all()

    # Weekly stats (manual only for calories, both for sessions/minutes)
    week_manual = [mw for mw in manual_workouts if mw.date >= week_start]
    week_hevy = [hw for hw in hevy_workouts if hw.get("sort_date", "") >= str(week_start)]

    week_sessions = len(week_manual) + len(week_hevy)
    week_minutes = sum((mw.duration_min or 0) for mw in week_manual)
    for hw in week_hevy:
        dur = hw.get("duration_seconds", 0) or 0
        week_minutes += dur // 60
    week_kcal = sum((mw.calories_burned or 0) for mw in week_manual)

    # Strava workouts
    strava_workouts = []
    strava_error = None
    strava_connected = bool(db.query(StravaToken).first())
    if strava_connected:
        try:
            access_token = get_valid_token(db)
            if access_token:
                raw_strava = fetch_activities(access_token, per_page=30)
                strava_workouts = [format_activity(a) for a in raw_strava]
                # Add Strava calories to weekly kcal
                week_strava = [a for a in strava_workouts if a.get("sort_date", "") >= str(week_start)]
                week_kcal += sum((a.get("calories") or 0) for a in week_strava)
                week_sessions += len(week_strava)
                for a in week_strava:
                    week_minutes += (a.get("duration_seconds") or 0) // 60
            else:
                strava_error = "Token de Strava inválido. Volvé a conectar."
                strava_connected = False
        except Exception as e:
            strava_error = f"Error al cargar Strava: {str(e)}"

    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    strava_param = request.query_params.get("strava_connected")
    strava_err_param = request.query_params.get("strava_error")

    return templates.TemplateResponse("workouts.html", {
        "request": request,
        "profile": profile,
        "hevy_workouts": hevy_workouts,
        "manual_workouts": manual_workouts,
        "strava_workouts": strava_workouts,
        "strava_connected": strava_connected,
        "strava_error": strava_error,
        "hevy_error": hevy_error,
        "week_sessions": week_sessions,
        "week_minutes": week_minutes,
        "week_kcal": week_kcal,
        "today": today,
        "anthropic_configured": bool(anthropic_key),
        "flash_strava_connected": strava_param == "1",
        "flash_strava_error": strava_err_param,
    })


@app.post("/workouts")
async def save_manual_workout(
    request: Request,
    db: Session = Depends(get_db),
    workout_date: str = Form(...),
    activity_type: str = Form(...),
    custom_type: str = Form(""),
    duration_min: str = Form(""),
    intensity: str = Form(""),
    calories_burned: str = Form(""),
    calories_source: str = Form("manual"),
    heart_rate_avg: str = Form(""),
    distance_km: str = Form(""),
    notes: str = Form(""),
):
    def opt_int(v):
        try:
            return int(v) if v and v.strip() else None
        except (ValueError, TypeError):
            return None

    def opt_float(v):
        try:
            return float(v) if v and v.strip() else None
        except (ValueError, TypeError):
            return None

    workout = ManualWorkout(
        date=date.fromisoformat(workout_date),
        activity_type=activity_type,
        custom_type=custom_type.strip() or None,
        duration_min=opt_int(duration_min),
        intensity=intensity or None,
        calories_burned=opt_int(calories_burned),
        calories_source=calories_source if calories_burned else None,
        heart_rate_avg=opt_int(heart_rate_avg),
        distance_km=opt_float(distance_km),
        notes=notes.strip() or None,
    )
    db.add(workout)
    db.commit()
    return RedirectResponse(url="/workouts", status_code=303)


@app.delete("/workouts/{workout_id}")
def delete_manual_workout(workout_id: int, db: Session = Depends(get_db)):
    workout = db.query(ManualWorkout).filter(ManualWorkout.id == workout_id).first()
    if not workout:
        raise HTTPException(status_code=404, detail="Actividad no encontrada")
    db.delete(workout)
    db.commit()
    return JSONResponse(content={"success": True})


@app.post("/api/workouts/estimate-calories")
async def estimate_calories(
    activity_type: str = Form(...),
    duration_min: str = Form(""),
    intensity: str = Form(""),
    notes: str = Form(""),
):
    import anthropic as _anthropic
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY no configurada")

    client = _anthropic.Anthropic(api_key=api_key)

    system = """Sos un experto en fisiología del ejercicio. Estimá las calorías quemadas para un hombre de 26 años, 109kg, 1.84m, muy activo deportivamente. Devolvé SOLO un JSON: {"calories": número_entero, "explanation": "una línea explicando el cálculo"}. Sé conservador y realista."""

    user_msg = f"Actividad: {activity_type}, Duración: {duration_min} minutos, Intensidad: {intensity}. {notes if notes else ''}"

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            system=system,
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = response.content[0].text.strip()
        start = raw.find("{")
        end = raw.rfind("}") + 1
        data = json.loads(raw[start:end])
        return JSONResponse(content=data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al estimar: {str(e)}")


@app.get("/api/workouts/all")
def api_all_workouts(db: Session = Depends(get_db)):
    today = date.today()
    manual_workouts = db.query(ManualWorkout).order_by(ManualWorkout.date.desc()).limit(30).all()
    manual_list = [
        {
            "source": "manual",
            "id": mw.id,
            "date": str(mw.date),
            "activity_type": mw.activity_type,
            "custom_type": mw.custom_type,
            "duration_min": mw.duration_min,
            "intensity": mw.intensity,
            "calories_burned": mw.calories_burned,
            "heart_rate_avg": mw.heart_rate_avg,
            "distance_km": mw.distance_km,
            "notes": mw.notes,
        }
        for mw in manual_workouts
    ]

    hevy_list = []
    hevy_key = os.environ.get("HEVY_API_KEY", "")
    if hevy_key:
        try:
            raw = fetch_recent_workouts(pages=2)
            hevy_list = [{"source": "hevy", **get_workout_display_data(w)} for w in raw[:30]]
        except Exception:
            pass

    all_workouts = (manual_list + hevy_list)
    all_workouts.sort(key=lambda x: x.get("date", x.get("start_time", "")), reverse=True)
    return JSONResponse(content={"workouts": all_workouts[:30]})


@app.post("/measurements/import")
async def import_measurement(file: UploadFile = File(...)):
    import anthropic as anthropic_sdk

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return JSONResponse(status_code=400, content={"error": "ANTHROPIC_API_KEY no configurada"})

    contents = await file.read()
    b64 = base64.standard_b64encode(contents).decode("utf-8")

    media_type = file.content_type or "image/jpeg"
    if media_type not in ("image/jpeg", "image/png", "image/gif", "image/webp"):
        media_type = "image/jpeg"

    prompt = (
        "Este es un resultado de InBody. "
        "Extraé los valores numéricos y devolvé SOLO un JSON con estas claves exactas "
        "(usa null si no encontrás el valor): "
        "peso_kg, agua_corporal_l, proteinas_kg, minerales_kg, masa_grasa_corporal_kg, "
        "masa_musculoesqueletica_kg, imc, pgc, "
        "magro_brazo_derecho_kg, magro_brazo_izquierdo_kg, magro_tronco_kg, "
        "magro_pierna_derecha_kg, magro_pierna_izquierda_kg, "
        "grasa_brazo_derecho_kg, grasa_brazo_izquierdo_kg, grasa_tronco_kg, "
        "grasa_pierna_derecha_kg, grasa_pierna_izquierda_kg, "
        "control_peso_kg, control_grasa_kg, control_musculo_kg, "
        "relacion_cintura_cadera, nivel_grasa_visceral, puntuacion_inbody"
    )

    try:
        client = anthropic_sdk.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": b64,
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        raw_text = response.content[0].text
        # Extract JSON from the response
        start = raw_text.find("{")
        end = raw_text.rfind("}") + 1
        if start == -1 or end == 0:
            return JSONResponse(status_code=422, content={"error": "No se pudo extraer JSON de la respuesta", "raw": raw_text})
        data = json.loads(raw_text[start:end])
        return JSONResponse(content={"success": True, "data": data})
    except json.JSONDecodeError as e:
        return JSONResponse(status_code=422, content={"error": f"JSON inválido: {e}", "raw": raw_text})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
