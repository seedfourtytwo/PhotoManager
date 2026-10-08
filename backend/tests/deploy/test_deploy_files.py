"""Static checks of the deployment files (deploy/).

The Docker image can't be built where CI runs without a daemon, so these tests catch what can
be caught by reading: pinned versions, non-root user, health check, safe port publishing, the
files the build copies actually exist and survive the .dockerignore. The image itself is
UNTESTED until built on the server (docs/guides/move-to-server.md).
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]  # PyYAML ships without stubs

from photo_assistant.api.ops_services import default_key_dir

REPO = Path(__file__).parents[3]
DEPLOY = REPO / "deploy"


def dockerfile() -> list[tuple[str, str, str]]:
    """(instruction, arguments, comment block just above it), continuation lines joined."""
    result, comments, pending = [], [], ""
    for raw in (DEPLOY / "Dockerfile").read_text().splitlines():
        line = raw.strip()
        if not pending and line.startswith("#"):
            comments.append(line)
            continue
        if not line:
            comments = [] if not pending else comments
            continue
        pending = f"{pending} {line.rstrip(chr(92)).strip()}".strip()
        if line.endswith("\\"):
            continue
        keyword, _, args = pending.partition(" ")
        result.append((keyword.upper(), args.strip(), "\n".join(comments)))
        comments, pending = [], ""
    return result


def _args() -> dict[str, str]:
    found = {}
    for kw, args, _ in dockerfile():
        if kw == "ARG" and "=" in args:
            name, _, value = args.partition("=")
            found[name] = value
    return found


def _resolve(image: str) -> str:
    return re.sub(r"\$\{(\w+)\}", lambda m: _args()[m.group(1)], image)


def test_base_images_are_pinned_never_latest() -> None:
    images = [_resolve(args.split()[0]) for kw, args, _ in dockerfile() if kw == "FROM"]
    assert len(images) == 4
    for image in images:
        name, _, tag = image.rpartition(":")
        assert name and re.match(r"v?\d+\.\d+\.\d+", tag), f"unpinned image {image}"
        assert "latest" not in image
    assert _args()["PYTHON_IMAGE"].startswith("python:3.12.")
    assert "bookworm" in _args()["PYTHON_IMAGE"]


def test_stages_and_copies_line_up() -> None:
    stages = {args.split()[-1] for kw, args, _ in dockerfile() if kw == "FROM" and " AS " in args}
    assert stages == {"uv", "web", "python", "runtime"}
    ignore = (DEPLOY / "Dockerfile.dockerignore").read_text().splitlines()
    for kw, args, _ in dockerfile():
        if kw != "COPY":
            continue
        parts = args.split()
        if parts[0].startswith("--from="):
            assert parts[0].removeprefix("--from=") in stages
            continue
        for source in parts[:-1]:
            assert (REPO / source).exists(), f"COPY source missing: {source}"
            keep = [i[1:] for i in ignore if i.startswith("!")]
            src = source.rstrip("/")
            included = any(src.startswith(k) or k.startswith(src + "/") for k in keep)
            assert included, f"{source} is excluded by Dockerfile.dockerignore"


def test_runtime_has_every_tool_and_runs_as_a_normal_user() -> None:
    steps = dockerfile()
    runtime = steps[[i for i, s in enumerate(steps) if s[0] == "FROM"][-1] :]
    installed = " ".join(args for kw, args, _ in runtime if kw == "RUN")
    for package in (
        "libvips42",
        "libimage-exiftool-perl",
        "libheif-plugin-libde265",
        "restic",
        "rclone",
    ):
        assert re.search(rf"\b{package}\b", installed), package
    kinds = [kw for kw, _, _ in runtime]
    assert kinds.index("USER") < kinds.index("CMD")
    assert dict((kw, a) for kw, a, _ in runtime)["USER"] not in ("root", "0")


def test_data_volume_health_check_and_listen_address() -> None:
    steps = dockerfile()
    env = " ".join(args for kw, args, _ in steps if kw == "ENV")
    assert "PA_DATA_ROOT=/data" in env
    assert any(kw == "VOLUME" and "/data" in args for kw, args, _ in steps)
    health = [args for kw, args, _ in steps if kw == "HEALTHCHECK"]
    assert len(health) == 1 and "/api/health" in health[0]
    (host_env,) = [(a, c) for kw, a, c in steps if kw == "ENV" and "PA_HOST=" in a]
    assert host_env[0] == "PA_HOST=0.0.0.0"
    warning = host_env[1].lower()
    assert "login" in warning and "allowed_hosts" in warning and "never" in warning
    assert "untested" in (DEPLOY / "Dockerfile").read_text().lower()


def test_compose_service_is_private_and_persistent() -> None:
    compose = yaml.safe_load((DEPLOY / "compose.yml").read_text())
    service = compose["services"]["photo-assistant"]
    assert (DEPLOY / service["build"]["context"] / service["build"]["dockerfile"]).is_file()
    assert not service["image"].endswith(":latest") and ":" in service["image"]
    assert service["restart"] in ("unless-stopped", "always")
    assert service["env_file"] == ["server.env"]
    assert (DEPLOY / "server.env.example").is_file()
    assert all(str(p).startswith("127.0.0.1:") for p in service["ports"]), "loopback only"
    assert any(str(v).endswith(":/data") for v in service["volumes"])
    assert any(str(v).endswith(":/secrets:ro") for v in service["volumes"])
    assert "tailscale" not in compose["services"], "the sidecar stays opt-in (commented out)"
    for line in (DEPLOY / "compose.yml").read_text().splitlines():
        assert "image:" not in line or ":latest" not in line


def _mounts() -> dict[str, str]:
    """Container path -> mount options ("" = read-write) of the app service."""
    service = yaml.safe_load((DEPLOY / "compose.yml").read_text())["services"]["photo-assistant"]
    mounts = {}
    for volume in service["volumes"]:
        _, target, *options = re.sub(r"\$\{[^}]*\}", "host", str(volume)).split(":")
        mounts[target] = ",".join(options)
    return mounts


def _server_env() -> dict[str, str]:
    lines = (DEPLOY / "server.env.example").read_text().splitlines()
    pairs = (line.partition("=") for line in lines if line and not line.startswith("#"))
    return {key: value for key, _, value in pairs}


def _container_home() -> Path:
    (home,) = [args for kw, args, _ in dockerfile() if kw == "WORKDIR" and "/home/" in args]
    return Path(home)


def _writable_mount_holding(path: Path) -> str | None:
    for target, options in _mounts().items():
        if path.is_relative_to(target) and "ro" not in options.split(","):
            return target
    return None


def test_backup_keys_and_rclone_config_survive_a_rebuilt_container() -> None:
    """`up -d --build` makes a new container: what is not on a mount is gone, and the key
    the guided backup setup made would go with it."""
    home, env = _container_home(), _server_env()
    default_keys = home / default_key_dir().relative_to(Path.home())
    key_dir = Path(env.get("PA_BACKUP_KEY_DIR") or default_keys)
    rclone = Path(env.get("PA_RCLONE_CONFIG") or home / ".config" / "rclone" / "rclone.conf")
    assert _writable_mount_holding(key_dir), f"{key_dir} is lost when the container is rebuilt"
    assert _writable_mount_holding(rclone), f"{rclone} is lost when the container is rebuilt"
    assert not key_dir.is_relative_to("/data"), "a backup must not carry its own key"


def test_mount_points_under_home_belong_to_the_app_user() -> None:
    """Docker creates a missing mount point as root; the image must own it first."""
    home = _container_home()
    prepared = " ".join(args for kw, args, _ in dockerfile() if kw == "RUN")
    compose = yaml.safe_load((DEPLOY / "compose.yml").read_text())
    under_home = [t for t in _mounts() if Path(t).is_relative_to(home)]
    assert under_home
    for target in under_home:
        assert re.search(rf"mkdir -p[^&]*{re.escape(target)}\b", prepared), target
        assert re.search(rf"chown[^&]*{re.escape(target)}\b", prepared), target
    assert set(compose["volumes"]) == {"restic-cache"}


def test_source_folder_mounts_are_read_only() -> None:
    """Originals are sacred: a photo folder is only ever offered to the container read-only."""
    text = (DEPLOY / "compose.yml").read_text()
    sources = re.findall(r"^\s*#?\s*-\s+\S+?:(/sources/\S*)$", text, flags=re.MULTILINE)
    assert sources, "compose shows how to mount a photo folder"
    assert all(target.endswith(":ro") for target in sources), sources


def test_server_env_is_never_committed() -> None:
    assert "deploy/server.env" in (REPO / ".gitignore").read_text().splitlines()


def _unit(text: str) -> dict[str, dict[str, list[str]]]:
    sections: dict[str, dict[str, list[str]]] = {}
    current: dict[str, list[str]] = {}
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("[") and line.endswith("]"):
            current = sections.setdefault(line[1:-1], {})
        elif line and not line.startswith("#"):
            key, _, value = line.partition("=")
            current.setdefault(key, []).append(value)
    return sections


def test_systemd_user_service() -> None:
    unit = _unit((DEPLOY / "photo-assistant.service").read_text())
    service = unit["Service"]
    assert service["WorkingDirectory"] == ["@REPO@/backend"]
    assert service["EnvironmentFile"] == ["@REPO@/.env"]
    assert service["ExecStart"][0].startswith("@REPO@/backend/.venv/bin/python -m photo_assistant")
    assert service["Restart"] == ["on-failure"] and service["Nice"] == ["5"]
    assert service["MemoryMax"]
    assert "PA_HOST" not in " ".join(service.get("Environment", [])), "stays on 127.0.0.1"
    assert unit["Install"]["WantedBy"] == ["default.target"], "user services: default.target"


@pytest.mark.skipif(shutil.which("systemd-analyze") is None, reason="no systemd-analyze")
def test_systemd_accepts_the_installed_unit(tmp_path: Path) -> None:
    """What `just install-service` writes, checked by systemd's own parser."""
    repo = tmp_path / "photo-assistant"
    python = repo / "backend" / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.symlink_to(shutil.which("python3") or "/usr/bin/python3")
    (repo / ".env").write_text("PA_DATA_ROOT=~/PhotoAssistant/data\n")
    text = (DEPLOY / "photo-assistant.service").read_text().replace("@REPO@", str(repo))
    assert "@" not in text.replace("@pm.me", "")
    unit = tmp_path / "photo-assistant.service"
    unit.write_text(text)
    done = subprocess.run(
        ["systemd-analyze", "verify", "--man=no", str(unit)],
        capture_output=True,
        text=True,
        check=False,
    )
    problems = [line for line in done.stderr.splitlines() if str(unit) in line]
    assert problems == [], done.stderr


def test_justfile_has_the_ops_recipes() -> None:
    justfile = (REPO / "justfile").read_text()
    for recipe in (
        "doctor:",
        "export-library dest",
        "verify-library",
        "backup *args",
        "install-service:",
        "uninstall-service:",
    ):
        assert recipe in justfile
    assert "systemctl --user" in justfile and "enable-linger" in justfile


def test_the_ci_workflow_is_valid_yaml_with_all_three_jobs() -> None:
    """GitHub rejects a workflow file it cannot parse without running anything."""
    workflow = yaml.safe_load((REPO / ".github" / "workflows" / "ci.yml").read_text())
    assert set(workflow["jobs"]) == {"backend", "web", "secrets"}
    assert all(job["steps"] for job in workflow["jobs"].values())
