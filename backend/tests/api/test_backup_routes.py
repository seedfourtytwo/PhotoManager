"""Backup admin endpoints, with the real store and restic and the real job queue."""

import shutil
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from photo_assistant.adapters.sqlite_database import Database
from photo_assistant.adapters.sqlite_repository import SqliteRepository
from photo_assistant.api.deps import admin_user, current_user
from photo_assistant.api.ops_services import OpsServices, RcloneTool, build_ops_services
from photo_assistant.api.routes import backup
from photo_assistant.api.settings import OpsSettings
from photo_assistant.domain.access import Role, User
from photo_assistant.domain.backup import NewBackupTarget
from photo_assistant.ports.backup import RepositoryMirror
from tests.api.conftest import answer_domain_errors, refusal
from tests.proton_cloud import Cloud

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which("restic") is None, reason="restic missing"),
]


class Env:
    def __init__(self, tmp_path: Path, mirror: RepositoryMirror | None = None) -> None:
        self.root = tmp_path / "data"
        self.root.mkdir()
        db = Database.open(self.root / "library.db")
        self.repo = SqliteRepository(db)
        self.ops: OpsServices = build_ops_services(
            self.root,
            OpsSettings(restic_cache_dir=tmp_path / "cache", backup_key_dir=tmp_path / "keys"),
            db=db,
            rclone=RcloneTool(),
            queue=self.repo,
            mirror=mirror,
        )
        self.keys = tmp_path / "keys"
        self.disk = tmp_path / "disk"
        self.disk.mkdir()
        app = FastAPI()
        answer_domain_errors(app)
        # core's admin check (session + role) is covered in test_wiring.py
        app.dependency_overrides[admin_user] = lambda: User(1, "c", "C", Role.ADMIN)
        app.state.services = SimpleNamespace(ops=self.ops)
        app.include_router(backup.router)
        self.client = TestClient(app)

    @property
    def password(self) -> Path:
        """A key file in the app's key folder (over HTTP no other path is accepted), made on
        first use so that the folder stays absent until a test needs it."""
        path = self.keys / "pw"
        if not path.exists():
            self.keys.mkdir(exist_ok=True)
            path.write_text("pw\n")
        return path

    def work(self) -> None:
        """What the worker does with queued backup jobs."""
        handlers = self.ops.backup.job_handlers()
        while job := self.repo.claim_next_job(self.ops.backup._clock.now()):
            handlers[job.kind](job.payload)
            self.repo.complete_job(job.id)


@pytest.fixture
def env(tmp_path: Path) -> Iterator[Env]:
    e = Env(tmp_path)
    yield e
    e.ops.close()
    e.repo.close()


def _add(env: Env, **extra: object) -> dict[str, object]:
    body = {
        "label": "Disk",
        "repository": str(env.disk / "photos"),
        "password_file": str(env.password),
    } | extra
    response = env.client.post("/api/backups", json=body)
    assert response.status_code == 201, response.text
    return response.json()  # type: ignore[no-any-return]


def test_add_run_and_watch_a_backup(env: Env) -> None:
    assert env.client.get("/api/backups").json() == []
    target = _add(env, schedule="weekly sun 03:00", retention={"daily": 3})
    assert target["retention"] == {"daily": 3, "weekly": 4, "monthly": 12}
    assert target["next_run_at"] and not target["needs_attention"] and target["kind"] == "local"
    queued = env.client.post(f"/api/backups/{target['id']}/run")
    assert queued.status_code == 202 and queued.json()["target_id"] == target["id"]
    env.client.post(f"/api/backups/{target['id']}/restore-test")
    env.work()
    runs = env.client.get(f"/api/backups/{target['id']}/runs").json()
    assert [(r["kind"], r["status"]) for r in runs] == [
        ("restore_test", "succeeded"),
        ("restore_test", "succeeded"),  # the first backup proves itself (issue 3)
        ("backup", "succeeded"),
    ]
    (listed,) = env.client.get("/api/backups").json()
    assert listed["last_success_at"] and listed["repo_bytes"]
    assert listed["last_proven_at"] and not listed["restore_failing"] and listed["key_saved"]
    assert listed["last_run"]["snapshot_id"]
    assert env.client.get(f"/api/backups/{target['id']}/runs?limit=1").json()[0]["kind"] == (
        "restore_test"
    )


