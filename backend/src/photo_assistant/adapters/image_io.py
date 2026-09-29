"""Decode any library image (JPEG, HEIC, PNG, WebP derivatives…) to an RGB uint8 array.

libvips does the decoding, so everything the thumbnailer reads, the ML adapters read too, with
EXIF orientation applied — face boxes are fractions of the image *as displayed*.
"""

from pathlib import Path

import numpy as np
import pyvips  # type: ignore[import-untyped]
from numpy.typing import NDArray

RgbImage = NDArray[np.uint8]  # H x W x 3


def load_rgb(path: Path) -> RgbImage:
    try:
        image = pyvips.Image.new_from_file(str(path)).autorot()
        if image.interpretation != "srgb":
            image = image.colourspace("srgb")
        if image.hasalpha():
            image = image.flatten(background=[255, 255, 255])
        image = image.extract_band(0, n=3).cast("uchar")
        data = image.write_to_memory()
    except pyvips.Error as exc:
        raise ValueError(f"cannot decode {path.name}: {exc}") from exc
    return np.ndarray(shape=(image.height, image.width, 3), dtype=np.uint8, buffer=data)
