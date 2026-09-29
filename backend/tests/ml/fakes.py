"""In-memory stand-ins for the ML models (the store in app tests is real SQLite in memory)."""

from collections.abc import Sequence
from pathlib import Path

from photo_assistant.domain.faces import BoundingBox, Face
from photo_assistant.domain.vectors import Vector, normalise
from photo_assistant.ports.ml import ModelInfo, ModelStatus, ModelUnavailableError


class _FakeModel:
    def __init__(self, name: str, dim: int, available: bool = True) -> None:
        self._name, self.dim, self.available = name, dim, available
        self.calls = 0

    @property
    def name(self) -> str:
        return self._name

    def _check(self) -> None:
        self.calls += 1
        if not self.available:
            raise ModelUnavailableError(f"{self._name} missing: run `just models`")

    def info(self) -> ModelInfo:
        self._check()
        return ModelInfo(self._name, self.dim)

    def status(self) -> ModelStatus:
        return ModelStatus(self.available, "fake")


class FakeClip(_FakeModel):
    """Image vector = the one registered for the file name (default: first axis)."""

    def __init__(self, dim: int = 4, available: bool = True, name: str = "clip-fake") -> None:
        super().__init__(name, dim, available)
        self.images: dict[str, Vector] = {}
        self.texts: dict[str, Vector] = {}

    def embed_images(self, paths: Sequence[Path]) -> list[Vector]:
        self._check()
        out = []
        for path in paths:
            if path.name.startswith("broken"):
                raise ValueError(f"cannot decode {path.name}")
            out.append(normalise(self.images.get(path.name, (1.0,) + (0.0,) * (self.dim - 1))))
        return out

    def embed_text(self, text: str) -> Vector:
        self._check()
        return normalise(self.texts.get(text, (0.0,) * (self.dim - 1) + (1.0,)))


class FakeFaces(_FakeModel):
    def __init__(self, available: bool = True) -> None:
        super().__init__("faces-fake", 3, available)
        self.faces: dict[str, list[Vector]] = {}

    def detect(self, path: Path) -> list[Face]:
        self._check()
        return [
            Face(BoundingBox(0.1 * i, 0.1, 0.2, 0.2), 0.9, ((0.5, 0.5),) * 5, normalise(v))
            for i, v in enumerate(self.faces.get(path.name, []))
        ]


class FakeLibrary:
    def __init__(self, root: Path) -> None:
        self.root = root

    def absolute(self, relative_path: str) -> Path:
        return self.root / relative_path