def test_failures_show_up_in_status(env: Env) -> None:
    target = _add(env)
    env.client.post(f"/api/backups/{target['id']}/run")
    env.work()
    env.password.write_text("someone changed it\n")
    env.client.post(f"/api/backups/{target['id']}/run")
    env.work()
    (listed,) = env.client.get("/api/backups").json()
    assert listed["needs_attention"] and listed["last_run"]["status"] == "failed"
    assert "wrong password" in listed["last_run"]["error"]
    patched = env.client.patch(f"/api/backups/{target['id']}", json={"enabled": False})
    assert patched.json()["enabled"] is False and not patched.json()["needs_attention"]


def test_a_first_backup_that_fails_for_real_raises_the_banner(env: Env) -> None:
    env.password.write_text("pw\n")
    target = _add(env)
    env.password.unlink()
    env.client.post(f"/api/backups/{target['id']}/run")
    env.work()
    (listed,) = env.client.get("/api/backups").json()
    assert listed["needs_attention"] and listed["last_run"]["status"] == "failed"
    assert listed["last_run"]["error"]


def test_a_disk_that_is_not_there_shows_as_skipped_not_as_trouble(env: Env) -> None:
    target = _add(env, repository="/media/nobody/NoDisk/photos")
    env.client.post(f"/api/backups/{target['id']}/run")
    env.work()
    (listed,) = env.client.get("/api/backups").json()
    assert listed["last_run"]["status"] == "skipped"
    assert "plug it in" in listed["last_run"]["error"]
    assert not listed["needs_attention"]


def test_a_target_reports_since_when_it_is_skipped(env: Env) -> None:
    target = _add(env, repository="/media/nobody/NoDisk/photos")
    assert target["skipped_since"] is None and target["mirror_overdue"] is False
    env.client.post(f"/api/backups/{target['id']}/run")
    env.work()
    (listed,) = env.client.get("/api/backups").json()
    assert listed["skipped_since"] is not None and listed["mirror_overdue"] is False


# --- health: are at least two places safe? -------------------------------------------------------


def test_health_with_no_backup_warns_that_none_is_set_up(env: Env) -> None:
    response = env.client.get("/api/backups/health")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["protected"] is False and body["places_ok"] == 0 and body["places_total"] == 0
    assert body["problems"], "someone must be told"
    assert set(body["problems"][0]) == {"severity", "message", "target_id"}
    assert body["problems"][0]["severity"] in ("alert", "warning")
    assert body["problems"][0]["target_id"] is None


def test_health_is_protected_with_two_fresh_places(env: Env) -> None:
    for name in ("one", "two"):
        place = env.disk / name
        place.mkdir()
        target = _add(env, label=name, repository=str(place / "photos"))
        env.client.post(f"/api/backups/{target['id']}/run")
        env.client.post(f"/api/backups/{target['id']}/restore-test")
    env.work()
    body = env.client.get("/api/backups/health").json()
    assert body["protected"] is True
    assert body["places_ok"] == 2 and body["places_total"] == 2


def test_health_is_admin_only(env: Env) -> None:
    app = env.client.app
    app.dependency_overrides.pop(admin_user)  # type: ignore[attr-defined]
    app.dependency_overrides[current_user] = lambda: User(2, "m", "M", Role.MEMBER)  # type: ignore[attr-defined]
    assert env.client.get("/api/backups/health").status_code == 403


def test_validation_and_unknown_targets(env: Env) -> None:
    _add(env)
    again = env.client.post(
        "/api/backups",
        json={"label": "Disk", "repository": "/x", "password_file": str(env.password)},
    )
    assert again.status_code == 409
    bad = env.client.post(
        "/api/backups",
        json={
            "label": "B",
            "repository": "/x",
            "password_file": str(env.password),
            "schedule": "sometimes",
        },
    )
    assert bad.status_code == 422 and "schedule" in bad.json()["detail"]
    inside = env.client.post(
        "/api/backups",
        json={"label": "C", "repository": str(env.root / "b"), "password_file": str(env.password)},
    )
    assert inside.status_code == 422
    for method, path in (
        ("post", "/api/backups/99/run"),
        ("post", "/api/backups/99/restore-test"),
        ("get", "/api/backups/99/runs"),
    ):
        assert getattr(env.client, method)(path).status_code == 404
    assert env.client.patch("/api/backups/99", json={"enabled": True}).status_code == 404


