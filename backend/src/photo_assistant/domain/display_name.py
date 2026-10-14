"""What a photo is called where people see it, and the name a download carries (FEATURES 4b.7).

Library files are named by their content hash and source files are never renamed, so a name
is made, never stored: the minute the photo was taken (``2015-06-12 14.32``), numbered
``· 2``, ``· 3``… when several photos share that minute. A date guessed from the file's
modification time says when it was copied, not taken: such a photo keeps its file name,
tidied, and a file name without a word in it (``10174880_9036…_n.jpg``) gives ``Photo <id>``.
"""

import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath

from photo_assistant.domain.archive_name import UNSAFE_NAME_CHARS
from photo_assistant.domain.capture_time import DateSource

NUMBER_SEPARATOR = " · "
_GUESSED = frozenset({DateSource.FILE_MTIME})
# What a copy adds at the end of a name: "(Copy)", "(copy 2)", " - Copy", " - Copy (3)" (Windows),
# " copy", " copy 2" (macOS), "(1)" (a browser saving the same name twice).
_COPY_MARK = re.compile(
    r"(?:\s*\(\s*copy(?:\s+\d+)?\s*\)|\s+-\s+copy(?:\s*\(\d+\))?|\s+copy(?:\s+\d+)?|\s*\(\d+\))$",
    re.IGNORECASE,
)
# Facebook's download names: numbers joined by "_", then one size letter (n, o, b, s, t…).
_FACEBOOK = re.compile(r"^\d+(?:_\d+)+_[a-z]$")
_LETTER = re.compile(r"[^\W\d_]")


@dataclass(frozen=True, slots=True)
class Dated:
    """What naming needs to know of a photo."""

    id: int
    taken_at: datetime  # local wall-clock
    date_source: DateSource


def tidy_file_name(name: str) -> str | None:
    """The file name without its extension and copy marks; ``None`` when no word is left."""
    stem = unicodedata.normalize("NFC", name).strip()
    if stem.startswith("."):
        return None
    stem = PurePosixPath(stem).stem
    while (shorter := _COPY_MARK.sub("", stem)) != stem:
        stem = shorter
    stem = UNSAFE_NAME_CHARS.sub("_", stem).strip(" .")
    if not _LETTER.search(stem) or _FACEBOOK.match(stem):
        return None
    return stem


def _minute(taken_at: datetime) -> str:
    return f"{taken_at:%Y-%m-%d %H.%M}"


def _order(photo: Dated) -> tuple[datetime, int]:
    return photo.taken_at, photo.id


def display_names(
    photos: Sequence[Dated], mates: Iterable[Dated], file_names: Mapping[int, str]
) -> dict[int, str]:
    """The name of each photo. ``mates``: the photos taken in the same minutes as these that
    may be counted (the viewer sees them); ``file_names``: original names the viewer may read."""
    by_minute: dict[str, set[tuple[datetime, int]]] = {}
    for mate in mates:
        if mate.date_source not in _GUESSED:
            by_minute.setdefault(_minute(mate.taken_at), set()).add(_order(mate))
    names = {}
    for photo in photos:
        if photo.date_source in _GUESSED:
            tidy = tidy_file_name(file_names.get(photo.id, ""))
            names[photo.id] = tidy or f"Photo {photo.id}"
            continue
        minute = _minute(photo.taken_at)
        before = sum(1 for o in by_minute.get(minute, ()) if o < _order(photo))
        names[photo.id] = minute + (f"{NUMBER_SEPARATOR}{before + 1}" if before else "")
    return names
