"""run_tool: the one way adapters start an external program."""

from pathlib import Path

import pytest

from photo_assistant.adapters.tool_runner import ToolMissingError, ToolTimeoutError, run_tool


def test_output_and_exit_code_come_back_and_a_failure_is_not_an_exception() -> None:
    done = run_tool(["sh", "-c", "echo out; echo err >&2; exit 3"], timeout=10)
    assert (done.returncode, done.stdout, done.stderr) == (3, "out\n", "err\n")


def test_the_tool_has_no_keyboard_to_wait_for() -> None:
    done = run_tool(["sh", "-c", "cat; echo end of input"], timeout=10)
    assert done.stdout == "end of input\n"


def test_environment_and_working_folder_are_the_callers(tmp_path: Path) -> None:
    done = run_tool(
        ["sh", "-c", 'echo "$PA_T in $PWD"'], timeout=10, env={"PA_T": "x"}, cwd=tmp_path
    )
    assert done.stdout == f"x in {tmp_path}\n"


def test_a_missing_program_and_a_hanging_one_are_told_apart(tmp_path: Path) -> None:
    with pytest.raises(ToolMissingError, match="no-such-tool"):
        run_tool([str(tmp_path / "no-such-tool")], timeout=10)
    with pytest.raises(ToolTimeoutError, match="sleep"):
        run_tool(["sleep", "30"], timeout=0.1)
