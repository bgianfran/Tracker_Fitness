import os
import time
from urllib.parse import urlencode
import httpx

STRAVA_CLIENT_ID = "256265"
STRAVA_AUTH_URL = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_API_BASE = "https://www.strava.com/api/v3"

SPORT_EMOJI = {
    "Run": "🏃", "TrailRun": "🏃", "Ride": "🚴", "VirtualRide": "🚴",
    "Swim": "🏊", "Walk": "🚶", "Hike": "🥾", "WeightTraining": "💪",
    "Yoga": "🧘", "Soccer": "⚽", "Football": "⚽", "Tennis": "🎾",
    "Workout": "🏋️", "Crossfit": "🤸", "Boxing": "🥊",
    "MartialArts": "🥋", "Rowing": "🚣", "Skiing": "⛷️",
    "Golf": "⛳", "Skateboard": "🛹", "Surfing": "🏄",
    "Kayaking": "🛶", "Pilates": "🧘", "Elliptical": "🏃",
    "StairStepper": "🪜", "RockClimbing": "🧗",
}


def get_auth_url(redirect_uri: str) -> str:
    params = {
        "client_id": STRAVA_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "approval_prompt": "auto",
        "scope": "activity:read_all",
    }
    return f"{STRAVA_AUTH_URL}?{urlencode(params)}"


def exchange_code(code: str, redirect_uri: str) -> dict:
    client_secret = os.environ.get("STRAVA_CLIENT_SECRET", "")
    resp = httpx.post(STRAVA_TOKEN_URL, data={
        "client_id": STRAVA_CLIENT_ID,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
    }, timeout=15)
    resp.raise_for_status()
    return resp.json()


def _refresh_access_token(refresh_tok: str) -> dict:
    client_secret = os.environ.get("STRAVA_CLIENT_SECRET", "")
    resp = httpx.post(STRAVA_TOKEN_URL, data={
        "client_id": STRAVA_CLIENT_ID,
        "client_secret": client_secret,
        "refresh_token": refresh_tok,
        "grant_type": "refresh_token",
    }, timeout=15)
    resp.raise_for_status()
    return resp.json()


def get_valid_token(db, user_id: int = None) -> str | None:
    from app.database import StravaToken
    q = db.query(StravaToken)
    if user_id is not None:
        q = q.filter(StravaToken.user_id == user_id)
    token = q.first()
    if not token:
        return None
    if token.expires_at < int(time.time()) + 300:
        try:
            data = _refresh_access_token(token.refresh_token)
            token.access_token = data["access_token"]
            token.refresh_token = data["refresh_token"]
            token.expires_at = data["expires_at"]
            db.commit()
        except Exception:
            return None
    return token.access_token


def fetch_activities(access_token: str, per_page: int = 30) -> list:
    resp = httpx.get(
        f"{STRAVA_API_BASE}/athlete/activities",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"per_page": per_page},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def format_activity(activity: dict) -> dict:
    sport_type = activity.get("sport_type") or activity.get("type", "Workout")
    start = activity.get("start_date_local", "")[:10]
    distance_m = activity.get("distance") or 0

    return {
        "source": "strava",
        "id": activity.get("id"),
        "sort_date": start,
        "title": activity.get("name", sport_type),
        "sport_type": sport_type,
        "emoji": SPORT_EMOJI.get(sport_type, "🏅"),
        "duration_seconds": activity.get("moving_time") or 0,
        "distance_km": round(distance_m / 1000, 2) if distance_m else None,
        "calories": activity.get("calories"),
        "avg_heart_rate": activity.get("average_heartrate"),
        "elevation_gain": activity.get("total_elevation_gain"),
    }
