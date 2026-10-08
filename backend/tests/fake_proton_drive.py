"""A stand-in for Proton's ``proton-drive`` CLI, driven by a JSON file (tests only).

It answers the commands the adapters use, in the real tool's shapes (v0.9.0), and logs every
invocation so tests can prove what was (and was not) asked for.

State file (``PA_FAKE_PROTON``):
    {"signed_in": true,
     "photos": [{"uid", "name", "mediaType", "source"}],          # the Photos timeline
     "tree": {"/my-files": [{"type", "uid", "name", "mediaType"?, "source"?, "ok"?}]},
     "fail": ["uid", ...], "crash_on_batch": false,
     "trash": {"uid": entry},                  # trashed, not yet deleted for good
     "fail_upload": ["file name", ...]}
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


def missing(path: str) -> int:
    print(f"Node not found: {path.rsplit('/', 1)[-1]}", file=sys.stderr)
    return 1


def tree_of(state: dict[str, object]) -> dict[str, list[dict[str, object]]]:
    tree: dict[str, list[dict[str, object]]] = state.setdefault("tree", {})  # type: ignore[assignment]
    return tree


def find(tree: dict[str, list[dict[str, object]]], path: str) -> dict[str, object] | None:
    folder, _, name = path.rpartition("/")
    return next((n for n in tree.get(folder, []) if n["name"] == name), None)


def upload(state: dict[str, object], local: Path, parent: str, tally: dict[str, int]) -> None:
    """``-f skip -d merge``: folders merge, a file whose name is there already is skipped."""
    # (measured on v0.9.0: an unchanged tree answers with its folders as transferred, 0 bytes)
    tree = tree_of(state)
    here = f"{parent}/{local.name}"
    existing = find(tree, here)
    if local.is_dir():
        if existing is None:
            tree[parent].append({"type": "folder", "uid": f"uid:{here}", "name": local.name})
            tree[here] = []
        tally["done"] += 1  # the real tool counts a merged folder as transferred too
        for child in sorted(local.iterdir()):
            upload(state, child, here, tally)
    elif existing is not None:
        tally["skipped"] += 1
    elif local.name in state.get("fail_upload", []):  # type: ignore[operator]
        tally["failed"] += 1
    else:
        blobs = STATE.parent / "uploaded"
        blobs.mkdir(exist_ok=True)
        copy = blobs / f"{len(list(blobs.iterdir()))}-{local.name}"
        shutil.copyfile(local, copy)
        tree[parent].append(
            {"type": "file", "uid": f"uid:{here}", "name": local.name, "source": str(copy)}
        )
        tally["done"] += 1
        tally["bytes"] += copy.stat().st_size


def do_upload(state: dict[str, object], locals_: list[str], parent: str) -> int:
    if parent not in tree_of(state):
        return missing(parent)
    tally = {"done": 0, "skipped": 0, "failed": 0, "bytes": 0}
    for local in locals_:
        upload(state, Path(local), parent, tally)
    summary = {
        "transferredItems": tally["done"],
        "transferredBytes": tally["bytes"],
        "skippedItems": tally["skipped"],
        "failedItems": tally["failed"],
        "failures": [{"error": "upload failed"}] * tally["failed"],
    }
    print(json.dumps(summary))
    return 0


def do_create(state: dict[str, object], parent: str, name: str) -> int:
    tree = tree_of(state)
    if parent not in tree:
        return missing(parent)
    if find(tree, f"{parent}/{name}") is not None:
        print("A file or folder with that name already exists", file=sys.stderr)
        return 1
    entry: dict[str, object] = {"type": "folder", "uid": f"uid:{parent}/{name}", "name": name}
    tree[parent].append(entry)
    tree[f"{parent}/{name}"] = []
    print(json.dumps(node(entry, "folder")))
    return 0


def do_info(state: dict[str, object], path: str) -> int:
    entry = find(tree_of(state), path)
    if entry is None:
        return missing(path)
    print(json.dumps(node(entry, str(entry["type"]))))
    return 0


def do_trash(state: dict[str, object], paths: list[str]) -> int:
    tree = tree_of(state)
    trash: dict[str, dict[str, object]] = state.setdefault("trash", {})  # type: ignore[assignment]
    for path in paths:
        entry = find(tree, path)
        if entry is None:
            return missing(path)
        tree[path.rpartition("/")[0]].remove(entry)
        for inside in [p for p in tree if p == path or p.startswith(path + "/")]:
            del tree[inside]
        trash[str(entry["uid"])] = entry
    print("[]")
    return 0


def do_delete(state: dict[str, object], paths: list[str]) -> int:
    trash: dict[str, dict[str, object]] = state.setdefault("trash", {})  # type: ignore[assignment]
    for path in paths:
        if trash.pop(path.removeprefix("/trash/"), None) is None:
            return missing(path)
    print("[]")
    return 0


def write(state: dict[str, object], args: list[str]) -> int | None:
    """The commands that change the Drive; None when ``args`` is not one of them."""
    match args:
        case ["filesystem", "upload", "-f", "skip", "-d", "merge", "-t", *locals_, parent]:
            code = do_upload(state, locals_, parent)
        case ["filesystem", "create-folder", parent, name]:
            code = do_create(state, parent, name)
        case ["filesystem", "info", path]:
            code = do_info(state, path)
        case ["filesystem", "trash", *paths]:
            code = do_trash(state, paths)
        case ["filesystem", "delete", *paths]:
            code = do_delete(state, paths)
        case _:
            return None
    STATE.write_text(json.dumps(state))
    return code


def read(state: dict[str, object], args: list[str]) -> int | None:
    """The commands that only look; None when ``args`` is not one of them."""
    photos: list[dict[str, object]] = state.get("photos", [])  # type: ignore[assignment]
    tree = tree_of(state)
    match args:
        case ["photo", "timeline", "-d"]:
            print(json.dumps([node(p, "photo") for p in photos]))
            return 0
        case ["filesystem", "list", path]:
            if path not in tree:
                return missing(path)
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
    return None


def main(argv: list[str]) -> int:
    state = json.loads(STATE.read_text())
    with (STATE.parent / "calls.log").open("a") as log:
        log.write(json.dumps(argv) + "\n")
    if not state.get("signed_in", True):
        print("Failed to load session from keychain: no session, run auth login", file=sys.stderr)
        return 1
    args = [a for a in argv if a != "--json"]
    for handle in (write, read):
        if (code := handle(state, args)) is not None:
            return code
    print(f"fake proton-drive: unexpected command {argv}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
