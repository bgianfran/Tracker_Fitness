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

from app.database import (
    get_db, init_db,
    User, FoodEntry, UserProfile, DayScore, ChatMessage,
    BodyMeasurement, ManualWorkout, StravaToken,
)
from app.food_data import search_foods, get_food, FOOD_DATABASE
from app.openfoodfacts import search_openfoodfacts, get_by_barcode
from app.hevy import fetch_recent_workouts, format_workout_summary, get_workout_display_data
from app.strava_api import get_auth_url, exchange_code, get_valid_token, fetch_activities, format_activity
from app.auth import (
    hash_password, verify_password,
    create_session_token, decode_session_token,
    get_user_from_request,
)


def calculate_score(cal_pct: float, protein_pct: float, wellbeing: str) -> int:
    if cal_pct > 130:
        base = 1
    elif cal_pct > 115:
        base = 2
    elif cal_pct > 105 or cal_pct < 70:
        base = 3
    elif cal_pct > 100 or cal_pct < 80:
        base = 4
    else:
        base = 5
    if protein_pct < 70:
        base -= 1
    if wellbeing == "overate":
        base -= 1
    elif wellbeing == "good":
        base += 0.5
    return max(1, min(5, round(base)))


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

app = FastAPI(title="FitTracker")
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

STRAVA_REDIRECT_URI = "https://trackerfitness-production.up.railway.app/strava/callback"


@app.get("/manifest.json")
def manifest():
    with open(os.path.join(BASE_DIR, "static", "manifest.json")) as f:
        return JSONResponse(content=json.load(f))


@app.on_event("startup")
def on_startup():
    init_db()


# ─── Auth ───────────────────────────────────────────────────────────────────

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    # Already logged in → go to dashboard
    token = request.cookies.get("session")
    if token and decode_session_token(token):
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@app.post("/login")
def login(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Form(...),
    password: str = Form(...),
):
    user = db.query(User).filter(User.email == email.lower().strip()).first()
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Email o contraseña incorrectos",
        })
    token = create_session_token(user.id)
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie("session", token, httponly=True, max_age=60 * 60 * 24 * 30, samesite="lax")
    return response


@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    token = request.cookies.get("session")
    if token and decode_session_token(token):
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse("register.html", {"request": request, "error": None})


@app.post("/register")
def register(
    request: Request,
    db: Session = Depends(get_db),
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
):
    email = email.lower().strip()
    if password != password_confirm:
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": "Las contraseñas no coinciden",
        })
    if len(password) < 6:
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": "La contraseña debe tener al menos 6 caracteres",
        })
    if db.query(User).filter(User.email == email).first():
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": "Ya existe una cuenta con ese email",
        })
    user = User(
        email=email,
        name=name.strip(),
        password_hash=hash_password(password),
    )
    db.add(user)
    db.flush()
    # Create default profile for this user
    profile = UserProfile(
        user_id=user.id,
        name=name.strip(),
        age=25,
        weight_kg=75.0,
        height_cm=175.0,
        activity_level="Moderada (3-4x/semana)",
        goal="Mejorar composición corporal",
        target_calories=2500,
        target_protein=150,
        target_carbs=300,
        target_fat=80,
    )
    db.add(profile)
    db.commit()

    token = create_session_token(user.id)
    response = RedirectResponse(url="/profile?new=1", status_code=303)
    response.set_cookie("session", token, httponly=True, max_age=60 * 60 * 24 * 30, samesite="lax")
    return response


@app.post("/logout")
def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("session")
    return response


# ─── API ────────────────────────────────────────────────────────────────────

@app.get("/api/search")
def api_search(q: str = ""):
    return JSONResponse(content=search_foods(q))


@app.get("/api/food/{name}")
def api_food(name: str):
    data = get_food(name)
    if not data:
        raise HTTPException(status_code=404, detail="Alimento no encontrado")
    return JSONResponse(content=data)


@app.get("/api/search/off")
def api_search_off(q: str = ""):
    """Search Open Food Facts — called when local results are insufficient."""
    if len(q.strip()) < 2:
        return JSONResponse(content=[])
    results = search_openfoodfacts(q.strip(), limit=12)
    return JSONResponse(content=results)


