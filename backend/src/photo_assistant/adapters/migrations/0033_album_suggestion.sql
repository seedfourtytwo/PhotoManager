-- 0033: suggested albums (FEATURES 5.6). Nothing is made until the account keeps a suggestion;
-- what it answered, Keep or Discard, is remembered so the suggestion does not come back.
--
-- key: the event's oldest photo in the library (domain/events.py `Event.key`), stable while
-- the event grows. album_id: the album Keep made, while it is still there.
CREATE TABLE album_suggestion_answer (
    user_id      INTEGER NOT NULL REFERENCES user(id) ON DELETE CASCADE,
    key          TEXT    NOT NULL,
    answer       TEXT    NOT NULL CHECK (answer IN ('kept', 'discarded')),
    album_id     INTEGER REFERENCES album(id) ON DELETE SET NULL,
    answered_at  TEXT    NOT NULL,
    PRIMARY KEY (user_id, key),
    CHECK (answer = 'kept' OR album_id IS NULL)
);
