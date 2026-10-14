"""MlStore on SQLite + sqlite-vec: embeddings, faces, people, tags (migration 0015).

KNN is brute force with sqlite-vec's ``vec_distance_cosine`` over float32 BLOBs, restricted to
what the caller may see: a viewer (the library's access rule, in the same statement) or a
candidate set of asset ids held in a temp table. It shares the process's one ``Database``
(writer and lock) with every other store.
"""

import json
import math
import sqlite3
import struct
from collections.abc import Collection, Iterable, Iterator, Mapping, Sequence
from contextlib import AbstractContextManager, contextmanager
from typing import Any

import sqlite_vec  # type: ignore[import-untyped]

from photo_assistant.adapters.sqlite_database import Database
from photo_assistant.adapters.sqlite_library import ASSET_FROM, ORDER, filter_sql, visibility
from photo_assistant.domain.access import Viewer
from photo_assistant.domain.faces import (
    BoundingBox,
    Circle,
    Face,
    automatic_circle,
    overlap,
    photo_size,
)
from photo_assistant.domain.library_filter import AssetFilter
from photo_assistant.domain.tags import TagScore
from photo_assistant.domain.vectors import Vector
from photo_assistant.ports.ml import (
    FaceChanges,
    FaceMatches,
    PersonSummary,
    Portrait,
    ScoredAsset,
    StoredFace,
    Visible,
)

_FACE_COLUMNS = "f.id, f.asset_id, f.box_x, f.box_y, f.box_w, f.box_h, f.score, f.person_id"
_FACE_ON_ITS_PHOTO = (
    f"SELECT {_FACE_COLUMNS}, a.content_hash, a.library_path, a.width, a.height, "
    "a.thumb_w, a.thumb_h FROM face f JOIN asset a ON a.id = f.asset_id WHERE f.id = ?"
)
_COVERS_ON = (
    f"SELECT pe.id AS person, {_FACE_COLUMNS} FROM person pe "
    "JOIN face f ON f.id = pe.cover_face_id WHERE f.asset_id = ? AND f.model = ?"
)
# A face detected again is the same face if its box shares this much with the old one.
_SAME_FACE = 0.5


def to_blob(vector: Sequence[float]) -> bytes:
    return struct.pack(f"<{len(vector)}f", *vector)


def from_blob(blob: bytes) -> Vector:
    return struct.unpack(f"<{len(blob) // 4}f", blob)


def load_sqlite_vec(conn: sqlite3.Connection) -> None:
    conn.enable_load_extension(True)
    try:
        sqlite_vec.load(conn)
    finally:
        conn.enable_load_extension(False)


def _stored_face(row: sqlite3.Row) -> StoredFace:
    box = BoundingBox(row["box_x"], row["box_y"], row["box_w"], row["box_h"])
    return StoredFace(row["id"], row["asset_id"], box, row["score"], row["person_id"])


