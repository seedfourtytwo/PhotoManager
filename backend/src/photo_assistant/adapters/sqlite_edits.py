"""Edit recipes and manual date fixes (FEATURES 4c, 2.12)."""

import json
from collections.abc import Sequence
from datetime import datetime

from photo_assistant.adapters.sqlite_accounts import utc_text
from photo_assistant.adapters.sqlite_base import SqliteBase
from photo_assistant.domain.capture_time import DateSource
from photo_assistant.domain.edit_recipe import Recipe


class EditsMixin(SqliteBase):
    def get_recipe(self, asset_id: int) -> Recipe | None:
        row = self._one("SELECT recipe_json FROM edit_recipe WHERE asset_id = ?", (asset_id,))
        return Recipe.from_dict(json.loads(row["recipe_json"])) if row else None

    def save_recipe(self, asset_id: int, recipe: Recipe, user_id: int, now: datetime) -> None:
        with self._transaction():
            self._conn.execute(
                """INSERT INTO edit_recipe (asset_id, recipe_json, updated_by, updated_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT (asset_id) DO UPDATE SET recipe_json = excluded.recipe_json,
                       updated_by = excluded.updated_by, updated_at = excluded.updated_at""",
                (asset_id, json.dumps(recipe.to_dict()), user_id, utc_text(now)),
            )
            self._bump_version(asset_id)

    def delete_recipe(self, asset_id: int) -> None:
        with self._transaction():
            self._conn.execute("DELETE FROM edit_recipe WHERE asset_id = ?", (asset_id,))
            self._bump_version(asset_id)

    def _bump_version(self, asset_id: int) -> None:
        self._conn.execute(
            "UPDATE asset SET edit_version = edit_version + 1 WHERE id = ?", (asset_id,)
        )

    def change_dates(
        self,
        changes: Sequence[tuple[int, datetime]],
        user_id: int,
        now: datetime,
    ) -> int:
        """Set new capture times (date_source 'manual'); the previous value is kept."""
        with self._transaction():
            for asset_id, new_time in changes:
                self._conn.execute(
                    """INSERT INTO date_change (asset_id, old_taken_at, old_tz_offset_min,
                           old_date_source, new_taken_at, changed_by, changed_at)
                       SELECT id, taken_at, tz_offset_min, date_source, ?, ?, ?
                       FROM asset WHERE id = ?""",
                    (new_time.isoformat(), user_id, utc_text(now), asset_id),
                )
                self._conn.execute(
                    "UPDATE asset SET taken_at = ?, date_source = ? WHERE id = ?",
                    (new_time.isoformat(), DateSource.MANUAL.value, asset_id),
                )
        return len(changes)
