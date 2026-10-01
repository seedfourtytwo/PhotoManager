"""Face analyzers: InsightFace buffalo_l via onnxruntime (synthetic ONNX graphs) and the
YuNet + SFace fallback via OpenCV (fake OpenCV objects: real models aren't available here)."""

from pathlib import Path

import numpy as np
import pytest

from photo_assistant.adapters.faces_insightface import InsightFaceAnalyzer
from photo_assistant.adapters.faces_opencv import YuNetSFaceAnalyzer
from photo_assistant.ports.ml import ModelFormatError, ModelUnavailableError
from tests.ml.onnx_models import constant_outputs_model, mean_pool_image_model
from tests.ml.test_face_geometry import scrfd_outputs

RED = np.array([255, 0, 0], dtype=np.uint8)


def red_image(h: int = 32, w: int = 64) -> np.ndarray:
    return np.tile(RED, (h, w, 1))


def buffalo(
    folder: Path, *, outputs: int = 9, rec_size: int = 112, det_shape: tuple = (1, 3, 32, 32)
) -> Path:
    outs = scrfd_outputs(size=32)[:outputs]
    constant_outputs_model(
        folder / "det_10g.onnx",
        [(f"out{i}", o) for i, o in enumerate(outs)],
        input_shape=list(det_shape),
    )
    mean_pool_image_model(
        folder / "w600k_r50.onnx",
        np.eye(3, 4),
        size=rec_size,
        input_name="input.1",
        output_name="683",
    )
    return folder


def analyzer(folder: Path, **kwargs: object) -> InsightFaceAnalyzer:
    return InsightFaceAnalyzer(folder, loader=lambda _: red_image(), **kwargs)  # type: ignore[arg-type]


def test_buffalo_detects_aligns_and_embeds(tmp_path: Path) -> None:
    faces = analyzer(buffalo(tmp_path)).detect(tmp_path / "photo.jpg")
    (face,) = faces
    # input 32x32 letterboxed from 64x32 (scale 0.5): box (8,0,24,16) → (16,0,48,32) px
    assert (face.box.x, face.box.y, face.box.width, face.box.height) == pytest.approx(
        (0.25, 0.0, 0.5, 1.0)
    )
    assert face.score == pytest.approx(0.9)
    assert face.landmarks[0] == pytest.approx((24 / 64, 12 / 32))
    assert face.landmarks[4] == pytest.approx((38.4 / 64, 24 / 32))
    r, g, b, extra = face.embedding
    assert sum(x * x for x in face.embedding) == pytest.approx(1.0)
    assert g == pytest.approx(b) and extra == 0.0 and r > g  # RGB order reached ArcFace


def test_min_score_filters_detections(tmp_path: Path) -> None:
    assert analyzer(buffalo(tmp_path), min_score=0.95).detect(tmp_path / "x.jpg") == []


def test_dynamic_detector_input_uses_the_configured_size(tmp_path: Path) -> None:
    folder = buffalo(tmp_path, det_shape=(1, 3, "h", "w"))
    faces = analyzer(folder, det_size=32).detect(tmp_path / "x.jpg")
    assert len(faces) == 1


def test_info_and_status(tmp_path: Path) -> None:
    face_model = analyzer(buffalo(tmp_path))
    assert face_model.name == "buffalo_l"
    assert face_model.status().ready
    assert face_model.info().dim == 4
    assert "CPUExecutionProvider" in face_model.status().detail


def test_missing_model_files(tmp_path: Path) -> None:
    face_model = analyzer(tmp_path / "missing")
    assert not face_model.status().ready
    assert "just models" in face_model.status().detail
    with pytest.raises(ModelUnavailableError, match=r"det_10g\.onnx"):
        face_model.detect(tmp_path / "x.jpg")


def test_detector_without_landmark_outputs_is_rejected(tmp_path: Path) -> None:
    face_model = analyzer(buffalo(tmp_path, outputs=6))
    with pytest.raises(ModelFormatError, match="9 outputs"):
        face_model.detect(tmp_path / "x.jpg")
    assert "9 outputs" in face_model.status().detail


