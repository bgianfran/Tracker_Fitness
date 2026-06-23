import os
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Date, Text, ForeignKey, Boolean, JSON
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


class Exercise(Base):
    """Exercise catalog (the in-app library). Seeded from the public-domain
    free-exercise-db; users can also add their own (is_custom=True).

    Muscle groups are normalised to our Spanish taxonomy (primary_muscle /
    secondary_muscles_es) so the analysis tab works natively, while the
    original English values are kept for reference. Images are hot-linked
    via CDN URLs; gif_url is left empty for now and can be filled later from
    a separate animated source without changing the schema."""
    __tablename__ = "exercises"

    id = Column(Integer, primary_key=True)
    slug = Column(String, unique=True, nullable=False, index=True)
    name_en = Column(String, nullable=False)
    name_es = Column(String, nullable=True)          # filled later (AI batch translate)

    category = Column(String, nullable=True)          # raw EN: strength, cardio...
    category_es = Column(String, nullable=True)       # Fuerza, Cardio...
    equipment = Column(String, nullable=True)         # raw EN
    equipment_es = Column(String, nullable=True, index=True)
    force = Column(String, nullable=True)             # push / pull / static
    level = Column(String, nullable=True)             # beginner / intermediate / expert
    mechanic = Column(String, nullable=True)          # compound / isolation

    primary_muscle = Column(String, nullable=True, index=True)   # canonical ES group
    primary_muscles_raw = Column(JSON, nullable=True)            # original EN list
    secondary_muscles_es = Column(JSON, nullable=True)           # canonical ES list
    secondary_muscles_raw = Column(JSON, nullable=True)

    instructions = Column(JSON, nullable=True)        # list of steps
    images = Column(JSON, nullable=True)              # list of full CDN URLs
    gif_url = Column(String, nullable=True)           # optional animated, linked later
    coach_notes = Column(Text, nullable=True)         # extra notes for the AI coach

    is_custom = Column(Boolean, default=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    source = Column(String, nullable=True)            # e.g. "free-exercise-db"
    license = Column(String, nullable=True)           # e.g. "Public Domain (Unlicense)"
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class WorkoutSession(Base):
    """A gym workout logged natively in the app (no Hevy needed).
    folder_id / routine_id are reserved for Fase 3 (carpetas + rutinas)."""
    __tablename__ = "workout_sessions"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    date = Column(Date, nullable=False, default=date.today)
    title = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    duration_min = Column(Integer, nullable=True)
    origin = Column(String, default="app")          # app / hevy / strava
    folder_id = Column(Integer, nullable=True, index=True)   # Fase 3
    routine_id = Column(Integer, nullable=True, index=True)  # Fase 3
    created_at = Column(DateTime, default=datetime.utcnow)


class WorkoutExercise(Base):
    """One exercise inside a WorkoutSession. Name/muscle are snapshotted at
    log time so history stays stable even if the catalog changes."""
    __tablename__ = "workout_exercises"

    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("workout_sessions.id"), nullable=False, index=True)
    exercise_id = Column(Integer, ForeignKey("exercises.id"), nullable=True)
    exercise_slug = Column(String, nullable=True)
    name = Column(String, nullable=False)
    muscle = Column(String, nullable=True)          # canonical ES group
    order = Column(Integer, default=0)
    notes = Column(Text, nullable=True)


class WorkoutSet(Base):
    """One set of a WorkoutExercise."""
    __tablename__ = "workout_sets"

    id = Column(Integer, primary_key=True)
    workout_exercise_id = Column(Integer, ForeignKey("workout_exercises.id"), nullable=False, index=True)
    set_index = Column(Integer, default=1)
    type = Column(String, default="normal")         # normal / warmup / dropset / failure
    weight_kg = Column(Float, nullable=True)
    reps = Column(Integer, nullable=True)
    rpe = Column(Float, nullable=True)


class Folder(Base):
    """A training block / folder that groups routines (e.g. "Hipertrofia")."""
    __tablename__ = "folders"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Routine(Base):
    """A reusable routine template (e.g. "Push A") living inside a folder."""
    __tablename__ = "routines"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    folder_id = Column(Integer, ForeignKey("folders.id"), nullable=True, index=True)
    name = Column(String, nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class RoutineExercise(Base):
    """An exercise prescribed in a routine, with target sets/reps."""
    __tablename__ = "routine_exercises"

    id = Column(Integer, primary_key=True)
    routine_id = Column(Integer, ForeignKey("routines.id"), nullable=False, index=True)
    exercise_id = Column(Integer, ForeignKey("exercises.id"), nullable=True)
    exercise_slug = Column(String, nullable=True)
    name = Column(String, nullable=False)
    muscle = Column(String, nullable=True)
    order = Column(Integer, default=0)
    target_sets = Column(Integer, nullable=True)
    target_reps = Column(String, nullable=True)     # e.g. "8-12"
    notes = Column(Text, nullable=True)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    Base.metadata.create_all(bind=engine)
    # Add eaten_at column if it doesn't exist (migration for existing deployments)
    try:
        with engine.connect() as conn:
            if DATABASE_URL.startswith("postgresql"):
                conn.execute(__import__("sqlalchemy").text(
                    "ALTER TABLE food_entries ADD COLUMN IF NOT EXISTS eaten_at TIMESTAMP"
                ))
                conn.commit()
    except Exception:
        pass
