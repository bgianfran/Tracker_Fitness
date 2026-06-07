from fastapi import FastAPI, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date, timedelta
import os

from app.database import get_db, init_db, FoodEntry, UserProfile, DayScore
from app.food_data import search_foods, get_food, FOOD_DATABASE

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
    score: int = Form(...),
    notes: str = Form(""),
    score_date: str = Form(""),
):
    target_date = date.fromisoformat(score_date) if score_date else date.today()
    if not (1 <= score <= 5):
        raise HTTPException(status_code=400, detail="Puntaje debe ser entre 1 y 5")

    existing = db.query(DayScore).filter(DayScore.date == target_date).first()
    if existing:
        existing.score = score
        existing.notes = notes
    else:
        db.add(DayScore(date=target_date, score=score, notes=notes))
    db.commit()
    return RedirectResponse(url="/", status_code=303)


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
