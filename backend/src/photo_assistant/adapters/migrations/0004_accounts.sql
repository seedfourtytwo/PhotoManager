-- 0004: accounts and sessions (M2). Passwords are argon2id hashes; sessions store only a
-- SHA-256 of the cookie token, so a copy of the database cannot be used to log in.

CREATE TABLE user (
    id             INTEGER PRIMARY KEY,
    username       TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    display_name   TEXT    NOT NULL,
    password_hash  TEXT    NOT NULL,
    role           TEXT    NOT NULL CHECK (role IN ('admin', 'member', 'guest')),
    disabled       INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE session (
    token_hash    TEXT    PRIMARY KEY,
    user_id       INTEGER NOT NULL REFERENCES user(id),
    created_at    TEXT    NOT NULL,
    last_seen_at  TEXT    NOT NULL
);
CREATE INDEX session_by_user ON session (user_id);

CREATE TABLE login_failure (
    username  TEXT NOT NULL COLLATE NOCASE,
    ip        TEXT NOT NULL,
    at        TEXT NOT NULL
);
CREATE INDEX login_failure_by_key ON login_failure (username, ip, at);
