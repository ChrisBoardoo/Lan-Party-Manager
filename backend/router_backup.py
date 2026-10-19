from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
import io, logging, os, queue, tarfile, shutil, tempfile, threading, time, zlib
from datetime import datetime

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


def _backup_entries():
    """(path, name in the archive) of everything a backup holds: the database,
    then the uploads tree, directories included, in a stable order."""
    if os.path.exists(DB_PATH):
        yield DB_PATH, "lanparty.db"
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


def _backup_size_estimate() -> int:
    """Bytes the archive will roughly weigh: what it holds, uncompressed. Media
    barely compresses, so it's close — the admin's progress bar runs on it."""
    db = os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0
    return db + (_dir_size(UPLOAD_DIR) if os.path.isdir(UPLOAD_DIR) else 0)


def _stream_backup():
    """Yield the .tar.gz as it's being built."""
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
                for path, arcname in _backup_entries():
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

    _checkpoint_wal()
    threading.Thread(target=produce, daemon=True).start()
    try:
        while True:
            item = chunks.get()
            if item is done:
                return
            yield item
    finally:
        stop.set()


@router.get("/export")
def export_backup(_: User = Depends(require_admin)):
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    return StreamingResponse(
        _stream_backup(),
        media_type="application/gzip",
        headers={
            "Content-Disposition": f'attachment; filename="lanparty_backup_{timestamp}.tar.gz"',
            # No Content-Length for an archive built on the fly: this is what the
            # admin's progress bar measures against (Settings → backup modal).
            "X-Backup-Estimate": str(_backup_size_estimate()),
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
