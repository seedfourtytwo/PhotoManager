"""Places as one list (GET /api/places): each country and each city, its count, cover and centre."""

import pytest

from photo_assistant.domain.places import PlaceGroup, tally_places


def group(
    country: str,
    city: str,
    count: int,
    *,
    centre: tuple[float, float] | None = None,
    located: int | None = None,
    cover: tuple[int, str] | None = None,
) -> PlaceGroup:
    lat, lon = centre or (None, None)
    return PlaceGroup(
        country=country,
        city=city,
        count=count,
        located=count if located is None and centre else (located or 0),
        lat=lat,
        lon=lon,
        cover_id=cover[0] if cover else None,
        cover_taken=cover[1] if cover else None,
    )


def test_nothing_gives_nothing() -> None:
    assert tally_places([]) == []


def test_a_country_counts_its_cities_and_the_photos_with_no_city() -> None:
    found = tally_places(
        [
            group("France", "Paris", 3, centre=(48.8, 2.3), cover=(7, "2020-05-01T10:00:00")),
            group("France", "Lyon", 1, centre=(45.8, 4.8), cover=(9, "2021-01-01T10:00:00")),
            group("France", "", 2),
        ]
    )
    assert [(p.name, p.kind, p.country, p.count, p.cover_id) for p in found] == [
        ("France", "country", "France", 6, 9),
        ("Paris", "city", "France", 3, 7),
        ("Lyon", "city", "France", 1, 9),
    ]
    centres = [x for p in found for x in (p.lat, p.lon)]
    assert centres == pytest.approx([48.05, 2.925, 48.8, 2.3, 45.8, 4.8], abs=0.01)


def test_most_photos_first_then_by_name() -> None:
    found = tally_places([group("Spain", "Bilbao", 2), group("Italy", "Rome", 2)])
    assert [(p.name, p.kind) for p in found] == [
        ("Italy", "country"),
        ("Spain", "country"),
        ("Bilbao", "city"),
        ("Rome", "city"),
    ]


def test_the_cover_is_the_newest_photo_and_ties_go_to_the_higher_id() -> None:
    found = tally_places(
        [
            group("Japan", "Kyoto", 1, cover=(4, "2019-04-01T09:00:00")),
            group("Japan", "Osaka", 1, cover=(5, "2019-04-01T09:00:00")),
            group("Japan", "Nara", 1),  # none of its photos has a thumbnail yet
        ]
    )
    covers = {p.name: p.cover_id for p in found}
    assert covers == {"Japan": 5, "Kyoto": 4, "Osaka": 5, "Nara": None}


def test_a_place_with_no_located_photo_has_no_centre() -> None:
    [country, city] = tally_places([group("Peru", "Cusco", 4)])
    assert (country.lat, country.lon, city.lat, city.lon) == (None, None, None, None)


def test_the_centre_weighs_each_city_by_its_located_photos() -> None:
    [country, *_] = tally_places(
        [
            group("Chile", "Arica", 10, centre=(-18.0, -70.0), located=3),
            group("Chile", "Santiago", 1, centre=(-34.0, -70.0), located=1),
        ]
    )
    assert country.lat == pytest.approx(-22.0) and country.lon == pytest.approx(-70.0)


def test_the_centre_of_a_country_across_the_date_line_stays_on_it() -> None:
    [country, *_] = tally_places(
        [
            group("Fiji", "Labasa", 1, centre=(-16.4, 179.4)),
            group("Fiji", "Taveuni", 1, centre=(-16.8, -179.9)),
        ]
    )
    assert country.lon == pytest.approx(179.75, abs=0.01), "not 0, the other side of the world"
