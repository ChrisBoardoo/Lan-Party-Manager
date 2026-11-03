"""Gallery photos (1.5.1): metadata stripping and grid thumbnails.

The strip has to be *lossless* — these are the crew's originals, rewritten in
place by the startup catch-up — so the tests compare decoded pixels, not just
"it still opens". And it has to keep what draws the photo right: a phone photo
stored on its side with an orientation tag must not come out sideways.
"""
import io
import os
import struct

from PIL import Image, ImageCms, PngImagePlugin

import database
import media_photos
import models
import uploads
from conftest import auth_header, login, make_user

GPS = {1: "N", 2: (48.0, 51.0, 24.0), 3: "E", 4: (2.0, 21.0, 3.0)}


def _exif(orientation=6, gps=True) -> bytes:
    exif = Image.Exif()
    exif[0x0112] = orientation
    exif[0x010F] = "PhoneMaker"
    if gps:
        exif[0x8825] = GPS
    return exif.tobytes()


def _icc() -> bytes:
    return ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()


def _picture(size=(96, 64)) -> Image.Image:
    """Not a flat colour (a re-encode would change pixels), and deterministic."""
    return Image.merge("RGB", [
        Image.linear_gradient("L").resize(size),
        Image.radial_gradient("L").resize(size),
        Image.linear_gradient("L").rotate(90).resize(size),
    ])


def _jpeg(size=(96, 64), orientation=6, gps=True, **save) -> bytes:
    buf = io.BytesIO()
    _picture(size).save(buf, "JPEG", quality=90, exif=_exif(orientation, gps), icc_profile=_icc(), **save)
    return buf.getvalue()


def _segment(marker: int, payload: bytes) -> bytes:
    return bytes((0xFF, marker)) + struct.pack(">H", len(payload) + 2) + payload


def _with_extras(jpeg: bytes) -> bytes:
    """XMP, IPTC and a comment after SOI, and a second image after EOI (the way
    MPF appends a gain map or depth map, with an EXIF of its own)."""
    xmp = _segment(0xE1, b"http://ns.adobe.com/xap/1.0/\x00<x:xmpmeta>exif:GPSLatitude=48,51</x:xmpmeta>")
    iptc = _segment(0xED, b"Photoshop 3.0\x008BIM city=Paris")
    com = _segment(0xFE, b"taken at home")
    trailer = b"\xff\xd8" + _segment(0xE1, b"Exif\x00\x00GPS-of-the-second-image") + b"\xff\xd9"
    return jpeg[:2] + xmp + iptc + com + jpeg[2:] + trailer


def _pixels(data: bytes) -> bytes:
    with Image.open(io.BytesIO(data)) as im:
        return im.convert("RGB").tobytes()


def _has_gps(data: bytes) -> bool:
    with Image.open(io.BytesIO(data)) as im:
        return bool(im.getexif().get_ifd(0x8825))


# ── strip_metadata: JPEG ──────────────────────────────────────────────────────

def test_jpeg_loses_gps_xmp_iptc_comment_and_trailer_but_not_a_pixel():
    original = _with_extras(_jpeg())
    cleaned = media_photos.strip_metadata(original)

    assert _has_gps(original) and not _has_gps(cleaned)
    for leak in (b"GPSLatitude", b"city=Paris", b"taken at home", b"PhoneMaker", b"second-image"):
        assert leak in original and leak not in cleaned
    assert _pixels(cleaned) == _pixels(original)
    assert cleaned.endswith(b"\xff\xd9")


def test_jpeg_keeps_its_orientation_and_colour_profile():
    cleaned = media_photos.strip_metadata(_jpeg(orientation=6))
    with Image.open(io.BytesIO(cleaned)) as im:
        assert im.getexif().get(0x0112) == 6
        assert im.info.get("icc_profile") == _icc()


def test_an_upright_jpeg_gets_no_exif_block_at_all():
    original = _jpeg(orientation=1)
    cleaned = media_photos.strip_metadata(original)
    assert b"Exif\x00\x00" not in cleaned
    assert _pixels(cleaned) == _pixels(original)


