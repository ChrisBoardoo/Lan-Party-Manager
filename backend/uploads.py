"""Shared upload plumbing: the capped read, the Pillow re-encode, deletion.

The re-encode block below used to be duplicated character-for-character across
five call sites (avatar, avatar/rotate, event cover, cover/rotate, prize photo).
Every copy shared the same three defects:

  * `content = await file.read()` with **no cap at all** — a 100 MB upload was
    buffered whole before anything looked at it. On a Pi that's the difference
    between a slow request and an OOM kill.
  * **no decompression-bomb guard** — a ~1 MB crafted PNG can declare
    100,000x100,000 and ask Pillow to allocate tens of gigabytes.
  * avatar and cover **never deleted the file they replaced**, so every avatar
    anyone ever changed is still on disk forever.

One copy now, hardened once. `file_validation.py` stays pure (no I/O, no Pillow,
no FastAPI) — this module is where the messy parts live. It's `uploads` rather
than `image_upload` because `read_capped` is format-agnostic and router_media
needs it for video.
"""
import io
import os
import uuid
from typing import Optional, Tuple

from fastapi import HTTPException, UploadFile
from PIL import Image

from file_validation import detect_mimes

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads")

# 12 MB covers any phone photo (typically 3-8 MB) and most DSLR JPEGs, while
# rejecting RAW dumps and 60 MB screenshots-of-screenshots.
MAX_IMAGE_BYTES = 12 * 1024 * 1024

# ~30 MP (about 6000x5000). This is the number that actually matters: a 12 MB
# *file* says nothing about decode cost. Peak decode is roughly w*h*3 bytes, so
# 30 MP ≈ 90 MB resident — survivable on a Pi with one uvicorn worker.
MAX_IMAGE_PIXELS = 30_000_000

# Deliberately narrower than "whatever Pillow can open": four well-fuzzed
# decoders instead of the long tail (BMP, TIFF, ICO, PPM, ...).
ALLOWED_IMAGE_MIMES = {"image/jpeg", "image/png", "image/webp", "image/gif"}

# Belt to the explicit check's braces — see the note in _decode().
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


async def read_capped(file: UploadFile, max_size: int) -> bytes:
    """Read an upload in chunks, aborting as soon as it passes max_size so an
    oversized file is never fully buffered into memory (matters on a Pi)."""
    chunks = bytearray()
    while True:
        chunk = await file.read(1024 * 1024)  # 1 MB
        if not chunk:
            break
        chunks.extend(chunk)
        if len(chunks) > max_size:
            raise HTTPException(400, f"File exceeds {max_size // (1024 * 1024)} MB limit.")
    return bytes(chunks)


def _public_url(subdir: Optional[str], filename: str) -> str:
    return f"/uploads/{subdir}/{filename}" if subdir else f"/uploads/{filename}"


def _disk_path(subdir: Optional[str], filename: str) -> str:
    return os.path.join(UPLOAD_DIR, subdir, filename) if subdir else os.path.join(UPLOAD_DIR, filename)


def _decode(content: bytes) -> Image.Image:
    """Bytes -> a decoded RGB image, or a 400.

    The explicit pixel check here is the real bomb guard. Setting
    `Image.MAX_IMAGE_PIXELS` is NOT sufficient on its own: Pillow only emits a
    *warning* between 1x and 2x the limit and raises DecompressionBombError
    above 2x, so relying on the global silently admits up to 60 MP. Checking
    `w * h` straight after `open()` — which parses the header and nothing else —
    bounds it before `convert()` allocates anything.
    """
    if not detect_mimes(content) & ALLOWED_IMAGE_MIMES:
        raise HTTPException(400, "Unsupported image type. Allowed: JPEG, PNG, WebP, GIF.")

    try:
        img = Image.open(io.BytesIO(content))
        width, height = img.size
        if width * height > MAX_IMAGE_PIXELS:
            raise HTTPException(
                400, f"Image is too large to process ({width}x{height}). Max {MAX_IMAGE_PIXELS // 1_000_000} megapixels."
            )
        return img.convert("RGB")
    except HTTPException:
        raise
    except Image.DecompressionBombError:
        raise HTTPException(400, "Image is too large to process.")
    except Exception as e:
        raise HTTPException(400, f"Invalid image: {e}")


def remove_upload(url: Optional[str], subdir: Optional[str] = None) -> None:
    """Delete the file behind a public /uploads URL. A missing file is fine —
    not worth failing a request over (mirrors the old _remove_banner_file)."""
    if not url:
        return
    path = _disk_path(subdir, os.path.basename(url))
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


async def save_image_upload(
    file: UploadFile,
    *,
    subdir: Optional[str],
    prefix: str,
    box: Tuple[int, int],
    quality: int = 80,
    replaces: Optional[str] = None,
) -> str:
    """Validate, re-encode to WebP, store, and return the public URL.

    `replaces` is the URL of the file this one supersedes; it's deleted only
    after the new file is safely on disk, so a failed encode never destroys the
    image the user still has.
    """
    content = await read_capped(file, MAX_IMAGE_BYTES)
    img = _decode(content)
    img.thumbnail(box)

    filename = f"{prefix}_{uuid.uuid4().hex[:8]}.webp"
    target_dir = os.path.join(UPLOAD_DIR, subdir) if subdir else UPLOAD_DIR
    os.makedirs(target_dir, exist_ok=True)
    img.save(os.path.join(target_dir, filename), "WEBP", quality=quality)

    remove_upload(replaces, subdir)
    return _public_url(subdir, filename)


def rotate_image_file(
    url: str,
    *,
    subdir: Optional[str],
    prefix: str,
    quality: int = 80,
) -> str:
    """Rotate an already-stored image 90° and return its new public URL.

    Two things here look wasteful and are not:

    * **A new uuid filename every time.** nginx serves /uploads/ as
      `immutable, 30d` (frontend/nginx.conf), so the uuid *is* the cache key.
      Saving in place would leave every browser and proxy showing the old
      orientation for a month with no way to bust it.
    * **`with Image.open(...)`.** Pillow's open is lazy and keeps the file
      handle; on Windows an open handle makes os.remove fail outright. The old
      code never closed it — invisible, because it also never deleted.
    """
    src = _disk_path(subdir, os.path.basename(url))
    if not os.path.exists(src):
        raise HTTPException(404, "Image file not found")

    try:
        with Image.open(src) as im:
            img = im.convert("RGB").transpose(Image.Transpose.ROTATE_270)
    except Exception as e:
        raise HTTPException(400, f"Could not rotate image: {e}")

    filename = f"{prefix}_{uuid.uuid4().hex[:8]}.webp"
    img.save(_disk_path(subdir, filename), "WEBP", quality=quality)
    remove_upload(url, subdir)
    return _public_url(subdir, filename)