class SqliteMlStore:
    """On the process's one ``Database``. Every query runs on the writer under the one lock:
    the KNN candidates live in a temp table, which belongs to a single connection."""

    def __init__(self, db: Database) -> None:
        self._db = db
        self._conn = self._db.writer
        self._lock = self._db.lock
        with self._lock:
            load_sqlite_vec(self._conn)
            self._conn.execute(
                "CREATE TEMP TABLE IF NOT EXISTS ml_candidates (asset_id INTEGER PRIMARY KEY)"
            )
            self._conn.execute(
                "CREATE TEMP TABLE IF NOT EXISTS ml_near_faces "
                "(face_id INTEGER PRIMARY KEY, dim INTEGER, embedding BLOB)"
            )

    def close(self) -> None:
        self._db.close()

    def vec_version(self) -> str:
        return str(self._scalar("SELECT vec_version()"))

    # --- helpers ---------------------------------------------------------------------------

    def _all(
        self, sql: str, params: Sequence[object] | dict[str, object] = ()
    ) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def _scalar(self, sql: str, params: Sequence[object] | dict[str, object] = ()) -> Any:
        # Any: SQLite values are dynamically typed; callers convert to the type they expect.
        with self._lock:
            row = self._conn.execute(sql, params).fetchone()
            return None if row is None else row[0]

    def _write(self, sql: str, params: Sequence[object] = ()) -> int:
        with self._lock:
            return int(self._conn.execute(sql, tuple(params)).lastrowid or 0)

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        with self._db.transaction() as conn:
            yield conn

    @contextmanager
    def _shown(self, visible: Visible) -> Iterator[tuple[str, dict[str, object]]]:
        """For queries run inside (held under the lock): ``SELECT a.id … WHERE …``, the photos
        ``visible`` covers, open for more conditions on ``a``; and its bindings.

        A viewer: THE access rule and the default filter (their hidden photos are left out),
        the two things ``visible_asset_ids`` puts in its query. Ids: the temp table.

        A query over much of the library asks ``x IN (that select)``: the rule runs once per
        photo. A query about a few photos (one person's) adds ``AND a.id = x`` or
        ``AND a.id IN (…)``, so only those photos are looked up, not the library listed."""
        if isinstance(visible, Viewer):
            rule, _, bindings = visibility(visible)
            where, filtered = filter_sql(AssetFilter())
            with self._lock:
                yield f"SELECT a.id {ASSET_FROM} {where} AND {rule}", bindings | filtered
        else:
            with self._candidates(visible):
                yield (
                    (
                        "SELECT a.id FROM asset a JOIN temp.ml_candidates c ON c.asset_id = a.id "
                        "WHERE 1"
                    ),
                    {},
                )

    def seen(self, asset_ids: Collection[int], visible: Visible) -> set[int]:
        if not isinstance(visible, Viewer):
            return set(asset_ids).intersection(visible)
        with self._shown(visible) as (shown, bindings):
            sql = f"{shown} AND a.id IN (SELECT value FROM json_each(:ids))"
            return {r[0] for r in self._all(sql, bindings | {"ids": json.dumps(list(asset_ids))})}

    def _candidates(self, ids: Collection[int]) -> AbstractContextManager[None]:
        """Fill the temp candidate table for one query (held under the lock)."""
        fill = "INSERT OR IGNORE INTO temp.ml_candidates VALUES (?)"
        return self._temp_rows("ml_candidates", fill, ((i,) for i in ids))

    @contextmanager
    def _temp_rows(
        self, table: str, fill: str, rows: Iterable[tuple[object, ...]]
    ) -> Iterator[None]:
        with self._lock:
            # one transaction for the fill: in autocommit every row is a transaction of its
            # own. Deferred (plain BEGIN): only the temp table is written, so a search never
            # waits for the library file's write lock.
            own = not self._conn.in_transaction
            if own:
                self._conn.execute("BEGIN")
            try:
                self._conn.execute(f"DELETE FROM temp.{table}")
                self._conn.executemany(fill, rows)
                if own:
                    self._conn.execute("COMMIT")
            except BaseException:
                if own and self._conn.in_transaction:
                    self._conn.execute("ROLLBACK")
                raise
            try:
                yield
            finally:
                self._conn.execute(f"DELETE FROM temp.{table}")

    # --- task bookkeeping ------------------------------------------------------------------

    def task_status(self, asset_id: int, task: str, model: str) -> str | None:
        value = self._scalar(
            "SELECT status FROM ml_task WHERE asset_id = ? AND task = ? AND model = ?",
            (asset_id, task, model),
        )
        return None if value is None else str(value)

    def set_task_status(
        self, asset_id: int, task: str, model: str, status: str, detail: str | None = None
    ) -> None:
        self._write(
            "INSERT INTO ml_task (asset_id, task, model, status, detail) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT (asset_id, task, model) DO UPDATE SET status = excluded.status, "
            "detail = excluded.detail, "
            "updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')",
            (asset_id, task, model, status, detail),
        )

    def assets_with_status(self, task: str, model: str, status: str) -> list[int]:
        rows = self._all(
            "SELECT asset_id FROM ml_task WHERE task = ? AND model = ? AND status = ? "
            "ORDER BY asset_id",
            (task, model, status),
        )
        return [r[0] for r in rows]

    def task_counts(self) -> dict[str, dict[str, int]]:
        """``{task: {status: n}}`` over every asset, for the ML status page."""
        counts: dict[str, dict[str, int]] = {}
        for row in self._all(
            "SELECT task, status, COUNT(*) AS n FROM ml_task GROUP BY task, status ORDER BY 1, 2"
        ):
            counts.setdefault(row["task"], {})[row["status"]] = int(row["n"])
        return counts

    # --- CLIP ------------------------------------------------------------------------------

    def save_clip(self, asset_id: int, model: str, vector: Vector) -> None:
        if not any(vector) or not all(math.isfinite(x) for x in vector):
            raise ValueError("an embedding needs a direction: not all zeros, no NaN or infinity")
        self._write(
            "INSERT OR REPLACE INTO clip_embedding (model, asset_id, dim, embedding) "
            "VALUES (?, ?, ?, ?)",
            (model, asset_id, len(vector), to_blob(vector)),
        )

    def clip_vector(self, asset_id: int, model: str) -> Vector | None:
        blob = self._scalar(
            "SELECT embedding FROM clip_embedding WHERE model = ? AND asset_id = ?",
            (model, asset_id),
        )
        return None if blob is None else from_blob(bytes(blob))

    def nearest_assets(
        self,
        query: Vector,
        model: str,
        candidates: Visible,
        limit: int,
        *,
        leave_out: int | None = None,
    ) -> list[ScoredAsset]:
        if not isinstance(candidates, Viewer) and not candidates:
            return []
        # A zero vector has no angle to anything: its distance is NULL and it is left out.
        # MATERIALIZED: the distance is computed once per photo, not again for the filter.
        with self._shown(candidates) as (shown, bindings):
            sql = (
                "WITH scored AS MATERIALIZED ("
                "SELECT e.asset_id AS asset_id, vec_distance_cosine(e.embedding, :query) AS d "
                "FROM clip_embedding e WHERE e.model = :model AND e.dim = :dim "
                f"AND e.asset_id IS NOT :leave_out AND e.asset_id IN ({shown})) "
                "SELECT asset_id, d FROM scored WHERE d IS NOT NULL ORDER BY d, asset_id "
                "LIMIT :limit"
            )
            asked = {"query": to_blob(query), "model": model, "dim": len(query)}
            rows = self._all(sql, bindings | asked | {"leave_out": leave_out, "limit": limit})
        return [ScoredAsset(r[0], 1.0 - r[1]) for r in rows]

    # --- faces -----------------------------------------------------------------------------

    def replace_faces(self, asset_id: int, model: str, faces: Sequence[Face]) -> list[int]:
        with self._transaction() as conn:
            were_covers = conn.execute(_COVERS_ON, (asset_id, model)).fetchall()
            conn.execute("DELETE FROM face WHERE asset_id = ? AND model = ?", (asset_id, model))
            ids = [self._insert_face(conn, asset_id, model, face) for face in faces]
            # deleting a cover emptied the person's choice: the face found in its place
            # takes it over, so a chosen portrait outlives a photo being analysed again
            for row in were_covers if faces else ():
                old = _stored_face(row).box
                shared, face_id = max(
                    (overlap(old, face.box), face_id)
                    for face_id, face in zip(ids, faces, strict=True)
                )
                if shared >= _SAME_FACE:
                    conn.execute(
                        "UPDATE person SET cover_face_id = ? WHERE id = ?", (face_id, row["person"])
                    )
            return ids

    @staticmethod
    def _insert_face(conn: sqlite3.Connection, asset_id: int, model: str, face: Face) -> int:
        box = face.box
        cur = conn.execute(
            "INSERT INTO face (asset_id, model, box_x, box_y, box_w, box_h, score, "
            "landmarks_json, dim, embedding) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                asset_id, model, box.x, box.y, box.width, box.height, face.score,
                json.dumps([list(p) for p in face.landmarks]),
                len(face.embedding), to_blob(face.embedding),
            ),
        )  # fmt: skip
        return int(cur.lastrowid or 0)

    def faces_to_cluster(
        self, model: str, *, deferred: bool, asset_id: int | None = None
    ) -> list[int]:
        state = "deferred" if deferred else "new"
        sql = "SELECT id FROM face WHERE model = ? AND cluster_state = ? AND person_id IS NULL"
        params: list[object] = [model, state]
        if asset_id is not None:
            sql += " AND asset_id = ?"
            params.append(asset_id)
        return [r[0] for r in self._all(sql + " ORDER BY id", params)]

    # LIMIT -1 keeps SQLite from merging the inner query into the outer one, which would
    # compute the distance a second time for every match: one scan, one distance per face.
    _MATCHES = (
        "WITH near AS MATERIALIZED (SELECT id, person_id, d FROM ("
        "SELECT f.id AS id, f.person_id AS person_id, "
        "vec_distance_cosine(f.embedding, me.embedding) AS d "
        "FROM face f JOIN face me ON me.id = ? "
        "WHERE f.model = me.model AND f.dim = me.dim AND f.id != me.id LIMIT -1) "
        "WHERE d <= ?) "
        "SELECT (SELECT count(*) FROM near), (SELECT person_id FROM near "
        "WHERE person_id IS NOT NULL ORDER BY d, id LIMIT 1)"
    )

    def face_matches(self, face_id: int, max_distance: float) -> FaceMatches:
        (row,) = self._all(self._MATCHES, (face_id, max_distance))
        return FaceMatches(int(row[0]), row[1])

    # created_at and the first numbers of the embedding: a face detected again can get the
    # id of the face it replaced. Only the faces that differ come back, not all of them.
    _CHANGED = (
        "SELECT f.id, f.person_id, f.cluster_state, f.created_at, substr(f.embedding, 1, 16) "
        "FROM face f LEFT JOIN face_cluster_mark m ON m.face_id = f.id "
        "WHERE f.model = ? AND (m.face_id IS NULL OR m.person_id IS NOT f.person_id "
        "OR m.cluster_state != f.cluster_state OR m.created_at != f.created_at "
        "OR m.fingerprint != substr(f.embedding, 1, 16))"
    )

    def face_changes(self, model: str) -> FaceChanges:
        with self._transaction() as conn:  # the settings and the marks of the same pass
            rule = conn.execute(
                "SELECT rule FROM face_cluster_pass WHERE model = ?", (model,)
            ).fetchone()
            rows = conn.execute(self._CHANGED, (model,)).fetchall()
        return FaceChanges(None if rule is None else rule[0], {r[0]: tuple(r)[1:] for r in rows})

    def keep_face_marks(
        self, model: str, rule: str, marks: Mapping[int, tuple[object, ...]]
    ) -> None:
        # A face deleted since its mark was read gets no row (it would point at nothing). A
        # face that got its id meanwhile differs from this mark, so it still counts as changed.
        keep = (
            "INSERT OR REPLACE INTO face_cluster_mark "
            "(face_id, person_id, cluster_state, created_at, fingerprint) "
            "SELECT id, ?, ?, ?, ? FROM face WHERE id = ?"
        )
        with self._transaction() as conn:
            conn.executemany(keep, ((*mark, face_id) for face_id, mark in marks.items()))
            conn.execute("INSERT OR REPLACE INTO face_cluster_pass VALUES (?, ?)", (model, rule))

    def deferred_faces_near(
        self, model: str, face_ids: Collection[int], max_distance: float
    ) -> list[int]:
        if not face_ids:
            return []
        # The given faces' vectors are copied next to each other first: each deferred face
        # is held against that small table, never against the whole face table.
        sql = (
            "SELECT d.id FROM face d WHERE d.model = ? AND d.cluster_state = 'deferred' "
            "AND d.person_id IS NULL AND EXISTS (SELECT 1 FROM temp.ml_near_faces n "
            "WHERE n.face_id != d.id AND n.dim = d.dim "
            "AND vec_distance_cosine(n.embedding, d.embedding) <= ?) ORDER BY d.id"
        )
        fill = (
            "INSERT OR IGNORE INTO temp.ml_near_faces "
            "SELECT id, dim, embedding FROM face WHERE id = ? AND model = ?"
        )
        with self._temp_rows("ml_near_faces", fill, ((i, model) for i in face_ids)):
            return [r[0] for r in self._all(sql, (model, max_distance))]

    def mark_deferred(self, face_id: int) -> None:
        self._write("UPDATE face SET cluster_state = 'deferred' WHERE id = ?", (face_id,))

    def mark_clustered(self, face_id: int) -> None:
        self._write("UPDATE face SET cluster_state = 'done' WHERE id = ?", (face_id,))

    def assign_face(self, face_id: int, person_id: int, *, by_user: bool = False) -> None:
        self._write(
            "UPDATE face SET person_id = ?, assigned_by = ?, cluster_state = 'done' WHERE id = ?",
            (person_id, "user" if by_user else "model", face_id),
        )

    def create_person(self, cover_face_id: int) -> int:
        with self._transaction() as conn:
            cur = conn.execute("INSERT INTO person (cover_face_id) VALUES (?)", (cover_face_id,))
            person_id = int(cur.lastrowid or 0)
            conn.execute(
                "UPDATE face SET person_id = ?, assigned_by = 'model', cluster_state = 'done' "
                "WHERE id = ?",
                (person_id, cover_face_id),
            )
        return person_id

    def faces_of_asset(self, asset_id: int) -> list[StoredFace]:
        rows = self._all(
            f"SELECT {_FACE_COLUMNS} FROM face f WHERE f.asset_id = ? ORDER BY f.id", (asset_id,)
        )
        return [_stored_face(r) for r in rows]

    def get_face(self, face_id: int) -> StoredFace | None:
        rows = self._all(f"SELECT {_FACE_COLUMNS} FROM face f WHERE f.id = ?", (face_id,))
        return _stored_face(rows[0]) if rows else None

    def face_portrait(self, face_id: int, chosen: Circle | None = None) -> Portrait | None:
        """``chosen``: the circle someone put on this face's photo, instead of the automatic."""
        rows = self._all(_FACE_ON_ITS_PHOTO, (face_id,))
        if not rows:
            return None
        (row,) = rows
        face = _stored_face(row)
        thumb = (row["thumb_w"], row["thumb_h"]) if row["thumb_w"] else None
        size = photo_size(row["width"], row["height"], thumb)
        return Portrait(
            face,
            chosen or automatic_circle(face.box, *size),
            chosen is not None,
            row["content_hash"],
            row["library_path"],
            size,
        )

    # --- people ----------------------------------------------------------------------------

    def _persons(
        self, visible: Visible, *, person_id: int | None = None, hidden: bool | None = None
    ) -> list[PersonSummary]:
        """Counted over the faces on photos ``visible`` covers; the cover is the chosen face
        if it is one of them, else the best of them. One pass over those faces. A chosen
        circle belongs to the chosen face: with any other cover the portrait is automatic."""
        with self._shown(visible) as (shown, bindings):
            if person_id is None:
                on_shown_photos = f"f.asset_id IN ({shown})"
            else:
                on_shown_photos = f"pe.id = :person AND EXISTS ({shown} AND a.id = f.asset_id)"
            asked: dict[str, object] = {} if person_id is None else {"person": person_id}
            if hidden is not None:
                on_shown_photos += " AND pe.hidden = :hidden"
                asked["hidden"] = int(hidden)
            sql = (
                "SELECT id, name, hidden, cover, chosen_face, cx, cy, size, count(*) AS faces, "
                "count(DISTINCT asset_id) AS assets "
                "FROM (SELECT pe.id AS id, pe.name AS name, pe.hidden AS hidden, "
                "pe.cover_face_id AS chosen_face, pe.portrait_cx AS cx, pe.portrait_cy AS cy, "
                "pe.portrait_size AS size, f.asset_id AS asset_id, "
                "first_value(f.id) OVER (PARTITION BY pe.id "
                "ORDER BY f.id = pe.cover_face_id DESC, f.score DESC, f.id) AS cover "
                f"FROM person pe JOIN face f ON f.person_id = pe.id WHERE {on_shown_photos}"
                ") GROUP BY id ORDER BY name IS NULL, assets DESC, id"
            )
            rows = self._all(sql, bindings | asked)
        found = []
        for r in rows:
            its_own = r["cover"] == r["chosen_face"] and r["size"] is not None
            circle = Circle(r["cx"], r["cy"], r["size"]) if its_own else None
            portrait = self.face_portrait(r["cover"], circle)
            found.append(
                PersonSummary(
                    r["id"],
                    r["name"],
                    portrait.face if portrait else None,
                    portrait,
                    r["faces"],
                    r["assets"],
                    bool(r["hidden"]),
                )
            )
        return found

    def list_persons(self, visible: Visible, *, hidden: bool | None = False) -> list[PersonSummary]:
        return self._persons(visible, hidden=hidden)

    def get_person(self, person_id: int, visible: Visible) -> PersonSummary | None:
        found = self._persons(visible, person_id=person_id)
        return found[0] if found else None

    def rename_person(self, person_id: int, name: str | None) -> None:
        self._write("UPDATE person SET name = ? WHERE id = ?", (name, person_id))

    def set_person_hidden(self, person_id: int, hidden: bool) -> None:
        self._write("UPDATE person SET hidden = ? WHERE id = ?", (int(hidden), person_id))

    def set_portrait(self, person_id: int, face_id: int, circle: Circle) -> None:
        self._write(
            "UPDATE person SET cover_face_id = ?, portrait_cx = ?, portrait_cy = ?, "
            "portrait_size = ? WHERE id = ?",
            (face_id, circle.cx, circle.cy, circle.size, person_id),
        )

    def clear_portrait(self, person_id: int) -> None:
        self._write(
            "UPDATE person SET portrait_cx = NULL, portrait_cy = NULL, portrait_size = NULL "
            "WHERE id = ?",
            (person_id,),
        )

    def person_faces(self, person_id: int, visible: Visible, limit: int) -> list[Portrait]:
        with self._shown(visible) as (shown, bindings):
            sql = (
                "SELECT f.id FROM face f WHERE f.person_id = :person "
                f"AND EXISTS ({shown} AND a.id = f.asset_id) "
                "ORDER BY f.score DESC, f.id LIMIT :limit"
            )
            ids = [r[0] for r in self._all(sql, bindings | {"person": person_id, "limit": limit})]
        return [portrait for face_id in ids if (portrait := self.face_portrait(face_id))]

    def merge_persons(self, target_id: int, source_ids: Sequence[int]) -> None:
        sources = [s for s in source_ids if s != target_id]
        marks = ",".join("?" * len(sources))
        with self._transaction() as conn:
            conn.execute(
                "UPDATE person SET name = coalesce(name, (SELECT name FROM person "
                f"WHERE id IN ({marks}) AND name IS NOT NULL ORDER BY id LIMIT 1)) WHERE id = ?",
                (*sources, target_id),
            )
            conn.execute(
                "UPDATE face SET person_id = ?, assigned_by = 'user', cluster_state = 'done' "
                f"WHERE person_id IN ({marks})",
                (target_id, *sources),
            )
            conn.execute(f"DELETE FROM person WHERE id IN ({marks})", sources)

    def move_faces(self, face_ids: Sequence[int], person_id: int) -> None:
        with self._transaction() as conn:
            conn.executemany(
                "UPDATE face SET person_id = ?, assigned_by = 'user', cluster_state = 'done' "
                "WHERE id = ?",
                [(person_id, face_id) for face_id in face_ids],
            )

    def create_empty_person(self, name: str | None) -> int:
        return self._write("INSERT INTO person (name) VALUES (?)", (name,))

    def person_asset_ids(self, person_id: int, visible: Visible) -> list[int]:
        with self._shown(visible) as (shown, bindings):
            sql = (
                f"{shown} AND a.id IN "
                f"(SELECT f.asset_id FROM face f WHERE f.person_id = :person) {ORDER}"
            )
            return [r[0] for r in self._all(sql, bindings | {"person": person_id})]

    def delete_empty_persons(self) -> int:
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM person WHERE NOT EXISTS "
                "(SELECT 1 FROM face WHERE face.person_id = person.id)"
            )
            return cur.rowcount

    # --- tags ------------------------------------------------------------------------------

    def replace_model_tags(
        self, asset_id: int, model: str, tags: Sequence[TagScore], screen_or_document: bool
    ) -> None:
        with self._transaction() as conn:
            conn.execute("DELETE FROM asset_tag WHERE asset_id = ? AND by = 'model'", (asset_id,))
            for tag in tags:
                conn.execute("INSERT OR IGNORE INTO tag (name) VALUES (?)", (tag.name,))
                conn.execute(
                    "INSERT OR IGNORE INTO asset_tag (asset_id, tag_id, score, by, model) "
                    "SELECT ?, id, ?, 'model', ? FROM tag WHERE name = ?",
                    (asset_id, tag.score, model, tag.name),
                )
            conn.execute(
                "INSERT OR REPLACE INTO asset_ml_flag (asset_id, screen_or_document, model) "
                "VALUES (?, ?, ?)",
                (asset_id, int(screen_or_document), model),
            )

    def tags_of(self, asset_id: int) -> list[TagScore]:
        rows = self._all(
            "SELECT t.name, coalesce(a.score, 1.0) AS score FROM asset_tag a "
            "JOIN tag t ON t.id = a.tag_id WHERE a.asset_id = ? ORDER BY score DESC, t.name",
            (asset_id,),
        )
        return [TagScore(r["name"], r["score"]) for r in rows]

    def is_screen_or_document(self, asset_id: int) -> bool | None:
        value = self._scalar(
            "SELECT screen_or_document FROM asset_ml_flag WHERE asset_id = ?", (asset_id,)
        )
        return None if value is None else bool(value)

    def asset_ids_with_tag(self, name: str, visible: Visible) -> list[int]:
        """For the ``tag:`` search facet; tag names match case-insensitively."""
        with self._shown(visible) as (shown, bindings):
            sql = (
                "SELECT t.asset_id FROM asset_tag t JOIN tag n ON n.id = t.tag_id "
                f"WHERE n.name = :name COLLATE NOCASE AND t.asset_id IN ({shown}) "
                "ORDER BY t.asset_id"
            )
            return [r[0] for r in self._all(sql, bindings | {"name": name})]

    def screen_or_document_ids(self, visible: Visible) -> list[int]:
        """Screenshots, documents, receipts, memes: left out of "memories" by default."""
        with self._shown(visible) as (shown, bindings):
            sql = (
                "SELECT m.asset_id FROM asset_ml_flag m "
                f"WHERE m.screen_or_document = 1 AND m.asset_id IN ({shown}) "
                "ORDER BY m.asset_id"
            )
            return [r[0] for r in self._all(sql, bindings)]
