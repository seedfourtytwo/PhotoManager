"""CLIP image + text encoders from an Immich-style model folder (Hugging Face immich-app/<name>).

Folder layout, as published by Immich (verify on the laptop — docs/wiring/ml.md):

    <name>/config.json                  {"embed_dim": 512, "text_cfg": {"context_length": 77}, …}
    <name>/visual/model.onnx            input "image" float32 [N,3,S,S] → [N,embed_dim]
    <name>/visual/preprocess_cfg.json   {"size": [S,S], "mean": [...], "std": [...], ...}
    <name>/textual/model.onnx           OpenCLIP: "text" int32 [N,77];
                                        M-CLIP: "input_ids" + "attention_mask" [N,L]
    <name>/textual/tokenizer.json       Hugging Face `tokenizers` file
    <name>/textual/tokenizer_config.json {"pad_token": ...}

Preprocessing follows Immich: resize the short side to S (bicubic), centre-crop SxS, scale to
0-1, normalise with mean/std, CHW. Vectors are L2-normalised here whatever the export did.
"""

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from numpy.typing import NDArray
from tokenizers import Tokenizer

from photo_assistant.adapters.image_io import RgbImage, load_rgb
from photo_assistant.adapters.onnx_common import DOWNLOAD_HINT, Lazy, Session, choose_providers
from photo_assistant.domain.vectors import Vector
from photo_assistant.ports.ml import (
    ModelFormatError,
    ModelInfo,
    ModelStatus,
    ModelUnavailableError,
)

FALLBACK_PAD_TOKENS = ("<|endoftext|>", "<pad>")
Floats = NDArray[np.float32]


@dataclass(frozen=True, slots=True)
class ClipPreprocess:
    size: int
    mean: tuple[float, ...]
    std: tuple[float, ...]
    resize_mode: str = "shortest"  # "shortest" (resize + centre crop) or "squash"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ModelUnavailableError(f"{path} is missing: {DOWNLOAD_HINT}")
    try:
        value = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise ModelFormatError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ModelFormatError(f"{path} should hold a JSON object")
    return value


def _size(raw: object) -> int:
    if isinstance(raw, int):
        return raw
    if isinstance(raw, list) and len(raw) == 2 and raw[0] == raw[1] and isinstance(raw[0], int):
        return raw[0]
    raise ValueError(f"size must be an int or a square [S, S], got {raw!r}")


def read_preprocess(path: Path) -> ClipPreprocess:
    raw = _read_json(path)
    try:
        mean = tuple(float(x) for x in raw["mean"])
        std = tuple(float(x) for x in raw["std"])
        mode = str(raw.get("resize_mode", "shortest"))
        if len(mean) != 3 or len(std) != 3:
            raise ValueError("mean and std need three values (RGB)")
        if mode not in ("shortest", "squash"):
            raise ValueError(f"resize_mode {mode!r} is not supported")
        return ClipPreprocess(_size(raw["size"]), mean, std, mode)
    except (KeyError, TypeError, ValueError) as exc:
        raise ModelFormatError(f"{path} (preprocess_cfg): {exc}") from exc


def _resize(image: RgbImage, width: int, height: int) -> RgbImage:
    # INTER_AREA when shrinking approximates PIL's antialiased bicubic that Immich uses.
    shrinking = width < image.shape[1] or height < image.shape[0]
    method = cv2.INTER_AREA if shrinking else cv2.INTER_CUBIC
    return np.asarray(cv2.resize(image, (width, height), interpolation=method), dtype=np.uint8)


