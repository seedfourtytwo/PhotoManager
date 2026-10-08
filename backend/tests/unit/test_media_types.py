import pytest

from photo_assistant.domain.media_types import (
    MediaKind,
    classify,
    edited_original_name,
    edited_original_stem,
    is_picture,
)


@pytest.mark.parametrize(
    "name",
    ["IMG_0001.JPG", "a.jpeg", "b.png", "IMG_0027(1).HEIC", "x.heif", "y.webp", "z.tif", "z.TIFF"],
)
def test_common_photo_formats_are_photos(name: str) -> None:
    assert classify(name) is MediaKind.PHOTO


@pytest.mark.parametrize(
    "name", ["DSC_1.NEF", "a.CR2", "a.cr3", "a.ARW", "a.dng", "a.RAF", "a.orf"]
)
def test_raw_formats_are_raw(name: str) -> None:
    assert classify(name) is MediaKind.RAW


@pytest.mark.parametrize("name", ["IMG_1.MOV", "clip.mp4", "a.m4v", "GOPR1.MP4", "a.avi", "a.mkv"])
def test_videos_are_recognised_so_they_can_be_reported(name: str) -> None:
    assert classify(name) is MediaKind.VIDEO


@pytest.mark.parametrize("name", ["IMG_0001.AAE", "a.xmp", "a.XMP", "Thumbs.db", ".DS_Store"])
def test_sidecars_and_system_files_are_ignored(name: str) -> None:
    assert classify(name) is MediaKind.IGNORED


@pytest.mark.parametrize("name", ["France.pdf", "notes.txt", "noextension", "archive.zip"])
def test_everything_else_is_unsupported(name: str) -> None:
    assert classify(name) is MediaKind.UNSUPPORTED


def test_hidden_macos_resource_forks_are_ignored() -> None:
    assert classify("._IMG_0001.JPG") is MediaKind.IGNORED


@pytest.mark.parametrize(
    ("name", "original"),
    [("IMG_E1234.JPG", "IMG_1234.JPG"), ("IMG_E0001.HEIC", "IMG_0001.HEIC")],
)
def test_iphone_edited_copies_point_to_their_original(name: str, original: str) -> None:
    assert edited_original_name(name) == original


@pytest.mark.parametrize("name", ["IMG_1234.JPG", "IMAGE_E1.JPG", "IMG_EXTRA.JPG"])
def test_non_edited_names_have_no_original(name: str) -> None:
    assert edited_original_name(name) is None


@pytest.mark.parametrize(
    ("name", "stem"),
    [
        ("IMG_E1234.JPG", "IMG_1234"),
        ("IMG_E0001.HEIC", "IMG_0001"),
        ("a/b/IMG_E0042.jpg", "IMG_0042"),
    ],
)
def test_an_edit_names_its_original_whatever_the_extension(name: str, stem: str) -> None:
    """The edit of IMG_1234.HEIC is IMG_E1234.JPG: only the stem is shared."""
    assert edited_original_stem(name) == stem


@pytest.mark.parametrize("name", ["IMG_1234.JPG", "IMAGE_E1.JPG", "IMG_EXTRA.JPG", "IMG_E1234"])
def test_non_edited_names_have_no_original_stem(name: str) -> None:
    assert edited_original_stem(name) is None


@pytest.mark.parametrize(
    ("name", "picture"),
    [
        ("IMG_1234.HEIC", True),
        ("IMG_1234.jpg", True),
        ("IMG_1234.DNG", True),
        ("IMG_1234.MOV", False),
        ("IMG_1234.AAE", False),
        ("IMG_1234.pdf", False),
    ],
)
def test_only_photos_and_raw_files_can_be_the_original_of_an_edit(name: str, picture: bool) -> None:
    assert is_picture(name) is picture
