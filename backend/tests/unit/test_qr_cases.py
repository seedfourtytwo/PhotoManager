"""The QR codes the web app draws can be read (docs/contracts/qr-cases.json).

The web app has its own small QR encoder (web/src/lib/qr.ts, no library). Its unit test pins
it, square for square, to the codes in that file; this test reads those same codes back with
OpenCV's decoder, which shares no code with the encoder. Together: what the app draws is what
a phone reads.
"""

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

CASES = json.loads(
    (Path(__file__).parents[3] / "docs" / "contracts" / "qr-cases.json").read_text("utf-8")
)["cases"]
SCALE, QUIET_ZONE = 8, 4  # pixels per square; light squares around the code, as the app draws it


def _picture(rows: list[str]) -> np.ndarray[tuple[int, ...], np.dtype[np.uint8]]:
    dark = np.array([[cell == "1" for cell in row] for row in rows])
    squares = np.pad(np.where(dark, 0, 255).astype(np.uint8), QUIET_ZONE, constant_values=255)
    return np.kron(squares, np.ones((SCALE, SCALE), dtype=np.uint8))


@pytest.mark.parametrize("case", CASES, ids=[c["text"][:24] for c in CASES])
def test_a_decoder_reads_the_text_back(case: dict[str, object]) -> None:
    rows: list[str] = case["rows"]  # type: ignore[assignment]
    assert len(rows) == 17 + 4 * int(str(case["version"]))
    text, _, _ = cv2.QRCodeDetector().detectAndDecode(_picture(rows))
    assert text == case["text"]


def test_the_cases_include_a_link_as_the_app_makes_them() -> None:
    assert any("/receive.html#" in str(c["text"]) for c in CASES)
