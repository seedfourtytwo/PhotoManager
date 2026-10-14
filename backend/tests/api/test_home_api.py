"""GET /api/home (issue 54): the signed-in account's Home, within what it may see."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from photo_assistant.domain.access import SourceAccess
from photo_assistant.domain.places import Place
from tests.api.conftest import BASE, add_user, services_of
from tests.factories import new_asset
from tests.fakes import FakeClock

NOW = datetime(2026, 10, 14, 12, tzinfo=UTC)


@pytest.fixture
def home(admin: TestClient, monkeypatch: pytest.MonkeyPatch) -> dict[str, list[int]]:
    """Home in Paris (12 photos in 2022), a trip to Lisbon in July 2024, three photos of
    14 October 2023 (one in a folder only admins see), and two that arrived this week."""
    services = services_of(admin)
    monkeypatch.setattr(services, "clock", FakeClock(NOW))
    repo = services.repo
    family = repo.add_source("Family", "/family").id
    secret = repo.add_source("Admins only", "/secret", access=SourceAccess(None)).id
    n = 0

    def photos(count: int, start: datetime, step: timedelta, source: int = family) -> list[int]:
        nonlocal n
        made = []
        for i in range(count):
            n += 1
            imported = NOW - timedelta(days=30)
            asset_id = repo.add_asset(new_asset(n, start + i * step), imported)
            repo.add_asset_source(asset_id, source, f"{n}.jpg")
            made.append(asset_id)
        return made

    at_home = photos(12, datetime(2022, 3, 1, 10), timedelta(days=2))
    repo.set_places([(i, Place("France", "Ile-de-France", "Paris")) for i in at_home])
    trip = photos(10, datetime(2024, 7, 3, 10), timedelta(hours=6))
    repo.set_places([(i, Place("Portugal", "Lisboa", "Lisbon")) for i in trip])
    that_day = photos(2, datetime(2023, 10, 14, 10), timedelta(hours=1))
    that_day += photos(1, datetime(2023, 10, 14, 9), timedelta(0), secret)
    new = photos(2, datetime(2026, 10, 12, 10), timedelta(hours=1))
    for days, asset_id in enumerate(new):
        imported = (NOW - timedelta(days=days)).isoformat()
        repo._write("UPDATE asset SET imported_at = ? WHERE id = ?", (imported, asset_id))
    return {"at_home": at_home, "trip": trip, "that_day": that_day, "new": new}


def test_home_answers_on_this_day_memories_and_what_is_new(
    admin: TestClient, home: dict[str, list[int]]
) -> None:
    body = admin.get("/api/home").json()
    secret_one = home["that_day"][2]
    assert body["on_this_day"] | {"cover": body["on_this_day"]["cover"]["id"]} == {
        "day": "2023-10-14",
        "years_ago": 3,
        "exact": True,
        "count": 3,
        "cover": secret_one,
        "place": None,
        "people": [],
        "filter": {"from": "2023-10-14", "to": "2023-10-14", "guessed_date": False},
    }
    (memory,) = body["memories"]
    assert memory | {"cover": memory["cover"]["id"]} == {
        "key": "2024-07-03_2024-07-05",
        "title": "Lisbon, July 2024",
        "from": "2024-07-03",
        "to": "2024-07-05",
        "count": 10,
        "cover": home["trip"][0],
        "filter": {"from": "2024-07-03", "to": "2024-07-05", "guessed_date": False},
    }
    new = body["new"]
    assert (new["count"], new["days"]) == (2, 7)
    assert new["sources"] == [{"id": 1, "label": "Family", "count": 2}]
    assert [a["id"] for a in new["items"]] == home["new"]
    assert set(new["items"][0]) >= {"id", "thumb", "favourite", "pinned", "taken_at"}


def test_home_answers_photos_to_rediscover_and_the_years(
    admin: TestClient, home: dict[str, list[int]]
) -> None:
    body = admin.get("/api/home").json()
    picks = [a["id"] for a in body["rediscover"]]
    # one from each month before the last 30 days: March 2022, October 2023, July 2024
    assert len(picks) == 3 and set(picks) <= set(home["at_home"] + home["trip"] + home["that_day"])
    assert set(body["rediscover"][0]) >= {"id", "thumb", "taken_at", "date_source", "place"}
    # 2024 (the trip, 10 photos) and 2022 (12 at home); 2023 and 2026 have too few
    assert [(y["title"], y["count"]) for y in body["years"]] == [("2024", 10), ("2022", 12)]
    year = body["years"][0]
    assert year | {"cover": year["cover"]["id"]} == {
        "key": "2024-01-01_2024-12-31",
        "title": "2024",
        "from": "2024-01-01",
        "to": "2024-12-31",
        "count": 10,
        "cover": year["cover"]["id"],
        "filter": {"from": "2024-01-01", "to": "2024-12-31", "guessed_date": False},
    }
    assert year["cover"]["id"] in home["trip"]


def test_the_filter_lists_exactly_the_photos_counted(
    admin: TestClient, home: dict[str, list[int]]
) -> None:
    body = admin.get("/api/home").json()
    for block in (body["on_this_day"], *body["memories"], *body["years"]):
        listed = admin.get("/api/assets", params=block["filter"]).json()["items"]
        assert len(listed) == block["count"]


def test_home_keeps_to_what_the_account_may_see(
    admin: TestClient, home: dict[str, list[int]]
) -> None:
    lea = add_user(admin, "lea")
    day = lea.get("/api/home").json()["on_this_day"]
    assert day["count"] == 2 and day["cover"]["id"] == home["that_day"][0]
    lea.post("/api/assets/state", json={"ids": home["trip"], "hidden": True})
    assert lea.get("/api/home").json()["memories"] == [], "hidden photos make no memory"
    assert len(admin.get("/api/home").json()["memories"]) == 1, "hiding is for lea alone"


def test_home_needs_a_session(admin: TestClient) -> None:
    assert TestClient(admin.app, base_url=BASE).get("/api/home").status_code == 401
