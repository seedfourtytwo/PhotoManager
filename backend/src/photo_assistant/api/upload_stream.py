"""Streaming multipart receiver: each file part goes straight into the upload spool.

Driven by python-multipart's push parser, so a file is never held in memory or spooled whole
to the system temp folder, and an oversized file is cut off as soon as it passes the limit.
"""

from collections.abc import Callable
from typing import Any

from python_multipart.multipart import parse_options_header

from photo_assistant.app.upload import UploadInbox, UploadOutcome, UploadResult
from photo_assistant.ports.upload import SpoolWriter, UploadTooLargeError

FALLBACK_NAME = "upload"


def part_filename(headers: dict[bytes, bytes]) -> str | None:
    """The client's file name, or None for a plain form field.

    ``filename*=`` (RFC 5987) isn't parsed by python-multipart; such a part still counts as a
    file when it declares a non-text content type, and gets a fallback name."""
    _, params = parse_options_header(headers.get(b"content-disposition", b""))
    if b"filename" in params:
        return params[b"filename"].decode("utf-8", "replace")
    content_type = headers.get(b"content-type", b"text/plain").lower()
    return None if content_type.startswith(b"text/plain") else FALLBACK_NAME


class UploadReceiver:
    def __init__(self, upload: UploadInbox, user_id: int, max_files: int) -> None:
        self._upload = upload
        self._user_id = user_id
        self._max_files = max_files
        self.results: list[UploadResult] = []
        self.complete = False
        self._files = 0
        self._headers: dict[bytes, bytes] = {}
        self._field = b""
        self._value = b""
        self._name = ""
        self._writer: SpoolWriter | None = None

    def callbacks(self) -> dict[str, Callable[..., Any]]:
        return {
            "on_part_begin": self._part_begin,
            "on_header_field": self._header_field,
            "on_header_value": self._header_value,
            "on_header_end": self._header_end,
            "on_headers_finished": self._headers_finished,
            "on_part_data": self._part_data,
            "on_part_end": self._part_end,
            "on_end": self._end,
        }

    def abort(self) -> None:
        """The request broke off: drop the half-received file."""
        if self._writer is not None:
            self._writer.discard()
            self._writer = None

    def _part_begin(self) -> None:
        self._headers = {}

    def _header_field(self, data: bytes, start: int, end: int) -> None:
        self._field += data[start:end]

    def _header_value(self, data: bytes, start: int, end: int) -> None:
        self._value += data[start:end]

    def _header_end(self) -> None:
        self._headers[self._field.lower()] = self._value
        self._field, self._value = b"", b""

    def _headers_finished(self) -> None:
        name = part_filename(self._headers)
        if name is None:
            return
        if self._files >= self._max_files:
            reason = f"too many files in one upload (at most {self._max_files}); send the rest"
            self.results.append(UploadResult(name, UploadOutcome.REJECTED, reason=reason))
            return
        self._files += 1
        self._name = name
        self._writer = self._upload.start()

    def _part_data(self, data: bytes, start: int, end: int) -> None:
        if self._writer is None:
            return
        try:
            self._writer.write(data[start:end])
        except UploadTooLargeError:
            self._writer = None  # the spool already removed the partial file
            self.results.append(self._upload.too_large(self._name))

    def _part_end(self) -> None:
        if self._writer is None:
            return
        spooled = self._writer.finish()
        self._writer = None
        self.results.append(self._upload.accept(self._user_id, self._name, spooled))

    def _end(self) -> None:
        self.complete = True
