"""Reading the library as one viewer: the visibility rule, filters, facets, calendar, map.

``visible_assets_cte`` is THE access rule (ARCHITECTURE §7). Every query that lists, counts,
searches or serves photos starts from it; nothing is filtered in Python afterwards.
"""

import json
import sqlite3
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta

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

_VISIBLE = """vis(asset_id, level) AS (
    SELECT g.asset_id, MIN(MAX(g.level), :vis_cap)
    FROM (
        -- a source that grants you (or everyone) a level
        SELECT x.asset_id AS asset_id, sa.level AS level
          FROM asset_source x JOIN source_access sa ON sa.source_id = x.source_id
         WHERE sa.user_id IS NULL OR sa.user_id = :vis_uid
        UNION ALL
        -- a source you own
        SELECT x.asset_id, 3
          FROM asset_source x JOIN source s ON s.id = x.source_id
         WHERE s.owner_id = :vis_uid
        UNION ALL
        -- an album you own (download) or that is shared with you (viewer: view, editor: download)
        SELECT ai.asset_id,
               CASE WHEN al.owner_id = :vis_uid OR am.role = 'editor' THEN 2 ELSE 1 END
          FROM album_item ai JOIN album al ON al.id = ai.album_id
          LEFT JOIN album_member am ON am.album_id = al.id AND am.user_id = :vis_uid
         WHERE al.owner_id = :vis_uid OR am.user_id IS NOT NULL
        UNION ALL
        -- admins: everything
        SELECT id, 3 FROM asset WHERE :vis_admin
    ) g
    JOIN asset a ON a.id = g.asset_id
    LEFT JOIN source fs ON fs.id = a.first_source_id
    -- private photos are for their owner only (admins included)
    WHERE (a.private = 0 OR fs.owner_id = :vis_uid)
      AND (a.trashed_at IS NOT NULL) = :vis_trashed
    GROUP BY g.asset_id
)"""

ASSET_FROM = """FROM asset a JOIN vis ON vis.asset_id = a.id
    LEFT JOIN user_asset ua ON ua.asset_id = a.id AND ua.user_id = :vis_uid
    LEFT JOIN source fs ON fs.id = a.first_source_id
    LEFT JOIN place p ON p.id = a.place_id
    LEFT JOIN edit_recipe er ON er.asset_id = a.id"""

ASSET_COLUMNS = """a.*, vis.level AS vis_level, COALESCE(ua.favourite, 0) AS vis_favourite,
    COALESCE(ua.hidden, 0) AS vis_hidden, fs.owner_id AS vis_owner, p.country, p.region, p.city,
    er.recipe_json AS vis_recipe"""

# Albums and sources you can see (used for search, facets, origins and album lists).
ALBUM_VISIBLE = """(:vis_admin OR al.owner_id = :vis_uid OR EXISTS (
    SELECT 1 FROM album_member m WHERE m.album_id = al.id AND m.user_id = :vis_uid))"""
SOURCE_VISIBLE = """(:vis_admin OR s.owner_id = :vis_uid OR EXISTS (
    SELECT 1 FROM source_access sa WHERE sa.source_id = s.id
       AND (sa.user_id IS NULL OR sa.user_id = :vis_uid)))"""

ORDER = "ORDER BY a.taken_at DESC, a.id DESC"


def visible_assets_cte(viewer: Viewer, *, trashed: bool = False) -> tuple[str, Bindings]:
    """``WITH vis(asset_id, level)``: the photos this viewer may see and their level."""
    params: Bindings = {
        "vis_uid": viewer.user_id,
        "vis_admin": int(viewer.is_admin),
        "vis_cap": int(viewer.level_cap),
        "vis_trashed": int(trashed),
    }
    return "WITH " + _VISIBLE, params


def view_from_row(row: sqlite3.Row) -> AssetView:
    place = Place(row["country"], row["region"], row["city"]) if row["country"] else None
    trashed = row["trashed_at"]
    return AssetView(
        asset=asset_from_row(row),
        level=Level(row["vis_level"]),
        favourite=bool(row["vis_favourite"]),
        hidden=bool(row["vis_hidden"]),
        private=bool(row["private"]),
        owner_id=row["vis_owner"],
        place=place,
        edit_version=row["edit_version"],
        edited=row["vis_recipe"] is not None,
        group_id=row["group_id"],
        trashed_at=datetime.fromisoformat(trashed) if trashed else None,
        recipe=Recipe.from_dict(json.loads(row["vis_recipe"])) if row["vis_recipe"] else None,
    )


