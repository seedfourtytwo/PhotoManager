"""The name of a downloaded ZIP says what is in it (contract v1.3: Downloads)."""

from datetime import date

import pytest

from photo_assistant.domain.archive_name import (
    MAX_NAME_LENGTH,
    album_zip_name,
    ascii_fallback,
    filters_zip_name,
    ids_zip_name,
)
from photo_assistant.domain.library_filter import AssetFilter


def test_an_album_zip_is_named_after_the_album() -> None:
    assert album_zip_name("Summers at the house") == "Summers at the house.zip"
    assert album_zip_name("Été à Paris 🌊") == "Été à Paris 🌊.zip"


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("2019/2020", "2019_2020.zip"),
        ("a\\b", "a_b.zip"),
        ('say "cheese"', "say _cheese_.zip"),
        ("tab\there\nnewline", "tab_here_newline.zip"),
        ("  spaced   out  ", "spaced out.zip"),
        ("../../etc", "_.._etc.zip"),
        ("..", "album.zip"),
        ("", "album.zip"),
        ("\x00\x1f", "album.zip"),
    ],
)
def test_album_titles_are_made_safe(title: str, expected: str) -> None:
    assert album_zip_name(title) == expected


def test_long_names_are_cut_but_keep_the_extension() -> None:
    name = album_zip_name("x" * 500)
    assert len(name) == MAX_NAME_LENGTH and name.endswith("x.zip")
    words = filters_zip_name(AssetFilter(q="word " * 100))
    assert len(words) <= MAX_NAME_LENGTH and words.endswith(".zip") and "-.zip" not in words


@pytest.mark.parametrize(
    ("f", "expected"),
    [
        (AssetFilter(), "photos-all.zip"),
        (AssetFilter(year=2019, place="France"), "photos-2019-france.zip"),
        (AssetFilter(year=2019, month=7), "photos-2019-07.zip"),
        (AssetFilter(from_day=date(2019, 7, 4), to_day=date(2019, 7, 4)), "photos-2019-07-04.zip"),
        (
            AssetFilter(from_day=date(2019, 7, 1), to_day=date(2019, 8, 31)),
            "photos-2019-07-01-to-2019-08-31.zip",
        ),
        (AssetFilter(from_day=date(2019, 7, 1)), "photos-from-2019-07-01.zip"),
        (AssetFilter(to_day=date(2019, 7, 1)), "photos-to-2019-07-01.zip"),
        (AssetFilter(source_ids=(3,)), "photos-1-source.zip"),
        (AssetFilter(source_ids=(3, 4)), "photos-2-sources.zip"),
        (AssetFilter(person_ids=(5,)), "photos-1-person.zip"),
        (AssetFilter(person_ids=(5, 6, 7)), "photos-3-people.zip"),
        (AssetFilter(source_ids=(3,), person_ids=(5,)), "photos-1-source-1-person.zip"),
        (AssetFilter(camera="iPhone 12 Pro"), "photos-iphone-12-pro.zip"),
        (AssetFilter(q="Beach day!", place="Le Havre"), "photos-le-havre-beach-day.zip"),
        (AssetFilter(place="Île-de-France"), "photos-île-de-france.zip"),
        (AssetFilter(favourite=True, hidden=True), "photos-favourites-hidden.zip"),
        (AssetFilter(favourite=True, pinned=True), "photos-favourites-pinned.zip"),
        (AssetFilter(guessed_date=True), "photos-guessed-dates.zip"),
        (AssetFilter(has_location=True), "photos-with-location.zip"),
        (AssetFilter(has_location=False), "photos-without-location.zip"),
        (
            AssetFilter(favourite=False, pinned=False, hidden=False, guessed_date=False),
            "photos-all.zip",
        ),
        (AssetFilter(q="/../"), "photos-all.zip"),
    ],
)
def test_a_filtered_zip_is_named_after_its_filters(f: AssetFilter, expected: str) -> None:
    assert filters_zip_name(f) == expected


def test_a_selection_zip_is_named_after_its_size() -> None:
    assert ids_zip_name(12) == "photos-12.zip"
    assert ids_zip_name(1) == "photos-1.zip"


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Summers at the house.zip", "Summers at the house.zip"),
        ("Été à Paris.zip", "Ete a Paris.zip"),
        ("Beach 🌊.zip", "Beach _.zip"),
        ("東京.zip", "__.zip"),
        ("ﬁle.zip", "file.zip"),
    ],
)
def test_the_ascii_fallback_keeps_what_it_can(name: str, expected: str) -> None:
    assert ascii_fallback(name) == expected
