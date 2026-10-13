-- 0028: send to a device (spec 2026-10-13; asked for by C, off until PA_SEND_TO_DEVICE=true).
--
-- A hand-over: a fixed list of photos that one device may collect once, within minutes, with
-- a link instead of an account. Only the SHA-256 of the link's token is kept, as for sessions
-- and device tokens. The rows are also the trail an admin reads (who sent how many photos,
-- when, collected or not, from which address); the daily clean-up deletes them after 90 days.
-- Its state (waiting, redeemed, expired, cancelled) is worked out in domain/handover.py.
CREATE TABLE handover (
    id               INTEGER PRIMARY KEY,
    token_hash       TEXT    NOT NULL UNIQUE,
    created_by       INTEGER NOT NULL REFERENCES user(id) ON DELETE CASCADE,
    created_at       TEXT    NOT NULL,            -- UTC, like expires_at: compared as text
    expires_at       TEXT    NOT NULL,
    asset_ids        TEXT    NOT NULL,            -- JSON list of photo ids, in the order sent
    byte_size        INTEGER NOT NULL,            -- estimated size of the copies
    encrypted        INTEGER NOT NULL,            -- 1: the link is an https one
    details_removed  INTEGER NOT NULL,            -- 1: the copies carry no metadata
    max_redemptions  INTEGER NOT NULL DEFAULT 1 CHECK (max_redemptions >= 1),
    redemptions      INTEGER NOT NULL DEFAULT 0,
    redeemed_at      TEXT,
    redeemed_from    TEXT,                        -- the address that collected it
    redeemed_agent   TEXT,                        -- what its browser called itself
    cancelled_at     TEXT
);
CREATE INDEX handover_by_creator ON handover (created_by, id);
