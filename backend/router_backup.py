from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
import io, os, tarfile, shutil, tempfile, threading, time
from datetime import datetime

from models import User
from auth import require_admin
from database import engine

router = APIRouter()

DB_PATH = os.path.abspath("./data/lanparty.db")
UPLOAD_DIR = os.path.abspath(os.getenv("UPLOAD_DIR", "./uploads"))
SQLITE_MAGIC = b"SQLite format 3\x00"


def _dir_size(path: str) -> int:
    """Total bytes on disk under `path` — media (and avatars/thumbnails) are the
    one thing in this app that grows without an obvious ceiling, unlike the
    SQLite db. A plain os.walk is fine at self-hosted-LAN-party scale; this is
    an admin-only, on-demand read, not a hot path."""
    total = 0
    for dirpath, _dirnames, filenames in os.walk(path):
        for name in filenames:
            try:
                total += os.path.getsize(os.path.join(dirpath, name))
            except OSError:
                pass  # deleted mid-walk / broken symlink — skip, don't fail the whole read
    return total


def _checkpoint_wal() -> None:
    """Fold any pending WAL transactions back into the main .db file so a copy of
    lanparty.db alone is a complete snapshot (WAL mode keeps recent commits in a
    separate -wal file that a plain file copy would otherwise miss)."""
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
    except Exception:
        # A checkpoint failure shouldn't block a backup — worst case the -wal
        # sidecar simply isn't folded in yet; the export still captures the db file.
        pass


@router.get("/storage")
def storage_stats(_: User = Depends(require_admin)):
    """Disk space on the volume backing UPLOAD_DIR — media is the one thing in
    this app that can quietly fill a disk over the course of an event, unlike
    the SQLite db. Falls back to "/" if uploads hasn't been created yet (a
    brand-new install before the first upload)."""
    disk_path = UPLOAD_DIR if os.path.isdir(UPLOAD_DIR) else "/"
    total, used, free = shutil.disk_usage(disk_path)
    return {
        "disk_total": total,
        "disk_used": used,
        "disk_free": free,
        "uploads_size": _dir_size(UPLOAD_DIR) if os.path.isdir(UPLOAD_DIR) else 0,
    }


@router.get("/export")
def export_backup(_: User = Depends(require_admin)):
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    def stream():
        _checkpoint_wal()
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            if os.path.exists(DB_PATH):
                tar.add(DB_PATH, arcname="lanparty.db")
            if os.path.exists(UPLOAD_DIR):
                tar.add(UPLOAD_DIR, arcname="uploads")
        buf.seek(0)
        while True:
            chunk = buf.read(65536)
            if not chunk:
                break
            yield chunk

    return StreamingResponse(
        stream(),
        media_type="application/gzip",
        headers={
            "Content-Disposition": f'attachment; filename="lanparty_backup_{timestamp}.tar.gz"'
        },
    )


def _extract_safely(tar: tarfile.TarFile, dest: str) -> None:
    """Extract only `lanparty.db` and files under `uploads/`, rejecting anything
    that would escape `dest` (absolute paths, `..`, symlinks, devices)."""
    safe = []
    for m in tar.getmembers():
        name = m.name.replace("\\", "/").lstrip("/")
        # Extract under the name that was checked, not the raw one: the raw
        # name may be absolute ("/uploads/../app/main.py"), which tarfile would
        # write as is and land outside `dest`.
        m.name = name
        if name != "lanparty.db" and name != "uploads" and not name.startswith("uploads/"):
            continue
        if not (m.isfile() or m.isdir()):
            continue  # skip symlinks, hardlinks, devices
        target = os.path.normpath(os.path.join(dest, name))
        if target != dest and not target.startswith(dest + os.sep):
            continue  # path traversal attempt
        safe.append(m)
    if not any(m.name == "lanparty.db" for m in safe):
        raise HTTPException(400, "Backup archive does not contain lanparty.db")
    # filter="data" (3.11.4+) is tarfile's own guard against the same family:
    # absolute paths, `..`, links and special files raise instead of escaping.
    tar.extractall(dest, members=safe, filter="data")


@router.post("/import")
async def import_backup(file: UploadFile = File(...), _: User = Depends(require_admin)):
    """Restore a backup produced by /export. Replaces the SQLite database and the
    uploads directory, then exits the process so the container (restart: unless-stopped)
    reopens the restored database cleanly — swapping the db file under the live engine
    while WAL sidecars are open is not safe to keep serving from."""
    if not (file.filename or "").lower().endswith((".tar.gz", ".tgz")):
        raise HTTPException(400, "Expected a .tar.gz backup file")

    data = await file.read()

    with tempfile.TemporaryDirectory() as tmp:
        try:
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
                _extract_safely(tar, tmp)
        except tarfile.TarError:
            raise HTTPException(400, "Invalid or corrupted backup archive")

        new_db = os.path.join(tmp, "lanparty.db")
        with open(new_db, "rb") as f:
            if f.read(16) != SQLITE_MAGIC:
                raise HTTPException(400, "lanparty.db in the archive is not a valid SQLite database")

        # Drop pooled connections before touching the file on disk.
        engine.dispose()

        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        if os.path.exists(DB_PATH):
            shutil.copy2(DB_PATH, DB_PATH + ".pre-restore.bak")
        # Unlink the old db + its WAL/SHM sidecars (the engine's open fd keeps the old
        # inode alive until the process exits), then write the restored db as a fresh file.
        for p in (DB_PATH, DB_PATH + "-wal", DB_PATH + "-shm"):
            if os.path.exists(p):
                os.remove(p)
        shutil.copy2(new_db, DB_PATH)

        # Replace uploads only if the archive actually included them.
        extracted_uploads = os.path.join(tmp, "uploads")
        if os.path.isdir(extracted_uploads):
            os.makedirs(UPLOAD_DIR, exist_ok=True)
            for entry in os.listdir(UPLOAD_DIR):
                full = os.path.join(UPLOAD_DIR, entry)
                if os.path.isdir(full) and not os.path.islink(full):
                    shutil.rmtree(full, ignore_errors=True)
                else:
                    try:
                        os.remove(full)
                    except OSError:
                        pass
            for entry in os.listdir(extracted_uploads):
                shutil.move(os.path.join(extracted_uploads, entry), os.path.join(UPLOAD_DIR, entry))

    # Respond, then exit so the container restarts against the restored database.
    def _delayed_exit():
        time.sleep(1.5)
        os._exit(0)

    threading.Thread(target=_delayed_exit, daemon=True).start()
    return {"ok": True, "restored_at": datetime.utcnow().isoformat() + "Z", "restarting": True}