def test_recogniser_with_wrong_crop_size_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ModelFormatError, match="112"):
        analyzer(buffalo(tmp_path, rec_size=128)).detect(tmp_path / "x.jpg")


# --- YuNet + SFace (OpenCV) -------------------------------------------------------------------


class FakeDetector:
    def __init__(self, rows: np.ndarray | None) -> None:
        self.rows = rows
        self.sizes: list[tuple[int, int]] = []

    def setInputSize(self, size: tuple[int, int]) -> None:  # noqa: N802 (OpenCV's name)
        self.sizes.append(size)

    def detect(self, image: np.ndarray) -> tuple[int, np.ndarray | None]:
        return 1, self.rows


class FakeRecognizer:
    def __init__(self) -> None:
        self.aligned: list[np.ndarray] = []

    def alignCrop(self, image: np.ndarray, row: np.ndarray) -> np.ndarray:  # noqa: N802
        self.aligned.append(row.copy())
        return image[:4, :4]

    def feature(self, crop: np.ndarray) -> np.ndarray:
        return np.array([[3.0, 4.0] + [0.0] * 126], dtype=np.float32)


def yunet_folder(tmp_path: Path) -> Path:
    for name in ("face_detection_yunet_2023mar.onnx", "face_recognition_sface_2021dec.onnx"):
        (tmp_path / name).write_bytes(b"x")
    return tmp_path


def yunet(tmp_path: Path, rows: np.ndarray | None, image: np.ndarray) -> tuple:
    detector, recognizer = FakeDetector(rows), FakeRecognizer()
    made: list[tuple] = []

    def make_detector(model: str, config: str, size: tuple, score: float, nms: float) -> object:
        made.append((Path(model).name, score))
        return detector

    face_model = YuNetSFaceAnalyzer(
        yunet_folder(tmp_path),
        min_score=0.8,
        det_max_edge=100,
        loader=lambda _: image,
        detector_factory=make_detector,
        recognizer_factory=lambda model, config: recognizer,
    )
    return face_model, detector, recognizer, made


def test_yunet_rows_become_faces_in_full_image_coordinates(tmp_path: Path) -> None:
    # detection runs on a 100x50 downscale of a 200x100 image; rows are in that space
    row = np.array([[10, 5, 20, 30, 12, 10, 24, 10, 18, 18, 13, 25, 23, 25, 0.93]], np.float32)
    face_model, detector, recognizer, made = yunet(tmp_path, row, red_image(100, 200))
    (face,) = face_model.detect(tmp_path / "x.jpg")
    assert detector.sizes == [(100, 50)]
    assert made == [("face_detection_yunet_2023mar.onnx", 0.8)]
    assert (face.box.x, face.box.y, face.box.width, face.box.height) == pytest.approx(
        (0.1, 0.1, 0.2, 0.6)
    )
    assert face.landmarks[0] == pytest.approx((0.12, 0.2))
    assert face.score == pytest.approx(0.93)
    assert face.embedding[:2] == pytest.approx((0.6, 0.8))
    assert recognizer.aligned[0][:4].tolist() == [20, 10, 40, 60]  # scaled to the full image
    assert face_model.info().dim == 128 and face_model.name == "yunet_sface"


def test_yunet_without_faces(tmp_path: Path) -> None:
    face_model, *_ = yunet(tmp_path, None, red_image(40, 40))
    assert face_model.detect(tmp_path / "x.jpg") == []
    assert face_model.status().ready


def test_yunet_missing_files(tmp_path: Path) -> None:
    face_model = YuNetSFaceAnalyzer(tmp_path / "none")
    assert not face_model.status().ready
    with pytest.raises(ModelUnavailableError, match="yunet"):
        face_model.detect(tmp_path / "x.jpg")


def test_yunet_unloadable_model_is_a_format_error(tmp_path: Path) -> None:
    face_model = YuNetSFaceAnalyzer(yunet_folder(tmp_path))  # real OpenCV, junk files
    with pytest.raises(ModelFormatError):
        face_model.detect(tmp_path / "x.jpg")
