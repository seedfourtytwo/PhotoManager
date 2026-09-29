"""FaceAnalyzer with InsightFace buffalo_l, run by onnxruntime directly (no insightface package).

Files (from the buffalo_l release zip, downloaded by `just models`, never bundled — the weights
are for non-commercial use only, fine for a private family library):

    det_10g.onnx    SCRFD-10GF detector. Input [1,3,H,W] RGB, (x - 127.5) / 128, letterboxed
                    to 640x640. 9 outputs: scores [.,1], box distances [.,4], landmark
                    distances [.,10] for strides 8/16/32, two anchors per cell.
    w600k_r50.onnx  ArcFace R50 (WebFace600K). Input [N,3,112,112] RGB, (x - 127.5) / 127.5,
                    face aligned on five landmarks. Output [N,512].

insightface feeds BGR images through cv2.dnn.blobFromImage(swapRB=True), so the networks see
RGB; we decode to RGB and skip the swap.
"""

from collections.abc import Callable, Sequence
from pathlib import Path

import numpy as np

from photo_assistant.adapters.face_geometry import align_face, decode_scrfd, letterbox
from photo_assistant.adapters.image_io import RgbImage, load_rgb
from photo_assistant.adapters.onnx_common import DOWNLOAD_HINT, Lazy, Session, choose_providers
from photo_assistant.domain.faces import BoundingBox, Face
from photo_assistant.domain.vectors import Vector
from photo_assistant.ports.ml import ModelInfo, ModelStatus

DETECTOR_FILE = "det_10g.onnx"
RECOGNISER_FILE = "w600k_r50.onnx"
ARCFACE_SIZE = 112


class _Detector:
    def __init__(self, session: Session, det_size: int) -> None:
        self.session = session
        if len(session.inputs) != 1 or len(session.inputs[0].shape) != 4:
            raise session.fail("the detector should take one image input [1, 3, H, W]")
        if len(session.outputs) != 9:
            raise session.fail(
                "SCRFD detector should have 9 outputs (scores, boxes, 5-point landmarks for "
                "strides 8/16/32); is this buffalo_l's det_10g.onnx?"
            )
        image = session.inputs[0]
        self.height = image.fixed(2) or det_size
        self.width = image.fixed(3) or det_size

    def find(self, image: RgbImage, threshold: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        canvas, scale = letterbox(image, self.width, self.height)
        blob = ((canvas.astype(np.float32) - 127.5) / 128.0).transpose(2, 0, 1)[None]
        outputs = self.session.run({self.session.inputs[0].name: np.ascontiguousarray(blob)})
        boxes, kps, scores = decode_scrfd(outputs, self.height, self.width, threshold=threshold)
        return boxes / scale, kps / scale, scores


class _Recogniser:
    def __init__(self, session: Session) -> None:
        self.session = session
        if len(session.inputs) != 1 or len(session.inputs[0].shape) != 4:
            raise session.fail("the recogniser should take one input [N, 3, 112, 112]")
        crop = session.inputs[0]
        if {crop.fixed(2), crop.fixed(3)} - {None, ARCFACE_SIZE}:
            raise session.fail(f"ArcFace expects {ARCFACE_SIZE}x{ARCFACE_SIZE} crops")
        if len(session.outputs[0].shape) != 2:
            raise session.fail("the recogniser output should be [N, dim]")
        self.dim = session.outputs[0].fixed(1) or 512
        self.batch = 1 if crop.fixed(0) == 1 else 32

    def embed(self, crops: Sequence[RgbImage]) -> list[Vector]:
        vectors: list[Vector] = []
        name = self.session.inputs[0].name
        for start in range(0, len(crops), self.batch):
            chunk = np.stack(crops[start : start + self.batch]).astype(np.float32)
            blob = np.ascontiguousarray(((chunk - 127.5) / 127.5).transpose(0, 3, 1, 2))
            result = self.session.run({name: blob})[0]
            if result.shape != (len(chunk), self.dim):
                raise self.session.fail(f"produced {result.shape}, expected (n, {self.dim})")
            norms = np.linalg.norm(result, axis=1, keepdims=True)
            vectors += [tuple(float(x) for x in row) for row in result / np.maximum(norms, 1e-12)]
        return vectors


class InsightFaceAnalyzer:
    def __init__(
        self,
        folder: Path,
        *,
        name: str = "buffalo_l",
        provider: str = "auto",
        det_size: int = 640,
        min_score: float = 0.7,  # Immich's default minimum detection score
        loader: Callable[[Path], RgbImage] = load_rgb,
    ) -> None:
        self._folder = folder
        self._name = name
        self._provider = provider
        self._det_size = det_size
        self._min_score = min_score
        self._loader = loader
        self._models = Lazy(self._load)

    @property
    def name(self) -> str:
        return self._name

    def _load(self) -> tuple[_Detector, _Recogniser]:
        providers = choose_providers(self._provider)
        detector = _Detector(Session(self._folder / DETECTOR_FILE, providers), self._det_size)
        recogniser = _Recogniser(Session(self._folder / RECOGNISER_FILE, providers))
        return detector, recogniser

    def info(self) -> ModelInfo:
        return ModelInfo(self._name, self._models.get()[1].dim)

    def status(self) -> ModelStatus:
        if self._models.error is not None:
            return ModelStatus(False, self._models.error)
        if not (self._folder / DETECTOR_FILE).is_file():
            return ModelStatus(False, f"face model {self._name} not found: {DOWNLOAD_HINT}")
        loaded = self._models.value
        where = ", ".join(loaded[0].session.providers) if loaded else "not loaded yet"
        return ModelStatus(True, f"{self._name} ({where})")

    def detect(self, path: Path) -> list[Face]:
        detector, recogniser = self._models.get()
        image = self._loader(path)
        boxes, kps, scores = detector.find(image, self._min_score)
        kept, crops = [], []
        for index in range(len(scores)):
            try:
                crops.append(align_face(image, kps[index], ARCFACE_SIZE))
            except ValueError:
                continue  # degenerate landmarks: no usable embedding
            kept.append(index)
        embeddings = recogniser.embed(crops) if crops else []
        height, width = image.shape[:2]
        return [
            _face(boxes[i], kps[i], float(scores[i]), vector, width, height)
            for i, vector in zip(kept, embeddings, strict=True)
        ]


def _face(
    box: np.ndarray, kps: np.ndarray, score: float, vector: Vector, width: int, height: int
) -> Face:
    x1, y1, x2, y2 = (float(v) for v in box)
    landmarks = tuple((float(x) / width, float(y) / height) for x, y in kps)
    bounds = BoundingBox.from_pixels(x1, y1, x2, y2, width=width, height=height)
    return Face(bounds, score, landmarks, vector)
