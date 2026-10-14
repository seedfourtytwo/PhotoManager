"""What a photo is called where people see it and when it is downloaded (FEATURES 4b.7)."""

from datetime import datetime

import pytest

from photo_assistant.domain.capture_time import DateSource
from photo_assistant.domain.display_name import Dated, display_names, tidy_file_name

JUNE = datetime(2015, 6, 12, 14, 32, 5)


def one(photo: Dated, file_name: str | None = None, mates: tuple[Dated, ...] = ()) -> str:
    return display_names([photo], mates, {photo.id: file_name} if file_name else {})[photo.id]


def test_a_trusted_date_names_the_photo_by_its_minute() -> None:
    assert one(Dated(7, JUNE, DateSource.EXIF), "IMG_4821.HEIC") == "2015-06-12 14.32"
    assert one(Dated(7, JUNE, DateSource.FILENAME), "x.jpg") == "2015-06-12 14.32"
    assert one(Dated(7, JUNE, DateSource.MANUAL)) == "2015-06-12 14.32", "no file name needed"


def test_the_name_is_the_wall_clock_the_camera_showed_whatever_its_offset() -> None:
    """Capture times are local wall-clock (capture_time.py); the offset is not applied."""
    midnight = datetime(2019, 12, 31, 23, 59, 59)
    assert one(Dated(1, midnight, DateSource.EXIF)) == "2019-12-31 23.59"


def test_photos_of_the_same_minute_are_numbered_by_time_then_id() -> None:
    first = Dated(30, datetime(2015, 6, 12, 14, 32, 1), DateSource.EXIF)
    burst_a = Dated(10, datetime(2015, 6, 12, 14, 32, 40), DateSource.EXIF)
    burst_b = Dated(20, datetime(2015, 6, 12, 14, 32, 40), DateSource.EXIF)
    other_minute = Dated(5, datetime(2015, 6, 12, 14, 33, 0), DateSource.EXIF)
    mates = (first, burst_a, burst_b, other_minute)
    names = display_names([burst_b, first, burst_a, other_minute], mates, {})
    assert names == {
        30: "2015-06-12 14.32",
        10: "2015-06-12 14.32 · 2",
        20: "2015-06-12 14.32 · 3",
        5: "2015-06-12 14.33",
    }


def test_the_number_counts_mates_even_when_only_one_photo_is_named() -> None:
    early = Dated(1, JUNE, DateSource.EXIF)
    late = Dated(2, JUNE.replace(second=50), DateSource.EXIF)
    assert one(late, mates=(early, late)) == "2015-06-12 14.32 · 2"
    assert one(late, mates=(early,)) == "2015-06-12 14.32 · 2", "itself need not be a mate"


def test_a_mate_whose_date_is_a_guess_takes_no_number() -> None:
    guessed = Dated(1, JUNE.replace(second=0), DateSource.FILE_MTIME)
    assert one(Dated(2, JUNE, DateSource.EXIF), mates=(guessed,)) == "2015-06-12 14.32"


def test_a_guessed_date_falls_back_to_the_tidied_file_name() -> None:
    photo = Dated(42, JUNE, DateSource.FILE_MTIME)
    assert one(photo, "Beach day (Copy).jpg") == "Beach day"
    assert one(photo, "IMG_4821.HEIC") == "IMG_4821"


def test_without_a_date_or_a_usable_file_name_it_is_photo_and_its_id() -> None:
    photo = Dated(42, JUNE, DateSource.FILE_MTIME)
    assert one(photo) == "Photo 42", "the file name is hidden from this viewer"
    assert one(photo, "10174880_903634589713690_321783628180766947_n (Copy).jpg") == "Photo 42"
    assert one(photo, "20150612.jpg") == "Photo 42"


@pytest.mark.parametrize(
    ("name", "tidy"),
    [
        ("Beach day.jpg", "Beach day"),
        ("Beach day (Copy).jpg", "Beach day"),
        ("Beach day (copy 2).jpg", "Beach day"),
        ("Beach day - Copy.jpg", "Beach day"),
        ("Beach day - Copy (3).jpg", "Beach day"),
        ("Beach day copy.jpg", "Beach day"),
        ("Beach day copy 2.jpg", "Beach day"),
        ("Beach day (1).jpg", "Beach day"),
        ("Beach day (1) (Copy).jpg", "Beach day"),
        ("Copycat.jpg", "Copycat"),
        ("Copy.jpg", "Copy"),
        ("Mum's scanned photos 1985.tiff", "Mum's scanned photos 1985"),
        ("Noël à Lyon.jpg", "Noël à Lyon"),
        ("a:b?.jpg", "a_b_"),
    ],
)
def test_tidying_drops_the_extension_and_copy_markers_only(name: str, tidy: str) -> None:
    assert tidy_file_name(name) == tidy


@pytest.mark.parametrize(
    "name",
    [
        "10174880_903634589713690_321783628180766947_n.jpg",  # Facebook download
        "10174880_903634589713690_321783628180766947_o (Copy).jpg",
        "20150612.jpg",
        "1234 (2).jpg",
        "2015-06-12.jpg",
        ".jpg",
        "",
        "  .png",
        "(Copy).jpg",
    ],
)
def test_a_name_without_words_is_not_a_name(name: str) -> None:
    assert tidy_file_name(name) is None
