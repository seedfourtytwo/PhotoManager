"""Pure rules for uploads: what counts as a photo (by content), and safe file names."""

import pytest

from photo_assistant.domain.uploads import (
    is_content_hash,
    numbered_names,
    safe_upload_name,
    sniff_image_type,
)

JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00"
PNG = b"\x89PNG\r\n\x1a\n\x00\x00"


@pytest.mark.parametrize(
    ("head", "expected"),
    [
        (JPEG, "jpg"),
        (PNG, "png"),
        (b"GIF89a\x01\x00", "gif"),
        (b"RIFF\x00\x00\x00\x00WEBPVP8 ", "webp"),
        (b"II*\x00\x08\x00\x00\x00", "tif"),  # also DNG, NEF, CR2, ARW
        (b"MM\x00*\x00\x00\x00\x08", "tif"),
        (b"\x00\x00\x00\x18ftypheic\x00\x00", "heic"),
        (b"\x00\x00\x00\x18ftypmif1\x00\x00", "heic"),
        (b"\x00\x00\x00\x18ftypavif\x00\x00", "avif"),
        (b"\x00\x00\x00\x18ftypcrx \x00\x00", "cr3"),
        (b"FUJIFILMCCD-RAW 0201", "raf"),
        (b"IIRO\x08\x00\x00\x00", "orf"),
        (b"IIU\x00\x08\x00\x00\x00", "rw2"),
    ],
)
def test_images_are_recognised_by_their_first_bytes(head: bytes, expected: str) -> None:
    assert sniff_image_type(head) == expected


@pytest.mark.parametrize(
    "head",
    [
        b"",
        b"hello world, I am text",
        b"%PDF-1.7\n",
        b"\x00\x00\x00\x18ftypqt  \x00\x00",  # a video (MOV)
        b"\x00\x00\x00\x18ftypisom\x00\x00",  # MP4
        b"PK\x03\x04",
        b"RIFF\x00\x00\x00\x00AVI ",
    ],
)
def test_everything_else_is_not_a_photo(head: bytes) -> None:
    assert sniff_image_type(head) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("IMG_1234.HEIC", "IMG_1234.HEIC"),
        ("../../etc/passwd.jpg", "passwd.jpg"),
        ("..\\..\\windows\\evil.jpg", "evil.jpg"),
        ("/abs/path/x.png", "x.png"),
        (".hidden.jpg", "hidden.jpg"),
        ("..", "upload.jpg"),
        ("", "upload.jpg"),
        ("a\nb\x00c.jpg", "abc.jpg"),
        ('we<ird>:"|?*.jpg', "we_ird______.jpg"),
        ("beach day 🌊.jpg", "beach day 🌊.jpg"),
        ("Café.jpg", "Café.jpg"),  # NFC, so macOS and iPhone names compare equal
        ("photo", "photo.jpg"),  # no extension: take the one the content proves
        ("notes.txt", "notes.txt.jpg"),  # the importer decides by extension
        ("IMG_1.dng", "IMG_1.dng"),  # a RAW sniffs as TIFF; its own extension is fine
    ],
)
def test_upload_names_are_made_safe(raw: str, expected: str) -> None:
    sniffed = "tif" if raw.endswith(".dng") else "jpg"
    assert safe_upload_name(raw, sniffed) == expected


def test_long_names_are_shortened_keeping_the_extension() -> None:
    name = safe_upload_name("é" * 300 + ".jpeg", "jpg")
    assert name.endswith(".jpeg")
    assert len(name.encode()) <= 200


@pytest.mark.parametrize(
    "raw",
    ["IMG\ud800.jpg", "\udcff" * 300 + ".jpg", "a\ud83d" * 150],
    ids=["short", "long", "long without extension"],
)
def test_a_name_with_half_a_character_is_made_storable(raw: str) -> None:
    """A lone surrogate cannot be written as UTF-8: it must not crash, nor reach the disk."""
    name = safe_upload_name(raw, "jpg")
    assert name.endswith(".jpg") and len(name.encode()) <= 200


def test_numbered_names_count_up_before_the_extension() -> None:
    names = numbered_names("IMG_1.HEIC")
    assert [next(names) for _ in range(3)] == ["IMG_1.HEIC", "IMG_1 (2).HEIC", "IMG_1 (3).HEIC"]


def test_content_hashes_are_64_lowercase_hex_characters() -> None:
    assert is_content_hash("a" * 64)
    assert not is_content_hash("A" * 64)
    assert not is_content_hash("a" * 63)
    assert not is_content_hash("g" * 64)
