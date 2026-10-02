"""File names and folders inside a download (FEATURES 4b.6), and size estimates."""

from datetime import datetime

import pytest

from photo_assistant.domain.export_naming import (
    ExportOptions,
    Folders,
    Naming,
    OptionsError,
    estimate_bytes,
    export_extension,
    export_stem,
    folder_for,
    unique_names,
)

JULY = datetime(2019, 7, 4, 18, 30, 5)


def test_original_names_are_kept_but_made_safe() -> None:
    assert export_stem("IMG_1234.HEIC", JULY, Naming.ORIGINAL) == "IMG_1234"
    assert export_stem("a/b\\c:d?.jpg", JULY, Naming.ORIGINAL) == "a_b_c_d_"
    assert export_stem("\x01bad.jpg", JULY, Naming.ORIGINAL) == "_bad"
    assert export_stem(".jpg", JULY, Naming.ORIGINAL) == "photo"


def test_date_names_carry_the_place_when_known() -> None:
    assert export_stem("x.jpg", JULY, Naming.DATE) == "2019-07-04_183005"
    assert export_stem("x.jpg", JULY, Naming.DATE, "Saint-Malo") == "2019-07-04_183005_Saint-Malo"
    assert export_stem("x.jpg", JULY, Naming.DATE, "São Paulo") == "2019-07-04_183005_São-Paulo"


@pytest.mark.parametrize(
    ("folders", "expected"),
    [(Folders.FLAT, ""), (Folders.YEAR, "2019/"), (Folders.MONTH, "2019/07/")],
)
def test_folders(folders: Folders, expected: str) -> None:
    assert folder_for(JULY, folders) == expected


def test_extensions_follow_the_format() -> None:
    assert export_extension("original", "IMG_1.HEIC") == ".HEIC"
    assert export_extension("original", "noext") == ""
    assert export_extension("jpeg", "IMG_1.HEIC") == ".jpg"
    assert export_extension("png", "x.jpg") == ".png"
    assert export_extension("webp", "x.jpg") == ".webp"


def test_names_never_collide() -> None:
    names = ["2019/a.jpg", "2019/a.jpg", "2019/A.JPG", "2019/a_2.jpg", "b"]
    assert unique_names(names) == [
        "2019/a.jpg",
        "2019/a_2.jpg",
        "2019/A_3.JPG",
        "2019/a_2_2.jpg",
        "b",
    ]


def test_options_are_checked() -> None:
    ExportOptions()  # defaults are fine
    with pytest.raises(OptionsError, match="format"):
        ExportOptions(format="gif")
    with pytest.raises(OptionsError, match="quality"):
        ExportOptions(quality=0)
    with pytest.raises(OptionsError, match="max_edge"):
        ExportOptions(max_edge=0)


def test_original_untouched_only_without_changes() -> None:
    assert ExportOptions().untouched
    assert ExportOptions(strip_location=True).untouched, "stripping works on a copy, no render"
    assert not ExportOptions(max_edge=1000).untouched
    assert not ExportOptions(format="jpeg").untouched


def test_estimates_start_from_the_real_bytes() -> None:
    size = (4000, 3000)

    def est(fmt: str, out: str | None = None, mime: str = "image/jpeg", **kw: object) -> int:
        return estimate_bytes(
            5_000_000, mime, size, size, out or fmt, ExportOptions(format=fmt, **kw)
        )  # type: ignore[arg-type]

    assert est("original") == 5_000_000, "sent untouched"
    jpeg = est("jpeg")
    assert 4_000_000 < jpeg < 5_500_000, "re-encoding a JPEG at q90 keeps about its size"
    assert 0 < est("jpeg", max_edge=1000) < jpeg
    assert est("original", out="jpeg", max_edge=1000) == est("jpeg", max_edge=1000)
    assert est("webp") < jpeg < est("png")
    assert est("jpeg", quality=50) < jpeg < est("jpeg", quality=100)
    assert est("jpeg", mime="image/heic") > jpeg, "HEIC holds the same picture in fewer bytes"
    assert (
        estimate_bytes(100, "image/jpeg", None, None, "jpeg", ExportOptions(format="jpeg")) == 100
    )