@app.get("/api/food/barcode/{barcode}")
def api_food_barcode(barcode: str):
    data = get_by_barcode(barcode)
    if not data:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    return JSONResponse(content=data)


# ─── Dashboard ──────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    current_user, redirect = get_user_from_request(request, db)
    if redirect:
        return redirect

    today = date.today()
    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
    if not profile:
        return RedirectResponse(url="/profile?new=1", status_code=303)

    entries = db.query(FoodEntry).filter(
        FoodEntry.user_id == current_user.id,
        FoodEntry.date == today,
    ).all()

    totals = {"calories": 0.0, "protein": 0.0, "carbs": 0.0, "fat": 0.0}
    meals: dict[str, list] = {"Desayuno": [], "Almuerzo": [], "Cena": [], "Merienda/Snack": []}
    meal_map = {"breakfast": "Desayuno", "lunch": "Almuerzo", "dinner": "Cena", "snack": "Merienda/Snack"}

    for e in entries:
        totals["calories"] += e.calories
        totals["protein"] += e.protein
        totals["carbs"] += e.carbs
        totals["fat"] += e.fat
        meals[meal_map.get(e.meal_type, e.meal_type)].append(e)

    totals = {k: round(v, 1) for k, v in totals.items()}

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

    today_score = db.query(DayScore).filter(
        DayScore.user_id == current_user.id,
        DayScore.date == today,
    ).first()

    week_start = today - timedelta(days=6)
    week_scores = db.query(DayScore).filter(
        DayScore.user_id == current_user.id,
        DayScore.date >= week_start,
    ).all()
    weekly_total = sum(s.score for s in week_scores)

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "current_user": current_user,
        "profile": profile,
        "totals": totals,
        "progress": progress,
        "meals": meals,
        "today_str": today_str,
        "today": today,
        "today_score": today_score,
        "weekly_total": weekly_total,
        "weekly_goal": 30,
        "scored_days": len(week_scores),
    })


# ─── Food Log ───────────────────────────────────────────────────────────────

@app.get("/log", response_class=HTMLResponse)
def log_page(request: Request, db: Session = Depends(get_db)):
    current_user, redirect = get_user_from_request(request, db)
    if redirect:
        return redirect
    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
    return templates.TemplateResponse("log.html", {
        "request": request,
        "current_user": current_user,
        "profile": profile,
        "food_names": sorted(FOOD_DATABASE.keys()),
    })


