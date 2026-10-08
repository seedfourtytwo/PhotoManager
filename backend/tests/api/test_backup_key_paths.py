"""Over HTTP a backup's password file is one of the app's own key files, never a free path:
the recovery sheet shows that file's contents, so a free path would read any file (QA)."""

from pathlib import Path

from fastapi.testclient import TestClient

from photo_assistant.domain.backup import NewBackupTarget
from tests.api.conftest import services_of

SECRET = "-----BEGIN OPENSSH PRIVATE KEY-----"


def _secret(tmp_path: Path) -> Path:
    secret = tmp_path / "home" / "id_ed25519"
    secret.parent.mkdir()
    secret.write_text(f"{SECRET}\n")
    return secret


def _key_folder(tmp_path: Path) -> Path:
    keys = tmp_path / "backup-keys"  # where tests/api/conftest.py points PA_BACKUP_KEY_DIR
    keys.mkdir(exist_ok=True)
    return keys


def _add(admin: TestClient, tmp_path: Path, password_file: Path, label: str = "Disk") -> int:
    body = {
        "label": label,
        "repository": str(tmp_path / "disk" / label),
        "password_file": str(password_file),
    }
    return admin.post("/api/backups", json=body).status_code


def test_a_password_file_outside_the_key_folder_is_refused_over_http(
    admin: TestClient, tmp_path: Path
) -> None:
    keys = _key_folder(tmp_path)
    secret = _secret(tmp_path)
    (keys / "link.key").symlink_to(secret)
    for path in (secret, keys / ".." / "home" / "id_ed25519", keys / "link.key", keys):
        assert _add(admin, tmp_path, path) == 422, path
    missing = admin.post(
        "/api/backups",
        json={"label": "D", "repository": "/mnt/x", "password_file": "/root/.ssh/id_ed25519"},
    )
    assert missing.status_code == 422 and "key folder" in missing.json()["detail"]
    assert "not found" not in missing.json()["detail"], "never says which files exist"
    assert admin.get("/api/backups").json() == []


def test_a_key_file_in_the_key_folder_is_accepted_over_http(
    admin: TestClient, tmp_path: Path
) -> None:
    own = _key_folder(tmp_path) / "mine.key"
    own.write_text("pw\n")
    assert _add(admin, tmp_path, own) == 201
    (target,) = admin.get("/api/backups").json()
    shown = admin.get(f"/api/backups/{target['id']}/recovery")
    assert shown.status_code == 200 and shown.json()["key"] == "pw"


def test_the_recovery_sheet_never_shows_a_file_outside_the_key_folder(
    admin: TestClient, tmp_path: Path
) -> None:
    # the command line may still point a target at any file (just backup add --password-file)
    new = NewBackupTarget("CLI", str(tmp_path / "disk" / "cli"), str(_secret(tmp_path)))
    target = services_of(admin).ops.backup.add_target(new)
    shown = admin.get(f"/api/backups/{target.id}/recovery")
    assert shown.status_code == 409 and "command line" in shown.json()["detail"]
    assert SECRET not in shown.text
