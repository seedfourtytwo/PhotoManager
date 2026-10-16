"""What kind of trouble a backup error is, so a screen can say it in plain words.

Read from the stored error text: the sentences our adapters write (restic_backup,
proton_drive, proton_mirror, app/backup) and the raw tool output they quote. Reading the text
rather than storing a kind at the time keeps it right for runs recorded before it existed.
"""

import re
from enum import StrEnum


class ErrorKind(StrEnum):
    UNREACHABLE = "unreachable"  # the disk is not plugged in, the server or network is away
    DISK_FULL = "disk_full"
    AUTH = "auth"  # a wrong or unreadable password, a sign-in that is missing or expired
    LOCKED = "locked"  # another run holds the repository
    UNKNOWN = "unknown"


# First match wins: a locked repository or a full disk can be reported through a sentence
# that also says "unable to open", and a sign-in problem through one that says "not found".
_RULES: tuple[tuple[ErrorKind, re.Pattern[str]], ...] = (
    (ErrorKind.LOCKED, re.compile(r"already locked|is locked by")),
    (
        ErrorKind.DISK_FULL,
        re.compile(r"no space left|disk (quota exceeded|full)|disk holding .* is full|enospc"),
    ),
    (
        ErrorKind.AUTH,
        re.compile(
            r"wrong password|password file|not signed in|not logged in|session expired|"
            r"failed to load session|couldn't login|login failed|unauthori[sz]ed|\b401\b|"
            r"\b403\b|forbidden|didn't find section in config file"
        ),
    ),
    (
        ErrorKind.UNREACHABLE,
        re.compile(
            r"is not connected|cannot be reached|until this computer is online|"
            r"is the disk plugged in|is there a repository|connection refused|"
            r"network is unreachable|no route to host|no such host|timed? ?out|"
            r"backup folder not found"
        ),
    ),
)


def error_kind(text: str | None) -> ErrorKind | None:
    """The kind of the error ``text``; None when there is no error."""
    if not text:
        return None
    lowered = text.lower()
    for kind, pattern in _RULES:
        if pattern.search(lowered):
            return kind
    return ErrorKind.UNKNOWN
