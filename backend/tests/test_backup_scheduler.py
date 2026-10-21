"""The nightly backup job (backup_scheduler.run_scheduled_backup).

Never tested until 1.4.1 (Q-12 of the 2026-10-20 review). Pinned here: the
archive holds a consistent database snapshot (the rows still in the -wal file
included — Q-4) and the uploads tree, it's written atomically, and only
KEEP_COUNT archives are kept.
"""
import io
import os
import sqlite3
import tarfile
import time

import backup_scheduler


def _real_db(path, rows=300):
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE rows(id INTEGER PRIMARY KEY, payload TEXT)")
    conn.executemany("INSERT INTO rows(payload) VALUES (?)", [(f"row {i}",) for i in range(rows)])
    conn.commit()
    return conn  # kept open so nothing checkpoints the -wal file


def _env(tmp_path, monkeypatch, keep=7):
    db = tmp_path / "data" / "lanparty.db"
    db.parent.mkdir()
    keeper = _real_db(db)
    uploads = tmp_path / "uploads" / "media"
    uploads.mkdir(parents=True)
    (uploads / "photo.webp").write_bytes(b"img" * 100)
    backups = tmp_path / "data" / "backups"
    monkeypatch.setattr(backup_scheduler, "DB_PATH", str(db))
    monkeypatch.setattr(backup_scheduler, "UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setattr(backup_scheduler, "BACKUP_DIR", str(backups))
    monkeypatch.setattr(backup_scheduler, "KEEP_COUNT", keep)
    return keeper, backups


def _archives(backups):
    return sorted(f for f in os.listdir(backups) if f.endswith(".tar.gz"))


def test_the_nightly_archive_holds_a_consistent_snapshot_and_the_uploads(tmp_path, monkeypatch):
    keeper, backups = _env(tmp_path, monkeypatch)
    backup_scheduler.run_scheduled_backup()
    names = _archives(backups)
    assert len(names) == 1 and names[0].startswith("lanparty_backup_")
    assert not [f for f in os.listdir(backups) if f.endswith(".tmp") or f.startswith("lanparty_snapshot_")]
    with tarfile.open(os.path.join(backups, names[0]), mode="r:gz") as tar:
        members = sorted(m.name for m in tar.getmembers())
        assert members == ["lanparty.db", "uploads", "uploads/media", "uploads/media/photo.webp"]
        restored = tmp_path / "restored.db"
        restored.write_bytes(tar.extractfile("lanparty.db").read())
    conn = sqlite3.connect(str(restored))
    try:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("SELECT count(*) FROM rows").fetchone()[0] == 300  # -wal rows included
    finally:
        conn.close()
        keeper.close()


def test_only_keep_count_archives_survive(tmp_path, monkeypatch):
    keeper, backups = _env(tmp_path, monkeypatch, keep=2)
    backups.mkdir(parents=True)
    for stamp in ("20260101_030000", "20260102_030000", "20260103_030000"):
        (backups / f"lanparty_backup_{stamp}.tar.gz").write_bytes(b"old")
    (backups / "unrelated.txt").write_bytes(b"keep me")
    backup_scheduler.run_scheduled_backup()
    names = _archives(backups)
    assert len(names) == 2 and names[0] == "lanparty_backup_20260103_030000.tar.gz"
    assert names[1] > names[0]  # the new one, newest
    assert (backups / "unrelated.txt").exists()
    keeper.close()


def test_a_failure_is_logged_not_raised(tmp_path, monkeypatch, caplog):
    """The job runs in APScheduler's thread: an exception there would kill the
    scheduler and the daily reminders with it."""
    keeper, backups = _env(tmp_path, monkeypatch)
    monkeypatch.setattr(backup_scheduler, "BACKUP_DIR", str(tmp_path / "data" / "lanparty.db" / "impossible"))
    backup_scheduler.run_scheduled_backup()  # must not raise
    assert any("Scheduled backup failed" in r.message for r in caplog.records)
    keeper.close()
