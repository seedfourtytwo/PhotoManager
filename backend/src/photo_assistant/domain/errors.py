"""The one error hierarchy for "the request can't be done" (ENGINEERING_RULES §4).

Use cases raise these with a sentence the user can act on; ``api/main.py`` turns each kind
into its HTTP status with ONE handler (``{"detail": message}``), and the job worker never
retries them (they are not transient: the same job would fail the same way).

So an error that may pass by waiting (the network, a locked repository) must NOT derive from
these. Every exception class of the package is either in this hierarchy or listed, with the
reason, in ``tests/unit/test_error_hierarchy.py``.
"""


class DomainError(Exception):
    """Base: the message is shown to the user as it is."""

    status = 400


class NotFoundError(DomainError):
    """It doesn't exist, or the caller may not know it does."""

    status = 404


class ForbiddenError(DomainError):
    """The caller sees it but lacks the role or access level."""

    status = 403


class InvalidError(DomainError):
    """The request is well-formed but makes no sense (bad values, impossible change)."""

    status = 422


class ConflictError(DomainError):
    """It clashes with the current state (a name taken, the last admin, already set up)."""

    status = 409


class UnavailableError(DomainError):
    """Something outside the library is missing: a folder, a tool, a model, a disk."""

    status = 503
