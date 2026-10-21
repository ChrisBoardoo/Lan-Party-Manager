from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
import io
import logging
import os
import queue
import sqlite3
import tarfile
import shutil
import tempfile
import threading
import time
import zlib
from datetime import datetime
from pathlib import Path

from models import User
from auth import require_admin
from database import engine

router = APIRouter()
logger = logging.getLogger(__name__)

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
    """Fold any pending WAL transactions back into the main .db file, so the
    -wal sidecar stays small. Not what makes a backup consistent any more —
    that's `_snapshot_db` — but still worth a line in the log when it fails:
    a checkpoint that can't run is a disk or lock problem worth knowing about."""
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
    except Exception as e:
        logger.warning("WAL checkpoint failed: %s", e)


def _snapshot_db(dest: str, src: str | None = None) -> None:
    """A consistent copy of the live database at `dest`, by SQLite's online
    backup API: writers carry on, the copy is one point in time — no torn copy,
    no commit left behind in the -wal file (Q-4 of the 2026-10-20 review: the
    old `tar.add(lanparty.db)` copied the live file after a checkpoint, and a
    write landing in between gave an archive that was out of date or wouldn't
    open). A file SQLite can't read (a corrupted database is exactly what an
    admin may want to export) is copied byte for byte instead."""
    src = src or DB_PATH
    try:
        source = sqlite3.connect(f"{Path(src).resolve().as_uri()}?mode=ro", uri=True)
        try:
            target = sqlite3.connect(dest)
            try:
                source.backup(target)
            finally:
                target.close()
        finally:
            source.close()
    except sqlite3.Error as e:
        logger.warning("SQLite backup API failed on %s (%s); copying the file as is", src, e)
        shutil.copyfile(src, dest)


def _snapshot_path() -> str:
    """A temp file next to the database (same volume, same permissions) for
    `_snapshot_db`; the caller removes it."""
    fd, path = tempfile.mkstemp(prefix="lanparty_snapshot_", suffix=".db", dir=os.path.dirname(DB_PATH) or None)
    os.close(fd)
    return path


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


# Photos and videos are already compressed: gzip -9 spent minutes of a Pi's CPU
# for nothing (a 200 MB backup took ~3 min, built before a byte was sent).
# Level 0 stores them as they are, still in the .tar.gz format /import expects.
# Measured on incompressible data: level 0 ~2400 MB/s and the same size; level
# 9 ~75 MB/s and the same size; level 1 ~125 MB/s but 5% *larger*. Only the
# database would shrink, and it weighs a few MB.
_GZIP_LEVEL = 0
# The archive is streamed while it's built: a producer thread writes the tar,
# the response sends it. At most this many chunks of _CHUNK_BYTES wait in
# between (~16 MB), so memory stays flat however big the uploads grow — the old
# export built the whole archive in RAM before sending its first byte.
_CHUNK_BYTES = 256 * 1024
_QUEUE_CHUNKS = 64


def _backup_entries(db_path: str):
    """(path, name in the archive) of everything a backup holds: the database
    snapshot, then the uploads tree, directories included, in a stable order."""
    if os.path.exists(db_path):
        yield db_path, "lanparty.db"
    if not os.path.isdir(UPLOAD_DIR):
        return
    yield UPLOAD_DIR, "uploads"
    for dirpath, dirnames, filenames in os.walk(UPLOAD_DIR):
        dirnames.sort()
        rel = os.path.relpath(dirpath, UPLOAD_DIR)
        base = "uploads" if rel == "." else "uploads/" + rel.replace(os.sep, "/")
        for name in dirnames:
            yield os.path.join(dirpath, name), f"{base}/{name}"
        for name in sorted(filenames):
            yield os.path.join(dirpath, name), f"{base}/{name}"


def _backup_size_estimate(db_path: str) -> int:
    """Bytes the archive will roughly weigh: what it holds, uncompressed. Media
    barely compresses, so it's close — the admin's progress bar runs on it.
    Measured on the snapshot: the live file alone is only the checkpointed
    part (7 KB for an 800 KB database, seen 2026-10-21), so the bar overshot."""
    db = os.path.getsize(db_path) if os.path.exists(db_path) else 0
    return db + (_dir_size(UPLOAD_DIR) if os.path.isdir(UPLOAD_DIR) else 0)


