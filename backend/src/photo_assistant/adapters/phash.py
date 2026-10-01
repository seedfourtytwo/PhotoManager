"""PerceptualHasher with imagehash (pHash) on the small thumbnail: fast and good enough."""

from pathlib import Path

import imagehash
from PIL import Image


class ImageHashPhash:
    def phash(self, image: Path) -> str:
        with Image.open(image) as im:
            return str(imagehash.phash(im.convert("RGB")))