def test_status_lookup_for_a_vanished_target(env: Env) -> None:
    with pytest.raises(backup.HTTPException):
        backup._status_of(env.ops.backup, 12345)


# --- v1.3: schedule, quiet window and retention can be changed ---------------------------------


def test_patch_changes_schedule_window_and_retention(env: Env) -> None:
    target = _add(env, quiet_window="22:00-06:00", retention={"daily": 3})
    url = f"/api/backups/{target['id']}"
    changed = env.client.patch(
        url, json={"schedule": "weekly sun 03:00", "retention": {"weekly": 2}}
    )
    assert changed.status_code == 200, changed.text
    body = changed.json()
    assert body["schedule"] == "weekly sun 03:00" and body["quiet_window"] == "22:00-06:00"
    assert body["retention"] == {"daily": 3, "weekly": 2, "monthly": 12}, "only what was sent"
    assert body["enabled"] is True
    cleared = env.client.patch(url, json={"quiet_window": None, "enabled": False}).json()
    assert cleared["quiet_window"] is None and cleared["enabled"] is False
    assert cleared["schedule"] == "weekly sun 03:00"
    assert env.client.patch(url, json={}).json() == cleared, "nothing sent, nothing changed"
    manual = env.client.patch(url, json={"schedule": "manual", "enabled": True}).json()
    assert manual["next_run_at"] is None and manual["enabled"] is True


@pytest.mark.parametrize(
    ("patch", "word"),
    [
        ({"schedule": "now and then"}, "schedule"),
        ({"schedule": None}, "schedule"),
        ({"quiet_window": "night"}, "quiet window"),
        ({"quiet_window": "22:00-22:00"}, "empty"),
        ({"retention": {"daily": 0, "weekly": 0, "monthly": 0}}, "retention"),
        ({"retention": {"daily": -1}}, "greater than or equal"),
        ({"label": "renamed"}, "extra"),
    ],
)
def test_patch_refuses_bad_settings_and_changes_nothing(
    env: Env, patch: dict[str, object], word: str
) -> None:
    target = _add(env)
    response = env.client.patch(f"/api/backups/{target['id']}", json=patch)
    assert response.status_code == 422 and word in str(response.json()["detail"])
    (listed,) = env.client.get("/api/backups").json()
    assert listed["schedule"] == target["schedule"] and listed["retention"] == target["retention"]
    assert listed["label"] == "Disk"


# --- guided setup (issue 3) --------------------------------------------------------------------


def test_places_report_the_library_size_and_where_a_backup_could_go(env: Env) -> None:
    places = env.client.get("/api/backups/places").json()
    assert places["library_bytes"] == 0
    assert isinstance(places["disks"], list) and isinstance(places["remotes"], list)


def test_plan_says_whether_a_place_will_do_without_creating_anything(env: Env) -> None:
    good = env.client.post("/api/backups/plan", json={"place": str(env.disk)})
    assert good.status_code == 200, good.text
    body = good.json()
    assert body["ok"] and body["problem"] is None
    assert body["repository"] == str(env.disk / "photo-assistant-backup")
    assert body["free_bytes"] > 0 and body["library_bytes"] == 0
    assert list(env.disk.iterdir()) == [] and not env.keys.exists()
    for place in (str(env.root), "relative", str(env.disk / "missing")):
        bad = env.client.post("/api/backups/plan", json={"place": place}).json()
        assert not bad["ok"] and bad["problem"], place


def test_guided_setup_backs_up_proves_the_restore_and_hands_over_the_key(env: Env) -> None:
    created = env.client.post("/api/backups/setup", json={"label": "USB", "place": str(env.disk)})
    assert created.status_code == 201, created.text
    body = created.json()
    target, recovery = body["target"], body["recovery"]
    assert target["schedule"] == "daily 02:30" and target["retention"]["daily"] == 7
    assert not target["key_saved"] and target["needs_attention"]
    assert recovery["repository"] == str(env.disk / "photo-assistant-backup")
    assert len(recovery["key"]) >= 40
    (key_file,) = env.keys.iterdir()
    assert key_file.read_text().strip() == recovery["key"]

    env.work()  # the first backup was queued by the setup itself
    runs = env.client.get(f"/api/backups/{target['id']}/runs").json()
    assert [(r["kind"], r["status"]) for r in runs] == [
        ("restore_test", "succeeded"),
        ("backup", "succeeded"),
    ], runs

    again = env.client.get(f"/api/backups/{target['id']}/recovery")
    assert again.status_code == 200 and again.json() == recovery
    saved = env.client.post(f"/api/backups/{target['id']}/key-saved")
    assert saved.status_code == 200
    assert saved.json()["key_saved"] and not saved.json()["needs_attention"]
    assert saved.json()["last_proven_at"]


