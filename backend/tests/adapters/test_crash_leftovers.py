"""What a crash leaves half-written is never taken for library content, and is cleared at the
next server start."""

import os
import time
from pathlib import Path

import pytest
import pyvips  # type: ignore[import-untyped]

from photo_assistant.adapters import vips_renderer
from photo_assistant.adapters.filesystem import DiskLibraryStore
from photo_assistant.adapters.library_files import LocalFileTree
from photo_assistant.ports import RenderSpec

HOURS = 3600


def _aged(path: Path, hours: float) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"half written")
    then = time.time() - hours * HOURS
    os.utime(path, (then, then))
    return path


@pytest.mark.integration
def test_a_render_in_progress_is_named_as_half_written_beside_its_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Killed mid-render, the file must be one that exports and backups pass over."""
    source = tmp_path / "in.png"
    pyvips.Image.black(8, 8).pngsave(str(source))
    destination = tmp_path / "data" / "derived" / "thumb" / "ab" / "x.webp"
    written: list[Path] = []
    real = vips_renderer._SAVERS["webp"]

    def save(image: pyvips.Image, path: str, spec: RenderSpec) -> None:
        written.append(Path(path))
        real(image, path, spec)

    monkeypatch.setitem(vips_renderer._SAVERS, "webp", save)
    vips_renderer.VipsRenderer().render(source, destination, 8)
    (partial,) = written
    assert partial.name.endswith(".partial") and partial.parent == destination.parent
    assert pyvips.Image.new_from_file(str(destination)).width == 8, "still a real WebP"
    partial.write_bytes(b"as if the render had been killed")
    assert list(LocalFileTree().files_under(tmp_path / "data", "derived")) == [
        "derived/thumb/ab/x.webp"
    ]


def test_the_sweep_clears_downloads_and_old_half_written_derivatives(tmp_path: Path) -> None:
    root = tmp_path / "data"
    download = _aged(root / "tmp" / "download-abc.jpg", hours=0)
    old_render = _aged(root / "derived" / "thumb" / "ab" / ".123.webp.partial", hours=2)
    live_render = _aged(root / "derived" / "thumb" / "ab" / ".456.webp.partial", hours=0)
    thumb = _aged(root / "derived" / "thumb" / "ab" / "x.webp", hours=2)
    other = _aged(root / "tmp" / "something-else.bin", hours=2)
    original = _aged(root / "originals" / "2020" / "01" / "a.partial", hours=2)
    assert DiskLibraryStore(root).sweep_tmp() == 2
    assert not download.exists() and not old_render.exists()
    assert live_render.exists(), "an import running beside the server may be writing it"
    assert thumb.exists() and other.exists()
    assert original.exists(), "the sweep never looks at originals"
