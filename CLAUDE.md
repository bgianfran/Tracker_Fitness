# CLAUDE.md — FitTracker

Guía de arquitectura y reglas de trabajo para sesiones de Claude Code.
**Toda sesión debe leer este archivo antes de empezar.**

---

## Qué es

App web full-stack de fitness y nutrición (PWA instalable). El usuario
registra comidas y entrenamientos, ve su progreso y consulta un coach IA.

**Stack:**
- Backend: **FastAPI** (Python) + **SQLAlchemy** ORM
- Frontend: templates **Jinja2** server-rendered + JS vanilla + **Tailwind CSS**
- DB: **PostgreSQL** en producción / **SQLite** en local (`tracker.db`)
- Auth: bcrypt + token de sesión firmado en cookie
- Integraciones: Hevy (fuerza), Strava (cardio), Open Food Facts (códigos de
  barra), RNPA (buscador de alimentos), Anthropic Claude (IA)
- Deploy: **Railway** (`railway.toml`, `Dockerfile`, `nixpacks.toml`)

---

## Cómo correr

```bash
pip install -r requirements.txt
python run.py            # levanta uvicorn (ver run.py)
```

Sin `DATABASE_URL` usa SQLite local. Variables relevantes: `DATABASE_URL`,
claves de Strava/Hevy/Anthropic vía entorno.

> No hay tests automatizados todavía. Antes de pushear, como mínimo:
> `python -m py_compile app/*.py` para validar sintaxis.

---

## Estructura

```
app/
├── main.py            # ⚠️ MONOLITO: TODAS las rutas (comidas, entrenos,
│                      #    dashboard, coach, perfil, score, auth, PWA)
├── database.py        # 🔒 COMPARTIDO: todos los modelos SQLAlchemy + init_db
├── auth.py            # 🔒 COMPARTIDO: hashing y tokens de sesión
├── hevy.py            # [Entrenos] integración Hevy (fuerza)
├── strava_api.py      # [Entrenos] integración Strava (cardio)
├── rnpa_search.py     # [Comidas] buscador de alimentos RNPA
├── openfoodfacts.py   # [Comidas] lookup por código de barra
├── portions.py        # [Comidas] tamaños de porción de referencia
├── templates/
│   ├── base.html      # 🔒 COMPARTIDO: layout, navegación (pestañas), tema
│   ├── comidas.html   # [Comidas]
│   ├── entrenos.html  # [Entrenos]
│   ├── dashboard.html # 🔒 COMPARTIDO: resumen diario (comida + score)
│   ├── coach.html     # [Coach]
│   ├── profile.html, measurements.html, history.html, reminders.html, ...
│   └── log.html, workouts.html   # ⚠️ LEGACY (rutas /log y /workouts redirigen) — candidatos a borrar
│   └── static/        # assets PWA (manifest, service worker, íconos)
data/                  # seed inicial
run.py                 # entrypoint
```

### Modelos (`app/database.py`)
`User`, `UserProfile`, `FoodEntry`, `DayScore`, `ChatMessage`,
`BodyMeasurement`, `ManualWorkout`, `StravaToken`, `CommunityFood`, `SavedMeal`.

---

## Mapa de features (quién toca qué)

| Feature | Archivos propios | Modelos |
|---|---|---|
| 🍽️ **Comidas** | `templates/comidas.html`, `rnpa_search.py`, `openfoodfacts.py`, `portions.py` + rutas de comidas en `main.py` | `FoodEntry`, `CommunityFood`, `SavedMeal` |
| 🏋️ **Entrenos** | `templates/entrenos.html`, `hevy.py`, `strava_api.py` + rutas de entrenos en `main.py` | `ManualWorkout`, `StravaToken` |
| 🤖 **Coach / Score** | `templates/coach.html`, `calculate_score()` + rutas de coach/score en `main.py` | `ChatMessage`, `DayScore` |
| 👤 **Perfil / Mediciones** | `templates/profile.html`, `measurements.html` | `UserProfile`, `BodyMeasurement` |

### 🔒 Archivos COMPARTIDOS (alto riesgo de conflicto)
`app/database.py`, `app/auth.py`, `app/main.py`, `app/templates/base.html`,
`app/templates/dashboard.html`, y `calculate_score()`.

**Cambios en archivos compartidos los coordina el chat de ESTRUCTURA.**

---

## 🧭 Reglas de trabajo en paralelo

Trabajamos con varias sesiones en simultáneo, una por tema:
- Chat **Comidas**, chat **Entrenos**, etc. → cada uno enfocado en su feature.
- Chat **Estructura** (este rol) → integra ramas, posee los archivos
  compartidos, mantiene este documento y resuelve conflictos.

**Reglas:**
1. **Una rama de git por chat.** Nunca dos chats pushean a la misma rama.
2. Cada chat edita **solo los archivos propios** de su feature.
3. Si una feature necesita un cambio en un archivo 🔒 compartido
   (`database.py`, `base.html`, `main.py` fuera de sus rutas, scoring),
   **lo pide al chat de Estructura** en lugar de hacerlo por su cuenta.
4. Rutas nuevas en `main.py`: agregarlas agrupadas por feature y lo más
   localizadas posible, para que el auto-merge no choque.
5. El chat de Estructura mantiene el **tronco de integración** donde todas
   las features conviven, y verifica el merge cada vez que una feature pushea.

### Refactor pendiente (cuando haya "freeze")
`main.py` es un monolito de ~1700 líneas. Cuando los chats de feature estén
pausados, partirlo en `app/routers/` (`comidas.py`, `entrenos.py`, `coach.py`,
`dashboard.py`, `profile.py`) con `APIRouter`, para que cada chat trabaje en su
propio archivo. **No hacer este refactor con chats de feature activos** (rompe
sus merges).

---

## Convenciones

- **UI en español** (es-AR). Textos y rótulos en español.
- **Macros siempre por 100 g / 100 ml.** El campo `unidad` es `"g"` o `"ml"`.
- **Sin Alembic**: las migraciones son livianas dentro de `init_db()`
  (`ALTER TABLE ... ADD COLUMN IF NOT EXISTS`). Al agregar una columna a un
  modelo existente, agregá también su `ALTER TABLE` ahí.
- `DATABASE_URL` con prefijo `postgres://` se normaliza a `postgresql://`.
- Auth: obtener el usuario con `get_user_from_request(request, db)`.
- Diseño: tokens de color/tema como variables CSS en `base.html` (no hardcodear
  colores en cada template).
