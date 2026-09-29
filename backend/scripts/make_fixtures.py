"""Generate the tiny, self-made fixture set. Deterministic: same bytes every run."""

from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "photos"

# Smallest valid PNG (1x1, grey) — written by hand, no third-party content.
PNG_1X1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c63f8cfc0f01f0005000201a3bd5d3c"
    "0000000049454e44ae426082"
)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "grey-1x1.png").write_bytes(PNG_1X1)
    (OUT / "duplicate-of-grey.png").write_bytes(PNG_1X1)
    (OUT / "empty.jpg").write_bytes(b"")
    (OUT / "not-an-image.jpg").write_bytes(b"this is text pretending to be a jpeg\n")


if __name__ == "__main__":
    main()