def preprocess_image(image: RgbImage, cfg: ClipPreprocess) -> Floats:
    """HxWx3 uint8 RGB → 3xSxS float32, exactly as the model was trained to see it."""
    s = cfg.size
    h, w = image.shape[:2]
    if cfg.resize_mode == "squash":
        square = _resize(image, s, s)
    else:
        new_w, new_h = (s, int(h / w * s)) if w < h else (int(w / h * s), s)
        resized = _resize(image, max(new_w, s), max(new_h, s))
        left = int(resized.shape[1] / 2 - s / 2)
        top = int(resized.shape[0] / 2 - s / 2)
        square = resized[top : top + s, left : left + s]
    scaled = square.astype(np.float32) / 255.0
    normalised = (scaled - np.array(cfg.mean, np.float32)) / np.array(cfg.std, np.float32)
    return np.ascontiguousarray(normalised.transpose(2, 0, 1), dtype=np.float32)


def _normalise_rows(matrix: Floats) -> list[Vector]:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return [tuple(float(x) for x in row) for row in matrix / norms]


def _check_embedding_output(session: Session, dim: int) -> None:
    out = session.outputs[0]
    if len(out.shape) != 2:
        raise session.fail("the first output should be [batch, embed_dim]")
    if out.fixed(1) not in (None, dim):
        raise session.fail(f"embedding size {out.fixed(1)} but config.json embed_dim is {dim}")


def _check_result(session: Session, result: Floats, rows: int, dim: int) -> Floats:
    if result.shape != (rows, dim):
        raise session.fail(f"produced shape {result.shape}, expected {(rows, dim)}")
    return result


class _Visual:
    def __init__(self, folder: Path, providers: Sequence[str], dim: int, batch: int) -> None:
        self.cfg = read_preprocess(folder / "visual" / "preprocess_cfg.json")
        self.session = Session(folder / "visual" / "model.onnx", providers)
        self.dim = dim
        self._check()
        self.batch = 1 if self.session.inputs[0].fixed(0) == 1 else batch

    def _check(self) -> None:
        session, size = self.session, self.cfg.size
        if len(session.inputs) != 1 or len(session.inputs[0].shape) != 4:
            raise session.fail("expected one image input [batch, 3, S, S]")
        image = session.inputs[0]
        if image.fixed(1) not in (None, 3):
            raise session.fail("the image input should have 3 channels")
        if {image.fixed(2), image.fixed(3)} - {None, size}:
            raise session.fail(
                f"image input is {image.fixed(2)}x{image.fixed(3)} but preprocess_cfg says {size}"
            )
        _check_embedding_output(session, self.dim)

    def embed(self, images: Sequence[RgbImage]) -> list[Vector]:
        vectors: list[Vector] = []
        name = self.session.inputs[0].name
        for start in range(0, len(images), self.batch):
            chunk = images[start : start + self.batch]
            blob = np.stack([preprocess_image(image, self.cfg) for image in chunk])
            result = self.session.run({name: blob})[0]
            vectors += _normalise_rows(_check_result(self.session, result, len(chunk), self.dim))
        return vectors


def _pad_token(folder: Path, tokenizer: Tokenizer) -> tuple[str, int]:
    config_path = folder / "textual" / "tokenizer_config.json"
    raw = _read_json(config_path).get("pad_token") if config_path.is_file() else None
    token = raw.get("content") if isinstance(raw, dict) else raw
    candidates = [str(token)] if token else list(FALLBACK_PAD_TOKENS)
    for candidate in candidates:
        pad_id = tokenizer.token_to_id(candidate)
        if pad_id is not None:
            return candidate, int(pad_id)
    raise ModelFormatError(f"pad token {candidates} not in {folder / 'textual/tokenizer.json'}")


_INT_TYPES: dict[str, type[np.signedinteger[Any]]] = {
    "tensor(int32)": np.int32,
    "tensor(int64)": np.int64,
}


