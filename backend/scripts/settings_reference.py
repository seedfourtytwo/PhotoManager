"""Write docs/guides/settings.md: every ``PA_*`` variable ``Settings`` reads, with its default.

Run in backend/:  ``uv run python scripts/settings_reference.py``  (``--check``: only compare).

Names and defaults come from ``Settings.model_fields`` and its sections; the one-line meanings
are ``MEANINGS`` below. A setting without a meaning, or a meaning for a setting that is gone,
stops the script, and ``tests/api/test_settings_reference.py`` fails while the committed file
differs from what this writes.
"""

import sys
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel
from pydantic.fields import FieldInfo

from photo_assistant.api.settings import _FACE_DEFAULTS, _SECTIONS, Settings

TARGET = Path(__file__).resolve().parents[2] / "docs" / "guides" / "settings.md"

AREAS = {"": "General", "integrations": "Uploads, sources, AI", "ml": "Local ML", "ops": "Backups"}

_SCORES = ", ".join(f"{score} for {model}" for model, (score, _) in _FACE_DEFAULTS.items())
_DISTANCES = ", ".join(f"{dist} for {model}" for model, (_, dist) in _FACE_DEFAULTS.items())

MEANINGS = {
    # general
    "PA_DATA_ROOT": "The library folder: database, originals, thumbnails, logs. The only "
    "machine-specific path.",
    "PA_HOST": "Address the server listens on. Keep it on 127.0.0.1 and let Tailscale forward "
    "to it (remote-access.md).",
    "PA_PORT": "Port the server listens on.",
    "PA_MIN_FREE_GB": "An import pauses instead of leaving less than this free on the library "
    "disk; `just doctor` warns near it.",
    "PA_THUMB_EDGE": "Longest edge of a thumbnail, in pixels.",
    "PA_PREVIEW_EDGE": "Longest edge of a preview (the big view), in pixels.",
    "PA_WORKER_ENABLED": "`false` starts the server without its background work: no job worker "
    "(previews, imports, ML, backups) and no periodic tasks.",
    "PA_WORKER_POLL_SECONDS": "How often an idle job worker looks for a new job.",
    "PA_VIPS_CONCURRENCY": "Threads libvips may use to render one image.",
    "PA_PREVIEW_WORKERS": "Previews rendered at the same time; `0` means two fewer than the "
    "processor's cores, at least 1.",
    "PA_LOG_LEVEL": "How much is logged: `DEBUG`, `INFO`, `WARNING` or `ERROR`.",
    "PA_ALLOWED_HOSTS": "Host names the server answers to; any other name is refused. Add the "
    "Tailscale name here (remote-access.md).",
    "PA_TRUSTED_PROXIES": "Addresses or networks of the https proxy in front of the server, "
    "comma-separated. Only these may say a request arrived over https and from which device. "
    "In Docker: the Docker networks (server.env.example).",
    "PA_WEB_DIR": "Folder with the built web app, served at `/`. `just run`, the systemd unit "
    "and the Docker image set it; not set = API only.",
    "PA_TRASH_PURGE_EVERY_HOURS": "How often the server deletes photos that have been in the "
    "trash for 30 days.",
    "PA_SOURCE_RECHECK_POLL_SECONDS": "How often the server looks for folders whose automatic "
    "re-check is due.",
    "PA_ARGON2_TIME_COST": "Work factor of the PIN hash. Tests lower it; never lower it in use.",
    "PA_ARGON2_MEMORY_KIB": "Memory used by one PIN hash, in KiB. Tests lower it; never lower "
    "it in use.",
    "PA_FACE_CLUSTER_EVERY_HOURS": "How often faces are regrouped into people.",
    "PA_TEST_MODE": "End-to-end tests only: adds `POST /__test/reset`, which wipes the library. "
    "Refused unless host and allowed hosts are loopback. Never set it on a real library.",
    # uploads, sources, AI
    "PA_UPLOAD_MAX_MB": "Largest single uploaded file, in MB; the upload is cut off as soon as "
    "it passes.",
    "PA_UPLOAD_MAX_FILES": "Most files in one upload request.",
    "PA_RCLONE_BINARY": "The rclone program (name on the PATH, or a full path).",
    "PA_RCLONE_CONFIG": "rclone's config file, where the cloud sign-ins live; not set = "
    "rclone's own default, `~/.config/rclone/rclone.conf`.",
    "PA_RCLONE_TPSLIMIT": "Most requests per second to a cloud source (MEGA blocks accounts "
    "that hammer it); `0` = no limit.",
    "PA_RCLONE_TRANSFERS": "Files rclone downloads at the same time.",
    "PA_RCLONE_CHECKERS": "Files rclone compares at the same time.",
    "PA_RCLONE_TIMEOUT_HOURS": "A pull from a cloud source is stopped after this long; the next "
    "run continues.",
    "PA_PROTON_DRIVE_BINARY": "Proton's own `proton-drive` program (also looked for in "
    "`~/.local/bin`).",
    "PA_AI_PROVIDER": "`none`, or `ollama` to switch the optional AI features on.",
    "PA_OLLAMA_BASE_URL": "Where Ollama runs: the only address AI requests are sent to.",
    "PA_OLLAMA_CAPTION_MODEL": "Ollama model that describes photos; not set = no captions.",
    "PA_OLLAMA_PLAN_MODEL": "Ollama model that proposes albums; not set = no album proposals.",
    "PA_OLLAMA_TIMEOUT_SECONDS": "How long to wait for one Ollama answer.",
    # local ML
    "PA_ML_ENABLED": "`false`: no photo is queued for search, faces or tags.",
    "PA_ML_MODELS_DIR": "Folder with the model files (`just models` fills it); not set = "
    "`<data root>/models`.",
    "PA_ML_PROVIDER": "Where models run: `auto` (graphics card if this onnxruntime supports "
    "it, else processor), `cpu`, or `cuda` (an error if it is missing).",
    "PA_ML_CLIP_MODEL": "The search model, by its Immich name on Hugging Face. "
    "`XLM-Roberta-Large-Vit-B-32` understands French and English queries.",
    "PA_ML_CLIP_BATCH_SIZE": "Photos handed to the search model at once (1 to 256).",
    "PA_ML_FACE_MODEL": "Face model: `buffalo_l` (more accurate, non-commercial licence) or "
    "`yunet_sface`.",
    "PA_ML_FACE_DET_SIZE": "Image size the face detector works at, in pixels (160 to 1920).",
    "PA_ML_FACE_MIN_SCORE": "How sure the detector must be that something is a face (0 to 1); "
    f"not set = {_SCORES}.",
    "PA_ML_FACE_MAX_DISTANCE": "How different two faces may be and still count as one person; "
    f"not set = {_DISTANCES}.",
    "PA_ML_FACE_MIN_FACES": "Faces needed before a new person is suggested.",
    "PA_ML_TAG_MARGIN": "How clearly a tag must beat the neutral baseline: higher = fewer, "
    "surer tags.",
    "PA_ML_TAG_MAX_TAGS": "Most automatic tags per photo.",
    "PA_ML_SEARCH_MIN_SCORE": "Search hits scoring below this are dropped; not set = keep all.",
    # backups
    "PA_BACKUP_ENABLED": "`false` stops scheduled backups from running inside the server "
    "(`just backup run` still works).",
    "PA_BACKUP_POLL_SECONDS": "How often the server checks whether a backup is due.",
    "PA_BACKUP_RESTORE_SAMPLE": "Photos restored and compared in one restore test.",
    "PA_BACKUP_SCRATCH_DIR": "Where a restore test unpacks its sample; not set = the system "
    "temp folder. Must be outside the library.",
    "PA_BACKUP_KEY_DIR": "Where the app keeps the backup encryption keys it makes; not set = "
    "`~/.config/photo-assistant/backup-keys`. Must be outside the library.",
    "PA_RESTIC_BINARY": "The restic program (name on the PATH, or a full path).",
    "PA_RESTIC_CACHE_DIR": "restic's cache folder; not set = restic's own default, "
    "`~/.cache/restic`.",
}

