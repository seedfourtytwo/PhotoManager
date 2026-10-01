"""Download the local ML models into <data_root>/models/ — run this ON THE LAPTOP.

    just models                                   # default CLIP + buffalo_l faces
    just models --clip XLM-Roberta-Large-Vit-B-32 # multilingual (French + English) search
    just models --faces yunet_sface               # Apache-2.0 fallback face models
    just models --data-root ~/PhotoAssistant/data --faces none

CLIP comes from Hugging Face ``immich-app/<name>`` (only the ONNX files, configs and tokenizer;
the ARM/RKNN variants are skipped). Each LFS file is checked against the size and SHA-256 the
Hub publishes. buffalo_l comes from the InsightFace GitHub release; its weights are for
**non-commercial research use only** — fine for a private family library, never redistribute
them. Only the two networks we use are extracted. Downloads are resumable by re-running:
finished files are skipped, partial ones are written to ``*.partial`` and renamed when done.
"""

import argparse
import hashlib
import json
import shutil
import sys
import urllib.request
import zipfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

HF = "https://huggingface.co"
BUFFALO_URL = "https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip"
BUFFALO_FILES = {"det_10g.onnx": 10_000_000, "w600k_r50.onnx": 100_000_000}  # minimum sizes
OPENCV_ZOO = "https://github.com/opencv/opencv_zoo/raw/main/models"
YUNET_FILES = {
    "face_detection_yunet_2023mar.onnx": f"{OPENCV_ZOO}/face_detection_yunet/",
    "face_recognition_sface_2021dec.onnx": f"{OPENCV_ZOO}/face_recognition_sface/",
}
CLIP_REQUIRED = (
    "config.json",
    "visual/model.onnx",
    "visual/preprocess_cfg.json",
    "textual/model.onnx",
    "textual/tokenizer.json",
)
KEEP_SUFFIXES = (".onnx", ".json", ".txt", ".model", ".onnx_data", ".data", ".bin")
SKIP_PARTS = {"armnn", "rknpu", "rknn"}
CHUNK = 1 << 20

Opener = Callable[[str], BinaryIO]


class DownloadError(RuntimeError):
    pass


@dataclass(frozen=True)
class RemoteFile:
    path: str
    size: int | None
    sha256: str | None


def open_url(url: str) -> BinaryIO:
    request = urllib.request.Request(url, headers={"User-Agent": "photo-assistant-models"})
    response: BinaryIO = urllib.request.urlopen(request, timeout=60)  # fixed https hosts only
    return response


def wanted(path: str) -> bool:
    parts = path.split("/")
    if path == "config.json":
        return True
    if parts[0] not in ("visual", "textual") or SKIP_PARTS & set(parts):
        return False
    return path.endswith(KEEP_SUFFIXES)


def clip_files(name: str, opener: Opener = open_url) -> list[RemoteFile]:
    """The files of immich-app/<name> we need, with their published sizes and hashes."""
    url = f"{HF}/api/models/immich-app/{name}/tree/main?recursive=true"
    try:
        with opener(url) as response:
            entries = json.load(response)
    except OSError as exc:
        raise DownloadError(f"cannot list immich-app/{name} on Hugging Face: {exc}") from exc
    files = [
        RemoteFile(e["path"], e.get("size"), (e.get("lfs") or {}).get("oid"))
        for e in entries
        if e.get("type") == "file" and wanted(e["path"])
    ]
    missing = set(CLIP_REQUIRED) - {f.path for f in files}
    if missing:
        raise DownloadError(
            f"immich-app/{name} lacks {sorted(missing)}: is the name right? See docs/wiring/ml.md"
        )
    return files


def _chunks(stream: BinaryIO) -> Iterator[bytes]:
    while chunk := stream.read(CHUNK):
        yield chunk


def is_complete(dest: Path, size: int | None) -> bool:
    return dest.is_file() and (size is None or dest.stat().st_size == size)


def download(
    url: str, dest: Path, *, size: int | None = None, sha256: str | None = None,
    opener: Opener = open_url,
) -> bool:  # fmt: skip
    """Fetch ``url`` to ``dest`` atomically. Returns False when it was already there."""
    if is_complete(dest, size) and sha256 is None:
        return False
    if is_complete(dest, size) and sha256 == file_sha256(dest):
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_name(dest.name + ".partial")
    digest, written = hashlib.sha256(), 0
    try:
        with opener(url) as response, partial.open("wb") as out:
            for chunk in _chunks(response):
                out.write(chunk)
                digest.update(chunk)
                written += len(chunk)
    except OSError as exc:
        raise DownloadError(f"download of {url} failed: {exc} (re-run to retry)") from exc
    if size is not None and written != size:
        partial.unlink()
        raise DownloadError(f"{dest.name}: got {written} bytes, expected {size}")
    if sha256 is not None and digest.hexdigest() != sha256:
        partial.unlink()
        raise DownloadError(f"{dest.name}: SHA-256 mismatch (corrupt download?)")
    partial.replace(dest)
    return True


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in _chunks(handle):
            digest.update(chunk)
    return digest.hexdigest()


