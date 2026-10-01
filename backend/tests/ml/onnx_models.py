"""Tiny synthetic ONNX models with the same input/output contract as the real ones.

They exercise the onnxruntime plumbing (names, dtypes, batching, output parsing) without the
real weights, which this workspace cannot download. Each builder documents what the real model
looks like so a mismatch between the two is visible in one place.
"""

import json
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper
from tokenizers import Tokenizer, models, normalizers, pre_tokenizers

OPSET = [helper.make_opsetid("", 17)]


def _save(graph: onnx.GraphProto, path: Path) -> Path:
    model = helper.make_model(graph, opset_imports=OPSET, ir_version=8)
    onnx.checker.check_model(model)
    path.parent.mkdir(parents=True, exist_ok=True)
    onnx.save(model, str(path))
    return path


def _init(name: str, array: np.ndarray) -> onnx.TensorProto:
    return numpy_helper.from_array(array, name)


def mean_pool_image_model(
    path: Path,
    weights: np.ndarray,
    *,
    size: int | str = "height",
    batch: int | str = "batch",
    input_name: str = "image",
    output_name: str = "embedding",
) -> Path:
    """[N,3,S,S] float → mean over pixels per channel → @ weights[3,D] → [N,D].

    Stands in for CLIP visual (input "image" [N,3,224,224], output [N,D]) and ArcFace
    (input [N,3,112,112], output [N,512])."""
    dim = weights.shape[1]
    s = size if isinstance(size, int) else "height"
    w = size if isinstance(size, int) else "width"
    graph = helper.make_graph(
        [
            helper.make_node("ReduceMean", [input_name], ["pooled"], axes=[2, 3], keepdims=0),
            helper.make_node("MatMul", ["pooled", "w"], [output_name]),
        ],
        "mean_pool",
        [helper.make_tensor_value_info(input_name, TensorProto.FLOAT, [batch, 3, s, w])],
        [helper.make_tensor_value_info(output_name, TensorProto.FLOAT, [batch, dim])],
        [_init("w", weights.astype(np.float32))],
    )
    return _save(graph, path)


def token_text_model(
    path: Path,
    weights: np.ndarray,
    *,
    inputs: Sequence[str] = ("text",),
    dtype: int = TensorProto.INT32,
) -> Path:
    """[N,L] ids (and optional mask) → float → (ids x mask) @ weights[L,D] → [N,D].

    OpenCLIP text (Immich): one input "text" int32 [N,77]. M-CLIP (XLM-Roberta): "input_ids"
    and "attention_mask" [N,L]."""
    length, dim = weights.shape
    nodes = [helper.make_node("Cast", [inputs[0]], ["ids_f"], to=TensorProto.FLOAT)]
    pooled = "ids_f"
    if len(inputs) > 1:
        nodes.append(helper.make_node("Cast", [inputs[1]], ["mask_f"], to=TensorProto.FLOAT))
        nodes.append(helper.make_node("Mul", ["ids_f", "mask_f"], ["masked"]))
        pooled = "masked"
    nodes.append(helper.make_node("MatMul", [pooled, "w"], ["embedding"]))
    graph = helper.make_graph(
        nodes,
        "token_text",
        [helper.make_tensor_value_info(n, dtype, ["batch", length]) for n in inputs],
        [helper.make_tensor_value_info("embedding", TensorProto.FLOAT, ["batch", dim])],
        [_init("w", weights.astype(np.float32))],
    )
    return _save(graph, path)


def constant_outputs_model(
    path: Path, outputs: Sequence[tuple[str, np.ndarray]], *, input_shape: Sequence[int | str]
) -> Path:
    """Input "input.1" [1,3,H,W]; each output = a fixed tensor (+ 0 x mean(input) so the input
    is really consumed). Stands in for SCRFD det_10g, whose 9 outputs are per-stride scores
    [1,A·h·w,1], box distances [1,A·h·w,4] and landmark distances [1,A·h·w,10]."""
    nodes = [
        helper.make_node("ReduceMean", ["input.1"], ["m"], keepdims=0),
        helper.make_node("Mul", ["m", "zero"], ["z"]),
    ]
    inits = [_init("zero", np.array(0.0, dtype=np.float32))]
    infos = []
    for index, (name, value) in enumerate(outputs):
        inits.append(_init(f"c{index}", value.astype(np.float32)))
        nodes.append(helper.make_node("Add", [f"c{index}", "z"], [name]))
        infos.append(helper.make_tensor_value_info(name, TensorProto.FLOAT, list(value.shape)))
    graph = helper.make_graph(
        nodes,
        "constants",
        [helper.make_tensor_value_info("input.1", TensorProto.FLOAT, list(input_shape))],
        infos,
        inits,
    )
    return _save(graph, path)


def word_tokenizer(path: Path, words: Sequence[str], pad: str = "<pad>") -> Path:
    """A whitespace/lowercase word-level tokenizer saved as tokenizer.json."""
    vocab = {pad: 0, "[UNK]": 1} | {w: i + 2 for i, w in enumerate(words)}
    tokenizer = Tokenizer(models.WordLevel(vocab, unk_token="[UNK]"))
    tokenizer.normalizer = normalizers.Lowercase()
    tokenizer.pre_tokenizer = pre_tokenizers.Whitespace()
    path.parent.mkdir(parents=True, exist_ok=True)
    tokenizer.save(str(path))
    return path


def write_json(path: Path, value: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))
    return path