@app.post("/api/analyze-food")
async def analyze_food(
    request: Request,
    db: Session = Depends(get_db),
    description: str = Form(""),
    file: UploadFile = File(None),
):
    current_user, redirect = get_user_from_request(request, db)
    if redirect:
        raise HTTPException(status_code=401, detail="No autenticado")

    import anthropic as _anthropic
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY no configurada")

    client = _anthropic.Anthropic(api_key=api_key)
    system = """Sos un nutricionista experto. Analizás platos de comida y estimás sus macronutrientes.
Devolvé SOLO un JSON con estas claves exactas (sin texto extra, solo el JSON):
{
  "nombre": "nombre descriptivo del plato",
  "cantidad_g": número,
  "calorias": número,
  "proteinas": número,
  "carbohidratos": número,
  "grasas": número,
  "confianza": "alta" | "media" | "baja",
  "nota": "breve aclaración si es necesaria"
}
Sé conservador y realista. Si hay ingredientes inciertos, asumí preparación casera estándar argentina."""

    if file and file.filename:
        contents = await file.read()
        img_b64 = base64.b64encode(contents).decode()
        media_type = file.content_type or "image/jpeg"
        messages = [{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": img_b64}},
            {"type": "text", "text": f"Analizá este plato.{' Contexto: ' + description if description else ''}"},
        ]}]
    else:
        messages = [{"role": "user", "content": f"Analizá este plato: {description}"}]

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            system=system,
            messages=messages,
        )
        raw = response.content[0].text.strip()
        start, end = raw.find("{"), raw.rfind("}") + 1
        return JSONResponse(content=json.loads(raw[start:end]))
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
    current_user, redirect = get_user_from_request(request, db)
    if redirect:
        return redirect

    today = date.today()
    factor = quantity_g / 100.0

    if entry_mode == "search" and food_name:
        data = get_food(food_name)
        if not data:
            raise HTTPException(status_code=400, detail="Alimento no encontrado")
        entry = FoodEntry(
            user_id=current_user.id,
            date=today, meal_type=meal_type, food_name=food_name,
            quantity_g=quantity_g,
            calories=round(data["calories"] * factor, 1),
            protein=round(data["protein"] * factor, 1),
            carbs=round(data["carbs"] * factor, 1),
            fat=round(data["fat"] * factor, 1),
        )
    else:
        entry = FoodEntry(
            user_id=current_user.id,
            date=today, meal_type=meal_type,
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
def delete_entry(entry_id: int, request: Request, db: Session = Depends(get_db)):
    current_user, _ = get_user_from_request(request, db)
    if not current_user:
        raise HTTPException(status_code=401)
    entry = db.query(FoodEntry).filter(
        FoodEntry.id == entry_id,
        FoodEntry.user_id == current_user.id,
    ).first()
    if not entry:
        raise HTTPException(status_code=404)
    db.delete(entry)
    db.commit()
    return JSONResponse(content={"success": True})


# ─── History ────────────────────────────────────────────────────────────────

@app.get("/history", response_class=HTMLResponse)
def history(request: Request, db: Session = Depends(get_db)):
    current_user, redirect = get_user_from_request(request, db)
    if redirect:
        return redirect

    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
    today = date.today()
    days_es = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
    months_es = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]

    days_data = []
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        entries = db.query(FoodEntry).filter(
            FoodEntry.user_id == current_user.id,
            FoodEntry.date == day,
        ).all()
        cals = round(sum(e.calories for e in entries), 1)
        protein = round(sum(e.protein for e in entries), 1)
        score_obj = db.query(DayScore).filter(
            DayScore.user_id == current_user.id,
            DayScore.date == day,
        ).first()
        days_data.append({
            "date": day,
            "label": f"{days_es[day.weekday()]} {day.day}/{months_es[day.month - 1]}",
            "is_today": day == today,
            "calories": cals,
            "protein": protein,
            "carbs": round(sum(e.carbs for e in entries), 1),
            "fat": round(sum(e.fat for e in entries), 1),
            "cal_pct": min(round((cals / profile.target_calories) * 100), 150) if cals and profile else 0,
            "protein_pct": min(round((protein / profile.target_protein) * 100), 150) if protein and profile else 0,
            "score": score_obj.score if score_obj else None,
            "score_notes": score_obj.notes if score_obj else "",
        })

    return templates.TemplateResponse("history.html", {
        "request": request,
        "current_user": current_user,
        "profile": profile,
        "days_data": days_data,
        "chart_labels": [d["label"] for d in days_data],
        "chart_calories": [d["calories"] for d in days_data],
        "chart_protein": [d["protein"] for d in days_data],
    })


# ─── Score ──────────────────────────────────────────────────────────────────

@app.post("/score")
def save_score(
    request: Request,
    db: Session = Depends(get_db),
    wellbeing: str = Form("good"),
    notes: str = Form(""),
    score_date: str = Form(""),
):
    current_user, redirect = get_user_from_request(request, db)
    if redirect:
        return redirect

    target_date = date.fromisoformat(score_date) if score_date else date.today()
    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
    entries = db.query(FoodEntry).filter(
        FoodEntry.user_id == current_user.id,
        FoodEntry.date == target_date,
    ).all()

    total_cal = sum(e.calories for e in entries)
    total_protein = sum(e.protein for e in entries)
    cal_pct = round((total_cal / profile.target_calories) * 100, 1) if profile and profile.target_calories else 0
    protein_pct = round((total_protein / profile.target_protein) * 100, 1) if profile and profile.target_protein else 0
    score = calculate_score(cal_pct, protein_pct, wellbeing)

    existing = db.query(DayScore).filter(
        DayScore.user_id == current_user.id,
        DayScore.date == target_date,
    ).first()
    if existing:
        existing.score = score
        existing.cal_pct = cal_pct
        existing.protein_pct = protein_pct
        existing.wellbeing = wellbeing
        existing.notes = notes
    else:
        db.add(DayScore(
            user_id=current_user.id,
            date=target_date, score=score,
            cal_pct=cal_pct, protein_pct=protein_pct,
            wellbeing=wellbeing, notes=notes,
        ))
    db.commit()
    return RedirectResponse(url="/", status_code=303)