HEADER = """# Settings

<!-- Generated by backend/scripts/settings_reference.py from api/settings.py. Do not edit:
     change the script (or the setting) and run it again. A test fails when this is stale. -->

Every setting is an environment variable starting with `PA_`. Put them in `.env` at the top
of the repository (laptop, `just run`, the systemd service) or in `deploy/server.env` (Docker).
A variable given to the process directly wins over the file. There is no other settings file.
Leave a setting out to get its default; restart the app after a change.

Write lists (`PA_ALLOWED_HOSTS`) comma-separated, without quotes, brackets or spaces.

| Area | Variable | Default | What it does |
|---|---|---|---|
"""

# (variables, read by, what it does): PA_ names that are not app settings
OTHERS = [
    (
        "`PA_HOST_DATA_ROOT`, `PA_HOST_CONFIG`, `PA_HOST_SECRETS`, `PA_HOST_BACKUP_DISK`",
        "`deploy/compose.yml`",
        "Folders on the server that Docker mounts into the container (move-to-server.md).",
    ),
    (
        "`PA_API`",
        "the web dev server (`web/vite.config.ts`)",
        "Which API `pnpm dev` talks to; default `http://127.0.0.1:8420`.",
    ),
    (
        "`PA_REQUIRE_TOOLS`",
        "the backend tests",
        "`1` makes a test that would be skipped for a missing tool (exiftool, vips, restic, "
        "rclone) fail instead. Set in the CI file.",
    ),
    (
        "`PA_MODELS_DIR`",
        "the backend tests",
        "Folder with the real model files, for `pytest -m models`.",
    ),
    ("`PA_UPDATE_GOLDENS`", "the print tests", "`1` rewrites the reference page images."),
]

