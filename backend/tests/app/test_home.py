"""Home for one viewer (issue 54): on this day with who is on it, memories, what is new."""

from datetime import UTC, date, datetime, timedelta

from photo_assistant.adapters.ml_store import SqliteMlStore
from photo_assistant.adapters.sqlite_database import Database
from photo_assistant.adapters.sqlite_repository import SqliteRepository
from photo_assistant.app.home import NEW_DAYS, home_page
from photo_assistant.app.people import People
from photo_assistant.domain.access import Role, Viewer
from photo_assistant.domain.faces import BoundingBox, Face
from tests.factories import new_asset

NOW = datetime(2026, 10, 14, 12, tzinfo=UTC)  # noon: the same date in every European zone


def test_home_puts_its_blocks_together_for_today(db: Database, repo: SqliteRepository) -> None:
    viewer = Viewer.of(repo.add_user("lea", "Lea", "h", Role.ADMIN))
    family = repo.add_source("Family", "/family").id
    long_ago = NOW - timedelta(days=400)

    def photo(n: int, taken: datetime, imported: datetime = long_ago) -> int:
        asset_id = repo.add_asset(new_asset(n, taken), imported)
        repo.add_asset_source(asset_id, family, f"{n}.jpg")
        return asset_id

    that_day = [photo(n, datetime(2023, 10, 14, 9 + n)) for n in range(1, 4)]
    # no place anywhere: all of it is home, and July 2024 is a month at home (20 photos)
    july = [
        photo(n, datetime(2024, 7, 1, 10) + (n - 10) * timedelta(days=1)) for n in range(10, 30)
    ]
    new = [photo(n, datetime(2026, 10, 1), NOW - timedelta(days=n - 40)) for n in range(40, 43)]
    repo.set_user_state(viewer.user_id, [that_day[1]], favourite=True)
    store = SqliteMlStore(db)
    vector = (1.0, 0.0, 0.0, 0.0)
    face_ids = [
        store.replace_faces(i, "f", [Face(BoundingBox(0, 0, 0.5, 0.5), 0.9, (), vector)])[0]
        for i in that_day
    ]
    sam, nameless, stranger = (store.create_person(f) for f in face_ids)
    store.rename_person(sam, "Sam")
    store.rename_person(stranger, "Stranger")
    store.set_person_hidden(stranger, True)

    page = home_page(repo, People(store), viewer, NOW)

    day = page.on_this_day
    assert day is not None and (day.day, day.years_ago, day.exact) == (date(2023, 10, 14), 3, True)
    assert day.cover_id == that_day[1], "the favourite"
    assert page.people == [(sam, "Sam")], "named and listed people only"
    assert [(m.title, m.count, m.cover_id) for m in page.memories] == [("July 2024", 20, july[0])]
    assert page.arrivals.count == 3 and page.arrivals.newest == new
    assert page.days == NEW_DAYS
    assert set(page.views) == {that_day[1], july[0], *new}
    assert nameless not in [p for p, _ in page.people]


def test_an_empty_library_has_an_empty_home(db: Database, repo: SqliteRepository) -> None:
    viewer = Viewer.of(repo.add_user("lea", "Lea", "h", Role.MEMBER))
    page = home_page(repo, People(SqliteMlStore(db)), viewer, NOW)
    assert (page.on_this_day, page.people, page.memories, page.views) == (None, [], [], {})
    assert page.arrivals.count == 0
