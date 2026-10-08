"""Pure rules for uploads from phones and browsers.

A file is accepted only if its *content* is a photo (magic bytes), whatever its name says; its
name is reduced to one safe path component, since it comes from an untrusted client.
"""

import re
import unicodedata
from collections.abc import Iterator
from pathlib import PurePosixPath

from photo_assistant.domain.media_types import MediaKind, classify

HEAD_BYTES = 32  # enough for every signature below
MAX_NAME_BYTES = 200
FALLBACK_STEM = "upload"

_HEIF_BRANDS = {b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"mif1", b"msf1"}
_AVIF_BRANDS = {b"avif", b"avis"}
_PREFIXES: tuple[tuple[bytes, str], ...] = (
    (b"\xff\xd8\xff", "jpg"),
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"GIF87a", "gif"),
    (b"GIF89a", "gif"),
    (b"II*\x00", "tif"),  # TIFF and TIFF-based RAW: DNG, NEF, CR2, ARW, PEF, SRW
    (b"MM\x00*", "tif"),
    (b"FUJIFILMCCD-RAW", "raf"),
    (b"IIRO", "orf"),
    (b"IIRS", "orf"),
    (b"MMOR", "orf"),
    (b"IIU\x00", "rw2"),
)
_UNSAFE = re.compile(r'[<>:"|?*]')
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_HASH = re.compile(r"^[0-9a-f]{64}$")


def sniff_image_type(head: bytes) -> str | None:
    """The photo format proven by the first bytes, as a file extension; None if not a photo.

    Videos (MOV/MP4 share the ISO box format with HEIC) are deliberately refused for now."""
    for prefix, ext in _PREFIXES:
        if head.startswith(prefix):
            return ext
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    if head[4:8] == b"ftyp":
        return _iso_brand(head[8:12])
    return None


def _iso_brand(brand: bytes) -> str | None:
    if brand in _HEIF_BRANDS:
        return "heic"
    if brand in _AVIF_BRANDS:
        return "avif"
    return "cr3" if brand == b"crx " else None


def safe_upload_name(raw: str, sniffed_ext: str) -> str:
    """One harmless file name: no folders, no control or reserved characters, NFC, bounded.

    If the name's extension is not a photo one, the sniffed extension is appended so the
    importer (which decides by extension) recognises the file."""
    # half a character (a lone surrogate) cannot be stored as UTF-8: it becomes "?", then "_"
    whole = raw.encode(errors="replace").decode()
    base = re.split(r"[\\/]", whole)[-1]
    name = _UNSAFE.sub("_", _CONTROL.sub("", unicodedata.normalize("NFC", base)))
    name = name.strip().lstrip(".").strip()
    if not name:
        name = FALLBACK_STEM
    if classify(name) not in (MediaKind.PHOTO, MediaKind.RAW):
        name = f"{name}.{sniffed_ext}"
    return _shorten(name)


def _shorten(name: str) -> str:
    if len(name.encode()) <= MAX_NAME_BYTES:
        return name
    suffix = PurePosixPath(name).suffix
    budget = MAX_NAME_BYTES - len(suffix.encode())
    stem = name[: len(name) - len(suffix)].encode()[:budget].decode(errors="ignore")
    return stem + suffix


def numbered_names(name: str) -> Iterator[str]:
    """``a.jpg``, ``a (2).jpg``, ``a (3).jpg``, … for picking a free name."""
    path = PurePosixPath(name)
    yield name
    number = 2
    while True:
        yield f"{path.stem} ({number}){path.suffix}"
        number += 1


def is_content_hash(value: str) -> bool:
    """A BLAKE3 digest as the library stores it: 64 lowercase hex characters."""
    return bool(_HASH.fullmatch(value))
