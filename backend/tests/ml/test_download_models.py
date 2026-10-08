"""scripts/download_models.py with a fake network (the real hosts are unreachable here)."""

import hashlib
import io
import json
import zipfile
from collections.abc import Sequence
from pathlib import Path
from typing import BinaryIO

import pytest
from scripts import download_models as dm


class FakeNet:
    def __init__(self, files: dict[str, bytes]) -> None:
        self.files = files
        self.fetched: list[str] = []

    def __call__(self, url: str) -> BinaryIO:
        self.fetched.append(url)
        if url not in self.files:
            raise OSError(f"404 {url}")
        return io.BytesIO(self.files[url])


def tree_entry(path: str, data: bytes, lfs: bool = True) -> dict[str, object]:
    entry: dict[str, object] = {"type": "file", "path": path, "size": len(data)}
    if lfs:
        entry["lfs"] = {"oid": hashlib.sha256(data).hexdigest(), "size": len(data)}
    return entry


def hf_net(name: str, files: dict[str, bytes], extra: Sequence[dict[str, object]] = ()) -> FakeNet:
    tree = [tree_entry(p, d, lfs=p.endswith(".onnx")) for p, d in files.items()]
    tree += [{"type": "directory", "path": "visual"}, *extra]
    urls = {f"{dm.HF}/immich-app/{name}/resolve/main/{p}": d for p, d in files.items()}
    urls[f"{dm.HF}/api/models/immich-app/{name}/tree/main?recursive=true"] = json.dumps(
        tree
    ).encode()
    return FakeNet(urls)


CLIP = {path: f"<{path}>".encode() for path in dm.CLIP_REQUIRED}


@pytest.mark.parametrize(
    ("path", "keep"),
    [
        ("config.json", True),
        ("visual/model.onnx", True),
        ("textual/tokenizer.json", True),
        ("textual/model.onnx_data", True),
        ("visual/armnn/model.armnn", False),
        ("visual/rknpu/rk3588/model.rknn", False),
        ("README.md", False),
        (".gitattributes", False),
    ],
)
def test_only_onnx_runtime_files_are_wanted(path: str, keep: bool) -> None:
    assert dm.wanted(path) is keep


def test_clip_is_downloaded_verified_and_skipped_next_time(tmp_path: Path) -> None:
    junk = tree_entry("visual/armnn/model.armnn", b"x")
    net = hf_net("ViT-B-32__openai", CLIP, [junk])
    folder = dm.fetch_clip("ViT-B-32__openai", tmp_path, net)
    assert (folder / "visual" / "model.onnx").read_bytes() == b"<visual/model.onnx>"
    assert not list(folder.rglob("*.armnn")) and not list(folder.rglob("*.partial"))
    before = len(net.fetched)
    dm.fetch_clip("ViT-B-32__openai", tmp_path, net)
    assert len(net.fetched) == before + 1  # only the listing


def test_corrupt_download_is_rejected(tmp_path: Path) -> None:
    net = hf_net("m", CLIP)
    net.files[f"{dm.HF}/immich-app/m/resolve/main/visual/model.onnx"] = b"<visual/model.onnX>"
    with pytest.raises(dm.DownloadError, match="SHA-256"):
        dm.fetch_clip("m", tmp_path, net)
    assert not (tmp_path / "clip/m/visual/model.onnx").exists()


def test_truncated_download_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(dm.DownloadError, match="bytes"):
        dm.download("u", tmp_path / "f", size=10, opener=FakeNet({"u": b"short"}))


def test_wrong_repo_name_says_what_is_missing(tmp_path: Path) -> None:
    net = hf_net("m", {"config.json": b"{}"})
    with pytest.raises(dm.DownloadError, match=r"visual/model\.onnx"):
        dm.fetch_clip("m", tmp_path, net)
    with pytest.raises(dm.DownloadError, match="cannot list"):
        dm.fetch_clip("other", tmp_path, net)


def test_network_failure_mid_download(tmp_path: Path) -> None:
    with pytest.raises(dm.DownloadError, match="re-run"):
        dm.download("missing", tmp_path / "f", opener=FakeNet({}))


def buffalo_zip(names: list[str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for name in names:
            zf.writestr(f"buffalo_l/{name}", b"w" * 64)
    return buffer.getvalue()


@pytest.fixture
def small_minimums(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dm, "BUFFALO_FILES", {"det_10g.onnx": 32, "w600k_r50.onnx": 32})


@pytest.mark.usefixtures("small_minimums")
def test_buffalo_extracts_only_the_two_networks(tmp_path: Path) -> None:
    names = ["det_10g.onnx", "w600k_r50.onnx", "genderage.onnx", "2d106det.onnx"]
    net = FakeNet({dm.BUFFALO_URL: buffalo_zip(names)})
    folder = dm.fetch_buffalo(tmp_path, net)
    assert sorted(p.name for p in folder.iterdir()) == ["det_10g.onnx", "w600k_r50.onnx"]
    assert not (tmp_path / "insightface" / "buffalo_l.zip").exists()
    dm.fetch_buffalo(tmp_path, net)
    assert len(net.fetched) == 1


@pytest.mark.usefixtures("small_minimums")
def test_buffalo_zip_problems(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    net = FakeNet({dm.BUFFALO_URL: buffalo_zip(["det_10g.onnx"])})
    with pytest.raises(dm.DownloadError, match="w600k_r50"):
        dm.fetch_buffalo(tmp_path, net)
    assert not (tmp_path / "insightface" / "buffalo_l").exists()  # nothing half-done
    net.files[dm.BUFFALO_URL] = b"not a zip"
    with pytest.raises(dm.DownloadError, match="valid zip"):
        dm.fetch_buffalo(tmp_path, net)
    monkeypatch.setattr(dm, "BUFFALO_FILES", {"det_10g.onnx": 10**6})
    net.files[dm.BUFFALO_URL] = buffalo_zip(["det_10g.onnx"])
    with pytest.raises(dm.DownloadError, match="small"):
        dm.fetch_buffalo(tmp_path, net)


def test_run_and_main(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    files = {base + name: b"m" for name, base in dm.YUNET_FILES.items()}
    net = hf_net("XLM", CLIP)
    net.files |= files
    args = dm.parse_args(["--models-dir", str(tmp_path), "--clip", "XLM", "--faces", "yunet_sface"])
    env = dm.run(args, net)
    assert env == ["PA_ML_CLIP_MODEL=XLM", "PA_ML_FACE_MODEL=yunet_sface",
                   f"PA_ML_MODELS_DIR={tmp_path}"]  # fmt: skip
    assert (tmp_path / "opencv" / "face_detection_yunet_2023mar.onnx").is_file()
    assert dm.run(dm.parse_args(["--data-root", str(tmp_path), "--clip", "none",
                                 "--faces", "none"]), net) == []  # fmt: skip
    monkeypatch.setattr(dm, "open_url", FakeNet({}))  # never the real network in tests
    assert dm.main(["--models-dir", str(tmp_path / "x"), "--faces", "none", "--clip", "nope?"]) == 1
    assert "error:" in capsys.readouterr().err
