"""CLIP via onnxruntime against synthetic Immich-style model folders."""

import math
from pathlib import Path

import numpy as np
import pytest
import pyvips  # type: ignore[import-untyped]
from onnx import TensorProto

from photo_assistant.adapters.image_io import load_rgb
from photo_assistant.adapters.onnx_clip import (
    ClipPreprocess,
    OnnxClip,
    preprocess_image,
    read_preprocess,
)
from photo_assistant.adapters.onnx_common import choose_providers
from photo_assistant.ports.ml import ModelFormatError, ModelUnavailableError
from tests.ml.onnx_models import mean_pool_image_model, token_text_model, word_tokenizer, write_json

MEAN = (0.48145466, 0.4578275, 0.40821073)
STD = (0.26862954, 0.26130258, 0.27577711)
SIZE = 16
CTX = 8
RED = (255, 0, 0)
BLUE = (0, 0, 255)


def solid(h: int, w: int, rgb: tuple[int, int, int]) -> np.ndarray:
    return np.tile(np.array(rgb, dtype=np.uint8), (h, w, 1))


def save_png(path: Path, array: np.ndarray) -> Path:
    h, w, bands = array.shape
    pyvips.Image.new_from_memory(array.tobytes(), w, h, bands, "uchar").pngsave(str(path))
    return path


def normalised_pixel(rgb: tuple[int, int, int]) -> np.ndarray:
    return (np.array(rgb, dtype=np.float32) / 255 - np.array(MEAN)) / np.array(STD)


def unit(v: np.ndarray) -> np.ndarray:
    return v / np.linalg.norm(v)


def make_clip_folder(
    root: Path,
    *,
    batch: int | str = "batch",
    visual_size: int = SIZE,
    embed_dim: int = 3,
    text_inputs: tuple[str, ...] = ("text",),
    text_dtype: int = TensorProto.INT32,
    visual_dim: int = 3,
) -> Path:
    write_json(root / "config.json", {"embed_dim": embed_dim, "text_cfg": {"context_length": CTX}})
    write_json(
        root / "visual" / "preprocess_cfg.json",
        {"size": [SIZE, SIZE], "mean": MEAN, "std": STD, "interpolation": "bicubic",
         "resize_mode": "shortest"},
    )  # fmt: skip
    mean_pool_image_model(
        root / "visual" / "model.onnx", np.eye(3, visual_dim), size=visual_size, batch=batch
    )
    text_w = np.zeros((CTX, 3), dtype=np.float32)
    text_w[:3, :3] = np.eye(3)  # embedding = the first three token ids
    token_text_model(root / "textual" / "model.onnx", text_w, inputs=text_inputs, dtype=text_dtype)
    word_tokenizer(root / "textual" / "tokenizer.json", ["a", "b", "c"])
    write_json(root / "textual" / "tokenizer_config.json", {"pad_token": "<pad>"})
    return root


CFG = ClipPreprocess(size=10, mean=MEAN, std=STD, resize_mode="shortest")


# --- preprocessing ----------------------------------------------------------------------------