def fetch_clip(name: str, models: Path, opener: Opener = open_url) -> Path:
    folder = models / "clip" / name
    for remote in clip_files(name, opener):
        url = f"{HF}/immich-app/{name}/resolve/main/{remote.path}"
        fresh = download(
            url, folder / remote.path, size=remote.size, sha256=remote.sha256, opener=opener
        )
        print(f"  {'downloaded' if fresh else 'present   '}  clip/{name}/{remote.path}")
    return folder


def fetch_buffalo(models: Path, opener: Opener = open_url) -> Path:
    folder = models / "insightface" / "buffalo_l"
    if all(_big_enough(folder / f, minimum) for f, minimum in BUFFALO_FILES.items()):
        print("  present     insightface/buffalo_l")
        return folder
    archive = models / "insightface" / "buffalo_l.zip"
    download(BUFFALO_URL, archive, opener=opener)
    extract_buffalo(archive, folder)
    archive.unlink()
    print("  downloaded  insightface/buffalo_l (det_10g.onnx, w600k_r50.onnx)")
    return folder


def _big_enough(path: Path, minimum: int) -> bool:
    return path.is_file() and path.stat().st_size >= minimum


def _extract_members(archive: Path, staging: Path) -> None:
    with zipfile.ZipFile(archive) as zf:
        members = {Path(n).name: n for n in zf.namelist() if not n.endswith("/")}
        for name, minimum in BUFFALO_FILES.items():
            if name not in members:
                raise DownloadError(f"{archive.name} has no {name}: not the buffalo_l pack?")
            with zf.open(members[name]) as src, (staging / name).open("wb") as dst:
                shutil.copyfileobj(src, dst, CHUNK)
            if not _big_enough(staging / name, minimum):
                raise DownloadError(f"{name} is suspiciously small: not the real model?")


def extract_buffalo(archive: Path, folder: Path) -> None:
    """Take only the detector and the recogniser, wherever the zip keeps them; all or nothing."""
    staging = folder.with_name(folder.name + ".partial")
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    try:
        _extract_members(archive, staging)
    except (zipfile.BadZipFile, DownloadError) as exc:
        shutil.rmtree(staging, ignore_errors=True)
        archive.unlink()  # a bad archive must be fetched again
        if isinstance(exc, DownloadError):
            raise
        raise DownloadError(f"{archive.name} is not a valid zip (re-run to retry)") from exc
    shutil.rmtree(folder, ignore_errors=True)
    staging.replace(folder)


def fetch_yunet(models: Path, opener: Opener = open_url) -> Path:
    folder = models / "opencv"
    for name, base in YUNET_FILES.items():
        fresh = download(base + name, folder / name, opener=opener)
        print(f"  {'downloaded' if fresh else 'present   '}  opencv/{name}")
    return folder


def default_data_root() -> Path:
    from photo_assistant.api.settings import Settings

    return Settings().data_root


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--data-root", type=Path, default=None)
    parser.add_argument("--models-dir", type=Path, default=None, help="default: <data-root>/models")
    parser.add_argument("--clip", default="ViT-B-32__openai", help="immich-app repo name or none")
    parser.add_argument(
        "--faces", choices=["buffalo_l", "yunet_sface", "none"], default="buffalo_l"
    )
    return parser.parse_args(argv)


def run(args: argparse.Namespace, opener: Opener = open_url) -> list[str]:
    models = (args.models_dir or (args.data_root or default_data_root()) / "models").expanduser()
    print(f"Models folder: {models}")
    env: list[str] = []
    if args.clip != "none":
        fetch_clip(args.clip, models, opener)
        env.append(f"PA_ML_CLIP_MODEL={args.clip}")
    if args.faces == "buffalo_l":
        fetch_buffalo(models, opener)
    elif args.faces == "yunet_sface":
        fetch_yunet(models, opener)
    if args.faces != "none":
        env.append(f"PA_ML_FACE_MODEL={args.faces}")
    if args.models_dir:
        env.append(f"PA_ML_MODELS_DIR={models}")
    return env


def main(argv: list[str] | None = None) -> int:
    try:
        env = run(parse_args(sys.argv[1:] if argv is None else argv), open_url)
    except DownloadError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print("\nDone. Next steps:")
    print("  1. Put these in backend/.env (only needed if they differ from the defaults):")
    for line in env:
        print(f"       {line}")
    print("  2. GPU (optional): uv pip uninstall onnxruntime && uv pip install onnxruntime-gpu")
    print("  3. Restart the app; then POST /api/ml/backfill (or the Settings page) to analyse")
    print("     photos imported before the models were here.")
    print("  4. Check: PA_MODELS_DIR=<models folder> uv run pytest -m models")
    return 0


if __name__ == "__main__":
    sys.exit(main())
