"""A ZIP written while it is sent (zipstream-ng): no temporary archive on the server.

Photos are *stored*, not deflated: JPEG/HEIC don't compress, and storing is fast.

One photo that can't be produced (a missing library file, a render error) must not cut the
archive short (QA A6): each file is started before it is added, a failure leaves it out, and
the archive ends with ``manifest.txt`` listing what was left out and why. A file only fails
before its first bytes — rendered files are finished in ``data/tmp`` before they are sent.
"""

import logging
from collections.abc import Iterable, Iterator
from itertools import chain

from zipstream import ZIP_STORED, ZipStream  # type: ignore[import-untyped]

from photo_assistant.domain.export_naming import skipped_manifest

log = logging.getLogger(__name__)
MANIFEST = "manifest.txt"


def zip_stream(entries: Iterable[tuple[str, Iterator[bytes]]]) -> Iterator[bytes]:
    """``entries``: (name inside the ZIP, lazy bytes). Each file is produced only when the
    archive reaches it."""
    archive = ZipStream(compress_type=ZIP_STORED)
    failed: list[tuple[str, str]] = []
    for name, content in entries:
        try:
            first = next(content, b"")
        except Exception as exc:  # reported in the manifest; the archive goes on
            log.warning("left %s out of a download: %s", name, exc)
            failed.append((name, str(exc) or type(exc).__name__))
            continue
        archive.add(chain((first,), content), name)
        yield from archive.all_files()
    if failed:
        archive.add(skipped_manifest(failed).encode(), MANIFEST)
        yield from archive.all_files()
    yield from archive.footer()
