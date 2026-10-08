"""Photos held for review (issue 8): which ones wait for a person instead of joining the library.

Two reasons:
- a look-alike: a newly imported photo whose perceptual hash is at most
  ``MAX_LOOKALIKE_DISTANCE`` bits from a photo that was already in the library. Photos of the
  same import that resemble each other are bursts; those belong to the groups, not here.
- clutter: the auto-tagger's best guess for the photo is a screenshot, document, receipt or
  meme. The reason is that tag's name.
"""

from collections.abc import Mapping, Sequence

from photo_assistant.domain.tags import VOCABULARY, TagScore, TagSpec

LOOKALIKE = "lookalike"
# Stricter than grouping's 6: there is no "taken minutes apart" check to back it up here.
MAX_LOOKALIKE_DISTANCE = 4


def lookalikes(new: Mapping[int, str], library: Mapping[int, str]) -> dict[int, int]:
    """new photo id → the library photo it most resembles (the oldest on a tie), for those
    close enough. Hashes are 64-bit hex."""
    known = sorted((asset_id, int(phash, 16)) for asset_id, phash in library.items())
    found: dict[int, int] = {}
    for asset_id, phash in new.items():
        mine = int(phash, 16)
        best, best_distance = None, MAX_LOOKALIKE_DISTANCE + 1
        for other_id, other in known:
            distance = (mine ^ other).bit_count()
            if distance < best_distance:
                best, best_distance = other_id, distance
        if best is not None:
            found[asset_id] = best
    return found


def clutter_reason(
    tags: Sequence[TagScore], vocabulary: Sequence[TagSpec] = VOCABULARY
) -> str | None:
    """The clutter tag when it is the best of ``tags`` (best first), else None."""
    clutter = {spec.name for spec in vocabulary if spec.screen_or_document}
    return tags[0].name if tags and tags[0].name in clutter else None
