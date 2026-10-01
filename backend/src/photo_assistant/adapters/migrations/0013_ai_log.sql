-- 0013: what every AI call asked
-- and answered, summarised. Never image bytes; prompts and answers truncated by the adapter.
CREATE TABLE ai_log (
    id             INTEGER PRIMARY KEY,
    capability     TEXT    NOT NULL,
    model          TEXT    NOT NULL,
    attempt        INTEGER NOT NULL DEFAULT 1,
    ok             INTEGER NOT NULL,
    duration_ms    INTEGER NOT NULL,
    error          TEXT,
    request_json   TEXT    NOT NULL,
    response_json  TEXT    NOT NULL,
    created_at     TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX ai_log_recent ON ai_log (id DESC);
