"""Tiny, pure vector maths for embeddings (CLIP, faces).

Embeddings cross layer boundaries as plain tuples of floats so the domain and the ports stay
free of numpy. Adapters convert at the edge; bulk maths (KNN) runs in sqlite-vec.
"""

import math
from collections.abc import Sequence

Vector = tuple[float, ...]


def dot(a: Sequence[float], b: Sequence[float]) -> float:
    if len(a) != len(b):
        raise ValueError(f"dimension mismatch: {len(a)} vs {len(b)}")
    return math.fsum(x * y for x, y in zip(a, b, strict=True))


def norm(v: Sequence[float]) -> float:
    return math.sqrt(dot(v, v))


def normalise(v: Sequence[float]) -> Vector:
    length = norm(v)
    if length == 0.0:
        raise ValueError("cannot normalise a zero vector")
    return tuple(x / length for x in v)


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    return dot(a, b) / (norm(a) * norm(b))


def cosine_distance(a: Sequence[float], b: Sequence[float]) -> float:
    """1 - cosine similarity: 0 = same direction, 1 = orthogonal, 2 = opposite."""
    return 1.0 - cosine_similarity(a, b)


def mean_direction(vectors: Sequence[Sequence[float]]) -> Vector:
    """Normalised average — how a prompt ensemble becomes one class prototype."""
    if not vectors:
        raise ValueError("mean of an empty set of vectors")
    total = [math.fsum(column) for column in zip(*vectors, strict=True)]
    return normalise(total)
