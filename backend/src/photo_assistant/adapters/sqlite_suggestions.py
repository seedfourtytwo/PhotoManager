"""What suggested albums read and remember (FEATURES 5.6).

The photos go through the visibility rule and Home's filter (real dates only, the viewer's
hidden photos left out), so a suggestion never holds a photo its viewer could not list.
"""

from collections.abc import Sequence
from datetime import datetime

from photo_assistant.adapters.sqlite_accounts import utc_text
from photo_assistant.adapters.sqlite_albums import AlbumsMixin
from photo_assistant.adapters.sqlite_home import MEMORABLE
from photo_assistant.adapters.sqlite_library import ALBUM_VISIBLE, filter_sql, visibility
from photo_assistant.domain.access import Viewer
from photo_assistant.domain.events import EventPhoto
from photo_assistant.domain.places import Place

_JOINS = """LEFT JOIN user_asset ua ON ua.asset_id = a.id AND ua.user_id = :vis_uid
    LEFT JOIN place p ON p.id = a.place_id"""


class SuggestionsMixin(AlbumsMixin):
    def event_photos(self, viewer: Viewer) -> list[EventPhoto]:
        """Every photo with a real date this viewer sees on the timeline: one pass over the
        library with its GPS, place and the people named on it."""
        visible, _, params = visibility(viewer)
        where, fparams = filter_sql(MEMORABLE)
        rows = self._all(
            f"""SELECT a.id, a.taken_at, a.latitude, a.longitude, p.country, p.region, p.city,
                    (SELECT group_concat(DISTINCT f.person_id) FROM face f
                      WHERE f.asset_id = a.id AND f.person_id IS NOT NULL) AS people
                FROM asset a {_JOINS} {where} AND {visible} ORDER BY a.taken_at, a.id""",
            params | fparams,
        )
        parse = datetime.fromisoformat
        return [
            EventPhoto(
                r["id"],
                parse(r["taken_at"]),
                (r["latitude"], r["longitude"]) if r["latitude"] is not None else None,
                frozenset(int(i) for i in r["people"].split(",")) if r["people"] else frozenset(),
                Place(r["country"], r["region"], r["city"]) if r["country"] is not None else None,
            )
            for r in rows
        ]

    def photos_in_albums(self, viewer: Viewer) -> set[int]:
        """The photos this viewer sees in any album it sees."""
        visible, _, params = visibility(viewer)
        rows = self._all(
            f"""SELECT DISTINCT ai.asset_id FROM album_item ai JOIN album al ON al.id = ai.album_id
                JOIN asset a ON a.id = ai.asset_id WHERE {ALBUM_VISIBLE} AND {visible}""",
            params,
        )
        return {int(r[0]) for r in rows}

    def suggestion_answers(self, user_id: int) -> set[str]:
        """The keys of the suggestions this account kept or discarded."""
        rows = self._all("SELECT key FROM album_suggestion_answer WHERE user_id = ?", (user_id,))
        return {str(r[0]) for r in rows}

    def _answer(self, user_id: int, key: str, answer: str, now: datetime) -> bool:
        """Record the answer; False when the account already answered this suggestion."""
        return bool(
            self._count(
                """INSERT INTO album_suggestion_answer (user_id, key, answer, answered_at)
                   VALUES (?, ?, ?, ?) ON CONFLICT DO NOTHING""",
                (user_id, key, answer, utc_text(now)),
            )
        )

    def discard_suggestion(self, user_id: int, key: str, now: datetime) -> bool:
        return self._answer(user_id, key, "discarded", now)

    def keep_suggestion(
        self, user_id: int, key: str, title: str, asset_ids: Sequence[int], now: datetime
    ) -> int | None:
        """Make the album, owned by this account, all at once with the answer; None when the
        suggestion was already answered (a second tap on Keep makes no second album)."""
        with self._transaction():
            if not self._answer(user_id, key, "kept", now):
                return None
            album_id = self.create_album(user_id, title, "", now)
            self.add_album_items(album_id, asset_ids, None, now)
            self._conn.execute(
                "UPDATE album_suggestion_answer SET album_id = ? WHERE user_id = ? AND key = ?",
                (album_id, user_id, key),
            )
        return album_id
