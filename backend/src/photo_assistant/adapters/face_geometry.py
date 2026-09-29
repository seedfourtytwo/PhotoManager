"""Numeric core of the InsightFace pipeline, ported from insightface's model_zoo/scrfd.py and
utils/face_align.py so we can run the ONNX files with onnxruntime alone.

SCRFD predicts, for each anchor of each stride (8, 16, 32), a score, distances from the anchor
centre to the four box sides and offsets to five landmarks — all in stride units. ArcFace
expects the face warped by a similarity transform onto a fixed 112x112 landmark template.
"""

from collections.abc import Sequence

import cv2
import numpy as np
from numpy.typing import NDArray

from photo_assistant.ports.ml import ModelFormatError

Array = NDArray[np.float64]
Image = NDArray[np.uint8]

STRIDES = (8, 16, 32)

# insightface.utils.face_align.arcface_dst: eyes, nose tip, mouth corners in a 112x112 crop.
ARCFACE_DST = np.array(
    [
        [38.2946, 51.6963],
        [73.5318, 51.5014],
        [56.0252, 71.7366],
        [41.5493, 92.3655],
        [70.7299, 92.2041],
    ],
    dtype=np.float32,
)


def anchor_centers(height: int, width: int, stride: int, num_anchors: int) -> Array:
    """(x, y) of every anchor, row by row, each repeated ``num_anchors`` times."""
    ys, xs = np.mgrid[:height, :width]
    grid = np.stack([xs, ys], axis=-1).astype(np.float64)
    centres = (grid * stride).reshape(-1, 2)
    return np.repeat(centres, num_anchors, axis=0)


def distance2bbox(points: Array, distance: Array) -> Array:
    return np.stack(
        [
            points[:, 0] - distance[:, 0],
            points[:, 1] - distance[:, 1],
            points[:, 0] + distance[:, 2],
            points[:, 1] + distance[:, 3],
        ],
        axis=-1,
    )


def distance2kps(points: Array, distance: Array) -> Array:
    """→ N x 5 x 2."""
    offsets = distance.reshape(len(distance), -1, 2)
    return points[:, None, :] + offsets


def nms(dets: Array, threshold: float) -> list[int]:
    """Greedy NMS over rows (x1, y1, x2, y2, score); insightface's +1 pixel area convention."""
    x1, y1, x2, y2, scores = (dets[:, i] for i in range(5))
    areas = (x2 - x1 + 1) * (y2 - y1 + 1)
    order = scores.argsort(kind="stable")[::-1]
    keep: list[int] = []
    while order.size > 0:
        i = int(order[0])
        keep.append(i)
        rest = order[1:]
        w = np.maximum(0.0, np.minimum(x2[i], x2[rest]) - np.maximum(x1[i], x1[rest]) + 1)
        h = np.maximum(0.0, np.minimum(y2[i], y2[rest]) - np.maximum(y1[i], y1[rest]) + 1)
        overlap = (w * h) / (areas[i] + areas[rest] - w * h)
        order = rest[overlap <= threshold]
    return keep


def letterbox(image: Image, width: int, height: int) -> tuple[Image, float]:
    """Fit into width x height keeping the aspect ratio, top-left aligned, black padding."""
    h, w = image.shape[:2]
    if h / w > height / width:
        new_h, new_w = height, int(height / (h / w))
    else:
        new_w, new_h = width, int(width * (h / w))
    canvas = np.zeros((height, width, 3), dtype=np.uint8)
    canvas[:new_h, :new_w] = cv2.resize(image, (new_w, new_h))
    return canvas, new_h / h


def similarity_transform(src: Array, dst: Array) -> Array:
    """2x3 matrix of the least-squares similarity (Umeyama, as skimage) mapping src → dst."""
    src_mean, dst_mean = src.mean(axis=0), dst.mean(axis=0)
    src_c, dst_c = src - src_mean, dst - dst_mean
    cov = dst_c.T @ src_c / len(src)
    if np.linalg.matrix_rank(cov) < 2:
        raise ValueError("degenerate landmarks: cannot estimate an alignment")
    d = np.ones(2)
    if np.linalg.det(cov) < 0:
        d[1] = -1
    u, s, vt = np.linalg.svd(cov)
    rotation = u @ np.diag(d) @ vt
    scale = (s @ d) / src_c.var(axis=0).sum()
    translation = dst_mean - scale * rotation @ src_mean
    return np.hstack([scale * rotation, translation[:, None]])


def align_face(image: Image, landmarks: Array, size: int = 112) -> Image:
    """Warp the face so its five landmarks land on the ArcFace template (insightface norm_crop)."""
    template = ARCFACE_DST.astype(np.float64) * (size / 112.0)
    matrix = similarity_transform(np.asarray(landmarks, dtype=np.float64), template)
    warped = cv2.warpAffine(image, matrix, (size, size), borderValue=0.0)
    return np.asarray(warped, dtype=np.uint8)


# --- SCRFD outputs ---------------------------------------------------------------------------


def _group_outputs(outputs: Sequence[NDArray[np.float32]]) -> dict[int, list[Array]]:
    """{1: scores, 4: boxes, 10: kps}, each ordered stride 8 → 32 (most rows first)."""
    if len(outputs) != 9:
        raise ModelFormatError(
            f"SCRFD detector should have 9 outputs (score/box/landmarks x 3 strides), "
            f"got {len(outputs)}"
        )
    groups: dict[int, list[Array]] = {1: [], 4: [], 10: []}
    for out in outputs:
        array = np.asarray(out[0] if out.ndim == 3 else out, dtype=np.float64)
        if array.ndim != 2 or array.shape[1] not in groups:
            raise ModelFormatError(f"SCRFD output with unexpected last dimension: {out.shape}")
        groups[array.shape[1]].append(array)
    for arrays in groups.values():
        arrays.sort(key=len, reverse=True)
    if any(len(arrays) != len(STRIDES) for arrays in groups.values()):
        raise ModelFormatError("SCRFD outputs should be 3 scores, 3 boxes and 3 landmark sets")
    return groups


def _centres_for(rows: int, height: int, width: int, stride: int) -> Array:
    cells = (height // stride) * (width // stride)
    if cells == 0 or rows % cells != 0:
        raise ModelFormatError(
            f"SCRFD stride {stride}: {rows} rows don't fit a {width}x{height} input"
        )
    return anchor_centers(height // stride, width // stride, stride, rows // cells)


def decode_scrfd(
    outputs: Sequence[NDArray[np.float32]], height: int, width: int, *, threshold: float
) -> tuple[Array, Array, Array]:
    """Boxes (N x 4), landmarks (N x 5 x 2) in input pixels and scores (N), best first, after
    NMS (0.4, as insightface)."""
    groups = _group_outputs(outputs)
    boxes, kps, scores = [], [], []
    for index, stride in enumerate(STRIDES):
        score = groups[1][index][:, 0]
        centres = _centres_for(len(score), height, width, stride)
        keep = score >= threshold
        boxes.append(distance2bbox(centres, groups[4][index] * stride)[keep])
        kps.append(distance2kps(centres, groups[10][index] * stride)[keep])
        scores.append(score[keep])
    all_boxes, all_kps, all_scores = np.vstack(boxes), np.vstack(kps), np.concatenate(scores)
    order = nms(np.hstack([all_boxes, all_scores[:, None]]), 0.4) if len(all_scores) else []
    return all_boxes[order], all_kps[order], all_scores[order]
