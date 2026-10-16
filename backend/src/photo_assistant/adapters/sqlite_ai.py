"""What the local AI made, on SQLite (migration 0035): photo captions and the plans for
suggested albums. Both are proposals or derived fields; nothing here changes a photo."""

import json
from collections.abc import Sequence

from photo_assistant.adapters.sqlite_base import SqliteBase
from photo_assistant.domain.album_plan import AlbumPlan, plan_from_json, plan_to_json
from photo_assistant.domain.media_types import MediaKind

CAPTION_TASK = "ai_caption"  # its ml_task rows: the photos a model could not describe


def _marks(ids: Sequence[int]) -> str:
    return ", ".join("?" for _ in ids)


class AIMixin(SqliteBase):
    def photos_to_caption(self, model: str, after_id: int, limit: int) -> list[tuple[int, str]]:
        """Photos in the library (not held, not trashed) with no caption that ``model`` has not
        failed on, by id after ``after_id``; with the best rendition to read."""
        rows = self._all(
            """SELECT a.id, coalesce(a.preview_path, a.thumb_path, a.library_path) AS path
               FROM asset a
               WHERE a.id > ? AND a.kind = ? AND a.trashed_at IS NULL AND a.held_reason IS NULL
                 AND NOT EXISTS (SELECT 1 FROM asset_caption c WHERE c.asset_id = a.id)
                 AND NOT EXISTS (SELECT 1 FROM ml_task t
                                 WHERE t.asset_id = a.id AND t.task = ? AND t.model = ?)
               ORDER BY a.id LIMIT ?""",
            (after_id, MediaKind.PHOTO.value, CAPTION_TASK, model, limit),
        )
        return [(int(r["id"]), str(r["path"])) for r in rows]

    def save_caption(self, asset_id: int, text: str, model: str, lang: str) -> None:
        self._write(
            """INSERT INTO asset_caption (asset_id, text, model, lang) VALUES (?, ?, ?, ?)
               ON CONFLICT (asset_id) DO UPDATE SET text = excluded.text, model = excluded.model,
                   lang = excluded.lang, created_at = excluded.created_at""",
            (asset_id, text, model, lang),
        )

    def caption_failed(self, asset_id: int, model: str, detail: str) -> None:
        self._write(
            """INSERT OR REPLACE INTO ml_task (asset_id, task, model, status, detail)
               VALUES (?, ?, ?, 'failed', ?)""",
            (asset_id, CAPTION_TASK, model, detail),
        )

    def captions_of(self, asset_ids: Sequence[int]) -> dict[int, str]:
        rows = self._all(
            f"SELECT asset_id, text FROM asset_caption WHERE asset_id IN ({_marks(asset_ids)})",
            tuple(asset_ids),
        )
        return {int(r["asset_id"]): str(r["text"]) for r in rows}

    def tags_of_assets(self, asset_ids: Sequence[int]) -> dict[int, tuple[str, ...]]:
        rows = self._all(
            f"""SELECT at.asset_id, t.name FROM asset_tag at JOIN tag t ON t.id = at.tag_id
                WHERE at.asset_id IN ({_marks(asset_ids)}) ORDER BY at.asset_id, t.name""",
            tuple(asset_ids),
        )
        found: dict[int, tuple[str, ...]] = {}
        for r in rows:
            found[int(r["asset_id"])] = (*found.get(int(r["asset_id"]), ()), str(r["name"]))
        return found

    def album_plan(self, key: str, photos: str) -> AlbumPlan | None:
        row = self._one(
            "SELECT plan_json FROM album_suggestion_plan WHERE key = ? AND photos = ?",
            (key, photos),
        )
        return None if row is None else plan_from_json(json.loads(row["plan_json"]))

    def save_album_plan(self, key: str, photos: str, model: str, plan: AlbumPlan) -> None:
        """Store the plan; the event's older plans (made for other photos) go."""
        with self._transaction():
            self._conn.execute("DELETE FROM album_suggestion_plan WHERE key = ?", (key,))
            self._conn.execute(
                """INSERT INTO album_suggestion_plan (key, photos, model, plan_json)
                   VALUES (?, ?, ?, ?)""",
                (key, photos, model, json.dumps(plan_to_json(plan))),
            )
