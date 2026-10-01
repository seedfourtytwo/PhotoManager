"""FaceAnalyzer fallback: YuNet detector + SFace recogniser through OpenCV (Apache-2.0 weights).

Files (OpenCV Zoo, downloaded by `just models --faces yunet_sface`):
    face_detection_yunet_2023mar.onnx    rows of [x, y, w, h, 5 landmarks (x, y), score]
    face_recognition_sface_2021dec.onnx  128-d features from ``alignCrop`` output

Needs OpenCV ≥ 4.8 for the 2023mar YuNet. Faces are detected on a downscaled copy (YuNet's cost
grows with the input size) and aligned from the full image.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from photo_assistant.adapters.image_io import RgbImage, load_rgb
from photo_assistant.adapters.onnx_common import DOWNLOAD_HINT, Lazy
from photo_assistant.domain.faces import BoundingBox, Face
from photo_assistant.ports.ml import ModelFormatError, ModelInfo, ModelStatus, ModelUnavailableError

DETECTOR_FILE = "face_detection_yunet_2023mar.onnx"
RECOGNISER_FILE = "face_recognition_sface_2021dec.onnx"
SFACE_DIM = 128

Factory = Callable[..., Any]  # Any: OpenCV's detector/recogniser objects are untyped


class YuNetSFaceAnalyzer:
    def __init__(
        self,
        folder: Path,
        *,
        name: str = "yunet_sface",
        min_score: float = 0.8,
        det_max_edge: int = 640,
        loader: Callable[[Path], RgbImage] = load_rgb,
        detector_factory: Factory = cv2.FaceDetectorYN.create,
        recognizer_factory: Factory = cv2.FaceRecognizerSF.create,
    ) -> None:
        self._folder = folder
        self._name = name
        self._min_score = min_score
        self._max_edge = det_max_edge
        self._loader = loader
        self._make_detector = detector_factory
        self._make_recognizer = recognizer_factory
        self._models = Lazy(self._load)

    @property
    def name(self) -> str:
        return self._name

    def _load(self) -> tuple[Any, Any]:
        paths = [self._folder / DETECTOR_FILE, self._folder / RECOGNISER_FILE]
        for path in paths:
            if not path.is_file():
                raise ModelUnavailableError(f"model file {path} is missing: {DOWNLOAD_HINT}")
        try:
            detector = self._make_detector(str(paths[0]), "", (320, 320), self._min_score, 0.3)
            recognizer = self._make_recognizer(str(paths[1]), "")
        except cv2.error as exc:
            raise ModelFormatError(f"OpenCV cannot load the YuNet/SFace models: {exc}") from exc
        return detector, recognizer

    def info(self) -> ModelInfo:
        return ModelInfo(self._name, SFACE_DIM)

    def status(self) -> ModelStatus:
        if self._models.error is not None:
            return ModelStatus(False, self._models.error)
        if not (self._folder / DETECTOR_FILE).is_file():
            return ModelStatus(False, f"face model {self._name} not found: {DOWNLOAD_HINT}")
        return ModelStatus(True, f"{self._name} (OpenCV DNN, CPU)")

    def detect(self, path: Path) -> list[Face]:
        detector, recognizer = self._models.get()
        bgr = np.ascontiguousarray(self._loader(path)[:, :, ::-1])
        height, width = bgr.shape[:2]
        scale = min(1.0, self._max_edge / max(height, width))
        small = cv2.resize(bgr, (round(width * scale), round(height * scale)))
        detector.setInputSize((small.shape[1], small.shape[0]))
        _, rows = detector.detect(small)
        faces = []
        for row in [] if rows is None else rows:
            full = row.copy()
            full[:14] /= scale
            feature = np.asarray(recognizer.feature(recognizer.alignCrop(bgr, full)))[0]
            faces.append(_face(full, feature, width, height))
        return sorted(faces, key=lambda face: -face.score)


def _face(row: np.ndarray, feature: np.ndarray, width: int, height: int) -> Face:
    x, y, w, h = (float(v) for v in row[:4])
    box = BoundingBox.from_pixels(x, y, x + w, y + h, width=width, height=height)
    landmarks = tuple(
        (float(row[4 + 2 * i]) / width, float(row[5 + 2 * i]) / height) for i in range(5)
    )
    norm = float(np.linalg.norm(feature)) or 1.0
    return Face(box, float(row[14]), landmarks, tuple(float(v) / norm for v in feature))
