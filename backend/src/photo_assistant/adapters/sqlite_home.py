"""What Home reads (issue 54): the photos memories are made of, and what arrived lately.

Both go through the visibility rule and the timeline's default filter (the viewer's hidden
photos stay out), so every number Home shows can be listed again through ``/api/assets``.
"""

import collections
from datetime import datetime

from photo_assistant.adapters.sqlite_accounts import utc_text
from photo_assistant.adapters.sqlite_base import SqliteBase
from photo_assistant.adapters.sqlite_library import SOURCE_VISIBLE, filter_sql, visibility
from photo_assistant.domain.access import Viewer
from photo_assistant.domain.library_filter import AssetFilter
from photo_assistant.domain.memories import Moment
from photo_assistant.ports.library import Arrivals, Count

# A date guessed from a file's mtime is the day it was copied, not the day it was taken:
# hundreds of such photos would make a "trip" of a copy. Home's own filters say so too.
MEMORABLE = AssetFilter(guessed_date=False)

_JOINS = """LEFT JOIN user_asset ua ON ua.asset_id = a.id AND ua.user_id = :vis_uid
    LEFT JOIN place p ON p.id = a.place_id"""


class HomeMixin(SqliteBase):
    def moments(self, viewer: Viewer) -> list[Moment]:
        """The photos with a real date this viewer sees on the timeline, in time order: one
        pass over the library, the columns memories and "on this day" need and no more."""
        visible, _, params = visibility(viewer)
        where, fparams = filter_sql(MEMORABLE)
        rows = self._all(
            f"""SELECT a.id, a.taken_at, COALESCE(ua.favourite, 0) AS favourite,
                    COALESCE(NULLIF(p.city, ''), NULLIF(p.region, ''), NULLIF(p.country, ''))
                    AS place
                FROM asset a {_JOINS} {where} AND {visible} ORDER BY a.taken_at, a.id""",
            params | fparams,
        )
        parse = datetime.fromisoformat
        return [Moment(i, parse(taken), place, bool(fav)) for i, taken, fav, place in rows]

    def arrivals(self, viewer: Viewer, since: datetime, limit: int) -> Arrivals:
        """Photos imported since ``since`` that this viewer sees on the timeline, the newest
        arrival first. Each counts for the folder that brought it, when the viewer may see that
        folder."""
        visible, _, params = visibility(viewer)
        where, fparams = filter_sql(AssetFilter())
        rows = self._all(
            f"""SELECT a.id, s.id AS source_id, s.label,
                    s.id IS NOT NULL AND {SOURCE_VISIBLE} AS shown
                FROM asset a {_JOINS} LEFT JOIN source s ON s.id = a.first_source_id
                {where} AND a.imported_at >= :since AND {visible}
                ORDER BY a.imported_at DESC, a.id DESC""",
            params | fparams | {"since": utc_text(since)},
        )
        counts: collections.Counter[tuple[int, str]] = collections.Counter(
            (int(r["source_id"]), str(r["label"])) for r in rows if r["shown"]
        )
        by_count = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0][1], kv[0][0]))
        return Arrivals(
            count=len(rows),
            newest=[int(r["id"]) for r in rows[:limit]],
            sources=[Count(str(sid), n, label) for (sid, label), n in by_count],
        )