# --- filters: each adds its SQL condition(s) --------------------------------------------------


def _days(f: AssetFilter, where: Clauses, params: Bindings) -> None:
    if f.from_day:
        where.append("a.taken_at >= :f_from")
        params["f_from"] = f.from_day.isoformat()
    if f.to_day:
        where.append("a.taken_at < :f_to")
        params["f_to"] = (f.to_day + timedelta(days=1)).isoformat()


def _year_month(f: AssetFilter, where: Clauses, params: Bindings) -> None:
    if f.year is not None:
        where.append("substr(a.taken_at, 1, 4) = :f_year")
        params["f_year"] = f"{f.year:04d}"
    if f.month is not None:
        where.append("substr(a.taken_at, 6, 2) = :f_month")
        params["f_month"] = f"{f.month:02d}"


def _sources(f: AssetFilter, where: Clauses, params: Bindings) -> None:
    if not f.source_ids:
        return
    names = [f":f_src{i}" for i in range(len(f.source_ids))]
    params.update({n[1:]: sid for n, sid in zip(names, f.source_ids, strict=True)})
    where.append(
        "EXISTS (SELECT 1 FROM asset_source x WHERE x.asset_id = a.id "
        f"AND x.source_id IN ({', '.join(names)}))"
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
            f"""(EXISTS (SELECT 1 FROM asset_source x WHERE x.asset_id = a.id
                     AND x.relative_path {like})
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


def filter_sql(f: AssetFilter) -> tuple[str, Bindings]:
    """``WHERE …`` for a filter (always at least ``1``)."""
    where: Clauses = ["1"]
    params: Bindings = {}
    for add in _FILTERS:
        add(f, where, params)
    return "WHERE " + " AND ".join(where), params


class LibraryMixin(SqliteBase):
    def _filtered(
        self, viewer: Viewer, f: AssetFilter, tail: str, extra: Bindings | None = None
    ) -> list[sqlite3.Row]:
        cte, params = visible_assets_cte(viewer)
        where, fparams = filter_sql(f)
        sql = f"{cte} SELECT {ASSET_COLUMNS} {ASSET_FROM} {where} {tail}"
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
        cte, params = visible_assets_cte(viewer)
        where, fparams = filter_sql(f or AssetFilter())
        rows = self._all(f"{cte} SELECT a.id {ASSET_FROM} {where} {ORDER}", params | fparams)
        return [int(r["id"]) for r in rows]

    def list_all_views(self, viewer: Viewer, f: AssetFilter) -> list[AssetView]:
        return [view_from_row(r) for r in self._filtered(viewer, f, ORDER)]

    def views_by_ids(
        self, viewer: Viewer, ids: Sequence[int], *, trashed: bool = False
    ) -> list[AssetView]:
        if not ids:
            return []
        cte, params = visible_assets_cte(viewer, trashed=trashed)
        wanted = list(dict.fromkeys(ids))
        names = ", ".join(f":id{i}" for i in range(len(wanted)))
        params |= {f"id{i}": v for i, v in enumerate(wanted)}
        rows = self._all(
            f"{cte} SELECT {ASSET_COLUMNS} {ASSET_FROM} WHERE a.id IN ({names})", params
        )
        by_id = {r["id"]: view_from_row(r) for r in rows}
        return [by_id[i] for i in wanted if i in by_id]

    def get_view(self, viewer: Viewer, asset_id: int, *, trashed: bool = False) -> AssetView | None:
        found = self.views_by_ids(viewer, [asset_id], trashed=trashed)
        return found[0] if found else None

    def group_views(self, viewer: Viewer, group_id: int) -> list[AssetView]:
        cte, params = visible_assets_cte(viewer)
        rows = self._all(
            f"""{cte} SELECT {ASSET_COLUMNS} {ASSET_FROM} WHERE a.group_id = :group
                ORDER BY a.taken_at, a.id""",
            params | {"group": group_id},
        )
        return [view_from_row(r) for r in rows]

    def trashed_views(self, viewer: Viewer) -> list[AssetView]:
        cte, params = visible_assets_cte(viewer, trashed=True)
        rows = self._all(
            f"{cte} SELECT {ASSET_COLUMNS} {ASSET_FROM} ORDER BY a.trashed_at DESC", params
        )
        return [view_from_row(r) for r in rows]

    def count_visible(self, viewer: Viewer) -> int:
        cte, params = visible_assets_cte(viewer)
        return self._scalar(f"{cte} SELECT COUNT(*) FROM vis", params)

    # --- facets, calendar, map -------------------------------------------------------------

    def _grouped(
        self, viewer: Viewer, f: AssetFilter, select: str, group: str, joins: str = ""
    ) -> list[sqlite3.Row]:
        cte, params = visible_assets_cte(viewer)
        where, fparams = filter_sql(f)
        sql = f"{cte} SELECT {select} {ASSET_FROM} {joins} {where} {group}"
        return self._all(sql, params | fparams)

    def facets(self, viewer: Viewer, f: AssetFilter) -> Facets:
        def counts(select: str, group: str) -> list[Count]:
            rows = self._grouped(viewer, f, select, group)
            return [Count(str(r["k"]), int(r["n"]), str(r["label"] or "")) for r in rows]

        years = counts(
            "substr(a.taken_at, 1, 4) AS k, COUNT(*) AS n, '' AS label",
            "GROUP BY k ORDER BY k DESC",
        )
        cameras = counts(
            "a.camera_model AS k, COUNT(*) AS n, '' AS label",
            "AND a.camera_model IS NOT NULL GROUP BY k ORDER BY n DESC, k",
        )
        totals = self._grouped(
            viewer, f, "COUNT(*) AS n, SUM(a.date_source = 'file_mtime') AS g", ""
        )[0]
        return Facets(
            years=years,
            sources=self._source_facets(viewer, f),
            cameras=cameras,
            places=self._place_facets(viewer, f),
            guessed_dates=int(totals["g"] or 0),
            total=int(totals["n"]),
        )

    def _source_facets(self, viewer: Viewer, f: AssetFilter) -> list[Count]:
        rows = self._grouped(
            viewer,
            f,
            "s.id AS k, s.label AS label, COUNT(DISTINCT a.id) AS n",
            f"AND {SOURCE_VISIBLE} GROUP BY s.id ORDER BY n DESC, s.id",
            joins="JOIN asset_source x ON x.asset_id = a.id JOIN source s ON s.id = x.source_id",
        )
        return [Count(str(r["k"]), int(r["n"]), r["label"]) for r in rows]

    def _place_facets(self, viewer: Viewer, f: AssetFilter) -> list[Count]:
        """Countries and cities together: every name works as a ``place`` filter."""
        rows = self._grouped(
            viewer,
            f,
            "p.country AS country, p.city AS city, COUNT(*) AS n",
            "AND p.id IS NOT NULL GROUP BY p.country, p.city",
        )
        totals: dict[str, int] = {}
        for r in rows:
            for name in {r["country"], r["city"]} - {""}:
                totals[name] = totals.get(name, 0) + int(r["n"])
        ordered = sorted(totals.items(), key=lambda kv: (-kv[1], kv[0]))
        return [Count(name, n) for name, n in ordered]

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
        cte, params = visible_assets_cte(viewer)
        rows = self._all(
            f"""{cte} SELECT s.*, x.relative_path FROM asset_source x
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
        cte, params = visible_assets_cte(viewer)
        rows = self._all(
            f"""{cte} SELECT al.id, al.title FROM album_item ai JOIN album al ON al.id = ai.album_id
                WHERE ai.asset_id = :asset AND {ALBUM_VISIBLE} ORDER BY al.title, al.id""",
            params | {"asset": asset_id},
        )
        return [(int(r["id"]), str(r["title"])) for r in rows]

    def first_origin_name(self, asset_id: int) -> str | None:
        row = self._one(
            """SELECT x.relative_path FROM asset a JOIN asset_source x ON x.asset_id = a.id
               WHERE a.id = ? ORDER BY x.source_id = a.first_source_id DESC, x.rowid LIMIT 1""",
            (asset_id,),
        )
        return str(row["relative_path"]).rsplit("/", 1)[-1] if row else None

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

    def set_private(self, asset_id: int, private: bool) -> None:
        self._write("UPDATE asset SET private = ? WHERE id = ?", (int(private), asset_id))