def test_progressive_and_restart_marker_jpegs_survive_byte_for_byte():
    for extra in ({"progressive": True}, {"restart_marker_blocks": 1}):
        original = _jpeg(size=(160, 120), **extra)
        cleaned = media_photos.strip_metadata(original)
        assert not _has_gps(cleaned)
        assert _pixels(cleaned) == _pixels(original), extra


def test_stripping_twice_changes_nothing_more():
    once = media_photos.strip_metadata(_with_extras(_jpeg()))
    assert media_photos.strip_metadata(once) == once


def test_a_broken_jpeg_is_stored_as_uploaded():
    broken = _jpeg()[:40]  # cut inside the EXIF segment
    assert media_photos.strip_metadata(broken) == broken


# ── strip_metadata: PNG, WebP, GIF ────────────────────────────────────────────

def test_png_loses_its_exif_and_text_chunks_but_not_a_pixel():
    info = PngImagePlugin.PngInfo()
    info.add_text("Location", "48.85,2.35")
    info.add_itxt("XML:com.adobe.xmp", "<x:xmpmeta>GPS</x:xmpmeta>")
    buf = io.BytesIO()
    _picture().save(buf, "PNG", exif=_exif(), pnginfo=info)
    original = buf.getvalue()

    cleaned = media_photos.strip_metadata(original)

    for chunk in (b"eXIf", b"tEXt", b"iTXt"):
        assert chunk in original and chunk not in cleaned
    assert _pixels(cleaned) == _pixels(original)


def test_webp_loses_its_exif_chunk_and_flag():
    buf = io.BytesIO()
    _picture().save(buf, "WEBP", lossless=True, exif=_exif())
    original = buf.getvalue()

    cleaned = media_photos.strip_metadata(original)

    assert b"EXIF" in original and b"EXIF" not in cleaned
    assert struct.unpack("<I", cleaned[4:8])[0] == len(cleaned) - 8
    if cleaned[12:16] == b"VP8X":
        assert cleaned[20] & 0x08 == 0
    assert _pixels(cleaned) == _pixels(original)


def test_gif_is_left_alone():
    buf = io.BytesIO()
    _picture().convert("P").save(buf, "GIF")
    assert media_photos.strip_metadata(buf.getvalue()) == buf.getvalue()


# ── make_thumbnail ────────────────────────────────────────────────────────────

def test_thumbnail_is_an_upright_small_webp_without_exif():
    # Stored 1200x900 on its side (orientation 6): displayed 900x1200.
    thumb = media_photos.make_thumbnail(media_photos.strip_metadata(_jpeg(size=(1200, 900))))

    with Image.open(io.BytesIO(thumb)) as im:
        assert im.format == "WEBP"
        assert im.size == (600, 800)  # upright, short side 600
        assert not im.getexif()
        assert im.info.get("icc_profile") == _icc()


def test_a_small_photo_is_not_upscaled():
    with Image.open(io.BytesIO(media_photos.make_thumbnail(_jpeg(size=(320, 200), orientation=1)))) as im:
        assert im.size == (320, 200)


def test_a_panorama_is_capped_on_its_long_side():
    with Image.open(io.BytesIO(media_photos.make_thumbnail(_jpeg(size=(3000, 500), orientation=1)))) as im:
        assert im.size == (1200, 200)


def test_a_transparent_png_keeps_its_alpha():
    buf = io.BytesIO()
    Image.new("RGBA", (800, 800), (255, 0, 0, 0)).save(buf, "PNG")
    with Image.open(io.BytesIO(media_photos.make_thumbnail(buf.getvalue()))) as im:
        assert im.mode == "RGBA" and im.size == (600, 600)


def test_no_thumbnail_for_what_cant_be_decoded():
    assert media_photos.make_thumbnail(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64) is None


# ── Upload ────────────────────────────────────────────────────────────────────

def _upload(client, content, name="photo.jpg", mime="image/jpeg"):
    make_user("snap")
    tok = login(client, "snap")
    resp = client.post("/api/media/upload", files={"file": (name, content, mime)}, headers=auth_header(tok))
    assert resp.status_code == 200, resp.text
    return resp.json(), tok


