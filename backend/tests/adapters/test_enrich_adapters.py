"""The real geocoder (offline data) and perceptual hasher."""

from pathlib import Path

import pytest
from PIL import Image, ImageFilter

from photo_assistant.adapters.geocoder import OfflineGeocoder, country_name
from photo_assistant.adapters.phash import ImageHashPhash
from photo_assistant.domain.grouping import phash_distance
from photo_assistant.domain.places import Place
from tests.synthetic import write_photo

pytestmark = pytest.mark.integration


def test_known_places_offline() -> None:
    geocoder = OfflineGeocoder()
    paris, quimper, sea = geocoder.places_for([(48.8566, 2.3522), (47.996, -4.102), (45.0, -30.0)])
    assert paris == Place("France", "Ile-de-France", "Paris")
    assert quimper is not None and quimper.country == "France" and quimper.region == "Brittany"
    assert sea is None, "the middle of the Atlantic is nowhere"
    assert geocoder.places_for([]) == []


def test_country_names() -> None:
    assert country_name("GB") == "United Kingdom"
    assert country_name("TW") == "Taiwan"
    assert country_name("XX") == "XX"


def test_similar_images_have_close_hashes(tmp_path: Path) -> None:
    a = write_photo(tmp_path / "a.jpg", seed=1, size=(200, 150))
    with Image.open(a) as im:
        im.filter(ImageFilter.GaussianBlur(1)).resize((180, 135)).save(tmp_path / "b.png")
    write_photo(tmp_path / "c.jpg", seed=2, size=(200, 150))
    hasher = ImageHashPhash()
    ha, hb, hc = (hasher.phash(tmp_path / n) for n in ("a.jpg", "b.png", "c.jpg"))
    assert len(ha) == 16
    assert phash_distance(ha, hb) <= 6 < phash_distance(ha, hc)
