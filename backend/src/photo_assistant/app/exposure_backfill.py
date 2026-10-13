"""Exposure settings for photos imported before they were kept (migration 0028).

New imports store them from the metadata the import reads anyway. For older photos this job
reads the library copy (never a source folder; reading changes nothing in the file) and
fills in what it finds.

One job is one batch. It looks only at photos that still have none of the four values, past
the id its payload names, and queues the next batch itself. So it can be cut off anywhere:
the batch that was running is run again and stores the same values, the batches before it
are not read again, and starting the whole thing a second time only re-reads the photos that
had no exposure tags (scans, screenshots).
"""

from collections.abc import Callable
from pathlib import Path

from photo_assistant.ports import MetadataReader
from photo_assistant.ports.enrich import ExposureStore

EXPOSURE_BACKFILL_JOB = "exposure_backfill"
# Photos read per job. The metadata reader is shared with imports and held for one batch at
# a time, so a batch stays well under a second on the laptop (see PERFORMANCE.md).
BATCH = 200


class BackfillExposure:
    """Job handler. Payload ``{}`` starts at the first photo, ``{"after": id}`` goes on."""

    def __init__(
        self,
        store: ExposureStore,
        metadata: MetadataReader,
        absolute: Callable[[str], Path],
        batch: int = BATCH,
    ) -> None:
        self._store = store
        self._metadata = metadata
        self._absolute = absolute
        self._batch = batch

    def __call__(self, payload: dict[str, object]) -> int:
        """Returns how many photos of this batch got values."""
        after = int(str(payload.get("after", 0)))
        todo = self._store.assets_without_exposure(after, self._batch)
        if not todo:
            return 0
        read = self._metadata.read_many([self._absolute(path) for _, path in todo])
        found = [
            (asset_id, meta.exposure)
            for (asset_id, _), meta in zip(todo, read, strict=True)
            if not meta.exposure.is_empty
        ]
        self._store.set_exposures(found)
        if len(todo) == self._batch:
            self._store.enqueue(EXPOSURE_BACKFILL_JOB, {"after": todo[-1][0]})
        return len(found)
