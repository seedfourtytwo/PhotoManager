"""PA_REQUIRE_TOOLS=1 (set in CI): a test skipped for a missing external tool is a failure.

Without it CI would go green with whole test modules skipped because a tool was never installed.
"""

import pytest

from tests.conftest import missing_tool

HOOKS = "from tests.conftest import pytest_configure, pytest_runtest_makereport  # noqa: F401\n"
TESTS = """
import pytest

@pytest.mark.skipif(True, reason="restic missing")
def test_needs_restic(): pass

def test_needs_rclone_found_while_running():
    pytest.skip("rclone not installed")

@pytest.mark.skipif(True, reason="root can write anywhere")
def test_skipped_for_another_reason(): pass

@pytest.mark.xfail(reason="exiftool bug, known")
def test_expected_failure(): raise AssertionError

def test_passes(): pass
"""


@pytest.mark.parametrize(
    ("reason", "tool"),
    [
        ("restic missing", "restic"),
        ("rclone not installed", "rclone"),
        ("needs libvips", "vips"),
        ("ExifTool missing", "exiftool"),
        ("root can write anywhere", None),
        ("set PA_MODELS_DIR to the models folder", None),
        ("", None),
    ],
)
def test_a_skip_reason_names_the_missing_tool(reason: str, tool: str | None) -> None:
    assert missing_tool(reason) == tool


def test_tool_skips_fail_when_tools_are_required(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PA_REQUIRE_TOOLS", "1")
    pytester.makeconftest(HOOKS)
    pytester.makepyfile(TESTS)
    result = pytester.runpytest_inprocess()
    # a skipif is decided during setup, so pytest counts it as an error; both end the run red
    result.assert_outcomes(errors=1, failed=1, skipped=1, xfailed=1, passed=1)
    result.stdout.fnmatch_lines(["PA_REQUIRE_TOOLS=1 but restic is not installed (restic missing)"])
    assert result.ret != 0


@pytest.mark.parametrize("value", [None, "0", ""])
def test_tool_skips_stay_skips_on_a_developer_machine(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch, value: str | None
) -> None:
    if value is None:
        monkeypatch.delenv("PA_REQUIRE_TOOLS", raising=False)
    else:
        monkeypatch.setenv("PA_REQUIRE_TOOLS", value)
    pytester.makeconftest(HOOKS)
    pytester.makepyfile(TESTS)
    pytester.runpytest_inprocess().assert_outcomes(skipped=3, xfailed=1, passed=1)
