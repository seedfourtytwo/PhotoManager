"""A photo's dominant colour (Flight placeholders): what a grid paints until the thumbnail
arrives. Not an average: a photo of blue sky over a red roof is blue or red, never purple."""

from collections.abc import Iterable

RGB = tuple[int, int, int]

# Each channel is cut into 8 steps of 32: close shades of one sky land in one bucket.
_STEP = 32


def dominant_colour(pixels: Iterable[RGB]) -> str | None:
    """``#rrggbb``: the mean of the most crowded bucket of similar colours (on a tie, the one
    seen first). None for no pixels."""
    buckets: dict[RGB, list[RGB]] = {}
    for r, g, b in pixels:
        buckets.setdefault((r // _STEP, g // _STEP, b // _STEP), []).append((r, g, b))
    if not buckets:
        return None
    crowd = max(buckets.values(), key=len)  # max keeps the first of equals
    n = len(crowd)
    r, g, b = (round(sum(p[i] for p in crowd) / n) for i in range(3))
    return f"#{r:02x}{g:02x}{b:02x}"