def halves(h: int, w: int, vertical: bool = True) -> np.ndarray:
    image = solid(h, w, RED)
    if vertical:
        image[:, w // 2 :] = BLUE
    else:
        image[h // 2 :, :] = BLUE
    return image


def test_landscape_is_resized_on_the_short_side_then_centre_cropped() -> None:
    out = preprocess_image(halves(20, 40), CFG)  # → 20x10, crop columns 5..15
    assert out.shape == (3, 10, 10) and out.dtype == np.float32
    assert out[:, 5, 0] == pytest.approx(normalised_pixel(RED), abs=1e-5)
    assert out[:, 5, 4] == pytest.approx(normalised_pixel(RED), abs=1e-5)
    assert out[:, 5, 5] == pytest.approx(normalised_pixel(BLUE), abs=1e-5)
    assert out[:, 5, 9] == pytest.approx(normalised_pixel(BLUE), abs=1e-5)


def test_portrait_is_cropped_vertically() -> None:
    out = preprocess_image(halves(40, 20, vertical=False), CFG)
    assert out[:, 0, 5] == pytest.approx(normalised_pixel(RED), abs=1e-5)
    assert out[:, 9, 5] == pytest.approx(normalised_pixel(BLUE), abs=1e-5)


def test_squash_mode_keeps_the_whole_frame() -> None:
    cfg = ClipPreprocess(10, MEAN, STD, "squash")
    out = preprocess_image(halves(20, 40), cfg)
    assert out[:, 5, 0] == pytest.approx(normalised_pixel(RED), abs=1e-5)
    assert out[:, 5, 9] == pytest.approx(normalised_pixel(BLUE), abs=1e-5)


def test_small_images_are_upscaled() -> None:
    assert preprocess_image(solid(3, 5, RED), CFG).shape == (3, 10, 10)


def test_preprocess_config_accepts_int_or_list_size(tmp_path: Path) -> None:
    path = write_json(tmp_path / "p.json", {"size": 224, "mean": MEAN, "std": STD})
    assert read_preprocess(path) == ClipPreprocess(224, MEAN, STD, "shortest")
    write_json(path, {"size": [256, 256], "mean": MEAN, "std": STD, "resize_mode": "squash"})
    assert read_preprocess(path).size == 256


@pytest.mark.parametrize(
    "bad",
    [
        {"mean": MEAN, "std": STD},
        {"size": 224, "mean": [0.5], "std": STD},
        {"size": 224, "mean": MEAN, "std": STD, "resize_mode": "longest"},
        {"size": [224, 200], "mean": MEAN, "std": STD},
    ],
)
def test_bad_preprocess_config_is_a_clear_format_error(tmp_path: Path, bad: object) -> None:
    with pytest.raises(ModelFormatError, match="preprocess_cfg"):
        read_preprocess(write_json(tmp_path / "preprocess_cfg.json", bad))


# --- providers -----------------------------------------------------------------------------------


def test_provider_choice() -> None:
    both = ["CUDAExecutionProvider", "CPUExecutionProvider"]
    assert choose_providers("cpu", both) == ["CPUExecutionProvider"]
    assert choose_providers("auto", both) == both
    assert choose_providers("auto", ["CPUExecutionProvider"]) == ["CPUExecutionProvider"]
    assert choose_providers("cuda", both) == both
    with pytest.raises(ModelUnavailableError, match="onnxruntime-gpu"):
        choose_providers("cuda", ["CPUExecutionProvider"])
    with pytest.raises(ValueError, match="provider"):
        choose_providers("tpu", both)


# --- image loading ----------------------------------------------------------------------------


def test_load_rgb_handles_grey_alpha_and_orientation(tmp_path: Path) -> None:
    grey = pyvips.Image.new_from_memory(bytes([200] * 6), 3, 2, 1, "uchar")
    grey.pngsave(str(tmp_path / "grey.png"))
    assert load_rgb(tmp_path / "grey.png").shape == (2, 3, 3)

    rgba = np.zeros((2, 2, 4), dtype=np.uint8)
    rgba[..., 0] = 255
    rgba[..., 3] = 255
    loaded = load_rgb(save_png(tmp_path / "rgba.png", rgba))
    assert loaded.shape == (2, 2, 3) and loaded[0, 0].tolist() == [255, 0, 0]

    wide = pyvips.Image.new_from_memory(solid(10, 20, RED).tobytes(), 20, 10, 3, "uchar").copy()
    wide.set_type(pyvips.GValue.gint_type, "orientation", 6)
    wide.jpegsave(str(tmp_path / "rotated.jpg"))
    assert load_rgb(tmp_path / "rotated.jpg").shape == (20, 10, 3)


def test_load_rgb_of_a_broken_file_raises_value_error(tmp_path: Path) -> None:
    (tmp_path / "bad.jpg").write_bytes(b"not an image")
    with pytest.raises(ValueError, match=r"bad\.jpg"):
        load_rgb(tmp_path / "bad.jpg")


# --- end to end through onnxruntime ------------------------------------------------------------


@pytest.fixture
def clip_dir(tmp_path: Path) -> Path:
    return make_clip_folder(tmp_path / "ViT-test")


def test_missing_model_reports_status_and_raises(tmp_path: Path) -> None:
    clip = OnnxClip(tmp_path / "nothing", "ViT-B-32__openai")
    status = clip.status()
    assert not status.ready and "just models" in status.detail
    assert clip.name == "ViT-B-32__openai"
    with pytest.raises(ModelUnavailableError, match="just models"):
        clip.embed_text("hello")
    with pytest.raises(ModelUnavailableError):
        clip.info()


def test_images_are_embedded_in_batches_and_normalised(clip_dir: Path, tmp_path: Path) -> None:
    paths = [
        save_png(tmp_path / f"{i}.png", solid(12, 20, colour))
        for i, colour in enumerate([RED, BLUE, RED])
    ]
    clip = OnnxClip(clip_dir, "ViT-test", batch_size=2)
    vectors = clip.embed_images(paths)
    assert len(vectors) == 3
    assert vectors[0] == pytest.approx(tuple(unit(normalised_pixel(RED))), abs=1e-4)
    assert vectors[1] == pytest.approx(tuple(unit(normalised_pixel(BLUE))), abs=1e-4)
    assert vectors[2] == pytest.approx(vectors[0])
    assert math.fsum(x * x for x in vectors[1]) == pytest.approx(1.0)
    assert clip.info().dim == 3
    assert clip.status().ready and "CPUExecutionProvider" in clip.status().detail
    assert clip.embed_images([]) == []


def test_fixed_batch_of_one_models_run_image_by_image(tmp_path: Path) -> None:
    folder = make_clip_folder(tmp_path / "m", batch=1)
    images = [save_png(tmp_path / f"{i}.png", solid(16, 16, RED)) for i in range(2)]
    assert len(OnnxClip(folder, "m", batch_size=8).embed_images(images)) == 2


def test_text_is_tokenised_padded_and_embedded(clip_dir: Path) -> None:
    clip = OnnxClip(clip_dir, "ViT-test")
    assert clip.embed_text("B  a") == pytest.approx(tuple(unit(np.array([3.0, 2.0, 0.0]))))
    long = " ".join(["c"] * 50)  # truncated to the context length, no crash
    assert clip.embed_text(long) == pytest.approx(tuple(unit(np.ones(3))))


def test_multilingual_style_text_model_with_mask_and_int64(tmp_path: Path) -> None:
    folder = make_clip_folder(
        tmp_path / "XLM", text_inputs=("input_ids", "attention_mask"), text_dtype=TensorProto.INT64
    )
    clip = OnnxClip(folder, "XLM")
    assert clip.embed_text("a b c") == pytest.approx(tuple(unit(np.array([2.0, 3.0, 4.0]))))


def test_visual_input_size_must_match_preprocess_config(tmp_path: Path) -> None:
    folder = make_clip_folder(tmp_path / "m", visual_size=32)
    image = save_png(tmp_path / "x.png", solid(16, 16, RED))
    with pytest.raises(ModelFormatError, match="32"):
        OnnxClip(folder, "m").embed_images([image])


def test_output_dimension_must_match_config(tmp_path: Path) -> None:
    folder = make_clip_folder(tmp_path / "m", embed_dim=512)
    image = save_png(tmp_path / "x.png", solid(16, 16, RED))
    clip = OnnxClip(folder, "m")
    with pytest.raises(ModelFormatError, match="512"):
        clip.embed_images([image])
    assert not clip.status().ready and "512" in clip.status().detail


def test_unknown_text_inputs_are_a_format_error(tmp_path: Path) -> None:
    folder = make_clip_folder(tmp_path / "m", text_inputs=("tokens",))
    with pytest.raises(ModelFormatError, match="tokens"):
        OnnxClip(folder, "m").embed_text("a")


def test_corrupt_onnx_file_is_a_format_error(clip_dir: Path) -> None:
    (clip_dir / "textual" / "model.onnx").write_bytes(b"garbage")
    with pytest.raises(ModelFormatError, match=r"model\.onnx"):
        OnnxClip(clip_dir, "m").embed_text("a")


def test_pad_token_may_be_an_object_or_missing(clip_dir: Path) -> None:
    write_json(clip_dir / "textual" / "tokenizer_config.json", {"pad_token": {"content": "<pad>"}})
    assert OnnxClip(clip_dir, "m").embed_text("a") == pytest.approx((1.0, 0.0, 0.0))
    (clip_dir / "textual" / "tokenizer_config.json").unlink()  # falls back to a known pad
    assert OnnxClip(clip_dir, "m").embed_text("a") == pytest.approx((1.0, 0.0, 0.0))
    write_json(clip_dir / "textual" / "tokenizer_config.json", {"pad_token": "<nope>"})
    with pytest.raises(ModelFormatError, match="<nope>"):
        OnnxClip(clip_dir, "m").embed_text("a")
