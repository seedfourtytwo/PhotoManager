"""EnrichmentStore and ExposureStore on SQLite: places, perceptual hashes, groups, exposure."""

from collections.abc import Sequence
from datetime import datetime

from photo_assistant.adapters.sqlite_base import SqliteBase
from photo_assistant.domain.exposure import Exposure
from photo_assistant.domain.grouping import Shot
from photo_assistant.domain.places import Place

# A photo with none of the four values: not read yet, or it carries none (a scan).
_NO_EXPOSURE = "f_number IS NULL AND exposure_time IS NULL AND iso IS NULL AND focal_length IS NULL"


class EnrichMixin(SqliteBase):
    def assets_to_geocode(self, after_id: int, limit: int) -> list[tuple[int, float, float]]:
        rows = self._all(
            """SELECT id, latitude, longitude FROM asset
               WHERE id > ? AND place_id IS NULL AND latitude IS NOT NULL
                 AND longitude IS NOT NULL AND trashed_at IS NULL
               ORDER BY id LIMIT ?""",
            (after_id, limit),
        )
        return [(int(r["id"]), float(r["latitude"]), float(r["longitude"])) for r in rows]

    def set_places(self, places: Sequence[tuple[int, Place]]) -> None:
        with self._transaction():
            for asset_id, place in places:
                key = (place.country, place.region, place.city)
                self._conn.execute(
                    "INSERT OR IGNORE INTO place (country, region, city) VALUES (?, ?, ?)", key
                )
                self._conn.execute(
                    """UPDATE asset SET place_id = (SELECT id FROM place
                           WHERE country = ? AND region = ? AND city = ?) WHERE id = ?""",
                    (*key, asset_id),
                )

    def assets_without_phash(self, after_id: int, limit: int) -> list[tuple[int, str]]:
        rows = self._all(
            """SELECT id, thumb_path FROM asset
               WHERE id > ? AND phash IS NULL AND thumb_path IS NOT NULL AND trashed_at IS NULL
               ORDER BY id LIMIT ?""",
            (after_id, limit),
        )
        return [(int(r["id"]), str(r["thumb_path"])) for r in rows]

    def assets_without_exposure(self, after_id: int, limit: int) -> list[tuple[int, str]]:
        rows = self._all(
            f"""SELECT id, library_path FROM asset WHERE id > ? AND {_NO_EXPOSURE}
               ORDER BY id LIMIT ?""",
            (after_id, limit),
        )
        return [(int(r["id"]), str(r["library_path"])) for r in rows]

    def count_without_exposure(self) -> int:
        """How many photos the exposure backfill still has to read."""
        return self._scalar(f"SELECT COUNT(*) FROM asset WHERE {_NO_EXPOSURE}")

    def set_exposures(self, exposures: Sequence[tuple[int, Exposure]]) -> None:
        with self._transaction():
            self._conn.executemany(
                """UPDATE asset SET f_number = ?, exposure_time = ?, iso = ?, focal_length = ?
                   WHERE id = ?""",
                [(e.f_number, e.exposure_time, e.iso, e.focal_length, i) for i, e in exposures],
            )

    def set_phash(self, asset_id: int, phash: str) -> None:
        self._write("UPDATE asset SET phash = ? WHERE id = ?", (phash, asset_id))

    def shots(self) -> list[Shot]:
        rows = self._all(
            """SELECT id, taken_at, camera_model, phash FROM asset
               WHERE trashed_at IS NULL AND held_reason IS NULL"""
        )
        return [
            Shot(int(r["id"]), datetime.fromisoformat(r["taken_at"]), r["camera_model"], r["phash"])
            for r in rows
        ]

    def shot_times(self) -> list[tuple[int, datetime]]:
        rows = self._all(
            "SELECT id, taken_at FROM asset WHERE trashed_at IS NULL AND held_reason IS NULL"
        )
        return [(int(r["id"]), datetime.fromisoformat(r["taken_at"])) for r in rows]

    def shots_in(self, runs: Sequence[tuple[datetime, datetime]]) -> list[Shot]:
        found: list[Shot] = []
        for start, end in runs:  # each range walks the timeline index
            rows = self._all(
                """SELECT id, taken_at, camera_model, phash FROM asset
                   WHERE trashed_at IS NULL AND held_reason IS NULL
                     AND taken_at BETWEEN ? AND ?""",
                (start.isoformat(), end.isoformat()),
            )
            found += [
                Shot(
                    int(r["id"]),
                    datetime.fromisoformat(r["taken_at"]),
                    r["camera_model"],
                    r["phash"],
                )
                for r in rows
            ]
        return found

    def set_groups(self, groups: dict[int, int | None]) -> int:
        with self._transaction():
            changed = 0
            for asset_id, group_id in groups.items():
                changed += self._conn.execute(
                    "UPDATE asset SET group_id = ? WHERE id = ? AND group_id IS NOT ?",
                    (group_id, asset_id, group_id),
                ).rowcount
            # a photo held for review is in no group (it rejoins one when it is kept)
            self._conn.execute(
                """UPDATE asset SET group_id = NULL
                   WHERE held_reason IS NOT NULL AND group_id IS NOT NULL"""
            )
        return changed