FOOTER = """
## Other `PA_` names you may meet

These are not read by the app's settings.

| Variable | Read by | What it does |
|---|---|---|
"""


@dataclass(frozen=True, slots=True)
class Row:
    area: str
    name: str
    default: str
    meaning: str


def _fields() -> Iterator[tuple[str, str, FieldInfo]]:
    """(area, variable name, field) for the top level, then each section."""
    for name, field in Settings.model_fields.items():
        if name not in _SECTIONS:
            yield AREAS[""], f"PA_{name}".upper(), field
    for section, (model, prefix) in _SECTIONS.items():
        for name, field in model.model_fields.items():
            yield AREAS[section], f"{prefix}{name}".upper(), field


def _default(field: FieldInfo) -> str:
    value = field.get_default(call_default_factory=True)
    if value is None:
        return "not set"
    if isinstance(value, bool):
        return f"`{str(value).lower()}`"
    if isinstance(value, Path):
        home = str(Path.home())
        text = str(value)
        return f"`{'~' + text.removeprefix(home) if text.startswith(home) else text}`"
    if isinstance(value, list):
        return f"`{','.join(str(item) for item in value)}`"
    if isinstance(value, float) and value.is_integer():
        return f"`{int(value)}`"
    assert not isinstance(value, BaseModel), "sections are expanded, never printed"
    return f"`{value}`"


def rows() -> list[Row]:
    found = [
        Row(area, name, _default(field), MEANINGS.get(name, "")) for area, name, field in _fields()
    ]
    names = {row.name for row in found}
    if missing := sorted(names - MEANINGS.keys()):
        raise SystemExit(f"no meaning in MEANINGS for: {', '.join(missing)}")
    if stale := sorted(MEANINGS.keys() - names):
        raise SystemExit(f"MEANINGS describes settings that no longer exist: {', '.join(stale)}")
    return found


def render() -> str:
    lines = [f"| {r.area} | `{r.name}` | {r.default} | {r.meaning} |" for r in rows()]
    others = [f"| {' | '.join(other)} |" for other in OTHERS]
    return HEADER + "\n".join(lines) + "\n" + FOOTER + "\n".join(others) + "\n"


def main(argv: Sequence[str]) -> int:
    text = render()
    if "--check" in argv:
        current = TARGET.read_text(encoding="utf-8") if TARGET.exists() else ""
        if current != text:
            print(f"{TARGET} is out of date: run scripts/settings_reference.py", file=sys.stderr)
            return 1
        return 0
    TARGET.write_text(text, encoding="utf-8")
    print(f"wrote {len(rows())} settings to {TARGET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