@app.get("/api/score/preview")
def api_score_preview(request: Request, db: Session = Depends(get_db), wellbeing: str = "good"):
    current_user, _ = get_user_from_request(request, db)
    if not current_user:
        raise HTTPException(status_code=401)
    today = date.today()
    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
    entries = db.query(FoodEntry).filter(
        FoodEntry.user_id == current_user.id, FoodEntry.date == today,
    ).all()
    total_cal = sum(e.calories for e in entries)
    total_protein = sum(e.protein for e in entries)
    cal_pct = round((total_cal / profile.target_calories) * 100, 1) if profile and profile.target_calories else 0
    protein_pct = round((total_protein / profile.target_protein) * 100, 1) if profile and profile.target_protein else 0
    score = calculate_score(cal_pct, protein_pct, wellbeing)
    return JSONResponse(content={"score": score, "cal_pct": cal_pct, "protein_pct": protein_pct})


@app.get("/api/scores/week")
def api_week_scores(request: Request, db: Session = Depends(get_db)):
    current_user, _ = get_user_from_request(request, db)
    if not current_user:
        raise HTTPException(status_code=401)
    today = date.today()
    week_start = today - timedelta(days=6)
    scores = db.query(DayScore).filter(
        DayScore.user_id == current_user.id,
        DayScore.date >= week_start,
    ).all()
    return JSONResponse(content={str(s.date): s.score for s in scores})


# ─── Reminders ──────────────────────────────────────────────────────────────

@app.get("/reminders", response_class=HTMLResponse)
def reminders_page(request: Request, db: Session = Depends(get_db)):
    current_user, redirect = get_user_from_request(request, db)
    if redirect:
        return redirect
    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
    return templates.TemplateResponse("reminders.html", {
        "request": request,
        "current_user": current_user,
        "profile": profile,
    })


# ─── Profile ────────────────────────────────────────────────────────────────

@app.get("/profile", response_class=HTMLResponse)
def profile_page(request: Request, db: Session = Depends(get_db)):
    current_user, redirect = get_user_from_request(request, db)
    if redirect:
        return redirect
    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
    new_user = request.query_params.get("new") == "1"
    bmi = bmr = tdee = None
    if profile:
        height_m = profile.height_cm / 100
        bmi = round(profile.weight_kg / (height_m ** 2), 1)
        bmr = round(10 * profile.weight_kg + 6.25 * profile.height_cm - 5 * profile.age + 5)
        tdee = round(bmr * 1.725)
    return templates.TemplateResponse("profile.html", {
        "request": request,
        "current_user": current_user,
        "profile": profile,
        "bmi": bmi,
        "bmr": bmr,
        "tdee": tdee,
        "new_user": new_user,
    })


@app.post("/profile")
async def save_profile(
    request: Request,
    db: Session = Depends(get_db),
):
    current_user, redirect = get_user_from_request(request, db)
    if redirect:
        return redirect

    form = await request.form()

    def fi(key, default=0):
        try:
            return int(form.get(key, default))
        except (ValueError, TypeError):
            return default

    def ff(key, default=0.0):
        try:
            return float(form.get(key, default))
        except (ValueError, TypeError):
            return default

    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
    data = {
        "user_id": current_user.id,
        "name": form.get("name", current_user.name),
        "age": fi("age", 25),
        "weight_kg": ff("weight_kg", 75.0),
        "height_cm": ff("height_cm", 175.0),
        "activity_level": form.get("activity_level", "Moderada"),
        "goal": form.get("goal", ""),
        "target_calories": fi("target_calories", 2500),
        "target_protein": fi("target_protein", 150),
        "target_carbs": fi("target_carbs", 300),
        "target_fat": fi("target_fat", 80),
    }

    if profile:
        for k, v in data.items():
            setattr(profile, k, v)
    else:
        db.add(UserProfile(**data))

    # Update hevy_api_key on user if provided
    hevy_key = form.get("hevy_api_key", "").strip()
    if hevy_key:
        current_user.hevy_api_key = hevy_key
    elif form.get("hevy_api_key") == "":
        current_user.hevy_api_key = None

    db.commit()
    return RedirectResponse(url="/profile", status_code=303)


# ─── Coach ──────────────────────────────────────────────────────────────────

