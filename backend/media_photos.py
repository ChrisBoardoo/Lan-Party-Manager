"""Gallery photos: metadata stripping and grid thumbnails (1.5.1).

Both happen once per photo — at upload, or in the startup catch-up for photos
stored before 1.5.1 (and for an older backup restored over this version):

* ``strip_metadata`` — a phone photo carries EXIF and XMP, often with the GPS
  position it was taken at, and ``/uploads/`` is public (the recap share link
  shows the photos too). The strip is lossless: a JPEG's compressed scan data is
  copied byte for byte, never re-encoded. What it keeps is what the browser
  needs to draw the photo right — the colour profile (ICC) and the orientation.
* ``store_thumbnail`` — the grid used to load every original (1.7 MB on average,
  up to 7 MB, on the crew's instance) into a tile a couple of hundred pixels
  wide. A 600 px WebP is about 1/50th of that.

The lightbox and the kiosk keep showing the original; only grids and feeds use
the thumbnail, through ``MediaItem.thumbnail_url`` — the column videos already
used for their ffmpeg frame, so no migration.
"""
import io
import logging
import os
import struct
from typing import Optional

from PIL import Image, ImageOps
from sqlalchemy.orm.exc import StaleDataError

from database import SessionLocal
from models import MediaItem
from uploads import MAX_IMAGE_PIXELS, UPLOAD_DIR

logger = logging.getLogger(__name__)

# Shortest side of a thumbnail: a 2-column phone grid draws a tile ~180 CSS px
# wide at 3x, and the tiles crop to a square (object-cover), so it's the short
# side that has to hold up. Panoramas are capped on their long side.
THUMB_SHORT_SIDE = 600
THUMB_LONG_SIDE_MAX = 1200
THUMB_QUALITY = 75

# Pillow names a JPEG with an MPF block (the HDR gain map of recent phones)
# "MPO". Same decoder, same treatment.
_JPEG_FORMATS = ("JPEG", "MPO")


class _Malformed(ValueError):
    pass


# ── Metadata ──────────────────────────────────────────────────────────────────

def strip_metadata(data: bytes) -> bytes:
    """The same image without its EXIF/XMP/IPTC/comments, or `data` unchanged
    when there is nothing to strip or the structure can't be parsed (a photo
    stays uploadable even if this can't clean it). Never re-encodes."""
    try:
        if data.startswith(b"\xff\xd8"):
            return _strip_jpeg(data)
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            return _strip_png(data)
        if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            return _strip_webp(data)
    except (_Malformed, IndexError, struct.error):
        logger.warning("Could not parse a photo to strip its metadata; stored as uploaded")
    return data  # GIF carries no EXIF


def _orientation(exif_payload: Optional[bytes]) -> int:
    """The EXIF orientation (1-8) read from an APP1 payload — parsed on its
    own, without opening the image (no pixel-count guard to trip)."""
    if not exif_payload:
        return 1
    try:
        exif = Image.Exif()
        exif.load(exif_payload)
        value = exif.get(0x0112, 1)
    except Exception:
        return 1
    return value if isinstance(value, int) and 1 <= value <= 8 else 1


def _orientation_segment(orientation: int) -> bytes:
    """A minimal APP1 Exif segment holding the orientation and nothing else:
    big-endian TIFF header, one IFD with one SHORT entry, no next IFD."""
    tiff = b"MM\x00\x2a\x00\x00\x00\x08" + struct.pack(">H", 1)
    tiff += struct.pack(">HHIHH", 0x0112, 3, 1, orientation, 0) + b"\x00\x00\x00\x00"
    payload = b"Exif\x00\x00" + tiff
    return b"\xff\xe1" + struct.pack(">H", len(payload) + 2) + payload


def _keep_jpeg_segment(marker: int, payload: bytes) -> bool:
    if marker == 0xE0:                       # APP0 JFIF/JFXX: density, no metadata
        return True
    if marker == 0xE2:                       # APP2: the colour profile only, not MPF
        return payload.startswith(b"ICC_PROFILE\x00")
    if marker == 0xEE:                       # APP14 Adobe: colour transform, needed to decode
        return True
    if 0xE1 <= marker <= 0xEF or marker == 0xFE:
        return False                         # Exif, XMP, IPTC, vendor blocks, comments
    return True                              # tables, frame and scan headers