class _Textual:
    def __init__(self, folder: Path, providers: Sequence[str], dim: int, context: int) -> None:
        self.session = Session(folder / "textual" / "model.onnx", providers)
        self.dim = dim
        self.types = self._check_inputs()
        _check_embedding_output(self.session, dim)
        self.tokenizer = self._tokenizer(folder, context)

    def _check_inputs(self) -> dict[str, type[np.signedinteger[Any]]]:
        names = {i.name for i in self.session.inputs}
        mclip = "input_ids" in names and names <= {"input_ids", "attention_mask"}
        if names != {"text"} and not mclip:
            raise self.session.fail(
                f"unexpected text inputs {sorted(names)}; expected 'text' (OpenCLIP) or "
                "'input_ids' + 'attention_mask' (M-CLIP)"
            )
        types = {i.name: _INT_TYPES.get(i.type) for i in self.session.inputs}
        checked = {name: kind for name, kind in types.items() if kind is not None}
        if len(checked) != len(types):
            raise self.session.fail("text inputs should be int32 or int64 token ids")
        return checked

    @staticmethod
    def _tokenizer(folder: Path, context: int) -> Tokenizer:
        path = folder / "textual" / "tokenizer.json"
        if not path.is_file():
            raise ModelUnavailableError(f"{path} is missing: {DOWNLOAD_HINT}")
        try:
            tokenizer = Tokenizer.from_file(str(path))
        except Exception as exc:  # tokenizers raises a bare Exception subclass
            raise ModelFormatError(f"cannot read {path}: {exc}") from exc
        pad, pad_id = _pad_token(folder, tokenizer)
        tokenizer.enable_padding(length=context, pad_id=pad_id, pad_token=pad)
        tokenizer.enable_truncation(max_length=context)
        return tokenizer

    def embed(self, text: str) -> Vector:
        encoding = self.tokenizer.encode(" ".join(text.split()))
        values = {
            "text": encoding.ids,
            "input_ids": encoding.ids,
            "attention_mask": encoding.attention_mask,
        }
        feed = {name: np.array([values[name]], dtype=kind) for name, kind in self.types.items()}
        result = _check_result(self.session, self.session.run(feed)[0], 1, self.dim)
        return _normalise_rows(result)[0]


class OnnxClip:
    """Implements ImageEmbedder and TextEmbedder. Loads each half lazily, once."""

    def __init__(
        self,
        folder: Path,
        name: str,
        *,
        provider: str = "auto",
        batch_size: int = 16,
        loader: Callable[[Path], RgbImage] = load_rgb,
    ) -> None:
        self._folder = folder
        self._name = name
        self._provider = provider
        self._batch = batch_size
        self._loader = loader
        self._visual = Lazy(self._make_visual)
        self._textual = Lazy(self._make_textual)

    @property
    def name(self) -> str:
        return self._name

    def _config(self) -> tuple[int, int]:
        config = _read_json(self._folder / "config.json")
        try:
            dim = int(config["embed_dim"])
            context = int(config.get("text_cfg", {}).get("context_length", 77))
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise ModelFormatError(f"{self._folder / 'config.json'}: {exc!r}") from exc
        return dim, context

    def _make_visual(self) -> _Visual:
        dim, _ = self._config()
        return _Visual(self._folder, choose_providers(self._provider), dim, self._batch)

    def _make_textual(self) -> _Textual:
        dim, context = self._config()
        return _Textual(self._folder, choose_providers(self._provider), dim, context)

    def info(self) -> ModelInfo:
        return ModelInfo(self._name, self._config()[0])

    def status(self) -> ModelStatus:
        error = self._visual.error or self._textual.error
        if error is not None:
            return ModelStatus(False, error)
        if not (self._folder / "visual" / "model.onnx").is_file():
            return ModelStatus(False, f"CLIP model {self._name} not found: {DOWNLOAD_HINT}")
        loaded = self._visual.value or self._textual.value
        where = ", ".join(loaded.session.providers) if loaded else "not loaded yet"
        return ModelStatus(True, f"{self._name} ({where})")

    def embed_images(self, paths: Sequence[Path]) -> list[Vector]:
        if not paths:
            return []
        visual = self._visual.get()
        return visual.embed([self._loader(path) for path in paths])

    def embed_text(self, text: str) -> Vector:
        return self._textual.get().embed(text)