@app.get("/coach", response_class=HTMLResponse)
def coach_page(request: Request, db: Session = Depends(get_db)):
    current_user, redirect = get_user_from_request(request, db)
    if redirect:
        return redirect

    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
    messages = db.query(ChatMessage).filter(
        ChatMessage.user_id == current_user.id,
    ).order_by(ChatMessage.created_at.asc()).limit(20).all()

    hevy_error = None
    recent_workouts_display = []
    hevy_key = current_user.hevy_api_key or os.environ.get("HEVY_API_KEY", "")
    if hevy_key:
        try:
            raw = fetch_recent_workouts(pages=1, api_key=hevy_key)
            recent_workouts_display = [get_workout_display_data(w) for w in raw[:5]]
        except Exception as e:
            hevy_error = str(e)
    else:
        hevy_error = "Hevy no vinculado. Agregá tu API key en Perfil."

    return templates.TemplateResponse("coach.html", {
        "request": request,
        "current_user": current_user,
        "profile": profile,
        "messages": messages,
        "recent_workouts": recent_workouts_display,
        "hevy_error": hevy_error,
        "anthropic_configured": bool(os.environ.get("ANTHROPIC_API_KEY")),
    })


@app.post("/coach/chat")
async def coach_chat(
    request: Request,
    db: Session = Depends(get_db),
    message: str = Form(...),
):
    import anthropic as anthropic_sdk

    current_user, redirect = get_user_from_request(request, db)
    if redirect:
        return redirect

    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
    user_message = message.strip()
    if not user_message:
        return RedirectResponse(url="/coach", status_code=303)

    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    db.add(ChatMessage(user_id=current_user.id, role="user", content=user_message))
    db.commit()

    if not anthropic_key:
        db.add(ChatMessage(user_id=current_user.id, role="assistant",
                           content="Error: ANTHROPIC_API_KEY no configurada."))
        db.commit()
        return RedirectResponse(url="/coach", status_code=303)

    today = date.today()
    today_entries = db.query(FoodEntry).filter(
        FoodEntry.user_id == current_user.id, FoodEntry.date == today,
    ).all()
    today_calories = sum(e.calories for e in today_entries)
    today_protein = sum(e.protein for e in today_entries)

    workout_summaries = []
    hevy_key = current_user.hevy_api_key or os.environ.get("HEVY_API_KEY", "")
    if hevy_key:
        try:
            raw_workouts = fetch_recent_workouts(pages=2, api_key=hevy_key)
            workout_summaries = [format_workout_summary(w) for w in raw_workouts[:10]]
        except Exception:
            pass

    manual_workouts = db.query(ManualWorkout).filter(
        ManualWorkout.user_id == current_user.id,
    ).order_by(ManualWorkout.date.desc()).limit(10).all()
    manual_summaries = [
        f"[{mw.date}] {mw.activity_type}{' (' + mw.custom_type + ')' if mw.custom_type else ''} "
        f"({mw.duration_min or '?'}min, {mw.intensity or 'sin intensidad'}, {mw.calories_burned or '?'} kcal)"
        for mw in manual_workouts
    ]

    target_cal = profile.target_calories if profile else 2500
    target_pro = profile.target_protein if profile else 150

    system = f"""Sos un coach deportivo y nutricional personalizado.
Atleta: {current_user.name}, {profile.age if profile else '?'} años, {profile.weight_kg if profile else '?'}kg, {profile.height_cm if profile else '?'}cm
Objetivo: {profile.goal if profile else 'no configurado'}
Nivel de actividad: {profile.activity_level if profile else 'no configurado'}
Objetivos diarios: {target_cal} kcal, {target_pro}g proteína

Entrenamientos recientes (Hevy):
{chr(10).join(workout_summaries) if workout_summaries else 'Sin datos de Hevy'}

Actividades manuales recientes:
{chr(10).join(manual_summaries) if manual_summaries else 'Sin actividades manuales'}

Nutrición hoy: {today_calories:.0f} kcal / {target_cal} kcal, proteína: {today_protein:.0f}g / {target_pro}g

Respondé en español. Sé directo y conciso. Máximo 3-4 párrafos."""

    history = db.query(ChatMessage).filter(
        ChatMessage.user_id == current_user.id,
    ).order_by(ChatMessage.created_at.desc()).limit(11).all()
    history.reverse()
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

    db.add(ChatMessage(user_id=current_user.id, role="assistant", content=assistant_reply))
    db.commit()
    return RedirectResponse(url="/coach", status_code=303)


