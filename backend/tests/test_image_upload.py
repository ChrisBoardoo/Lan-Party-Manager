"""The shared image-upload helper (``uploads.py``).

Worth stating plainly: **avatar upload had zero test coverage in this repo until
this file existed**, which is a large part of why it shipped uncapped, without a
decompression-bomb guard, and leaking the file it replaced for every release to
date.

These are unit-style like test_file_validation.py — the helper is exercised
directly rather than through a router, because the defects it fixes are in the
helper's contract, not in any one endpoint.
"""
import asyncio
import io
import os
import tempfile
from pathlib import Path

import pytest
from fastapi import HTTPException, UploadFile
from PIL import Image

import uploads


def _png_bytes(size=(20, 20), color=(255, 61, 0)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()


def _bmp_bytes(size=(20, 20)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (0, 0, 0)).save(buf, "BMP")
    return buf.getvalue()


def _upload(content: bytes, filename="x.png") -> UploadFile:
    return UploadFile(filename=filename, file=io.BytesIO(content))


@pytest.fixture
def upload_dir(monkeypatch):
    """Point the helper at a throwaway directory for the duration of a test."""
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setattr(uploads, "UPLOAD_DIR", tmp)
        yield tmp


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ── read_capped ───────────────────────────────────────────────────────────────

def test_read_capped_accepts_a_file_under_the_cap():
    content = b"x" * 100
    assert _run(uploads.read_capped(_upload(content), 1024)) == content


def test_read_capped_rejects_a_file_over_the_cap():
    with pytest.raises(HTTPException) as exc:
        _run(uploads.read_capped(_upload(b"x" * (3 * 1024 * 1024)), 1 * 1024 * 1024))
    assert exc.value.status_code == 400


def test_read_capped_message_reflects_the_limit_it_was_given():
    """The message used to hardcode "100 MB" while taking max_size as a param,
    so a 12 MB avatar cap reported itself as 100 MB."""
    with pytest.raises(HTTPException) as exc:
        _run(uploads.read_capped(_upload(b"x" * (3 * 1024 * 1024)), 2 * 1024 * 1024))
    assert "2 MB" in exc.value.detail
    assert "100 MB" not in exc.value.detail


# ── Format narrowing ──────────────────────────────────────────────────────────

def test_a_png_is_accepted(upload_dir):
    url = _run(uploads.save_image_upload(_upload(_png_bytes()), subdir=None, prefix="t", box=(50, 50)))
    assert url.startswith("/uploads/t_") and url.endswith(".webp")


def test_a_bmp_is_now_rejected(upload_dir):
    """Previously anything Pillow could open was accepted. The set is now four
    well-fuzzed decoders; a BMP is a real behavior change, not an oversight."""
    with pytest.raises(HTTPException) as exc:
        _run(uploads.save_image_upload(_upload(_bmp_bytes(), "x.bmp"), subdir=None, prefix="t", box=(50, 50)))
    assert exc.value.status_code == 400


def test_a_non_image_is_rejected(upload_dir):
    with pytest.raises(HTTPException) as exc:
        _run(uploads.save_image_upload(_upload(b"not an image at all, just bytes"), subdir=None, prefix="t", box=(50, 50)))
    assert exc.value.status_code == 400


# ── The decompression-bomb guard ──────────────────────────────────────────────

def test_an_oversized_image_is_rejected_by_pixel_count(upload_dir, monkeypatch):
    """The guard is the explicit w*h check, NOT Image.MAX_IMAGE_PIXELS.

    Pillow only *warns* between 1x and 2x its limit and raises only above 2x, so
    the global alone would silently admit up to 2x. Rather than allocate 30 MP in
    a test, drop the limit under a real image's size — this exercises the same
    branch, deterministically, in milliseconds.
    """
    monkeypatch.setattr(uploads, "MAX_IMAGE_PIXELS", 100)  # a 20x20 PNG is 400px
    with pytest.raises(HTTPException) as exc:
        _run(uploads.save_image_upload(_upload(_png_bytes((20, 20))), subdir=None, prefix="t", box=(50, 50)))
    assert exc.value.status_code == 400
    assert "megapixel" in exc.value.detail.lower() or "too large" in exc.value.detail.lower()


def test_an_image_at_the_pixel_limit_is_accepted(upload_dir, monkeypatch):
    monkeypatch.setattr(uploads, "MAX_IMAGE_PIXELS", 400)  # exactly 20x20
    url = _run(uploads.save_image_upload(_upload(_png_bytes((20, 20))), subdir=None, prefix="t", box=(50, 50)))
    assert url.endswith(".webp")


def test_the_oversized_image_leaves_no_file_behind(upload_dir, monkeypatch):
    monkeypatch.setattr(uploads, "MAX_IMAGE_PIXELS", 100)
    with pytest.raises(HTTPException):
        _run(uploads.save_image_upload(_upload(_png_bytes((20, 20))), subdir=None, prefix="t", box=(50, 50)))
    assert os.listdir(upload_dir) == []


# ── Re-encoding & storage ─────────────────────────────────────────────────────

def test_the_stored_file_is_webp_and_fits_the_box(upload_dir):
    url = _run(uploads.save_image_upload(_upload(_png_bytes((400, 200))), subdir=None, prefix="t", box=(100, 100)))
    path = os.path.join(upload_dir, os.path.basename(url))
    with Image.open(path) as im:
        assert im.format == "WEBP"
        assert im.size == (100, 50)  # aspect preserved, fits inside the box


def test_a_subdir_is_created_and_reflected_in_the_url(upload_dir):
    url = _run(uploads.save_image_upload(_upload(_png_bytes()), subdir="setup", prefix="s_1", box=(50, 50)))
    assert url.startswith("/uploads/setup/s_1_")
    assert os.path.exists(os.path.join(upload_dir, "setup", os.path.basename(url)))


# ── Deletion — the storage leak ───────────────────────────────────────────────

def test_saving_deletes_the_file_it_replaces(upload_dir):
    """Every avatar anyone ever changed used to stay on disk forever."""
    first = _run(uploads.save_image_upload(_upload(_png_bytes()), subdir=None, prefix="t", box=(50, 50)))
    first_path = os.path.join(upload_dir, os.path.basename(first))
    assert os.path.exists(first_path)

    second = _run(uploads.save_image_upload(
        _upload(_png_bytes()), subdir=None, prefix="t", box=(50, 50), replaces=first,
    ))
    assert not os.path.exists(first_path)
    assert os.path.exists(os.path.join(upload_dir, os.path.basename(second)))


def test_a_failed_save_does_not_delete_what_it_would_have_replaced(upload_dir):
    """`replaces` is removed only after the new file is on disk — a rejected
    upload must never cost you the image you still had."""
    first = _run(uploads.save_image_upload(_upload(_png_bytes()), subdir=None, prefix="t", box=(50, 50)))
    first_path = os.path.join(upload_dir, os.path.basename(first))

    with pytest.raises(HTTPException):
        _run(uploads.save_image_upload(
            _upload(b"garbage"), subdir=None, prefix="t", box=(50, 50), replaces=first,
        ))
    assert os.path.exists(first_path)


def test_remove_upload_on_a_missing_file_is_a_noop(upload_dir):
    uploads.remove_upload("/uploads/does_not_exist.webp", None)  # must not raise


def test_remove_upload_on_none_is_a_noop(upload_dir):
    uploads.remove_upload(None, None)  # must not raise


# ── Rotate ────────────────────────────────────────────────────────────────────

def test_rotate_returns_a_new_filename_and_deletes_the_source(upload_dir):
    """The new uuid is NOT waste — nginx serves /uploads/ as `immutable, 30d`,
    so the filename is the cache key. Rotating in place would leave browsers
    showing the old orientation for a month. Never 'optimize' this."""
    original = _run(uploads.save_image_upload(_upload(_png_bytes((40, 20))), subdir=None, prefix="t", box=(50, 50)))
    original_path = os.path.join(upload_dir, os.path.basename(original))

    rotated = uploads.rotate_image_file(original, subdir=None, prefix="t")

    assert rotated != original
    assert not os.path.exists(original_path)
    assert os.path.exists(os.path.join(upload_dir, os.path.basename(rotated)))


def test_rotate_actually_turns_the_image(upload_dir):
    original = _run(uploads.save_image_upload(_upload(_png_bytes((40, 20))), subdir=None, prefix="t", box=(100, 100)))
    rotated = uploads.rotate_image_file(original, subdir=None, prefix="t")
    with Image.open(os.path.join(upload_dir, os.path.basename(rotated))) as im:
        assert im.size == (20, 40)  # was 40x20


def test_rotate_on_a_missing_file_is_404(upload_dir):
    with pytest.raises(HTTPException) as exc:
        uploads.rotate_image_file("/uploads/gone.webp", subdir=None, prefix="t")
    assert exc.value.status_code == 404
