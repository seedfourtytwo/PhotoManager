"""Where library files live, expressed relative to the data root.

Portability rule (ARCHITECTURE §6): the database only ever stores paths relative to the data
root, so moving the library from the laptop to the server is "copy the folder, change one
setting". These functions are the single place that rule is applied.
"""

from pathlib import PurePosixPath

_HASH_ALPHABET = frozenset("0123456789abcdef")
_BLAKE3_HEX_LENGTH = 64


class InvalidLibraryPathError(ValueError):
    """A path that would escape the data root or is not a valid library path."""


def original_relpath(content_hash: str, year: int, month: int, extension: str) -> PurePosixPath:
    """Relative path of an immutable original: ``originals/YYYY/MM/<hash>.<ext>``."""
    if len(content_hash) != _BLAKE3_HEX_LENGTH or not set(content_hash) <= _HASH_ALPHABET:
        raise InvalidLibraryPathError(f"not a lowercase BLAKE3 hex digest: {content_hash!r}")
    if not 1 <= month <= 12:
        raise InvalidLibraryPathError(f"month out of range: {month}")
    if not 1800 <= year <= 9999:
        raise InvalidLibraryPathError(f"year out of range: {year}")
    ext = extension.lower().lstrip(".")
    if not ext.isalnum():
        raise InvalidLibraryPathError(f"bad extension: {extension!r}")
    return PurePosixPath("originals", f"{year:04d}", f"{month:02d}", f"{content_hash}.{ext}")


def ensure_relative(path: str) -> PurePosixPath:
    """Validate a stored path: relative, and never climbing out of the data root."""
    candidate = PurePosixPath(path)
    if candidate.is_absolute() or ".." in candidate.parts or path.strip() == "":
        msg = f"library paths must be relative and inside the root: {path!r}"
        raise InvalidLibraryPathError(msg)
    return candidate


DERIVATIVE_KINDS = ("thumb", "preview")
_RECIPE_KEY_LENGTH = 16


def derived_relpath(kind: str, content_hash: str) -> PurePosixPath:
    """``derived/<kind>/<first two hex chars>/<hash>.webp``; sharded to keep folders small."""
    if kind not in DERIVATIVE_KINDS:
        raise InvalidLibraryPathError(f"unknown derivative kind: {kind!r}")
    if len(content_hash) != _BLAKE3_HEX_LENGTH or not set(content_hash) <= _HASH_ALPHABET:
        raise InvalidLibraryPathError(f"not a lowercase BLAKE3 hex digest: {content_hash!r}")
    return PurePosixPath("derived", kind, content_hash[:2], f"{content_hash}.webp")


def print_relpath(content_hash: str, recipe_key: str) -> PurePosixPath:
    """``derived/print/<hh>/<hash>-<recipe key>.jpg``: a full-resolution print rendition
    (oriented, edited, sRGB JPEG); cached per content and recipe like edited previews."""
    edited_relpath("preview", content_hash, recipe_key)  # validates the hash and the key
    return PurePosixPath("derived", "print", content_hash[:2], f"{content_hash}-{recipe_key}.jpg")


def edited_relpath(kind: str, content_hash: str, recipe_key: str) -> PurePosixPath:
    """``derived/edited/<hh>/<hash>-<recipe key>-<kind>.webp``: a cached render of an edit.
    Keyed by content *and* recipe, so a changed recipe never serves a stale image."""
    base = derived_relpath(kind, content_hash)
    if len(recipe_key) != _RECIPE_KEY_LENGTH or not set(recipe_key) <= _HASH_ALPHABET:
        raise InvalidLibraryPathError(f"not a recipe key: {recipe_key!r}")
    return PurePosixPath(
        "derived", "edited", content_hash[:2], f"{content_hash}-{recipe_key}-{base.parts[1]}.webp"
    )
