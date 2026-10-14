"""What a downloaded ZIP is called: after the album, the filters, or the number of photos.

The names end up in a ``Content-Disposition`` header and on the user's disk, so they carry no
path separators, control characters or quotes, and stay short enough for any file system.
"""

import re
import unicodedata

from photo_assistant.domain.library_filter import AssetFilter

MAX_NAME_LENGTH = 100  # characters, ".zip" included
_EXT = ".zip"
# not allowed in a file name on some system (control characters, path separators, Windows)
UNSAFE_NAME_CHARS = re.compile(r"[\x00-\x1f\x7f/\\:*?\"<>|]")
_NOT_WORD = re.compile(r"[\W_]+")


def _clip(stem: str, trim: str) -> str:
    return stem[: MAX_NAME_LENGTH - len(_EXT)].rstrip(trim)


def album_zip_name(title: str) -> str:
    """``<title>.zip``, made safe; ``album.zip`` when nothing usable is left."""
    text = UNSAFE_NAME_CHARS.sub("_", unicodedata.normalize("NFC", title))
    text = " ".join(text.split()).strip(". ")
    if not text.strip("_"):
        text = "album"
    return _clip(text, ". ") + _EXT


def _slug(text: str) -> str:
    return _NOT_WORD.sub("-", unicodedata.normalize("NFC", text).lower()).strip("-")


def _days(f: AssetFilter) -> str | None:
    if f.from_day and f.from_day == f.to_day:
        return f.from_day.isoformat()
    if f.from_day and f.to_day:
        return f"{f.from_day.isoformat()}-to-{f.to_day.isoformat()}"
    if f.from_day:
        return f"from-{f.from_day.isoformat()}"
    if f.to_day:
        return f"to-{f.to_day.isoformat()}"
    return None


def _year(f: AssetFilter) -> str | None:
    if f.year is None:
        return None
    return f"{f.year}-{f.month:02d}" if f.month else str(f.year)


def _sources(f: AssetFilter) -> str | None:
    n = len(f.source_ids)
    return None if n == 0 else f"{n}-source{'s' if n != 1 else ''}"


def _people(f: AssetFilter) -> str | None:
    """By how many: a name would need a lookup, and a person may have none."""
    n = len(f.person_ids)
    return None if n == 0 else "1-person" if n == 1 else f"{n}-people"


def _flags(f: AssetFilter) -> list[str]:
    words = [
        "favourites" if f.favourite else "",
        "pinned" if f.pinned else "",
        "hidden" if f.hidden else "",
        "guessed-dates" if f.guessed_date else "",
    ]
    if f.has_location is not None:
        words.append("with-location" if f.has_location else "without-location")
    return words


def filter_words(f: AssetFilter) -> list[str]:
    """Short lowercase words for the filters, in the order the filter panel lists them."""
    words = [_days(f), _year(f), _sources(f), _people(f)]
    words += [_slug(t) for t in (f.camera, f.place, f.q) if t]
    words += _flags(f)
    return [w for w in words if w]


def filters_zip_name(f: AssetFilter) -> str:
    """``photos-<words>.zip``, e.g. ``photos-2019-france.zip``; ``photos-all.zip`` unfiltered."""
    return _clip("photos-" + ("-".join(filter_words(f)) or "all"), "-") + _EXT


def ids_zip_name(count: int) -> str:
    """A hand-picked selection: ``photos-<count>.zip``."""
    return f"photos-{count}{_EXT}"


def ascii_fallback(name: str) -> str:
    """The name for clients that ignore RFC 6266's ``filename*``: accents dropped, anything
    else outside ASCII becomes ``_``."""
    out = []
    for char in unicodedata.normalize("NFC", name):
        plain = "".join(
            c for c in unicodedata.normalize("NFKD", char) if not unicodedata.combining(c)
        )
        out.append(plain if plain.isascii() and plain else "_")
    return UNSAFE_NAME_CHARS.sub("_", "".join(out))
