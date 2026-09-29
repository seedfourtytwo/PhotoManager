import pytest
from hypothesis import given
from hypothesis import strategies as st

from photo_assistant.domain.library_paths import (
    InvalidLibraryPathError,
    derived_relpath,
    ensure_relative,
    original_relpath,
)

HASH = "a" * 64


def test_original_path_is_sharded_by_year_and_month() -> None:
    assert str(original_relpath(HASH, 2019, 7, "JPG")) == f"originals/2019/07/{HASH}.jpg"


def test_extension_dot_is_optional() -> None:
    assert original_relpath(HASH, 2019, 7, ".heic").suffix == ".heic"


@pytest.mark.parametrize("bad_hash", ["", "A" * 64, "g" * 64, "a" * 63])
def test_rejects_anything_but_a_blake3_hex_digest(bad_hash: str) -> None:
    with pytest.raises(InvalidLibraryPathError):
        original_relpath(bad_hash, 2019, 7, "jpg")


@pytest.mark.parametrize(("year", "month"), [(2019, 0), (2019, 13), (1700, 1), (10000, 1)])
def test_rejects_impossible_dates(year: int, month: int) -> None:
    with pytest.raises(InvalidLibraryPathError):
        original_relpath(HASH, year, month, "jpg")


def test_rejects_extension_that_could_inject_a_path() -> None:
    with pytest.raises(InvalidLibraryPathError):
        original_relpath(HASH, 2019, 7, "jpg/../../etc")


@pytest.mark.parametrize("bad", ["/etc/passwd", "../outside.jpg", "originals/../../x", "", "  "])
def test_stored_paths_must_stay_inside_the_data_root(bad: str) -> None:
    with pytest.raises(InvalidLibraryPathError):
        ensure_relative(bad)


@given(
    year=st.integers(1800, 9999),
    month=st.integers(1, 12),
    digest=st.text("0123456789abcdef", min_size=64, max_size=64),
)
def test_every_generated_original_path_is_a_valid_stored_path(
    year: int, month: int, digest: str
) -> None:
    path = original_relpath(digest, year, month, "jpg")
    assert ensure_relative(str(path)) == path


def test_derivatives_are_sharded_by_hash_prefix() -> None:
    digest = "ab" + "c" * 62
    assert str(derived_relpath("thumb", digest)) == f"derived/thumb/ab/{digest}.webp"


@pytest.mark.parametrize(("kind", "digest"), [("poster", HASH), ("thumb", "xyz")])
def test_derivative_paths_reject_unknown_kinds_and_bad_hashes(kind: str, digest: str) -> None:
    with pytest.raises(InvalidLibraryPathError):
        derived_relpath(kind, digest)