def _strip_jpeg(data: bytes) -> bytes:
    head: list[bytes] = []                   # kept segments before the first scan
    body = bytearray()                       # the first scan header onwards
    in_head = True
    exif_payload: Optional[bytes] = None
    n = len(data)
    i = 2
    while i < n:
        if data[i] != 0xFF:
            raise _Malformed("expected a marker")
        while data[i] == 0xFF:               # fill bytes
            i += 1
        marker = data[i]
        i += 1
        if marker == 0xD9:                   # EOI. What follows (MPF secondary
            body += b"\xff\xd9"              # images, with their own EXIF) goes.
            break
        if marker == 0x01 or 0xD0 <= marker <= 0xD7:
            (head.append if in_head else body.extend)(bytes((0xFF, marker)))
            continue
        length = struct.unpack(">H", data[i:i + 2])[0]
        end = i + length
        if length < 2 or end > n:
            raise _Malformed("segment runs past the end")
        payload = data[i + 2:end]
        segment = bytes((0xFF, marker)) + data[i:end]
        i = end
        if marker == 0xE1 and exif_payload is None and payload.startswith(b"Exif\x00\x00"):
            exif_payload = payload
        if marker != 0xDA:
            if _keep_jpeg_segment(marker, payload):
                (head.append if in_head else body.extend)(segment)
            continue
        # Start of scan: its header, then entropy-coded data up to the next
        # marker. In that data an 0xFF is always followed by 0x00 (stuffing),
        # a restart marker or another 0xFF (fill); anything else ends the scan.
        in_head = False
        body += segment
        j = i
        while True:
            k = data.find(b"\xff", j)
            if k == -1 or k + 1 >= n:        # truncated file: keep what's there
                body += data[i:]
                i = n
                break
            nxt = data[k + 1]
            if nxt == 0x00 or 0xD0 <= nxt <= 0xD7:
                j = k + 2
            elif nxt == 0xFF:
                j = k + 1
            else:
                body += data[i:k]
                i = k
                break
    if in_head:
        raise _Malformed("no scan")

    result = bytearray(b"\xff\xd8")
    rest = head
    if head and head[0][1] == 0xE0:          # Exif goes after JFIF's APP0, if there is one
        result += head[0]
        rest = head[1:]
    orientation = _orientation(exif_payload)
    if orientation != 1:
        result += _orientation_segment(orientation)
    for segment in rest:
        result += segment
    result += body
    return bytes(result)


_PNG_DROP = {b"eXIf", b"tEXt", b"zTXt", b"iTXt", b"tIME"}


def _strip_png(data: bytes) -> bytes:
    out = bytearray(data[:8])
    i, n = 8, len(data)
    while i < n:
        if i + 8 > n:
            raise _Malformed("chunk header past the end")
        length = struct.unpack(">I", data[i:i + 4])[0]
        ctype = data[i + 4:i + 8]
        end = i + 12 + length
        if end > n:
            raise _Malformed("chunk past the end")
        if ctype not in _PNG_DROP:
            out += data[i:end]
        i = end
        if ctype == b"IEND":
            break
    return bytes(out)


def _strip_webp(data: bytes) -> bytes:
    """Drop the EXIF and XMP chunks and clear their flags in VP8X. Browsers
    ignore EXIF orientation in WebP, so nothing visible is lost."""
    out = bytearray(b"RIFF\x00\x00\x00\x00WEBP")
    n = min(len(data), 8 + struct.unpack("<I", data[4:8])[0])
    i = 12
    while i + 8 <= n:
        fourcc = data[i:i + 4]
        size = struct.unpack("<I", data[i + 4:i + 8])[0]
        if i + 8 + size > n:
            raise _Malformed("chunk past the end")
        end = min(i + 8 + size + (size & 1), n)
        chunk = bytearray(data[i:end])
        i = end
        if fourcc in (b"EXIF", b"XMP "):
            continue
        if fourcc == b"VP8X" and size >= 1:
            chunk[8] &= 0xF3                 # clear the EXIF (0x08) and XMP (0x04) flags
        out += chunk
    out[4:8] = struct.pack("<I", len(out) - 8)
    return bytes(out)


