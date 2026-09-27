"""Unit tests for magic-byte upload validation (``file_validation``)."""

from file_validation import detect_mimes, matches_declared

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
GIF = b"GIF89a" + b"\x00" * 16
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 16
WEBP = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 8
AVI = b"RIFF" + b"\x00\x00\x00\x00" + b"AVI " + b"\x00" * 8
WEBM = b"\x1aE\xdf\xa3" + b"\x00" * 16
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 8


def test_recognises_real_images():
    assert detect_mimes(PNG) == {"image/png"}
    assert detect_mimes(GIF) == {"image/gif"}
    assert detect_mimes(JPEG) == {"image/jpeg"}
    assert detect_mimes(WEBP) == {"image/webp"}


def test_recognises_real_videos():
    assert detect_mimes(WEBM) == {"video/webm"}
    assert detect_mimes(AVI) == {"video/x-msvideo"}
    assert detect_mimes(MP4) == {"video/mp4", "video/quicktime"}


def test_matches_declared_accepts_truthful_type():
    assert matches_declared(PNG, "image/png")
    assert matches_declared(MP4, "video/mp4")
    assert matches_declared(MP4, "video/quicktime")  # ftyp shared by both


def test_matches_declared_rejects_spoofed_type():
    # An HTML/script payload labelled as a PNG must be rejected.
    html = b"<html><script>alert(1)</script></html>" + b"\x00" * 16
    assert detect_mimes(html) == set()
    assert not matches_declared(html, "image/png")


def test_declared_type_must_match_actual_bytes():
    # Real PNG bytes but declared as a video -> rejected (type mismatch).
    assert not matches_declared(PNG, "video/mp4")


def test_too_short_is_unrecognised():
    assert detect_mimes(b"\x89PNG") == set()
