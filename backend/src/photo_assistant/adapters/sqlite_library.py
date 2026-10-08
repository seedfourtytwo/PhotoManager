"""Reading the library as one viewer: the visibility rule, filters, facets, calendar, map.

``visibility`` is THE access rule (ARCHITECTURE §7). Every query that lists, counts, searches
or serves photos applies it; nothing is filtered in Python afterwards.
"""

import collections
import json
import re
import sqlite3
from collections.abc import Callable, Sequence
from datetime import date, datetime, timedelta

from photo_assistant.adapters.sqlite_base import (
    SqliteBase,
    asset_from_row,
    decode_cursor,
    encode_cursor,
)
from photo_assistant.domain.access import Level, Viewer
from photo_assistant.domain.edit_recipe import Recipe
from photo_assistant.domain.library_filter import AssetFilter, like_pattern, search_terms
from photo_assistant.domain.model import Source
from photo_assistant.domain.places import Place
from photo_assistant.ports.library import AssetView, Count, Facets, ViewPage

Clauses = list[str]
Bindings = dict[str, object]

# --- THE access rule (ARCHITECTURE §7), as per-photo SQL over the alias ``a`` --------------------
#
# A grant is a source that gives the viewer (or everyone) a level, a source the viewer owns
# (edit), or an album the viewer owns or is a member of (view only: QA A1). A private photo only
# counts grants through sources its marker does not own, unless the viewer is the marker;
# albums never reach it (QA A3). Admins have edit through every source (and on photos left
# without one). Guests are capped at download.
#
# Two expressions, both correlated on ``a`` (C25: evaluated per photo through the indexes, so
# a timeline page stops after its LIMIT instead of computing the whole library first):
# _MEMBER_VISIBLE / _ADMIN_VISIBLE decide *whether* (EXISTS, short-circuits) and go in WHERE;
# _MEMBER_LEVEL decides *which level* and is only computed for the rows returned.

_QUALIFIES = "(a.private = 0 OR a.private_by = :vis_uid OR {owner} IS NOT a.private_by)"

_MEMBER_VISIBLE = f"""(EXISTS (
        SELECT 1 FROM asset_source x JOIN source s ON s.id = x.source_id
         WHERE x.asset_id = a.id AND {_QUALIFIES.format(owner="s.owner_id")}
           AND (s.owner_id = :vis_uid OR EXISTS (
                SELECT 1 FROM source_access sa WHERE sa.source_id = s.id
                   AND (sa.user_id IS NULL OR sa.user_id = :vis_uid))))
    OR ((a.private = 0 OR a.private_by = :vis_uid) AND EXISTS (
        SELECT 1 FROM album_item ai JOIN album al ON al.id = ai.album_id
         WHERE ai.asset_id = a.id AND (al.owner_id = :vis_uid OR EXISTS (
               SELECT 1 FROM album_member am
                WHERE am.album_id = al.id AND am.user_id = :vis_uid)))))"""

_MEMBER_LEVEL = f"""(SELECT MIN(MAX(g.lv), :vis_cap) FROM (
        SELECT sa.level AS lv FROM asset_source x JOIN source s ON s.id = x.source_id
          JOIN source_access sa ON sa.source_id = x.source_id
         WHERE x.asset_id = a.id AND (sa.user_id IS NULL OR sa.user_id = :vis_uid)
           AND {_QUALIFIES.format(owner="s.owner_id")}
        UNION ALL
        SELECT 3 FROM asset_source x JOIN source s ON s.id = x.source_id
         WHERE x.asset_id = a.id AND s.owner_id = :vis_uid
           AND {_QUALIFIES.format(owner="s.owner_id")}
        UNION ALL
        SELECT 1 FROM album_item ai JOIN album al ON al.id = ai.album_id
         WHERE ai.asset_id = a.id AND (a.private = 0 OR a.private_by = :vis_uid)
           AND (al.owner_id = :vis_uid OR EXISTS (
                SELECT 1 FROM album_member am
                 WHERE am.album_id = al.id AND am.user_id = :vis_uid))) g)"""