def test_guided_setup_refuses_bad_places_taken_names_and_bad_schedules(env: Env) -> None:
    ok = {"label": "USB", "place": str(env.disk)}
    inside = env.client.post("/api/backups/setup", json=ok | {"place": str(env.root)})
    assert inside.status_code == 422 and "cannot live inside" in inside.json()["detail"]
    often = env.client.post("/api/backups/setup", json=ok | {"schedule": "often"})
    assert often.status_code == 422 and "schedule" in often.json()["detail"]
    blank = env.client.post("/api/backups/setup", json=ok | {"label": "  "})
    assert blank.status_code == 422
    assert not env.keys.exists() and env.client.get("/api/backups").json() == []
    assert env.client.post("/api/backups/setup", json=ok).status_code == 201
    other = env.disk / "other"
    other.mkdir()
    taken = env.client.post("/api/backups/setup", json=ok | {"place": str(other)})
    assert taken.status_code == 409
    assert len(list(env.keys.iterdir())) == 1


def test_a_second_setup_in_the_same_place_is_refused_once_the_first_backup_exists(
    env: Env,
) -> None:
    assert (
        env.client.post("/api/backups/setup", json={"label": "USB", "place": str(env.disk)})
    ).status_code == 201
    env.work()
    again = env.client.post("/api/backups/setup", json={"label": "USB 2", "place": str(env.disk)})
    assert again.status_code == 422 and "already a backup" in again.json()["detail"]


def test_recovery_and_key_saved_for_unknown_targets_or_a_lost_key_file(env: Env) -> None:
    assert env.client.get("/api/backups/99/recovery").status_code == 404
    assert env.client.post("/api/backups/99/key-saved").status_code == 404
    created = env.client.post("/api/backups/setup", json={"label": "USB", "place": str(env.disk)})
    (key_file,) = env.keys.iterdir()
    key_file.unlink()
    lost = env.client.get(f"/api/backups/{created.json()['target']['id']}/recovery")
    assert lost.status_code == 409 and "key file is gone" in lost.json()["detail"]


# --- an off-site copy on Proton Drive (issue 14), with the stand-in Proton tool ------------------


@pytest.fixture
def proton(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[Env, Cloud]]:
    from photo_assistant.adapters.proton_mirror import ProtonMirror

    cloud = Cloud(tmp_path, monkeypatch)
    cloud.folder("/my-files", {"type": "folder", "uid": "b", "name": "Backups"})
    cloud.folder("/my-files/Backups")
    e = Env(tmp_path, ProtonMirror(cloud.drive))
    yield e, cloud
    e.ops.close()
    e.repo.close()


def _download(cloud: Cloud, copy: str, into: Path) -> Path:
    """What downloading the copy from Proton gives back, rebuilt from the stand-in's state."""
    import json

    tree = json.loads(cloud.state_file.read_text())["tree"]
    for folder, entries in tree.items():
        if folder == copy or folder.startswith(copy + "/"):
            target = into / folder.removeprefix(copy).lstrip("/")
            target.mkdir(parents=True, exist_ok=True)
            for entry in entries:
                if entry["type"] == "file":
                    shutil.copyfile(entry["source"], target / entry["name"])
    return into


