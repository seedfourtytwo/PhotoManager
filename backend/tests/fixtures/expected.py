"""What importing tests/fixtures/photos must produce. Keep in sync with scripts/make_fixtures.py."""

IMPORTED = {
    "IMG_1001.JPG",
    "IMG_1002.JPG",
    "IMG_E1001.JPG",
    "IMG_20180312_091500.jpg",
    "Screenshot from 2026-07-03 15-21-27.png",
    "beach day 🌊.jpg",
    "grey-1x1.png",
    "nested/no-exif.jpg",
}
DUPLICATE = {"nested/deeper/IMG_1001 (Copy).JPG"}
SKIPPED = {"Trip.pdf", "IMG_1003.MOV"}
FAILED = {"empty.jpg", "not-an-image.jpg", "truncated.jpg"}
IGNORED = 2  # IMG_1001.AAE, .DS_Store
TOTAL_FILES = len(IMPORTED) + len(DUPLICATE) + len(SKIPPED) + len(FAILED) + IGNORED
