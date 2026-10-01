"""What kind of file is this? Decided from the name only; content sniffing happens in adapters."""

import re
from enum import StrEnum
from pathlib import PurePath


class MediaKind(StrEnum):
    PHOTO = "photo"
    RAW = "raw"
    VIDEO = "video"  # recognised and reported, not imported yet (FEATURES 11.9)
    IGNORED = "ignored"  # sidecars and OS clutter: silently skipped
    UNSUPPORTED = "unsupported"  # anything else: reported as skipped


_PHOTO = {"jpg", "jpeg", "jpe", "png", "heic", "heif", "hif", "webp", "tif", "tiff", "gif", "avif"}
_RAW = {"nef", "cr2", "cr3", "arw", "dng", "raf", "orf", "rw2", "pef", "srw", "nrw"}
_VIDEO = {"mov", "mp4", "m4v", "avi", "mkv", "3gp", "mts", "m2ts", "webm", "wmv", "mpg", "mpeg"}
_SIDECAR = {"aae", "xmp", "thm"}
_OS_CLUTTER = {"thumbs.db", ".ds_store", "desktop.ini", ".picasa.ini", "picasa.ini"}

_EDITED = re.compile(r"^IMG_E(\d{4})(\.[A-Za-z0-9]+)$")


def classify(filename: str) -> MediaKind:
    name = PurePath(filename).name
    if name.lower() in _OS_CLUTTER or name.startswith("._"):
        return MediaKind.IGNORED
    ext = PurePath(name).suffix.lower().lstrip(".")
    if ext in _PHOTO:
        return MediaKind.PHOTO
    if ext in _RAW:
        return MediaKind.RAW
    if ext in _VIDEO:
        return MediaKind.VIDEO
    if ext in _SIDECAR:
        return MediaKind.IGNORED
    return MediaKind.UNSUPPORTED


def edited_original_name(filename: str) -> str | None:
    """iPhone exports edits as ``IMG_E1234.JPG`` next to ``IMG_1234.JPG``; return the latter."""
    match = _EDITED.match(PurePath(filename).name)
    return f"IMG_{match.group(1)}{match.group(2)}" if match else None


# What remote pulls fetch (rclone filter): photos and RAW only; videos aren't imported yet.
IMPORTABLE_EXTENSIONS: frozenset[str] = frozenset(_PHOTO | _RAW)