def test_a_backup_is_copied_to_proton_and_the_copy_is_a_healthy_repository(
    proton: tuple[Env, Cloud], tmp_path: Path
) -> None:
    import subprocess

    env, cloud = proton
    (env.root / "originals").mkdir()
    (env.root / "originals" / "a.jpg").write_bytes(b"pixels")
    target = _add(env)
    assert target["mirror_path"] is None
    path = f"/api/backups/{target['id']}/proton-copy"
    switched = env.client.put(path, json={"path": "/my-files/Backups"})
    assert switched.status_code == 200 and switched.json()["mirror_path"] == "/my-files/Backups"
    assert env.client.post(f"/api/backups/{target['id']}/run").status_code == 202
    env.work()
    status = env.client.get("/api/backups").json()[0]
    assert status["last_mirror_at"] and status["mirror_error"] is None
    assert not status["needs_attention"]
    runs = env.client.get(f"/api/backups/{target['id']}/runs").json()
    assert "mirror" in [r["kind"] for r in runs]
    restored = _download(cloud, "/my-files/Backups/photos", tmp_path / "from-proton")
    check = subprocess.run(
        ["restic", "-r", str(restored), "--password-file", str(env.password), "check"],
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin:/usr/local/bin", "RESTIC_CACHE_DIR": str(tmp_path / "c2")},
        check=False,
    )
    assert check.returncode == 0, check.stderr


def test_a_failed_copy_shows_on_the_target_and_switching_it_off_clears_it(
    proton: tuple[Env, Cloud],
) -> None:
    env, cloud = proton
    target = _add(env)
    path = f"/api/backups/{target['id']}/proton-copy"
    env.client.put(path, json={"path": "/my-files/Backups"})
    cloud.state["signed_in"] = False
    cloud.save()
    env.client.post(f"/api/backups/{target['id']}/run")
    env.work()
    status = env.client.get("/api/backups").json()[0]
    assert "proton-drive auth login" in status["mirror_error"] and status["needs_attention"]
    assert status["last_success_at"], "the backup itself worked"
    cleared = env.client.put(path, json={"path": None}).json()
    assert cleared["mirror_path"] is None and cleared["mirror_error"] is None
    assert not cleared["needs_attention"]


def test_the_copy_is_refused_for_bad_places_and_unknown_targets(
    proton: tuple[Env, Cloud],
) -> None:
    env, _ = proton
    target = _add(env)
    path = f"/api/backups/{target['id']}/proton-copy"
    for bad in ("/photos", "/trash", "Backups", "/my-files/../x"):
        assert env.client.put(path, json={"path": bad}).status_code == 422
    assert env.client.put("/api/backups/999/proton-copy", json={"path": None}).status_code == 404


def test_without_proton_on_the_server_the_copy_cannot_be_switched_on(env: Env) -> None:
    target = _add(env)
    refused = env.client.put(
        f"/api/backups/{target['id']}/proton-copy", json={"path": "/my-files/Backups"}
    )
    assert refused.status_code == 422 and "not available" in refused.json()["detail"]


# --- what a refused request says (status and sentence are the contract) ------------------------

BAD_SCHEDULE = (
    "unknown schedule 'sometimes': use 'manual', 'hourly', 'daily HH:MM' or 'weekly sun HH:MM'"
)


def test_adding_a_target_by_hand_says_why_it_is_refused(env: Env) -> None:
    _add(env)

    def add(**changes: object) -> tuple[int, object]:
        body = {"label": "B", "repository": "/x", "password_file": str(env.password)} | changes
        return refusal(env.client.post("/api/backups", json=body))

    assert add(label="Disk") == (409, {"detail": "a backup target named 'Disk' already exists"})
    assert add(schedule="sometimes") == (422, {"detail": BAD_SCHEDULE})
    assert add(quiet_window="night") == (
        422,
        {"detail": "quiet window 'night' must look like 22:00-06:00"},
    )
    assert add(label="  ") == (422, {"detail": "a backup target needs a name"})
    assert add(repository=" ") == (422, {"detail": "a backup target needs a repository location"})
    assert add(repository="relative") == (
        422,
        {"detail": "a local backup location must be an absolute path"},
    )
    assert add(repository=str(env.root / "b")) == (
        422,
        {"detail": "a backup cannot live inside the library, or contain it"},
    )
    assert add(retention={"daily": 0, "weekly": 0, "monthly": 0}) == (
        422,
        {"detail": "retention must keep at least one snapshot and no negative counts"},
    )
    assert add(password_file="/root/.ssh/id_ed25519") == (
        422,
        {
            "detail": "the password file must be a key file in this app's key folder; for a "
            "file elsewhere on the server use the command line (just backup add)"
        },
    )