@app.post("/coach/clear")
def coach_clear(request: Request, db: Session = Depends(get_db)):
    current_user, redirect = get_user_from_request(request, db)
    if redirect:
        return redirect
    db.query(ChatMessage).filter(ChatMessage.user_id == current_user.id).delete()
    db.commit()
    return RedirectResponse(url="/coach", status_code=303)


@app.get("/api/workouts/recent")
def api_recent_workouts(request: Request, db: Session = Depends(get_db)):
    current_user, _ = get_user_from_request(request, db)
    if not current_user:
        return JSONResponse(content={"error": "No autenticado", "workouts": []})
    hevy_key = current_user.hevy_api_key or os.environ.get("HEVY_API_KEY", "")
    if not hevy_key:
        return JSONResponse(content={"error": "Hevy no vinculado", "workouts": []})
    try:
        raw = fetch_recent_workouts(pages=1, api_key=hevy_key)
        return JSONResponse(content={"workouts": [get_workout_display_data(w) for w in raw[:10]]})
    except Exception as e:
        return JSONResponse(content={"error": str(e), "workouts": []})


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


def _parse_optional_float(v):
    try:
        return float(v) if v and str(v).strip() else None
    except (ValueError, TypeError):
        return None


def _parse_optional_int(v):
    try:
        return int(v) if v and str(v).strip() else None
    except (ValueError, TypeError):
        return None


@app.get("/measurements", response_class=HTMLResponse)
def measurements_page(request: Request, db: Session = Depends(get_db)):
    current_user, redirect = get_user_from_request(request, db)
    if redirect:
        return redirect
    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
    measurements = db.query(BodyMeasurement).filter(
        BodyMeasurement.user_id == current_user.id,
    ).order_by(BodyMeasurement.fecha_medicion.desc()).all()
    return templates.TemplateResponse("measurements.html", {
        "request": request,
        "current_user": current_user,
        "profile": profile,
        "measurements": measurements,
        "now": datetime.today,
    })


@app.post("/measurements")
async def save_measurement(request: Request, db: Session = Depends(get_db)):
    current_user, redirect = get_user_from_request(request, db)
    if redirect:
        return redirect

    form = await request.form()
    fecha_str = form.get("fecha_medicion", "")
    if not fecha_str:
        raise HTTPException(status_code=400, detail="fecha_medicion es requerida")

    kwargs = {
        "user_id": current_user.id,
        "fecha_medicion": date.fromisoformat(fecha_str),
        "notas": form.get("notas", "") or None,
    }
    for field in _MEASUREMENT_FLOAT_FIELDS:
        kwargs[field] = _parse_optional_float(form.get(field, ""))
    for field in _MEASUREMENT_INT_FIELDS:
        kwargs[field] = _parse_optional_int(form.get(field, ""))

    db.add(BodyMeasurement(**kwargs))
    db.commit()
    return RedirectResponse(url="/measurements", status_code=303)


@app.delete("/measurements/{measurement_id}")
def delete_measurement(measurement_id: int, request: Request, db: Session = Depends(get_db)):
    current_user, _ = get_user_from_request(request, db)
    if not current_user:
        raise HTTPException(status_code=401)
    m = db.query(BodyMeasurement).filter(
        BodyMeasurement.id == measurement_id,
        BodyMeasurement.user_id == current_user.id,
    ).first()
    if not m:
        raise HTTPException(status_code=404)
    db.delete(m)
    db.commit()
    return JSONResponse(content={"success": True})


@app.post("/measurements/import")
async def import_measurement(request: Request, db: Session = Depends(get_db), file: UploadFile = File(...)):
    current_user, _ = get_user_from_request(request, db)
    if not current_user:
        return JSONResponse(status_code=401, content={"error": "No autenticado"})

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
        "Este es un resultado de InBody. Extraé los valores numéricos y devolvé SOLO un JSON con estas claves "
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
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}},
                {"type": "text", "text": prompt},
            ]}],
        )
        raw_text = response.content[0].text
        start, end = raw_text.find("{"), raw_text.rfind("}") + 1
        if start == -1:
            return JSONResponse(status_code=422, content={"error": "No se pudo extraer JSON", "raw": raw_text})
        return JSONResponse(content={"success": True, "data": json.loads(raw_text[start:end])})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# ─── Workouts ───────────────────────────────────────────────────────────────

