from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Date, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime, date

DATABASE_URL = "sqlite:///./tracker.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class FoodEntry(Base):
    __tablename__ = "food_entries"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False, default=date.today)
    meal_type = Column(String, nullable=False)  # breakfast, lunch, dinner, snack
    food_name = Column(String, nullable=False)
    quantity_g = Column(Float, nullable=False)
    calories = Column(Float, nullable=False)
    protein = Column(Float, nullable=False)
    carbs = Column(Float, nullable=False)
    fat = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id = Column(Integer, primary_key=True, index=True)
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
    date = Column(Date, nullable=False, unique=True)
    score = Column(Integer, nullable=False)       # 1-5 calculado automáticamente
    cal_pct = Column(Float, nullable=True)        # % calorías vs objetivo
    protein_pct = Column(Float, nullable=True)    # % proteína vs objetivo
    wellbeing = Column(String, nullable=True)     # 'hungry' | 'good' | 'overate'
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True)
    role = Column(String, nullable=False)   # 'user' or 'assistant'
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        profile = db.query(UserProfile).first()
        if not profile:
            default_profile = UserProfile(
                name="Usuario",
                age=26,
                weight_kg=109.0,
                height_cm=184.0,
                activity_level="Muy alta (fútbol, MMA, pesas 5-6x/semana)",
                goal="Perder grasa, preservar/ganar músculo, mejorar rendimiento deportivo",
                target_calories=3150,
                target_protein=200,
                target_carbs=375,
                target_fat=90,
            )
            db.add(default_profile)
            db.commit()
    finally:
        db.close()
