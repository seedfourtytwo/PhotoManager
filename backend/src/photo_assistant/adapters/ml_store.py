"""MlStore on SQLite + sqlite-vec: embeddings, faces, people, tags (migration 0015).

KNN is brute force with sqlite-vec's ``vec_distance_cosine`` over float32 BLOBs, restricted to
a candidate set held in a temp table — the visible asset ids passed in by the caller. Use a
connection of its own (``open_ml_store``) next to the repository's: each has its own lock.
"""

import json
import sqlite3
import struct
import threading
from collections.abc import Collection, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import sqlite_vec  # type: ignore[import-untyped]

from photo_assistant.adapters.sqlite_repository import open_database
from photo_assistant.domain.faces import BoundingBox, Face
from photo_assistant.domain.tags import TagScore
from photo_assistant.domain.vectors import Vector
from photo_assistant.ports.ml import PersonSummary, ScoredAsset, StoredFace

_FACE_COLUMNS = "f.id, f.asset_id, f.box_x, f.box_y, f.box_w, f.box_h, f.score, f.person_id"


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


def open_ml_store(path: str | Path) -> "SqliteMlStore":
    """A second connection to the library database (migrated), with sqlite-vec loaded."""
    return SqliteMlStore(open_database(path))


def _stored_face(row: sqlite3.Row) -> StoredFace:
    box = BoundingBox(row["box_x"], row["box_y"], row["box_w"], row["box_h"])
    return StoredFace(row["id"], row["asset_id"], box, row["score"], row["person_id"])


class SqliteMlStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        load_sqlite_vec(conn)
        conn.execute("CREATE TEMP TABLE IF NOT EXISTS ml_candidates (asset_id INTEGER PRIMARY KEY)")

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def vec_version(self) -> str:
        return str(self._scalar("SELECT vec_version()"))

    # --- helpers ---------------------------------------------------------------------------

    def _all(self, sql: str, params: Sequence[object] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, tuple(params)).fetchall()

    def _scalar(self, sql: str, params: Sequence[object] = ()) -> Any:
        # Any: SQLite values are dynamically typed; callers convert to the type they expect.
        with self._lock:
            row = self._conn.execute(sql, tuple(params)).fetchone()
            return None if row is None else row[0]

    def _write(self, sql: str, params: Sequence[object] = ()) -> int:
        with self._lock:
            return int(self._conn.execute(sql, tuple(params)).lastrowid or 0)

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self._conn.execute("BEGIN")
            try:
                yield self._conn
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise
            self._conn.execute("COMMIT")

    @contextmanager
    def _candidates(self, ids: Collection[int]) -> Iterator[None]:
        """Fill the temp candidate table for one query (held under the lock)."""
        with self._lock:
            self._conn.execute("DELETE FROM temp.ml_candidates")
            self._conn.executemany(
                "INSERT OR IGNORE INTO temp.ml_candidates VALUES (?)", ((i,) for i in ids)
            )
            try:
                yield
            finally:
                self._conn.execute("DELETE FROM temp.ml_candidates")

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
        self, query: Vector, model: str, candidates: Collection[int], limit: int
    ) -> list[ScoredAsset]:
        if not candidates:
            return []
        sql = (
            "SELECT e.asset_id, vec_distance_cosine(e.embedding, ?) AS d "
            "FROM clip_embedding e JOIN temp.ml_candidates c ON c.asset_id = e.asset_id "
            "WHERE e.model = ? AND e.dim = ? ORDER BY d, e.asset_id LIMIT ?"
        )
        with self._candidates(candidates):
            rows = self._all(sql, (to_blob(query), model, len(query), limit))
        return [ScoredAsset(r[0], 1.0 - r[1]) for r in rows]

    # --- faces -----------------------------------------------------------------------------

    def replace_faces(self, asset_id: int, model: str, faces: Sequence[Face]) -> list[int]:
        with self._transaction() as conn:
            conn.execute("DELETE FROM face WHERE asset_id = ? AND model = ?", (asset_id, model))
            return [self._insert_face(conn, asset_id, model, face) for face in faces]

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

    _NEIGHBOURS = (
        "FROM face f JOIN face me ON me.id = ? "
        "WHERE f.model = me.model AND f.dim = me.dim AND f.id != me.id "
        "AND vec_distance_cosine(f.embedding, me.embedding) <= ?"
    )

    def count_face_matches(self, face_id: int, max_distance: float, limit: int) -> int:
        sql = f"SELECT count(*) FROM (SELECT 1 {self._NEIGHBOURS} LIMIT ?)"
        return int(self._scalar(sql, (face_id, max_distance, limit)))

    def nearest_person(self, face_id: int, max_distance: float) -> int | None:
        sql = (
            f"SELECT f.person_id {self._NEIGHBOURS} AND f.person_id IS NOT NULL "
            "ORDER BY vec_distance_cosine(f.embedding, me.embedding), f.id LIMIT 1"
        )
        value = self._scalar(sql, (face_id, max_distance))
        return None if value is None else int(value)

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

    # --- people ----------------------------------------------------------------------------

    _PERSONS = (
        "SELECT p.id, p.name, p.cover_face_id, count(f.id) AS faces, "
        "count(DISTINCT f.asset_id) AS assets "
        "FROM person p JOIN face f ON f.person_id = p.id "
        "JOIN temp.ml_candidates c ON c.asset_id = f.asset_id "
    )

    def _persons(
        self, where: str, params: Sequence[object], visible: Collection[int]
    ) -> list[PersonSummary]:
        sql = self._PERSONS + where + " GROUP BY p.id ORDER BY p.name IS NULL, assets DESC, p.id"
        with self._candidates(visible):
            rows = self._all(sql, params)
            return [self._summary(r) for r in rows]

    def _summary(self, row: sqlite3.Row) -> PersonSummary:
        """Runs inside _candidates: the cover is the chosen face if visible, else the best."""
        cover_id = self._scalar(
            "SELECT f.id FROM face f JOIN temp.ml_candidates c ON c.asset_id = f.asset_id "
            "WHERE f.person_id = ? ORDER BY f.id = ? DESC, f.score DESC, f.id LIMIT 1",
            (row["id"], row["cover_face_id"]),
        )
        cover = self.get_face(int(cover_id))
        return PersonSummary(row["id"], row["name"], cover, row["faces"], row["assets"])

    def list_persons(self, visible: Collection[int]) -> list[PersonSummary]:
        return self._persons("", (), visible)

    def get_person(self, person_id: int, visible: Collection[int]) -> PersonSummary | None:
        found = self._persons("WHERE p.id = ?", (person_id,), visible)
        return found[0] if found else None

    def rename_person(self, person_id: int, name: str | None) -> None:
        self._write("UPDATE person SET name = ? WHERE id = ?", (name, person_id))

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

    def person_asset_ids(self, person_id: int, visible: Collection[int]) -> list[int]:
        sql = (
            "SELECT DISTINCT f.asset_id FROM face f "
            "JOIN temp.ml_candidates c ON c.asset_id = f.asset_id "
            "WHERE f.person_id = ? ORDER BY f.asset_id"
        )
        with self._candidates(visible):
            return [r[0] for r in self._all(sql, (person_id,))]

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

    def asset_ids_with_tag(self, name: str, visible: Collection[int]) -> list[int]:
        """For the ``tag:`` search facet; tag names match case-insensitively."""
        sql = (
            "SELECT a.asset_id FROM asset_tag a JOIN tag t ON t.id = a.tag_id "
            "JOIN temp.ml_candidates c ON c.asset_id = a.asset_id "
            "WHERE t.name = ? COLLATE NOCASE ORDER BY a.asset_id"
        )
        with self._candidates(visible):
            return [r[0] for r in self._all(sql, (name,))]

    def screen_or_document_ids(self, visible: Collection[int]) -> list[int]:
        """Screenshots, documents, receipts, memes: left out of "memories" by default."""
        sql = (
            "SELECT f.asset_id FROM asset_ml_flag f "
            "JOIN temp.ml_candidates c ON c.asset_id = f.asset_id "
            "WHERE f.screen_or_document = 1 ORDER BY f.asset_id"
        )
        with self._candidates(visible):
            return [r[0] for r in self._all(sql)]
