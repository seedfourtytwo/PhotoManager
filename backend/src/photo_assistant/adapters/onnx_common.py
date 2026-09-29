"""onnxruntime plumbing shared by the CLIP and face adapters: providers, sessions, IO checks.

Real model files can't be exercised in CI, so every adapter checks input/output names, ranks
and fixed dimensions when it loads a model and fails with a ``ModelFormatError`` that says
what it expected and what it found.
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import onnxruntime as ort  # type: ignore[import-untyped]
from numpy.typing import NDArray

from photo_assistant.ports.ml import ModelFormatError, ModelUnavailableError

log = logging.getLogger(__name__)

CPU = "CPUExecutionProvider"
CUDA = "CUDAExecutionProvider"
DOWNLOAD_HINT = "run `just models` on this machine to download it"

Dim = int | str | None  # onnx dims: fixed int, symbolic name, or unknown


def choose_providers(preference: str, available: Sequence[str] | None = None) -> list[str]:
    """``auto``: CUDA when this onnxruntime build has it (the RTX 2070), else CPU."""
    found = list(ort.get_available_providers() if available is None else available)
    if preference == "cpu":
        return [CPU]
    if preference not in ("auto", "cuda"):
        raise ValueError(f"unknown ML provider {preference!r} (use auto, cpu or cuda)")
    if CUDA in found:
        return [CUDA, CPU]
    if preference == "cuda":
        raise ModelUnavailableError(
            "CUDA was requested but this onnxruntime has no CUDAExecutionProvider: "
            "install onnxruntime-gpu (see docs/wiring/ml.md) or set PA_ML_PROVIDER=cpu"
        )
    return [CPU]


@dataclass(frozen=True, slots=True)
class TensorInfo:
    name: str
    shape: tuple[Dim, ...]
    type: str  # e.g. "tensor(float)"

    def fixed(self, axis: int) -> int | None:
        value = self.shape[axis]
        return value if isinstance(value, int) and value > 0 else None


class Session:
    """A loaded model with its described inputs and outputs."""

    def __init__(self, path: Path, providers: Sequence[str]) -> None:
        if not path.is_file():
            raise ModelUnavailableError(f"model file {path} is missing: {DOWNLOAD_HINT}")
        options = ort.SessionOptions()
        options.log_severity_level = 3  # errors only; ORT warns about unused initialisers
        try:
            self._session = ort.InferenceSession(str(path), options, providers=list(providers))
        except Exception as exc:  # ort raises several unrelated exception types
            raise ModelFormatError(f"cannot load {path}: {exc}") from exc
        self.path = path
        self.inputs = [_info(i) for i in self._session.get_inputs()]
        self.outputs = [_info(o) for o in self._session.get_outputs()]
        self.providers: list[str] = list(self._session.get_providers())
        log.info("loaded model", extra={"model": str(path), "providers": self.providers})

    def run(self, feed: dict[str, NDArray[Any]]) -> list[NDArray[np.float32]]:
        return [np.asarray(out, dtype=np.float32) for out in self._session.run(None, feed)]

    def describe(self) -> str:
        def fmt(items: list[TensorInfo]) -> str:
            return ", ".join(f"{t.name}{list(t.shape)}:{t.type}" for t in items)

        return f"inputs [{fmt(self.inputs)}], outputs [{fmt(self.outputs)}]"

    def fail(self, problem: str) -> ModelFormatError:
        return ModelFormatError(f"{self.path}: {problem}; found {self.describe()}")


def _info(arg: object) -> TensorInfo:
    shape = tuple(d if isinstance(d, int | str) else None for d in arg.shape)  # type: ignore[attr-defined]
    return TensorInfo(arg.name, shape, arg.type)  # type: ignore[attr-defined]
