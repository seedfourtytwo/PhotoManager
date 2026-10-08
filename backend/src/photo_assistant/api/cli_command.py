"""What one sub-command of ``python -m photo_assistant`` is. The table of them all is
``COMMANDS`` in ``photo_assistant/__main__.py``: a new command is one more entry there."""

import argparse
from collections.abc import Callable
from dataclasses import dataclass


def _no_arguments(parser: argparse.ArgumentParser) -> None:
    pass


@dataclass(frozen=True, slots=True)
class Command:
    name: str
    help: str  # its line in ``--help``
    run: Callable[[argparse.Namespace], int]  # returns the exit code
    arguments: Callable[[argparse.ArgumentParser], None] = _no_arguments  # adds its options
