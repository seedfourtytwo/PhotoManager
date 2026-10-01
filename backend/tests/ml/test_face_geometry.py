"""SCRFD decoding, NMS, letterboxing and ArcFace alignment, checked on known geometry."""

import math

import numpy as np
import pytest

from photo_assistant.adapters.face_geometry import (
    ARCFACE_DST,
    align_face,
    anchor_centers,
    decode_scrfd,
    distance2bbox,
    distance2kps,
    letterbox,
    nms,
    similarity_transform,
)
from photo_assistant.ports.ml import ModelFormatError


def test_anchor_centres_run_row_major_with_repeated_anchors() -> None:
    centres = anchor_centers(2, 3, stride=8, num_anchors=2)
    expected = [(0, 0), (8, 0), (16, 0), (0, 8), (8, 8), (16, 8)]
    assert centres.tolist() == [list(p) for p in expected for _ in range(2)]


def test_distances_decode_to_boxes_and_keypoints() -> None:
    centre = np.array([[10.0, 20.0]])
    assert distance2bbox(centre, np.array([[1.0, 2.0, 3.0, 4.0]])).tolist() == [[9, 18, 13, 24]]
    kps = distance2kps(centre, np.array([[1, 2, -1, -2, 0, 0, 3, 3, -3, -3]], dtype=float))
    assert kps.tolist() == [[[11, 22], [9, 18], [10, 20], [13, 23], [7, 17]]]


def test_nms_keeps_the_best_of_overlapping_boxes() -> None:
    dets = np.array(
        [
            [0, 0, 10, 10, 0.9],
            [1, 1, 11, 11, 0.8],  # IoU with the first ≈ 0.70 → suppressed
            [20, 20, 30, 30, 0.7],
            [0, 0, 10, 4, 0.6],  # IoU with the first ≈ 0.45: suppressed at 0.4, kept at 0.5
        ]
    )
    assert nms(dets, 0.4) == [0, 2]
    assert nms(dets, 0.5) == [0, 2, 3]
    assert nms(np.zeros((0, 5)), 0.4) == []


@pytest.mark.parametrize(
    ("h", "w", "new_h", "new_w", "scale"),
    [(50, 100, 32, 64, 0.64), (100, 50, 64, 32, 0.64), (64, 64, 64, 64, 1.0)],
)
def test_letterbox_fits_top_left_and_pads(
    h: int, w: int, new_h: int, new_w: int, scale: float
) -> None:
    image = np.full((h, w, 3), 200, dtype=np.uint8)
    canvas, got = letterbox(image, 64, 64)
    assert canvas.shape == (64, 64, 3) and got == pytest.approx(scale)
    assert canvas[new_h - 1, new_w - 1].tolist() == [200, 200, 200]
    assert canvas[63, 63].tolist() == ([0, 0, 0] if (new_h, new_w) != (64, 64) else [200] * 3)


def rotation(scale: float, degrees: float, tx: float, ty: float) -> np.ndarray:
    a = math.radians(degrees)
    c, s = scale * math.cos(a), scale * math.sin(a)
    return np.array([[c, -s, tx], [s, c, ty]])


def apply(matrix: np.ndarray, points: np.ndarray) -> np.ndarray:
    return points @ matrix[:, :2].T + matrix[:, 2]


def test_similarity_transform_recovers_a_known_transform() -> None:
    known = rotation(2.5, 30, 100, 40)
    src = ARCFACE_DST.astype(np.float64)
    estimated = similarity_transform(src, apply(known, src))
    assert estimated == pytest.approx(known, abs=1e-6)


def test_similarity_transform_rejects_degenerate_points() -> None:
    with pytest.raises(ValueError, match="degenerate"):
        similarity_transform(np.ones((5, 2)), ARCFACE_DST)


def test_alignment_moves_landmarks_to_the_arcface_template() -> None:
    to_image = rotation(3.0, -20, 200, 150)
    landmarks = apply(to_image, ARCFACE_DST.astype(np.float64))
    image = np.zeros((600, 600, 3), dtype=np.uint8)
    for x, y in landmarks.round().astype(int):
        image[y - 2 : y + 3, x - 2 : x + 3] = 255
    aligned = align_face(image, landmarks)
    assert aligned.shape == (112, 112, 3) and aligned.dtype == np.uint8
    for x, y in ARCFACE_DST.round().astype(int):
        assert aligned[y, x, 0] > 128, (x, y)
    assert aligned[5, 5, 0] == 0


# --- SCRFD output decoding ----------------------------------------------------------------------


def scrfd_outputs(size: int = 32, batched: bool = True) -> list[np.ndarray]:
    """Nine outputs (scores, boxes, kps per stride 8/16/32), two anchors per cell, one face."""
    outs = []
    for last in (1, 4, 10):
        for stride in (8, 16, 32):
            rows = (size // stride) ** 2 * 2
            outs.append(np.zeros((rows, last), dtype=np.float32))
    row = (1 * 4 + 2) * 2  # stride 8, cell y=1 x=2 → centre (16, 8), anchor 0
    outs[0][row] = 0.9
    outs[0][row + 1] = 0.85  # the second anchor sees the same face → removed by NMS
    outs[1][0] = 0.3  # stride 16, below threshold
    outs[3][row] = outs[3][row + 1] = [1, 1, 1, 1]  # in stride units → (8, 0, 24, 16)
    outs[6][row] = [-0.5, -0.25, 0.5, -0.25, 0, 0, -0.4, 0.5, 0.4, 0.5]
    return [o[None] if batched else o for o in outs]


@pytest.mark.parametrize("batched", [True, False])
def test_decode_scrfd_finds_the_face_in_input_pixels(batched: bool) -> None:
    boxes, kps, scores = decode_scrfd(scrfd_outputs(batched=batched), 32, 32, threshold=0.5)
    assert scores.tolist() == pytest.approx([0.9])  # the duplicate anchor fell to NMS
    assert boxes[0].tolist() == [8, 0, 24, 16]
    assert kps[0] == pytest.approx(np.array([[12, 6], [20, 6], [16, 8], [12.8, 12], [19.2, 12]]))


def test_decode_scrfd_output_order_does_not_matter() -> None:
    outs = scrfd_outputs()
    shuffled = [outs[i] for i in (8, 3, 0, 6, 1, 4, 7, 2, 5)]
    boxes, _, _ = decode_scrfd(shuffled, 32, 32, threshold=0.5)
    assert boxes[0].tolist() == [8, 0, 24, 16]


def test_decode_scrfd_rejects_unexpected_outputs() -> None:
    outs = scrfd_outputs()
    with pytest.raises(ModelFormatError, match="9 outputs"):
        decode_scrfd(outs[:6], 32, 32, threshold=0.5)
    with pytest.raises(ModelFormatError, match="rows"):
        decode_scrfd(outs, 64, 64, threshold=0.5)
    bad = [*outs[:8], np.zeros((1, 2, 7), dtype=np.float32)]
    with pytest.raises(ModelFormatError, match="last dimension"):
        decode_scrfd(bad, 32, 32, threshold=0.5)
