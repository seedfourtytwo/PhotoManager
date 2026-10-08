"""Deleting a photo checks ``clip_embedding`` for rows pointing at it. Its primary key starts
with the model, so without planner statistics for the table (a library analysed before its
first embedding existed) SQLite scanned it, vectors and all. Migration 0025 gives the check an
index on ``asset_id``."""

from photo_assistant.adapters.sqlite_repository import SqliteRepository, open_database


def test_the_delete_check_of_embeddings_uses_its_index_without_planner_statistics() -> None:
    repo = SqliteRepository(open_database(":memory:"))
    conn = repo._conn
    stats = conn.execute("SELECT COUNT(*) FROM sqlite_stat1 WHERE tbl = 'clip_embedding'")
    assert stats.fetchone()[0] == 0, "the case that scanned: no statistics for the table"

    rows = conn.execute("EXPLAIN QUERY PLAN DELETE FROM asset WHERE id = ?", (1,))
    plan = [str(row["detail"]) for row in rows]

    embeddings = [step for step in plan if step.split()[1] == "clip_embedding"]
    assert embeddings == [
        "SEARCH clip_embedding USING COVERING INDEX clip_embedding_by_asset (asset_id=?)"
    ], plan