def test_a_guided_setup_says_why_it_is_refused(env: Env) -> None:
    def set_up(**changes: object) -> tuple[int, object]:
        body = {"label": "USB", "place": str(env.disk)} | changes
        return refusal(env.client.post("/api/backups/setup", json=body))

    assert set_up(place=str(env.root)) == (
        422,
        {"detail": "a backup cannot live inside the library, or contain it"},
    )
    assert set_up(place="relative") == (
        422,
        {"detail": "a local backup location must be an absolute path"},
    )
    assert set_up(place="rclone:nowhere") == (
        422,
        {"detail": "a cloud location looks like rclone:<name>:<folder>"},
    )
    assert set_up(schedule="sometimes") == (422, {"detail": BAD_SCHEDULE})
    assert set_up(label="  ") == (422, {"detail": "a backup target needs a name"})
    assert env.client.post(
        "/api/backups/setup", json={"label": "USB", "place": str(env.disk)}
    ).is_success
    other = env.disk / "other"
    other.mkdir()
    assert set_up(place=str(other)) == (
        409,
        {"detail": "a backup target named 'USB' already exists"},
    )


def test_changing_a_target_says_why_it_is_refused(env: Env) -> None:
    target = _add(env)

    def patch(**changes: object) -> tuple[int, object]:
        return refusal(env.client.patch(f"/api/backups/{target['id']}", json=changes))

    assert patch(schedule="sometimes") == (422, {"detail": BAD_SCHEDULE})
    assert patch(schedule=None) == (
        422,
        {"detail": "the schedule can't be empty: use 'manual' to pause it"},
    )
    assert patch(quiet_window="22:00-22:00") == (
        422,
        {"detail": "quiet window '22:00-22:00' is empty: start and end are the same"},
    )
    assert patch(retention={"daily": 0, "weekly": 0, "monthly": 0}) == (
        422,
        {"detail": "retention must keep at least one snapshot and no negative counts"},
    )


def test_unknown_targets_and_unreadable_keys_say_so(env: Env) -> None:
    unknown = (404, {"detail": "backup target not found"})
    assert refusal(env.client.get("/api/backups/99/recovery")) == unknown
    assert refusal(env.client.patch("/api/backups/99", json={"enabled": False})) == unknown
    assert refusal(env.client.post("/api/backups/99/run")) == unknown
    assert refusal(env.client.get("/api/backups/99/runs")) == unknown
    created = env.client.post("/api/backups/setup", json={"label": "USB", "place": str(env.disk)})
    (key_file,) = env.keys.iterdir()
    key_file.unlink()
    lost = env.client.get(f"/api/backups/{created.json()['target']['id']}/recovery")
    assert refusal(lost) == (
        409,
        {
            "detail": f"the key file is gone: {key_file} "
            "(the saved recovery key still opens the backup)"
        },
    )
    elsewhere = env.keys.parent / "elsewhere.pw"
    elsewhere.write_text("pw\n")
    by_hand = env.ops.backup.add_target(
        NewBackupTarget("CLI", str(env.disk / "cli"), str(elsewhere))
    )
    hidden = env.client.get(f"/api/backups/{by_hand.id}/recovery")
    assert refusal(hidden) == (
        409,
        {
            "detail": "this backup's password file was chosen on the command line, so it is "
            f"not shown here: read {elsewhere} on the server"
        },
    )


def test_the_proton_copy_says_why_it_is_refused(proton: tuple[Env, Cloud]) -> None:
    env, _ = proton
    target = _add(env)
    refused = env.client.put(f"/api/backups/{target['id']}/proton-copy", json={"path": "/photos"})
    assert refusal(refused) == (422, {"detail": "choose a folder in My files on Proton Drive"})
    cloud_target = _add(env, label="Cloud", repository="rclone:mega:photos")
    remote = env.client.put(
        f"/api/backups/{cloud_target['id']}/proton-copy", json={"path": "/my-files/Backups"}
    )
    assert refusal(remote) == (
        422,
        {"detail": "only a backup in a folder or disk of this machine can be copied"},
    )


def test_without_proton_the_copy_says_it_is_not_available(env: Env) -> None:
    target = _add(env)
    refused = env.client.put(
        f"/api/backups/{target['id']}/proton-copy", json={"path": "/my-files/Backups"}
    )
    assert refusal(refused) == (
        422,
        {"detail": "a copy on Proton Drive is not available on this machine"},
    )