def _same_picture(original: bytes, cleaned: bytes) -> bool:
    """Before a stored original is replaced by its stripped copy: same kind of
    file, same dimensions, and the copy decodes (at 1/8 size for a JPEG)."""
    def kind(fmt):
        return "JPEG" if fmt in _JPEG_FORMATS else fmt

    try:
        with Image.open(io.BytesIO(original)) as a, Image.open(io.BytesIO(cleaned)) as b:
            if (kind(a.format), a.size) != (kind(b.format), b.size):
                return False
            if b.format in _JPEG_FORMATS:
                b.draft("RGB", (max(1, b.size[0] // 8), max(1, b.size[1] // 8)))
            elif b.size[0] * b.size[1] > MAX_IMAGE_PIXELS:
                return True  # too big to decode here; the header matched
            b.load()
        return True
    except Exception:
        return False


# ── Thumbnails ────────────────────────────────────────────────────────────────

def make_thumbnail(data: bytes) -> Optional[bytes]:
    """A WebP of the photo, upright, its short side THUMB_SHORT_SIDE px at
    most — or None when it can't be made (the grid then shows the original).

    A JPEG is decoded straight at 1/2, 1/4 or 1/8 of its size (`draft`): a
    24 MP phone photo costs a few MB of memory instead of ~70, on a Pi that
    runs short of it. No EXIF in the result; the colour profile is kept.
    """
    try:
        with Image.open(io.BytesIO(data)) as im:
            icc = im.info.get("icc_profile")
            w, h = im.size
            scale = min(1.0, THUMB_SHORT_SIDE / min(w, h), THUMB_LONG_SIDE_MAX / max(w, h))
            if im.format in _JPEG_FORMATS:
                im.draft("RGB", (max(1, round(w * scale)), max(1, round(h * scale))))
            elif w * h > MAX_IMAGE_PIXELS:
                return None
            img = ImageOps.exif_transpose(im)  # a loaded copy; a GIF's first frame
        w, h = img.size
        scale = min(1.0, THUMB_SHORT_SIDE / min(w, h), THUMB_LONG_SIDE_MAX / max(w, h))
        if scale < 1.0:
            img = img.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.Resampling.LANCZOS)
        if img.mode not in ("RGB", "RGBA"):
            transparent = img.mode in ("LA", "PA") or (img.mode == "P" and "transparency" in img.info)
            img = img.convert("RGBA" if transparent else "RGB")
        buf = io.BytesIO()
        img.save(buf, "WEBP", quality=THUMB_QUALITY, exif=b"", icc_profile=icc or None)
        return buf.getvalue()
    except Exception:
        logger.warning("Could not make a thumbnail", exc_info=True)
        return None


def _thumb_name(media_filename: str) -> str:
    return f"thumb_{media_filename.rsplit('.', 1)[0]}.webp"


def store_thumbnail(media_filename: str, data: bytes) -> Optional[str]:
    """Write the thumbnail of a stored photo; its public URL, or None."""
    thumb = make_thumbnail(data)
    if thumb is None:
        return None
    thumb_dir = os.path.join(UPLOAD_DIR, "thumbnails")
    os.makedirs(thumb_dir, exist_ok=True)
    name = _thumb_name(media_filename)
    _write_atomic(os.path.join(thumb_dir, name), thumb)
    return f"/uploads/thumbnails/{name}"


def _write_atomic(path: str, data: bytes) -> None:
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


# ── Catch-up for photos stored before 1.5.1 ───────────────────────────────────

def backfill_photos() -> None:
    """Strip and thumbnail every photo that has no thumbnail yet, one at a
    time. A photo with a thumbnail_url is done, so this is idempotent and costs
    one query once everything is. Run once in the background at startup
    (main.py) — about a second a photo on a Pi 4 — so it must never raise.
    """
    try:
        db = SessionLocal()
        try:
            ids = [
                row[0]
                for row in db.query(MediaItem.id)
                .filter(MediaItem.file_type == "image", MediaItem.thumbnail_url.is_(None))
                .order_by(MediaItem.id.desc())  # newest first: those are on screen
                .all()
            ]
        finally:
            db.close()
        if not ids:
            return
        done = sum(1 for media_id in ids if _backfill_one(media_id))
        logger.info("Photo catch-up: %d of %d photos stripped and thumbnailed", done, len(ids))
    except Exception:
        logger.exception("Photo catch-up failed")


def _backfill_one(media_id: int) -> bool:
    db = SessionLocal()
    thumb_url = None
    path = None
    rewritten = False
    try:
        item = db.get(MediaItem, media_id)
        if item is None or item.thumbnail_url:
            return False
        path = os.path.join(UPLOAD_DIR, "media", item.filename)
        if not os.path.exists(path):
            return False
        with open(path, "rb") as f:
            data = f.read()
        cleaned = strip_metadata(data)
        if cleaned != data and _same_picture(data, cleaned):
            _write_atomic(path, cleaned)
            item.file_size = len(cleaned)
            data = cleaned
            rewritten = True
        thumb_url = store_thumbnail(item.filename, data)
        item.thumbnail_url = thumb_url
        db.commit()
        return thumb_url is not None
    except StaleDataError:
        # Deleted by a request while this ran: don't leave its files behind.
        db.rollback()
        if thumb_url:
            _remove_quietly(os.path.join(UPLOAD_DIR, "thumbnails", os.path.basename(thumb_url)))
        if rewritten and path:
            _remove_quietly(path)
        return False
    except Exception:
        db.rollback()
        logger.exception("Photo catch-up failed for media %s", media_id)
        return False
    finally:
        db.close()


def _remove_quietly(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass
