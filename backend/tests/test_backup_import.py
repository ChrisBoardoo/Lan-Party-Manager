"""Backup import: `_extract_safely` keeps every member inside the destination."""

import io
import os
import tarfile

import pytest
from fastapi import HTTPException

from router_backup import _extract_safely


def _archive(members):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, data in members:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    buf.seek(0)
    return tarfile.open(fileobj=buf, mode="r:gz")


def _files_under(root):
    return sorted(
        os.path.relpath(os.path.join(d, f), root).replace("\\", "/")
        for d, _, files in os.walk(root) for f in files
    )


def test_regular_backup_is_extracted(tmp_path):
    dest = tmp_path / "dest"
    dest.mkdir()
    with _archive([("lanparty.db", b"db"), ("uploads/media/a.webp", b"img")]) as tar:
        _extract_safely(tar, str(dest))
    assert _files_under(dest) == ["lanparty.db", "uploads/media/a.webp"]


def test_absolute_member_name_stays_inside_dest(tmp_path):
    # "/uploads/../<somewhere>" passed the name check (leading "/" stripped)
    # but used to be extracted under its raw, absolute name.
    dest = tmp_path / "dest"
    dest.mkdir()
    escape = tmp_path / "escaped.txt"
    rel = os.path.splitdrive(str(escape))[1].replace("\\", "/").lstrip("/")
    with _archive([("lanparty.db", b"db"), ("/uploads/../" + rel, b"x")]) as tar:
        try:
            _extract_safely(tar, str(dest))
        except (HTTPException, tarfile.TarError):
            pass
    assert not escape.exists()
    for root, _, files in os.walk(tmp_path):
        assert root.startswith(str(dest)) or not files or root == str(tmp_path)


def test_dotdot_member_is_skipped(tmp_path):
    dest = tmp_path / "dest"
    dest.mkdir()
    with _archive([("lanparty.db", b"db"), ("uploads/../../evil.txt", b"x")]) as tar:
        _extract_safely(tar, str(dest))
    assert not (tmp_path / "evil.txt").exists()
    assert _files_under(dest) == ["lanparty.db"]


def test_archive_without_database_is_refused(tmp_path):
    with _archive([("uploads/a.webp", b"img")]) as tar:
        with pytest.raises(HTTPException):
            _extract_safely(tar, str(tmp_path))


# ── Export: streamed while it's built, readable by the import ─────────────────

def test_export_streams_a_tar_gz_the_import_accepts(client, tmp_path, monkeypatch):
    import router_backup
    from conftest import auth_header, login, make_user

    db = tmp_path / "lanparty.db"
    db.write_bytes(router_backup.SQLITE_MAGIC + b"\x00" * 100)
    uploads = tmp_path / "uploads"
    (uploads / "media").mkdir(parents=True)
    (uploads / "media" / "clip.mp4").write_bytes(os.urandom(600_000))  # several chunks, incompressible
    (uploads / "avatar_1.webp").write_bytes(b"img")
    monkeypatch.setattr(router_backup, "DB_PATH", str(db))
    monkeypatch.setattr(router_backup, "UPLOAD_DIR", str(uploads))

    make_user("boss", role="admin")
    make_user("member")
    assert client.get("/api/backup/export", headers=auth_header(login(client, "member"))).status_code == 403

    resp = client.get("/api/backup/export", headers=auth_header(login(client, "boss")))
    assert resp.status_code == 200
    assert int(resp.headers["X-Backup-Estimate"]) == 116 + 600_000 + 3
    body = resp.content
    assert len(body) >= 600_000  # media stays about its size

    dest = tmp_path / "restored"
    dest.mkdir()
    with tarfile.open(fileobj=io.BytesIO(body), mode="r:gz") as tar:
        _extract_safely(tar, str(dest))
    assert _files_under(dest) == ["lanparty.db", "uploads/avatar_1.webp", "uploads/media/clip.mp4"]
    assert (dest / "uploads" / "media" / "clip.mp4").read_bytes() == (uploads / "media" / "clip.mp4").read_bytes()


# ── Import: raw body, admin checked first, streamed to disk ──────────────────

def _restore_env(tmp_path, monkeypatch):
    import router_backup

    db = tmp_path / "live" / "lanparty.db"
    db.parent.mkdir()
    db.write_bytes(router_backup.SQLITE_MAGIC + b"old")
    uploads = tmp_path / "live" / "uploads"
    uploads.mkdir()
    (uploads / "old.webp").write_bytes(b"old")
    monkeypatch.setattr(router_backup, "DB_PATH", str(db))
    monkeypatch.setattr(router_backup, "UPLOAD_DIR", str(uploads))
    restarts = []
    monkeypatch.setattr(router_backup, "_schedule_restart", lambda: restarts.append(True))
    return db, uploads, restarts


def _backup_bytes(files):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, data in files:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def _post(client, token, body):
    from conftest import auth_header

    return client.post("/api/backup/import", content=body,
                       headers={**auth_header(token), "Content-Type": "application/gzip"})


def test_import_restores_a_raw_tar_gz_bigger_than_the_old_cap(client, tmp_path, monkeypatch):
    import router_backup
    from conftest import login, make_user

    db, uploads, restarts = _restore_env(tmp_path, monkeypatch)
    make_user("boss", role="admin")
    big = os.urandom(3_000_000)  # stands in for "bigger than nginx used to allow"
    body = _backup_bytes([("lanparty.db", router_backup.SQLITE_MAGIC + b"new"), ("uploads/media/clip.mp4", big)])

    resp = _post(client, login(client, "boss"), body)
    assert resp.status_code == 200, resp.text
    assert resp.json()["restarting"] is True and restarts == [True]
    assert db.read_bytes().endswith(b"new")
    assert (db.parent / "lanparty.db.pre-restore.bak").read_bytes().endswith(b"old")
    assert sorted(os.listdir(uploads)) == ["media"]
    assert (uploads / "media" / "clip.mp4").read_bytes() == big


def test_import_refuses_members_and_bad_archives_before_touching_anything(client, tmp_path, monkeypatch):
    import router_backup
    from conftest import login, make_user

    db, uploads, restarts = _restore_env(tmp_path, monkeypatch)
    make_user("boss", role="admin")
    make_user("member")
    good = _backup_bytes([("lanparty.db", router_backup.SQLITE_MAGIC + b"new")])

    assert _post(client, login(client, "member"), good).status_code == 403
    boss = login(client, "boss")
    assert _post(client, boss, b"PK\x03\x04 a zip").status_code == 400
    assert _post(client, boss, good[: len(good) // 2]).status_code == 400  # truncated
    assert _post(client, boss, _backup_bytes([("uploads/a.webp", b"x")])).status_code == 400  # no database

    assert db.read_bytes().endswith(b"old") and (uploads / "old.webp").exists() and restarts == []


def test_import_checks_free_space_first(client, tmp_path, monkeypatch):
    import router_backup
    from conftest import login, make_user

    db, _uploads, restarts = _restore_env(tmp_path, monkeypatch)
    make_user("boss", role="admin")
    monkeypatch.setattr(router_backup.shutil, "disk_usage", lambda _p: shutil_usage(free=10))
    body = _backup_bytes([("lanparty.db", router_backup.SQLITE_MAGIC + b"new")])
    resp = _post(client, login(client, "boss"), body)
    assert resp.status_code == 507
    assert db.read_bytes().endswith(b"old") and restarts == []


def shutil_usage(free):
    from collections import namedtuple

    return namedtuple("usage", "total used free")(free, 0, free)
