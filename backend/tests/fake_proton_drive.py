"""A stand-in for Proton's ``proton-drive`` CLI, driven by a JSON file (tests only).

It answers the read commands the adapter uses, in the real tool's shapes (v0.9.0), and logs
every invocation so tests can prove nothing but reads was asked for.

State file (``PA_FAKE_PROTON``):
    {"signed_in": true,
     "photos": [{"uid", "name", "mediaType", "source"}],          # the Photos timeline
     "tree": {"/my-files": [{"type", "uid", "name", "mediaType"?, "source"?, "ok"?}]},
     "fail": ["uid", ...], "crash_on_batch": false}
"""

import json
import os
import shutil
import sys
from pathlib import Path

STATE = Path(os.environ["PA_FAKE_PROTON"])


def node(item: dict[str, object], kind: str) -> dict[str, object]:
    name = {"ok": True, "value": item["name"]} if item.get("ok", True) else {"ok": False}
    source = item.get("source")
    size = Path(str(source)).stat().st_size if source else 0
    return {
        "uid": item["uid"],
        "name": name,
        "type": kind,
        "mediaType": item.get("mediaType", "Folder"),
        "totalStorageSize": size,
    }


def unique(folder: Path, name: str) -> Path:
    target, n = folder / name, 1
    while target.exists():
        target = folder / f"{Path(name).stem} ({n}){Path(name).suffix}"
        n += 1
    return target


def download(state: dict[str, object], wanted: list[dict[str, object]], dest: Path) -> int:
    if state.get("crash_on_batch") and len(wanted) > 1:
        print("network error: connection reset", file=sys.stderr)
        return 1
    done = failed = size = 0
    failures = []
    for item in wanted:
        if item["uid"] in state.get("fail", []):
            failed += 1
            failures.append({"path": item["name"], "error": "download failed"})
            continue
        target = unique(dest, str(item["name"]))
        shutil.copyfile(str(item["source"]), target)
        done += 1
        size += target.stat().st_size
    summary = {"transferredItems": done, "transferredBytes": size, "skippedItems": 0}
    print(json.dumps(summary | {"failedItems": failed, "failures": failures}))
    return 0


def main(argv: list[str]) -> int:
    state = json.loads(STATE.read_text())
    with (STATE.parent / "calls.log").open("a") as log:
        log.write(json.dumps(argv) + "\n")
    if not state.get("signed_in", True):
        print("Failed to load session from keychain: no session, run auth login", file=sys.stderr)
        return 1
    args = [a for a in argv if a != "--json"]
    photos: list[dict[str, object]] = state.get("photos", [])
    tree: dict[str, list[dict[str, object]]] = state.get("tree", {})
    match args:
        case ["photo", "timeline", "-d"]:
            print(json.dumps([node(p, "photo") for p in photos]))
            return 0
        case ["filesystem", "list", path]:
            if path not in tree:
                print(f"Node not found: {path.rsplit('/', 1)[-1]}", file=sys.stderr)
                return 1
            print(json.dumps([node(n, str(n["type"])) for n in tree[path]]))
            return 0
        case ["photo", "download", "-c", "rename", *paths, dest]:
            by_uid = {f"/photos/{p['uid']}": p for p in photos}
            return download(state, [by_uid[p] for p in paths], Path(dest))
        case ["filesystem", "download", "-f", "rename", "-d", "merge", *paths, dest]:
            wanted = []
            for path in paths:
                folder, _, name = path.rpartition("/")
                wanted.append(next(n for n in tree[folder] if n["name"] == name))
            return download(state, wanted, Path(dest))
    print(f"fake proton-drive: unexpected command {argv}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