# Admins (C27): no access lists to consult; only someone else's private photo needs a look.
_ADMIN_VISIBLE = f"""(a.private = 0 OR a.private_by = :vis_uid
    OR EXISTS (SELECT 1 FROM asset_source x JOIN source s ON s.id = x.source_id
                WHERE x.asset_id = a.id AND {_QUALIFIES.format(owner="s.owner_id")})
    OR NOT EXISTS (SELECT 1 FROM asset_source x WHERE x.asset_id = a.id))"""


# Where a photo is: in the library, held for review (issue 8), or in the trash.
_LIVE = "a.trashed_at IS NULL AND a.held_reason IS NULL"
_HELD = "a.trashed_at IS NULL AND a.held_reason IS NOT NULL"
_TRASHED = "a.trashed_at IS NOT NULL"


def visibility(
    viewer: Viewer, *, trashed: bool = False, held: bool = False
) -> tuple[str, str, Bindings]:
    """THE access rule for one viewer: (condition "``a`` is visible and in the library" — or
    in the trash, or held for review —, expression "the viewer's level on ``a``", bindings).
    Every query that lists, counts, searches or serves photos uses it; nothing is filtered in
    Python afterwards."""
    params: Bindings = {
        "vis_uid": viewer.user_id,
        "vis_admin": int(viewer.is_admin),
        "vis_cap": int(viewer.level_cap),
    }
    trash = _TRASHED if trashed else _HELD if held else _LIVE
    if viewer.is_admin:
        return f"({trash} AND {_ADMIN_VISIBLE})", ":vis_cap", params
    return f"({trash} AND {_MEMBER_VISIBLE})", _MEMBER_LEVEL, params


ASSET_JOINS = """LEFT JOIN user_asset ua ON ua.asset_id = a.id AND ua.user_id = :vis_uid
    LEFT JOIN place p ON p.id = a.place_id
    LEFT JOIN edit_recipe er ON er.asset_id = a.id"""
ASSET_FROM = f"FROM asset a {ASSET_JOINS}"


def asset_columns(level: str) -> str:
    """Everything ``view_from_row`` reads, with ``level`` from ``visibility``."""
    return f"""a.*, {level} AS vis_level, COALESCE(ua.favourite, 0) AS vis_favourite,
    COALESCE(ua.hidden, 0) AS vis_hidden, p.country, p.region, p.city,
    er.recipe_json AS vis_recipe"""


# Albums and sources you can see (used for search, facets, origins and album lists).
ALBUM_VISIBLE = """(:vis_admin OR al.owner_id = :vis_uid OR EXISTS (
    SELECT 1 FROM album_member m WHERE m.album_id = al.id AND m.user_id = :vis_uid))"""
SOURCE_VISIBLE = """(:vis_admin OR s.owner_id = :vis_uid OR EXISTS (
    SELECT 1 FROM source_access sa WHERE sa.source_id = s.id
       AND (sa.user_id IS NULL OR sa.user_id = :vis_uid)))"""

ORDER = "ORDER BY a.taken_at DESC, a.id DESC"


def view_from_row(row: sqlite3.Row) -> AssetView:
    place = Place(row["country"], row["region"], row["city"]) if row["country"] else None
    trashed = row["trashed_at"]
    return AssetView(
        asset=asset_from_row(row),
        level=Level(row["vis_level"]),
        favourite=bool(row["vis_favourite"]),
        hidden=bool(row["vis_hidden"]),
        private=bool(row["private"]),
        place=place,
        edit_version=row["edit_version"],
        edited=row["vis_recipe"] is not None,
        group_id=row["group_id"],
        trashed_at=datetime.fromisoformat(trashed) if trashed else None,
        held_reason=row["held_reason"],
        held_like=row["held_like"],
        recipe=Recipe.from_dict(json.loads(row["vis_recipe"])) if row["vis_recipe"] else None,
    )


# --- filters: each adds its SQL condition(s) --------------------------------------------------


def _days(f: AssetFilter, where: Clauses, params: Bindings) -> None:
    if f.from_day:
        where.append("a.taken_at >= :f_from")
        params["f_from"] = f.from_day.isoformat()
    if f.to_day and f.to_day < date.max:  # the last day of the calendar bounds nothing
        where.append("a.taken_at < :f_to")
        params["f_to"] = (f.to_day + timedelta(days=1)).isoformat()


