"""Checks against the REAL model files — run on the laptop after `just models`:

    PA_MODELS_DIR=~/PhotoAssistant/data/models uv run pytest -m models

Skipped everywhere else (CI and cloud workspaces can't download the weights). Images are drawn
here; no real photos. These catch format mismatches the synthetic graphs can't: input/output
names and shapes, preprocessing size, embedding dimension, tokenizer padding.
"""

import os
from pathlib import Path

import numpy as np
import pytest

from photo_assistant.adapters.faces_insightface import InsightFaceAnalyzer
from photo_assistant.adapters.faces_opencv import YuNetSFaceAnalyzer
from photo_assistant.adapters.onnx_clip import OnnxClip
from photo_assistant.domain.vectors import dot
from tests.ml.test_onnx_clip import save_png, solid

MODELS = Path(os.environ.get("PA_MODELS_DIR", "/nonexistent")).expanduser()
CLIP_NAME = os.environ.get("PA_ML_CLIP_MODEL", "ViT-B-32__openai")

pytestmark = [
    pytest.mark.models,
    pytest.mark.skipif(not MODELS.is_dir(), reason="set PA_MODELS_DIR to the models folder"),
]

needs_clip = pytest.mark.skipif(
    not (MODELS / "clip" / CLIP_NAME).is_dir(), reason=f"CLIP {CLIP_NAME} not downloaded"
)
needs_buffalo = pytest.mark.skipif(
    not (MODELS / "insightface" / "buffalo_l").is_dir(), reason="buffalo_l not downloaded"
)
needs_yunet = pytest.mark.skipif(
    not (MODELS / "opencv").is_dir(), reason="yunet_sface not downloaded"
)


@pytest.fixture(scope="module")
def clip() -> OnnxClip:
    return OnnxClip(MODELS / "clip" / CLIP_NAME, CLIP_NAME, provider="auto")


@needs_clip
def test_clip_loads_and_reports_its_dimension(clip: OnnxClip) -> None:
    dim = clip.info().dim
    assert dim in (512, 640, 768, 1024)
    vector = clip.embed_text("a photo of a dog")
    assert len(vector) == dim
    assert dot(vector, vector) == pytest.approx(1.0, abs=1e-4)
    assert clip.status().ready, clip.status().detail


@needs_clip
def test_clip_text_and_image_share_a_space(clip: OnnxClip, tmp_path: Path) -> None:
    red = save_png(tmp_path / "red.png", solid(300, 400, (220, 20, 20)))
    blue = save_png(tmp_path / "blue.png", solid(400, 300, (20, 40, 220)))
    red_vec, blue_vec = clip.embed_images([red, blue])
    red_text = clip.embed_text("a plain red image")
    blue_text = clip.embed_text("a plain blue image")
    assert dot(red_vec, red_text) > dot(red_vec, blue_text)
    assert dot(blue_vec, blue_text) > dot(blue_vec, red_text)


@needs_clip
def test_long_and_accented_queries_work(clip: OnnxClip) -> None:
    clip.embed_text("les enfants dans la neige chez mamie, été 2019 " * 20)  # truncation
    english = clip.embed_text("children playing in the snow")
    french = clip.embed_text("des enfants qui jouent dans la neige")
    unrelated = clip.embed_text("a receipt from a supermarket")
    if "XLM" in CLIP_NAME or "nllb" in CLIP_NAME:  # multilingual models only
        assert dot(english, french) > dot(english, unrelated)


@needs_buffalo
def test_buffalo_loads_and_finds_nothing_on_a_blank_image(tmp_path: Path) -> None:
    faces = InsightFaceAnalyzer(MODELS / "insightface" / "buffalo_l")
    blank = save_png(tmp_path / "blank.png", solid(480, 640, (128, 128, 128)))
    assert faces.detect(blank) == []
    assert faces.info().dim == 512
    assert faces.status().ready, faces.status().detail


@needs_buffalo
def test_arcface_embeds_any_aligned_crop(tmp_path: Path) -> None:
    faces = InsightFaceAnalyzer(MODELS / "insightface" / "buffalo_l")
    _, recogniser = faces._models.get()  # internal: exercise the recogniser alone
    crop = np.full((112, 112, 3), 90, dtype=np.uint8)
    (vector,) = recogniser.embed([crop])
    assert len(vector) == 512 and dot(vector, vector) == pytest.approx(1.0, abs=1e-4)


@needs_yunet
def test_yunet_sface_loads_and_finds_nothing_on_a_blank_image(tmp_path: Path) -> None:
    faces = YuNetSFaceAnalyzer(MODELS / "opencv")
    blank = save_png(tmp_path / "blank.png", solid(480, 640, (128, 128, 128)))
    assert faces.detect(blank) == []
