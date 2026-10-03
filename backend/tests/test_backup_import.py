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
