"""A ZIP written while it is sent (zipstream-ng): no temporary archive on the server.

Photos are *stored*, not deflated: JPEG/HEIC don't compress, and storing is fast.
"""

from collections.abc import Iterable, Iterator

from zipstream import ZIP_STORED, ZipStream  # type: ignore[import-untyped]


def zip_stream(entries: Iterable[tuple[str, Iterator[bytes]]]) -> Iterator[bytes]:
    """``entries``: (name inside the ZIP, lazy bytes). Each file is produced only when the
    archive reaches it."""
    archive = ZipStream(compress_type=ZIP_STORED)
    for name, content in entries:
        archive.add(content, name)
    yield from archive