def _year_month(f: AssetFilter, where: Clauses, params: Bindings) -> None:
    """As a taken_at range (C25), so the timeline index serves it."""
    if f.year is None:
        return
    if f.month is None:
        start, end = date(f.year, 1, 1), (date(f.year + 1, 1, 1) if f.year < 9999 else None)
    else:
        start = date(f.year, f.month, 1)
        after = (f.year + 1, 1) if f.month == 12 else (f.year, f.month + 1)
        end = date(*after, 1) if after[0] <= 9999 else None
    where.append("a.taken_at >= :f_ym_start")
    params["f_ym_start"] = start.isoformat()
    if end is not None:
        where.append("a.taken_at < :f_ym_end")
        params["f_ym_end"] = end.isoformat()


def _sources(f: AssetFilter, where: Clauses, params: Bindings) -> None:
    if not f.source_ids:
        return
    names = [f":f_src{i}" for i in range(len(f.source_ids))]
    params.update({n[1:]: sid for n, sid in zip(names, f.source_ids, strict=True)})
    # only sources this viewer may see: a hidden source's id must not select anything (QA A9)
    where.append(
        "EXISTS (SELECT 1 FROM asset_source x JOIN source s ON s.id = x.source_id "
        f"WHERE x.asset_id = a.id AND x.source_id IN ({', '.join(names)}) AND {SOURCE_VISIBLE})"
    )


def _camera_place(f: AssetFilter, where: Clauses, params: Bindings) -> None:
    if f.camera is not None:
        where.append("a.camera_model = :f_camera")
        params["f_camera"] = f.camera
    if f.place is not None:
        where.append(
            "(p.country = :f_place COLLATE NOCASE OR p.region = :f_place COLLATE NOCASE "
            "OR p.city = :f_place COLLATE NOCASE)"
        )
        params["f_place"] = f.place


def _text(f: AssetFilter, where: Clauses, params: Bindings) -> None:
    for i, term in enumerate(search_terms(f.q)):
        key = f":f_q{i}"
        params[key[1:]] = like_pattern(term)
        like = f"LIKE {key} ESCAPE '\\'"
        where.append(
            f"""(EXISTS (SELECT 1 FROM asset_source x JOIN source s ON s.id = x.source_id
                     WHERE x.asset_id = a.id AND x.relative_path {like} AND {SOURCE_VISIBLE})
                 OR p.city {like} OR p.region {like} OR p.country {like}
                 OR a.camera_model {like} OR a.camera_make {like}
                 OR EXISTS (SELECT 1 FROM album_item ai JOIN album al ON al.id = ai.album_id
                     WHERE ai.asset_id = a.id AND al.title {like} AND {ALBUM_VISIBLE}))"""
        )


def _flag(column: str, value: bool | None, where: Clauses, default_off: bool = False) -> None:
    if value is None and not default_off:
        return
    where.append(f"{column} = {int(bool(value))}")


def _flags(f: AssetFilter, where: Clauses, params: Bindings) -> None:
    _flag("COALESCE(ua.favourite, 0)", f.favourite, where)
    _flag("COALESCE(ua.hidden, 0)", f.hidden, where, default_off=True)  # hidden: out unless asked
    _flag("(a.date_source = 'file_mtime')", f.guessed_date, where)
    _flag("(a.latitude IS NOT NULL)", f.has_location, where)


_FILTERS: list[Callable[[AssetFilter, Clauses, Bindings], None]] = [
    _days,
    _year_month,
    _sources,
    _camera_place,
    _text,
    _flags,
]


def from_sql(f: AssetFilter) -> str:
    """``FROM asset a`` with the per-photo joins. "Only my favourites" and "only my hidden
    photos" start from my own marks (C25): a handful of rows instead of a walk over the whole
    timeline."""
    mine = [f"fav.{flag} = 1" for flag in ("favourite", "hidden") if getattr(f, flag)]
    if mine:
        return f"""FROM user_asset fav JOIN asset a ON a.id = fav.asset_id
            AND fav.user_id = :vis_uid AND {" AND ".join(mine)} {ASSET_JOINS}"""
    return ASSET_FROM


