import logging
import os
import tarfile
from datetime import datetime

from router_backup import DB_PATH, UPLOAD_DIR, _checkpoint_wal

logger = logging.getLogger(__name__)

BACKUP_DIR = os.path.abspath(os.getenv("BACKUP_DIR", "./data/backups"))
# Keep this modest by default — each snapshot includes the full uploads
# directory, and self-hosted installs (a Pi's SD card) have limited disk.
# Admins with room to spare can raise it via BACKUP_KEEP_COUNT.
KEEP_COUNT = int(os.getenv("BACKUP_KEEP_COUNT", "7"))


def run_scheduled_backup() -> None:
    """Daily snapshot of the SQLite db + uploads into BACKUP_DIR, keeping only
    the most recent KEEP_COUNT — the on-demand /api/backup/export download is
    great for "before I do something risky", but does nothing for the
    SD-card-dies-silently-between-manual-exports case a self-hosted Pi is
    actually exposed to. Runs from APScheduler (see main.py's _start_scheduler),
    so any exception here must be caught — an uncaught one would kill the
    scheduler thread and silently take the daily reminder job down with it.
    """
    try:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        _checkpoint_wal()

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(BACKUP_DIR, f"lanparty_backup_{timestamp}.tar.gz")
        tmp_path = path + ".tmp"

        with tarfile.open(tmp_path, mode="w:gz") as tar:
            if os.path.exists(DB_PATH):
                tar.add(DB_PATH, arcname="lanparty.db")
            if os.path.exists(UPLOAD_DIR):
                tar.add(UPLOAD_DIR, arcname="uploads")
        os.replace(tmp_path, path)  # atomic — a reader never sees a half-written archive

        _prune_old_backups()
        logger.info("Scheduled backup written: %s", path)
    except Exception:
        logger.exception("Scheduled backup failed")


def _prune_old_backups() -> None:
    entries = sorted(
        (f for f in os.listdir(BACKUP_DIR) if f.startswith("lanparty_backup_") and f.endswith(".tar.gz")),
    )
    for stale in entries[:-KEEP_COUNT] if KEEP_COUNT > 0 else []:
        try:
            os.remove(os.path.join(BACKUP_DIR, stale))
        except OSError:
            pass