def _stream_backup(db_path: str):
    """Yield the .tar.gz as it's being built; `db_path` (a snapshot) is removed
    once the download ends or is dropped."""
    chunks: queue.Queue = queue.Queue(maxsize=_QUEUE_CHUNKS)
    stop = threading.Event()  # the download was dropped: stop building
    done = object()

    def put(item) -> bool:
        while not stop.is_set():
            try:
                chunks.put(item, timeout=1)
                return True
            except queue.Full:
                continue
        return False

    class _GzipSink(io.RawIOBase):
        """Where tarfile writes: gzip-compressed on the fly, handed over by chunk."""

        def __init__(self):
            self.gz = zlib.compressobj(_GZIP_LEVEL, zlib.DEFLATED, 16 + zlib.MAX_WBITS)
            self.pending = bytearray()

        def writable(self):
            return True

        def write(self, data):
            self.pending += self.gz.compress(bytes(data))
            if len(self.pending) >= _CHUNK_BYTES:
                self._hand_over()
            return len(data)

        def _hand_over(self):
            if self.pending and not put(bytes(self.pending)):
                raise OSError("backup download dropped")
            self.pending = bytearray()

        def finish(self):
            self.pending += self.gz.flush()
            self._hand_over()

    def produce():
        try:
            sink = _GzipSink()
            with tarfile.open(fileobj=sink, mode="w|") as tar:
                for path, arcname in _backup_entries(db_path):
                    if stop.is_set():
                        return
                    try:
                        tar.add(path, arcname=arcname, recursive=False)
                    except FileNotFoundError:
                        continue  # deleted while the backup ran
            sink.finish()
        except Exception:
            if not stop.is_set():
                logger.exception("Backup export failed midway; the archive sent is truncated")
        finally:
            put(done)

    threading.Thread(target=produce, daemon=True).start()
    try:
        while True:
            item = chunks.get()
            if item is done:
                return
            yield item
    finally:
        stop.set()
        try:
            os.remove(db_path)
        except OSError:
            pass


@router.get("/export")
def export_backup(_: User = Depends(require_admin)):
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    _checkpoint_wal()
    snapshot = _snapshot_path()
    try:
        if os.path.exists(DB_PATH):
            _snapshot_db(snapshot)
        else:
            os.remove(snapshot)
        estimate = _backup_size_estimate(snapshot)
    except Exception:
        try:
            os.remove(snapshot)
        except OSError:
            pass
        raise
    return StreamingResponse(
        _stream_backup(snapshot),
        media_type="application/gzip",
        headers={
            "Content-Disposition": f'attachment; filename="lanparty_backup_{timestamp}.tar.gz"',
            # No Content-Length for an archive built on the fly: this is what the
            # admin's progress bar measures against (Settings → backup modal).
            "X-Backup-Estimate": str(estimate),
            "Cache-Control": "no-store",
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


GZIP_MAGIC = b"\x1f\x8b"
# Room needed to restore: the archive itself, its extracted copy (media barely
# compresses, so about the same again), and a margin.
_RESTORE_MARGIN_BYTES = 64 * 1024 * 1024


@router.post("/import")
async def import_backup(request: Request, _: User = Depends(require_admin)):
    """Restore a backup produced by /export. Replaces the SQLite database and the
    uploads directory, then exits the process so the container (restart: unless-stopped)
    reopens the restored database cleanly — swapping the db file under the live engine
    while WAL sidecars are open is not safe to keep serving from.

    The archive is the raw request body (Content-Type application/gzip), not a
    multipart form: FastAPI parses a form *before* running dependencies, so any
    caller could have pushed gigabytes to the disk before being refused. Here
    require_admin runs first, then the body is streamed to a temp file — never
    held in RAM, whatever its size (nginx lets this one route through uncapped,
    see frontend/nginx.conf)."""
    tmp_root = tempfile.gettempdir()
    declared = int(request.headers.get("content-length") or 0)
    if declared and shutil.disk_usage(tmp_root).free < 2 * declared + _RESTORE_MARGIN_BYTES:
        raise HTTPException(507, "Not enough free disk space to restore this backup")

    with tempfile.TemporaryDirectory() as tmp:
        archive = os.path.join(tmp, "backup.tar.gz")
        with open(archive, "wb") as f:
            async for chunk in request.stream():
                f.write(chunk)
        await run_in_threadpool(_restore_from, archive, os.path.join(tmp, "extracted"))

    _schedule_restart()
    return {"ok": True, "restored_at": datetime.utcnow().isoformat() + "Z", "restarting": True}


def _schedule_restart() -> None:
    """Respond, then exit so the container (restart: unless-stopped) comes back
    against the restored database. Its own function so tests can stub it."""
    def _delayed_exit():
        time.sleep(1.5)
        os._exit(0)

    threading.Thread(target=_delayed_exit, daemon=True).start()


def _restore_from(archive: str, tmp: str) -> None:
    """Check, extract and swap in a backup archive. Blocking (disk and CPU for
    the length of the archive): run off the event loop. Nothing is touched until
    the archive has been fully read and checked."""
    with open(archive, "rb") as f:
        if f.read(2) != GZIP_MAGIC:
            raise HTTPException(400, "Expected a .tar.gz backup file")
    os.makedirs(tmp, exist_ok=True)
    try:
        with tarfile.open(archive, mode="r:gz") as tar:
            _extract_safely(tar, tmp)
    except (tarfile.TarError, EOFError, zlib.error, OSError):
        raise HTTPException(400, "Invalid or corrupted backup archive")
    os.remove(archive)  # its room is needed for the swap below

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
