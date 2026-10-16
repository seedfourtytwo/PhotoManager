-- 0035: what the local AI made (FEATURES 7.3, 7.4).
--
-- asset_caption: what a vision model saw in a photo. A derived field like the auto tags, never
-- the user's own data; it feeds the album-naming prompt. A photo the model could not describe
-- is an ml_task row (task 'ai_caption') so it is not asked again for that model.
CREATE TABLE asset_caption (
    asset_id    INTEGER PRIMARY KEY REFERENCES asset(id) ON DELETE CASCADE,
    text        TEXT    NOT NULL,
    model       TEXT    NOT NULL,
    lang        TEXT    NOT NULL,
    created_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- album_suggestion_plan: the AI's proposal (title, sections, captions) for a suggested album
-- (0033), a proposal until the account keeps it. photos: the event's sorted asset ids it was
-- made for; a viewer whose photos of the event differ gets the plain title. A new plan for an
-- event replaces the older ones.
CREATE TABLE album_suggestion_plan (
    key         TEXT    NOT NULL,
    photos      TEXT    NOT NULL,
    model       TEXT    NOT NULL,
    plan_json   TEXT    NOT NULL,
    created_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY (key, photos)
);