def _disk(url: str) -> str:
    return os.path.join(uploads.UPLOAD_DIR, *url.removeprefix("/uploads/").split("/"))


def test_an_uploaded_photo_is_stored_without_gps_and_gets_a_thumbnail(client):
    original = _with_extras(_jpeg(size=(1200, 900)))
    item, _ = _upload(client, original)

    with open(_disk(item["url"]), "rb") as f:
        stored = f.read()
    assert not _has_gps(stored) and b"GPSLatitude" not in stored
    assert _pixels(stored) == _pixels(original)
    assert item["file_size"] == len(stored)

    assert item["thumbnail_url"].startswith("/uploads/thumbnails/thumb_media_")
    with Image.open(_disk(item["thumbnail_url"])) as im:
        assert im.format == "WEBP" and im.size == (600, 800)


def test_deleting_a_photo_removes_its_thumbnail(client):
    item, tok = _upload(client, _jpeg())
    thumb = _disk(item["thumbnail_url"])
    assert os.path.exists(thumb)

    assert client.delete(f"/api/media/{item['id']}", headers=auth_header(tok)).status_code == 200

    assert not os.path.exists(thumb)
    assert not os.path.exists(_disk(item["url"]))


# ── Startup catch-up ──────────────────────────────────────────────────────────

def _stored(filename, content, file_type="image"):
    media_dir = os.path.join(uploads.UPLOAD_DIR, "media")
    os.makedirs(media_dir, exist_ok=True)
    with open(os.path.join(media_dir, filename), "wb") as f:
        f.write(content)
    uid = make_user(f"u_{filename.split('.')[0]}")
    session = database.SessionLocal()
    try:
        item = models.MediaItem(
            filename=filename, original_name=filename, file_type=file_type,
            mime_type="image/jpeg" if file_type == "image" else "video/mp4",
            file_size=len(content), url=f"/uploads/media/{filename}", uploaded_by=uid,
        )
        session.add(item)
        session.commit()
        return item.id
    finally:
        session.close()


def _row(media_id):
    session = database.SessionLocal()
    try:
        return session.get(models.MediaItem, media_id)
    finally:
        session.close()


def test_catch_up_strips_and_thumbnails_photos_stored_before_1_5_1():
    original = _with_extras(_jpeg(size=(1200, 900)))
    media_id = _stored("media_1_old.jpg", original)

    media_photos.backfill_photos()

    row = _row(media_id)
    assert row.thumbnail_url == "/uploads/thumbnails/thumb_media_1_old.webp"
    assert os.path.exists(_disk(row.thumbnail_url))
    with open(_disk(row.url), "rb") as f:
        stored = f.read()
    assert not _has_gps(stored)
    assert _pixels(stored) == _pixels(original)
    assert row.file_size == len(stored) < len(original)


def test_catch_up_is_a_no_op_the_second_time():
    media_id = _stored("media_1_twice.jpg", _jpeg())
    media_photos.backfill_photos()
    path = _disk(_row(media_id).url)
    before = os.stat(path).st_mtime_ns

    media_photos.backfill_photos()

    assert os.stat(path).st_mtime_ns == before


def test_catch_up_skips_videos_and_missing_files():
    video_id = _stored("media_1_clip.mp4", b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 32, file_type="video")
    gone_id = _stored("media_1_gone.jpg", _jpeg())
    os.remove(_disk(_row(gone_id).url))

    media_photos.backfill_photos()

    assert _row(video_id).thumbnail_url is None
    assert _row(gone_id).thumbnail_url is None


def test_catch_up_leaves_a_photo_it_cant_decode_untouched():
    junk = b"\xff\xd8\xff\xe0" + b"\x00" * 64
    media_id = _stored("media_1_junk.jpg", junk)

    media_photos.backfill_photos()

    assert _row(media_id).thumbnail_url is None
    with open(_disk(_row(media_id).url), "rb") as f:
        assert f.read() == junk