@app.get("/strava/connect")
def strava_connect(request: Request, db: Session = Depends(get_db)):
    current_user, redirect = get_user_from_request(request, db)
    if redirect:
        return redirect
    return RedirectResponse(url=get_auth_url(STRAVA_REDIRECT_URI))


@app.get("/strava/callback")
def strava_callback(
    request: Request,
    db: Session = Depends(get_db),
    code: str = "",
    error: str = "",
):
    current_user, redirect = get_user_from_request(request, db)
    if redirect:
        return redirect
    if error or not code:
        return RedirectResponse(url="/workouts?strava_error=denied", status_code=303)
    try:
        data = exchange_code(code, STRAVA_REDIRECT_URI)
        athlete_id = data.get("athlete", {}).get("id", 0)
        existing = db.query(StravaToken).filter(StravaToken.user_id == current_user.id).first()
        if existing:
            existing.athlete_id = athlete_id
            existing.access_token = data["access_token"]
            existing.refresh_token = data["refresh_token"]
            existing.expires_at = data["expires_at"]
        else:
            db.add(StravaToken(
                user_id=current_user.id,
                athlete_id=athlete_id,
                access_token=data["access_token"],
                refresh_token=data["refresh_token"],
                expires_at=data["expires_at"],
            ))
        db.commit()
        return RedirectResponse(url="/workouts?strava_connected=1", status_code=303)
    except Exception:
        return RedirectResponse(url="/workouts?strava_error=1", status_code=303)


@app.post("/strava/disconnect")
def strava_disconnect(request: Request, db: Session = Depends(get_db)):
    current_user, redirect = get_user_from_request(request, db)
    if redirect:
        return redirect
    db.query(StravaToken).filter(StravaToken.user_id == current_user.id).delete()
    db.commit()
    return RedirectResponse(url="/workouts", status_code=303)


