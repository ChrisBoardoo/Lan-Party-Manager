import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import text
from sqlalchemy.orm import Session
import os

from database import SessionLocal, get_db
from db_migrate import run_migrations
from limiter import limiter
import models
from router_settings import get_setting
from discord_notify import send_event_reminders
from backup_scheduler import run_scheduled_backup

logger = logging.getLogger(__name__)
from router_auth import router as auth_router
from router_users import router as users_router
from router_expenses import router as expenses_router
from router_tournaments import router as tournaments_router
from router_events import router as events_router
from router_streams import router as streams_router
from router_media import router as media_router
from router_sponsors import router as sponsors_router
from router_prizes import router as prizes_router
from router_planning import router as planning_router
from router_presence import router as presence_router
from router_announcements import router as announcements_router
from router_kiosk import router as kiosk_router
from router_gear import router as gear_router
from router_groceries import router as groceries_router
from router_recap import router as recap_router
from router_setup import router as setup_router
from router_checklist import router as checklist_router
from router_minigames import router as minigames_router
from router_games import router as games_router
from router_settings import router as settings_router
from router_activity import router as activity_router
from router_audit import router as audit_router
from router_backup import router as backup_router
from router_chat import router as chat_router
from router_trophies import router as trophies_router
from router_lol import router as lol_router

# Ensure required directories exist
os.makedirs("data", exist_ok=True)
upload_base = os.getenv("UPLOAD_DIR", "./uploads")
os.makedirs(upload_base, exist_ok=True)
os.makedirs(os.path.join(upload_base, "media"), exist_ok=True)

# Bring the database schema up to date via Alembic (safely adopts pre-Alembic
# databases at the baseline revision — see db_migrate.py).
run_migrations()


@asynccontextmanager
async def lifespan(app: FastAPI):
    from zoneinfo import ZoneInfo

    db = SessionLocal()
    try:
        tz_name = get_setting(db, "app_timezone") or "UTC"
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            logger.warning("Invalid app_timezone %r at startup, falling back to UTC", tz_name)
            tz = ZoneInfo("UTC")
    finally:
        db.close()

    scheduler = BackgroundScheduler()
    scheduler.add_job(send_event_reminders, CronTrigger(hour=10, minute=0, timezone=tz))
    if os.getenv("BACKUP_ENABLED", "true").lower() not in ("0", "false", "no"):
        # Off-hours by default (03:00) — the daily reminder job above runs at 10:00,
        # and neither should land during a LAN party's peak activity window.
        scheduler.add_job(run_scheduled_backup, CronTrigger(hour=3, minute=0, timezone=tz))
    scheduler.start()
    app.state.scheduler = scheduler

    yield

    scheduler.shutdown(wait=False)


app = FastAPI(title="LAN Party Manager API", version="1.3.3", lifespan=lifespan)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

_raw_origins = os.getenv("CORS_ORIGINS", "http://localhost:3001")
_cors_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router,        prefix="/api/auth",        tags=["Auth"])
app.include_router(users_router,       prefix="/api/users",       tags=["Users"])
app.include_router(expenses_router,    prefix="/api/expenses",    tags=["Expenses"])
app.include_router(tournaments_router, prefix="/api/tournaments", tags=["Tournaments"])
app.include_router(events_router,      prefix="/api/events",      tags=["Events"])
app.include_router(streams_router,     prefix="/api/streams",     tags=["Streams"])
app.include_router(media_router,       prefix="/api/media",       tags=["Media"])
app.include_router(sponsors_router,    prefix="/api/sponsors",    tags=["Sponsors"])
app.include_router(prizes_router,      prefix="/api/prizes",      tags=["Prizes"])
app.include_router(planning_router,    prefix="/api/planning",    tags=["Planning"])
app.include_router(presence_router,    prefix="/api/presence",    tags=["Presence"])
app.include_router(announcements_router, prefix="/api/announcements", tags=["Announcements"])
app.include_router(kiosk_router,       prefix="/api/kiosk",       tags=["Kiosk"])
app.include_router(gear_router,        prefix="/api/gear",        tags=["Gear"])
app.include_router(groceries_router,   prefix="/api/groceries",   tags=["Groceries"])
app.include_router(recap_router,       prefix="/api/recap",       tags=["Recap"])
app.include_router(setup_router,       prefix="/api/setup",       tags=["Setup"])
app.include_router(checklist_router,   prefix="/api/checklist",   tags=["Checklist"])
app.include_router(minigames_router,   prefix="/api/minigames",   tags=["MiniGames"])
app.include_router(games_router,       prefix="/api/games",       tags=["Games"])
app.include_router(settings_router,    prefix="/api/settings",    tags=["Settings"])
app.include_router(activity_router,    prefix="/api/activity",    tags=["Activity"])
app.include_router(chat_router,        prefix="/api/chat",        tags=["Chat"])
app.include_router(trophies_router,    prefix="/api/trophies",    tags=["Trophies"])
app.include_router(lol_router,         prefix="/api/lol",         tags=["LoL"])
app.include_router(audit_router,       prefix="/api/audit",       tags=["Audit"])
app.include_router(backup_router,      prefix="/api/backup",      tags=["Backup"])


@app.get("/")
def root():
    return {"status": "LAN Party Manager API is running"}


@app.get("/health")
def health(db: Session = Depends(get_db)):
    """Liveness/readiness probe for Docker's `healthcheck:` (and any external
    monitoring) — actually touches the database rather than just returning a
    static 200, so a locked/corrupted SQLite file is caught as unhealthy too,
    not just "the process is still running"."""
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database unavailable: {e}")
