"""Content-based (magic-byte) file-type validation.

Upload endpoints previously trusted the client-declared ``content_type``, which
is trivially spoofable. These helpers sniff the real leading bytes and confirm
they're consistent with the declared MIME type, so a caller can't smuggle an
HTML/SVG/script payload past an ``image/png`` label.

``detect_mimes(content)`` returns the set of MIME types the bytes are compatible
with (empty set if unrecognised). ``matches_declared(content, declared)`` is the
convenience check used by the routers.
"""

from typing import Set


def detect_mimes(content: bytes) -> Set[str]:
    """Best-effort MIME detection from a file's leading bytes.

    Returns every MIME type the signature is compatible with (some containers
    map to more than one — e.g. an ISO-BMFF ``ftyp`` box is used by both MP4 and
    QuickTime/MOV). An empty set means the bytes matched no known signature.
    """
    if len(content) < 12:
        return set()

    head = content[:16]

    # Images
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return {"image/png"}
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return {"image/gif"}
    if head[:3] == b"\xff\xd8\xff":
        return {"image/jpeg"}

    # RIFF containers: WebP (image) and AVI (video) share the RIFF header.
    if head[:4] == b"RIFF":
        fourcc = content[8:12]
        if fourcc == b"WEBP":
            return {"image/webp"}
        if fourcc == b"AVI ":
            return {"video/x-msvideo"}
        return set()

    # Matroska / WebM
    if head[:4] == b"\x1aE\xdf\xa3":
        return {"video/webm"}

    # ISO Base Media File Format: MP4 and QuickTime both use a 'ftyp' box at
    # offset 4. We don't distinguish the brand — either is an acceptable real
    # media container, which is all we're guarding against.
    if content[4:8] == b"ftyp":
        return {"video/mp4", "video/quicktime"}

    return set()


def matches_declared(content: bytes, declared: str) -> bool:
    """True if the sniffed content is compatible with the declared MIME type."""
    return declared in detect_mimes(content)