@app.get("/workouts", response_class=HTMLResponse)
def workouts_page(request: Request, db: Session = Depends(get_db)):
    current_user, redirect = get_user_from_request(request, db)
    if redirect:
        return redirect

    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
    today = date.today()
    week_start = today - timedelta(days=today.weekday())

    # Hevy workouts (per-user API key)
    hevy_workouts = []
    hevy_error = None
    hevy_key = current_user.hevy_api_key or os.environ.get("HEVY_API_KEY", "")
    if hevy_key:
        try:
            raw = fetch_recent_workouts(pages=3, api_key=hevy_key)
            hevy_workouts = [get_workout_display_data(w) for w in raw]
        except Exception as e:
            hevy_error = str(e)
    else:
        hevy_error = "Hevy no vinculado. Agregá tu API key en Perfil."

    # Manual workouts
    manual_workouts = db.query(ManualWorkout).filter(
        ManualWorkout.user_id == current_user.id,
    ).order_by(ManualWorkout.date.desc()).all()

    # Weekly stats
    week_manual = [mw for mw in manual_workouts if mw.date >= week_start]
    week_hevy = [hw for hw in hevy_workouts if hw.get("sort_date", "") >= str(week_start)]
    week_sessions = len(week_manual) + len(week_hevy)
    week_minutes = sum((mw.duration_min or 0) for mw in week_manual)
    for hw in week_hevy:
        week_minutes += (hw.get("duration_seconds", 0) or 0) // 60
    week_kcal = sum((mw.calories_burned or 0) for mw in week_manual)

    # Strava
    strava_workouts = []
    strava_error = None
    strava_token = db.query(StravaToken).filter(StravaToken.user_id == current_user.id).first()
    strava_connected = bool(strava_token)
    if strava_connected:
        try:
            access_token = get_valid_token(db, user_id=current_user.id)
            if access_token:
                raw_strava = fetch_activities(access_token, per_page=30)
                strava_workouts = [format_activity(a) for a in raw_strava]
                week_strava = [a for a in strava_workouts if a.get("sort_date", "") >= str(week_start)]
                week_kcal += sum((a.get("calories") or 0) for a in week_strava)
                week_sessions += len(week_strava)
                for a in week_strava:
                    week_minutes += (a.get("duration_seconds") or 0) // 60
            else:
                strava_error = "Token inválido. Volvé a conectar."
                strava_connected = False
        except Exception as e:
            strava_error = f"Error Strava: {str(e)}"

    return templates.TemplateResponse("workouts.html", {
        "request": request,
        "current_user": current_user,
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
        "anthropic_configured": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "flash_strava_connected": request.query_params.get("strava_connected") == "1",
        "flash_strava_error": request.query_params.get("strava_error"),
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
    current_user, redirect = get_user_from_request(request, db)
    if redirect:
        return redirect

    def opt_int(v):
        try:
            return int(v) if v and str(v).strip() else None
        except (ValueError, TypeError):
            return None

    def opt_float(v):
        try:
            return float(v) if v and str(v).strip() else None
        except (ValueError, TypeError):
            return None

    db.add(ManualWorkout(
        user_id=current_user.id,
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
    ))
    db.commit()
    return RedirectResponse(url="/workouts", status_code=303)


@app.delete("/workouts/{workout_id}")
def delete_manual_workout(workout_id: int, request: Request, db: Session = Depends(get_db)):
    current_user, _ = get_user_from_request(request, db)
    if not current_user:
        raise HTTPException(status_code=401)
    workout = db.query(ManualWorkout).filter(
        ManualWorkout.id == workout_id,
        ManualWorkout.user_id == current_user.id,
    ).first()
    if not workout:
        raise HTTPException(status_code=404)
    db.delete(workout)
    db.commit()
    return JSONResponse(content={"success": True})


@app.post("/api/workouts/estimate-calories")
async def estimate_calories(
    request: Request,
    db: Session = Depends(get_db),
    activity_type: str = Form(...),
    duration_min: str = Form(""),
    intensity: str = Form(""),
    notes: str = Form(""),
):
    current_user, _ = get_user_from_request(request, db)
    if not current_user:
        raise HTTPException(status_code=401)

    import anthropic as _anthropic
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY no configurada")

    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
    weight = profile.weight_kg if profile else 75
    age = profile.age if profile else 25

    client = _anthropic.Anthropic(api_key=api_key)
    system = f"""Sos un experto en fisiología del ejercicio. Estimá las calorías quemadas para un atleta de {age} años, {weight}kg.
Devolvé SOLO un JSON: {{"calories": número_entero, "explanation": "una línea explicando el cálculo"}}. Sé conservador y realista."""

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            system=system,
            messages=[{"role": "user", "content": f"Actividad: {activity_type}, Duración: {duration_min} min, Intensidad: {intensity}. {notes}"}],
        )
        raw = response.content[0].text.strip()
        start, end = raw.find("{"), raw.rfind("}") + 1
        return JSONResponse(content=json.loads(raw[start:end]))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al estimar: {str(e)}")


@app.get("/api/workouts/all")
def api_all_workouts(request: Request, db: Session = Depends(get_db)):
    current_user, _ = get_user_from_request(request, db)
    if not current_user:
        raise HTTPException(status_code=401)

    manual_workouts = db.query(ManualWorkout).filter(
        ManualWorkout.user_id == current_user.id,
    ).order_by(ManualWorkout.date.desc()).limit(30).all()
    manual_list = [
        {
            "source": "manual", "id": mw.id, "date": str(mw.date),
            "activity_type": mw.activity_type, "custom_type": mw.custom_type,
            "duration_min": mw.duration_min, "intensity": mw.intensity,
            "calories_burned": mw.calories_burned, "heart_rate_avg": mw.heart_rate_avg,
            "distance_km": mw.distance_km, "notes": mw.notes,
        }
        for mw in manual_workouts
    ]

    hevy_list = []
    hevy_key = current_user.hevy_api_key or os.environ.get("HEVY_API_KEY", "")
    if hevy_key:
        try:
            raw = fetch_recent_workouts(pages=2, api_key=hevy_key)
            hevy_list = [{"source": "hevy", **get_workout_display_data(w)} for w in raw[:30]]
        except Exception:
            pass

    all_workouts = manual_list + hevy_list
    all_workouts.sort(key=lambda x: x.get("date", x.get("start_time", "")), reverse=True)
    return JSONResponse(content={"workouts": all_workouts[:30]})
