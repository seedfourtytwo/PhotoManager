"""Fakes every part of the test suite shares. Fixtures that hand them out are in conftest.py."""

from datetime import datetime, timedelta

from tests.factories import NOW


class FakeClock:
    """The ``Clock`` port for tests: it stands still until the test moves it.

    Move it with ``advance`` or by assigning ``at``; ``current`` is the same instant under
    the name the worker and backup tests use.
    """

    def __init__(self, at: datetime = NOW) -> None:
        self.at = at

    def now(self) -> datetime:
        return self.at

    def advance(self, by: timedelta) -> None:
        self.at += by

    @property
    def current(self) -> datetime:
        return self.at

    @current.setter
    def current(self, value: datetime) -> None:
        self.at = value