def filter_sql(f: AssetFilter) -> tuple[str, Bindings]:
    """``WHERE …`` for a filter (always at least ``1``)."""
    where: Clauses = ["1"]
    params: Bindings = {}
    for add in _FILTERS:
        add(f, where, params)
    return "WHERE " + " AND ".join(where), params


def _by_count(counts: "collections.Counter[str]") -> list[Count]:
    return [Count(k, n) for k, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]


class LibraryMixin(SqliteBase):
    def _filtered(
        self, viewer: Viewer, f: AssetFilter, tail: str, extra: Bindings | None = None
    ) -> list[sqlite3.Row]:
        visible, level, params = visibility(viewer)
        where, fparams = filter_sql(f)
        sql = f"SELECT {asset_columns(level)} {from_sql(f)} {where} AND {visible} {tail}"
        return self._all(sql, params | fparams | (extra or {}))

    # --- lists -----------------------------------------------------------------------------

    def list_views(
        self, viewer: Viewer, f: AssetFilter, limit: int, cursor: str | None = None
    ) -> ViewPage:
        """Newest first; the cursor works with any filter. Raises ValueError for a bad cursor."""
        tail = f"{ORDER} LIMIT :limit"
        extra: Bindings = {"limit": limit + 1}
        if cursor is not None:
            taken_at, asset_id = decode_cursor(cursor)
            tail = f"AND (a.taken_at, a.id) < (:c_taken, :c_id) {tail}"
            extra |= {"c_taken": taken_at, "c_id": asset_id}
        rows = self._filtered(viewer, f, tail, extra)
        items = [view_from_row(r) for r in rows[:limit]]
        next_cursor = None
        if len(rows) > limit:
            last = rows[limit - 1]
            next_cursor = encode_cursor(last["taken_at"], last["id"])
        return ViewPage(items, next_cursor)

    def visible_asset_ids(self, viewer: Viewer, f: AssetFilter | None = None) -> list[int]:
        """The visibility rule (plus filters) as plain ids, newest first: the candidate set
        handed to search, similar photos and people, which never widen it."""
        f = f or AssetFilter()
        visible, _, params = visibility(viewer)
        where, fparams = filter_sql(f)
        rows = self._all(
            f"SELECT a.id {from_sql(f)} {where} AND {visible} {ORDER}", params | fparams
        )
        return [int(r["id"]) for r in rows]

    def list_all_views(self, viewer: Viewer, f: AssetFilter) -> list[AssetView]:
        return [view_from_row(r) for r in self._filtered(viewer, f, ORDER)]

    def views_by_ids(
        self, viewer: Viewer, ids: Sequence[int], *, trashed: bool = False, held: bool = False
    ) -> list[AssetView]:
        if not ids:
            return []
        visible, level, params = visibility(viewer, trashed=trashed, held=held)
        wanted = list(dict.fromkeys(ids))
        names = ", ".join(f":id{i}" for i in range(len(wanted)))
        params |= {f"id{i}": v for i, v in enumerate(wanted)}
        rows = self._all(
            f"""SELECT {asset_columns(level)} {ASSET_FROM}
                WHERE a.id IN ({names}) AND {visible}""",
            params,
        )
        by_id = {r["id"]: view_from_row(r) for r in rows}
        return [by_id[i] for i in wanted if i in by_id]

    def get_view(
        self, viewer: Viewer, asset_id: int, *, trashed: bool = False, held: bool = False
    ) -> AssetView | None:
        found = self.views_by_ids(viewer, [asset_id], trashed=trashed, held=held)
        return found[0] if found else None

    def group_views(self, viewer: Viewer, group_id: int) -> list[AssetView]:
        visible, level, params = visibility(viewer)
        rows = self._all(
            f"""SELECT {asset_columns(level)} {ASSET_FROM}
                WHERE a.group_id = :group AND {visible} ORDER BY a.taken_at, a.id""",
            params | {"group": group_id},
        )
        return [view_from_row(r) for r in rows]

    def trashed_views(self, viewer: Viewer) -> list[AssetView]:
        visible, level, params = visibility(viewer, trashed=True)
        rows = self._all(
            f"""SELECT {asset_columns(level)} {ASSET_FROM} WHERE {visible}
                ORDER BY a.trashed_at DESC""",
            params,
        )
        return [view_from_row(r) for r in rows]

    def count_visible(self, viewer: Viewer) -> int:
        visible, _, params = visibility(viewer)
        return self._scalar(f"SELECT COUNT(*) FROM asset a WHERE {visible}", params)

    # --- facets, calendar, map -------------------------------------------------------------

    def _grouped(
        self, viewer: Viewer, f: AssetFilter, select: str, group: str
    ) -> list[sqlite3.Row]:
        visible, _, params = visibility(viewer)
        where, fparams = filter_sql(f)
        sql = f"SELECT {select} {from_sql(f)} {where} AND {visible} {group}"
        return self._all(sql, params | fparams)

    def facets(self, viewer: Viewer, f: AssetFilter) -> Facets:
        """Two passes instead of five (C27): one grouped scan gives years, cameras, places,
        guessed dates and the total; one more counts photos per source you may see."""
        combos = self._grouped(
            viewer,
            f,
            """substr(a.taken_at, 1, 4) AS year, a.camera_model AS camera,
               a.date_source = 'file_mtime' AS guessed, p.country, p.city, COUNT(*) AS n""",
            "GROUP BY year, camera, guessed, p.country, p.city",
        )
        years: collections.Counter[str] = collections.Counter()
        cameras: collections.Counter[str] = collections.Counter()
        places: collections.Counter[str] = collections.Counter()
        guessed = 0
        for r in combos:
            n = int(r["n"])
            years[r["year"]] += n
            if r["camera"] is not None:
                cameras[r["camera"]] += n
            guessed += n if r["guessed"] else 0
            for name in {r["country"], r["city"]} - {None, ""}:  # each works as a filter
                places[name] += n
        return Facets(
            years=[Count(y, n) for y, n in sorted(years.items(), reverse=True)],
            sources=self._source_facets(viewer, f),
            cameras=_by_count(cameras),
            places=_by_count(places),
            guessed_dates=guessed,
            total=sum(years.values()),
        )

    def _source_facets(self, viewer: Viewer, f: AssetFilter) -> list[Count]:
        visible, _, params = visibility(viewer)
        where, fparams = filter_sql(f)
        rows = self._all(
            f"""SELECT s.id AS k, s.label AS label, COUNT(DISTINCT a.id) AS n
                {from_sql(f)} JOIN asset_source x ON x.asset_id = a.id
                JOIN source s ON s.id = x.source_id
                {where} AND {visible} AND {SOURCE_VISIBLE}
                GROUP BY s.id ORDER BY n DESC, s.id""",
            params | fparams,
        )
        return [Count(str(r["k"]), int(r["n"]), r["label"]) for r in rows]

    def calendar(self, viewer: Viewer, f: AssetFilter) -> list[Count]:
        rows = self._grouped(
            viewer,
            f,
            "substr(a.taken_at, 1, 10) AS day, COUNT(*) AS n",
            "GROUP BY day ORDER BY day",
        )
        return [Count(r["day"], int(r["n"])) for r in rows]

    def map_points(self, viewer: Viewer, f: AssetFilter) -> list[tuple[int, float, float]]:
        rows = self._grouped(
            viewer,
            f,
            "a.id AS id, a.latitude AS lat, a.longitude AS lon",
            f"AND a.latitude IS NOT NULL AND a.longitude IS NOT NULL {ORDER}",
        )
        return [(int(r["id"]), float(r["lat"]), float(r["lon"])) for r in rows]

    # --- context around one photo ----------------------------------------------------------

    def origins_for(self, viewer: Viewer, asset_id: int) -> list[tuple[Source, str]]:
        """Where the photo came from, limited to sources this viewer may see."""
        _, _, params = visibility(viewer)
        rows = self._all(
            f"""SELECT s.*, x.relative_path FROM asset_source x
                JOIN source s ON s.id = x.source_id
                WHERE x.asset_id = :asset AND {SOURCE_VISIBLE}
                ORDER BY s.id, x.relative_path""",
            params | {"asset": asset_id},
        )
        return [
            (
                Source(
                    r["id"], r["label"], r["root"], bool(r["enabled"]), r["kind"], r["owner_id"]
                ),
                r["relative_path"],
            )
            for r in rows
        ]

    def albums_of(self, viewer: Viewer, asset_id: int) -> list[tuple[int, str]]:
        _, _, params = visibility(viewer)
        rows = self._all(
            f"""SELECT al.id, al.title FROM album_item ai JOIN album al ON al.id = ai.album_id
                WHERE ai.asset_id = :asset AND {ALBUM_VISIBLE} ORDER BY al.title, al.id""",
            params | {"asset": asset_id},
        )
        return [(int(r["id"]), str(r["title"])) for r in rows]

    def first_origin_names(self, viewer: Viewer, asset_ids: Sequence[int]) -> dict[int, str]:
        """Each photo's original file name, from the first of its sources this viewer may see
        (a hidden source's file names stay hidden: no entry). One query for any number."""
        _, _, params = visibility(viewer)
        rows = self._all(
            f"""SELECT x.asset_id, x.relative_path FROM asset_source x
                JOIN asset a ON a.id = x.asset_id JOIN source s ON s.id = x.source_id
                WHERE x.asset_id IN (SELECT value FROM json_each(:assets)) AND {SOURCE_VISIBLE}
                ORDER BY x.asset_id, x.source_id = a.first_source_id DESC, x.rowid""",
            params | {"assets": json.dumps(list(asset_ids))},
        )
        first: dict[int, str] = {}
        for r in rows:
            # the bare file name: a (Linux) name may contain "\", which Windows reads as a path
            first.setdefault(int(r["asset_id"]), re.split(r"[/\\]", str(r["relative_path"]))[-1])
        return {asset_id: name for asset_id, name in first.items() if name}

    def first_origin_name(self, viewer: Viewer, asset_id: int) -> str | None:
        return self.first_origin_names(viewer, [asset_id]).get(asset_id)

    # --- per-user state --------------------------------------------------------------------

    def set_user_state(
        self,
        user_id: int,
        asset_ids: Sequence[int],
        *,
        favourite: bool | None = None,
        hidden: bool | None = None,
    ) -> int:
        with self._transaction():
            for asset_id in asset_ids:
                self._conn.execute(
                    """INSERT INTO user_asset (user_id, asset_id, favourite, hidden)
                       VALUES (?, ?, COALESCE(?, 0), COALESCE(?, 0))
                       ON CONFLICT (user_id, asset_id) DO UPDATE SET
                           favourite = COALESCE(?, favourite), hidden = COALESCE(?, hidden)""",
                    (user_id, asset_id, favourite, hidden, favourite, hidden),
                )
        return len(asset_ids)

    def hashes_present(self, viewer: Viewer, hashes: Sequence[str]) -> dict[str, int | None]:
        """Uploads (QA A7): visible photos by id (trash and review included), purged hashes
        as None."""
        if not hashes:
            return {}
        marks = ", ".join("?" for _ in hashes)
        present: dict[str, int | None] = {
            r[0]: None
            for r in self._all(
                f"SELECT content_hash FROM purged_hash WHERE content_hash IN ({marks})",
                tuple(hashes),
            )
        }
        rows = self._all(
            f"SELECT id, content_hash FROM asset WHERE content_hash IN ({marks})", tuple(hashes)
        )
        ids = [int(r["id"]) for r in rows]
        seen = {v.id for v in self.views_by_ids(viewer, ids)}
        seen |= {v.id for v in self.views_by_ids(viewer, ids, trashed=True)}
        seen |= {v.id for v in self.views_by_ids(viewer, ids, held=True)}
        present |= {r["content_hash"]: int(r["id"]) for r in rows if r["id"] in seen}
        return present

    def set_private(self, asset_id: int, private: bool, by: int) -> None:
        """Mark (or unmark) a photo private on behalf of ``by``, the marker (QA A3)."""
        self._write(
            "UPDATE asset SET private = ?, private_by = ? WHERE id = ?",
            (int(private), by if private else None, asset_id),
        )
