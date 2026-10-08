"""VipsRenderer's own housekeeping: the thread setting really reaches libvips."""

from collections.abc import Iterator

import pytest
import pyvips  # type: ignore[import-untyped]

from photo_assistant.adapters.vips_renderer import VipsRenderer

pytestmark = pytest.mark.integration


@pytest.fixture
def libvips_threads(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Put libvips' process-wide thread count back after the test."""
    monkeypatch.delenv("VIPS_CONCURRENCY", raising=False)
    before = pyvips.concurrency_get()
    yield
    pyvips.concurrency_set(before)


@pytest.mark.usefixtures("libvips_threads")
def test_the_concurrency_setting_reaches_libvips() -> None:
    pyvips.concurrency_set(3)  # libvips is long loaded: only its own setter still counts
    VipsRenderer(concurrency=1)
    assert pyvips.concurrency_get() == 1


@pytest.mark.usefixtures("libvips_threads")
def test_no_setting_and_the_users_own_variable_leave_libvips_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pyvips.concurrency_set(3)
    VipsRenderer()
    assert pyvips.concurrency_get() == 3
    monkeypatch.setenv("VIPS_CONCURRENCY", "3")  # set by the user before the start: it wins
    VipsRenderer(concurrency=1)
    assert pyvips.concurrency_get() == 3
