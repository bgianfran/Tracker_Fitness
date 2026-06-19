import os
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Date, Text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime, date

_raw_url = os.environ.get("DATABASE_URL", "sqlite:///./tracker.db")
# Railway gives postgres:// but SQLAlchemy needs postgresql://
DATABASE_URL = _raw_url.replace("postgres://", "postgresql://", 1)

_kwargs = {} if DATABASE_URL.startswith("postgresql") else {"connect_args": {"check_same_thread": False}}
engine = create_engine(DATABASE_URL, **_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    password_hash = Column(String, nullable=False)
    hevy_api_key = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class FoodEntry(Base):
    __tablename__ = "food_entries"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    date = Column(Date, nullable=False, default=date.today)
    meal_type = Column(String, nullable=False)
    food_name = Column(String, nullable=False)
    quantity_g = Column(Float, nullable=False)
    calories = Column(Float, nullable=False)
    protein = Column(Float, nullable=False)
    carbs = Column(Float, nullable=False)
    fat = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    eaten_at = Column(DateTime, nullable=True)  # local time when food was consumed
    unidad = Column(String, nullable=True, default="g")     # "g" or "ml"
    portion_label = Column(String, nullable=True)           # e.g. "1 vaso", "½ taza"


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    name = Column(String, nullable=False)
    age = Column(Integer, nullable=False)
    weight_kg = Column(Float, nullable=False)
    height_cm = Column(Float, nullable=False)
    activity_level = Column(String, nullable=False)
    goal = Column(String, nullable=False)
    target_calories = Column(Integer, nullable=False)
    target_protein = Column(Integer, nullable=False)
    target_carbs = Column(Integer, nullable=False)
    target_fat = Column(Integer, nullable=False)


class DayScore(Base):
    __tablename__ = "day_scores"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    date = Column(Date, nullable=False)
    score = Column(Integer, nullable=False)
    cal_pct = Column(Float, nullable=True)
    protein_pct = Column(Float, nullable=True)
    wellbeing = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class BodyMeasurement(Base):
    __tablename__ = "body_measurements"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    fecha_medicion = Column(Date, nullable=False)
    peso_kg = Column(Float)
    agua_corporal_l = Column(Float)
    proteinas_kg = Column(Float)
    minerales_kg = Column(Float)
    masa_grasa_corporal_kg = Column(Float)
    masa_musculoesqueletica_kg = Column(Float)
    imc = Column(Float)
    pgc = Column(Float)
    magro_brazo_derecho_kg = Column(Float)
    magro_brazo_izquierdo_kg = Column(Float)
    magro_tronco_kg = Column(Float)
    magro_pierna_derecha_kg = Column(Float)
    magro_pierna_izquierda_kg = Column(Float)
    grasa_brazo_derecho_kg = Column(Float)
    grasa_brazo_izquierdo_kg = Column(Float)
    grasa_tronco_kg = Column(Float)
    grasa_pierna_derecha_kg = Column(Float)
    grasa_pierna_izquierda_kg = Column(Float)
    control_peso_kg = Column(Float)
    control_grasa_kg = Column(Float)
    control_musculo_kg = Column(Float)
    relacion_cintura_cadera = Column(Float)
    nivel_grasa_visceral = Column(Integer)
    puntuacion_inbody = Column(Integer)
    pliegue_triceps_mm = Column(Float)
    pliegue_subescapular_mm = Column(Float)
    pliegue_suprailiaco_mm = Column(Float)
    pliegue_abdominal_mm = Column(Float)
    pliegue_muslo_mm = Column(Float)
    notas = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class ManualWorkout(Base):
    __tablename__ = "manual_workouts"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    date = Column(Date, nullable=False, default=date.today)
    activity_type = Column(String, nullable=False)
    custom_type = Column(String, nullable=True)
    duration_min = Column(Integer, nullable=True)
    intensity = Column(String, nullable=True)
    calories_burned = Column(Integer, nullable=True)
    calories_source = Column(String, nullable=True)
    heart_rate_avg = Column(Integer, nullable=True)
    distance_km = Column(Float, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class StravaToken(Base):
    __tablename__ = "strava_tokens"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    athlete_id = Column(Integer, nullable=False)
    access_token = Column(String, nullable=False)
    refresh_token = Column(String, nullable=False)
    expires_at = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CommunityFood(Base):
    """Barcode-indexed foods, sourced from Open Food Facts or contributed by users.
    Macros are stored per 100 g / 100 ml, like the rest of the food data."""
    __tablename__ = "community_foods"

    id = Column(Integer, primary_key=True)
    barcode = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    marca = Column(String, nullable=True)
    categoria = Column(String, nullable=True)
    calories = Column(Float, nullable=False)
    protein = Column(Float, nullable=False)
    carbs = Column(Float, nullable=False)
    fat = Column(Float, nullable=False)
    fiber = Column(Float, nullable=True)
    sodium = Column(Float, nullable=True)
    unidad = Column(String, nullable=False, default="g")  # "g" or "ml"
    source = Column(String, nullable=False, default="user")  # "openfoodfacts" | "user"
    contributed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    times_used = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SavedMeal(Base):
    """A reusable multi-ingredient meal (combo) saved by a user.
    `items` is a JSON list of {name, quantity_g, calories, protein, carbs,
    fat, unidad} with macros per 100 g/ml."""
    __tablename__ = "saved_meals"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    items = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    Base.metadata.create_all(bind=engine)
    # Lightweight migrations for existing deployments (add new columns if missing)
    from sqlalchemy import text
    pg = DATABASE_URL.startswith("postgresql")
    migrations = [
        "ALTER TABLE food_entries ADD COLUMN IF NOT EXISTS eaten_at TIMESTAMP",
        "ALTER TABLE food_entries ADD COLUMN IF NOT EXISTS unidad VARCHAR",
        "ALTER TABLE food_entries ADD COLUMN IF NOT EXISTS portion_label VARCHAR",
    ]
    if pg:
        for stmt in migrations:
            try:
                with engine.connect() as conn:
                    conn.execute(text(stmt))
                    conn.commit()
            except Exception:
                pass
    else:
        # SQLite: no "IF NOT EXISTS" for columns; try and ignore "duplicate" errors
        for col, typ in [("eaten_at", "TIMESTAMP"), ("unidad", "VARCHAR"), ("portion_label", "VARCHAR")]:
            try:
                with engine.connect() as conn:
                    conn.execute(text(f"ALTER TABLE food_entries ADD COLUMN {col} {typ}"))
                    conn.commit()
            except Exception:
                pass
