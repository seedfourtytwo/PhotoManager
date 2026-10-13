"""Send to a device over HTTP (spec 2026-10-13): a signed-in member makes a one-time link, a
device without a session collects the photos once.

Synthetic photos only. ``https://NAME`` stands for the Tailscale address (TestClient sets the
scheme the way uvicorn does behind its trusted proxy), ``http://NAME`` for plain http.
"""

import hashlib
import io
import logging
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from httpx2 import Response
from PIL import Image, ImageCms
from PIL.ExifTags import Base
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from photo_assistant.adapters.exiftool_reader import ExifToolReader
from photo_assistant.api.main import create_app
from photo_assistant.domain.handover import MAX_PHOTOS, MAX_WRONG_TOKENS_PER_CLIENT
from tests.api.conftest import (
    PIN,
    add_user,
    asset_id_of,
    import_folder,
    make_settings,
    refusal,
    services_of,
    user_id_of,
)
from tests.synthetic import write_photo

pytestmark = pytest.mark.integration

NAME = "photos.example.ts.net"
HTTPS, HTTP = f"https://{NAME}", f"http://{NAME}"
HOME = "http://192.168.1.20:8421"
GONE = (
    404,
    {
        "detail": "this link does not work any more: it was used, ran out or was cancelled; "
        "ask for a new one"
    },
)


def _oriented(path: Path) -> Path:
    """Stored lying on its side (EXIF orientation 6), with a colour profile, GPS and a camera:
    shown upright it is 100 x 200 with red on the right."""
    image = Image.new("RGB", (200, 100), "red")
    image.paste(Image.new("RGB", (200, 50), "blue"), (0, 50))
    write_photo(path, seed=0, image=image, camera="Test Cam", gps=(48.85, 2.35))
    with Image.open(path) as written:
        exif = written.getexif()
        exif[Base.Orientation] = 6
        profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
        written.save(path, "JPEG", quality=95, exif=exif, icc_profile=profile)
    return path


@dataclass
class World:
    admin: TestClient  # signed in at the https address
    ids: list[int]  # side.jpg, then IMG_20190704_1.jpg and _2
    source: int

    def client(self, base: str = HTTPS, peer: str = "100.64.0.7") -> TestClient:
        """Another device, with no session."""
        return TestClient(self.admin.app, base_url=base, client=(peer, 50000))

    def member(self, name: str, role: str = "member", base: str = HTTPS) -> TestClient:
        add_user(self.admin, name, role)
        client = TestClient(self.admin.app, base_url=base)
        assert client.post("/api/auth/login", json={"username": name, "pin": PIN}).is_success
        return client


@contextmanager
def _world(tmp_path: Path, **settings: object) -> Iterator[World]:
    values: dict[str, object] = {"send_to_device": True, "allowed_hosts": [NAME, "127.0.0.1"]}
    app = create_app(make_settings(tmp_path / "data", **(values | settings)))
    with TestClient(app, base_url=HTTPS) as admin:
        created = admin.post(
            "/api/setup", json={"username": "admin", "display_name": "C", "pin": PIN}
        )
        assert created.status_code == 201, created.text
        folder = tmp_path / "pics"
        _oriented(folder / "side.jpg")
        for n in (1, 2):
            write_photo(folder / f"IMG_20190704_{n}.jpg", seed=n, camera="Cam", gps=(1.0, 2.0))
        source = import_folder(admin, folder, "Pics")
        names = ["side.jpg", "IMG_20190704_1.jpg", "IMG_20190704_2.jpg"]
        yield World(admin, [asset_id_of(admin, source, n) for n in names], source)


@pytest.fixture
def world(tmp_path: Path) -> Iterator[World]:
    with _world(tmp_path) as made:
        yield made


def _send(client: TestClient, ids: list[int], **body: object) -> Response:
    request = {"ids": ids, "via": "here", "remove_details": True} | body
    return client.post("/api/handovers", json=request)


def _token(created: Response) -> str:
    assert created.status_code == 201, created.text
    url: str = created.json()["url"]
    return url.split("#", 1)[1]


def _collect(client: TestClient, token: str) -> Response:
    return client.post("/api/handovers/collect", data={"token": token})


def _look(client: TestClient, token: str) -> Response:
    return client.post("/api/handovers/look", json={"token": token})


# --- the switch -----------------------------------------------------------------------------


def test_switched_off_its_addresses_do_not_exist(tmp_path: Path) -> None:
    with _world(tmp_path, send_to_device=False) as world:
        unknown = world.admin.get("/api/no-such-thing")
        for method, path in [
            ("GET", "/api/handovers/options"),
            ("GET", "/api/handovers"),
            ("POST", "/api/handovers"),
            ("GET", "/api/handovers/1"),
            ("DELETE", "/api/handovers/1"),
            ("POST", "/api/handovers/look"),
            ("POST", "/api/handovers/collect"),
        ]:
            for client in (world.admin, world.client()):
                answer = client.request(method, path, json={"token": "x"})
                assert answer.status_code in (404, 405), f"{method} {path}"
                if method == "GET":
                    assert refusal(answer) == refusal(unknown)
        assert world.admin.get("/receive.html").status_code == 404


def test_it_is_off_unless_switched_on(tmp_path: Path) -> None:
    settings = make_settings(tmp_path / "data")
    assert settings.send_to_device is False
    assert (settings.send_to_device_minutes, settings.send_to_device_unencrypted) == (10, True)
    assert settings.send_to_device_remove_details is True
    assert settings.send_to_device_address is None and settings.send_to_device_listen is None


@pytest.mark.parametrize("minutes", [0, 61])
def test_the_lifetime_setting_takes_one_to_sixty_minutes(tmp_path: Path, minutes: int) -> None:
    with pytest.raises(ValueError, match="send_to_device_minutes"):
        make_settings(tmp_path / "data", send_to_device_minutes=minutes)


@pytest.mark.parametrize(
    "address", ["192.168.1.20:8421", "ftp://x", "http://x/path", "http://u:p@x", "http://"]
)
def test_the_home_address_must_be_a_plain_web_address(tmp_path: Path, address: str) -> None:
    with pytest.raises(ValueError, match="send_to_device_address"):
        make_settings(tmp_path / "data", send_to_device_address=address)
    ok = make_settings(tmp_path / "data", send_to_device_address="http://192.168.1.20:8421/")
    assert ok.send_to_device_address == HOME


# --- who may send what ----------------------------------------------------------------------


def test_the_senders_routes_need_a_session_and_the_receivers_do_not(world: World) -> None:
    nobody = world.client()
    paths = world.admin.app.openapi()["paths"]  # type: ignore[attr-defined]
    seen = 0
    for template, operations in paths.items():
        if not template.startswith("/api/handovers"):
            continue
        for method in operations:
            status = nobody.request(
                method.upper(), template.replace("{handover_id}", "1")
            ).status_code
            open_route = template.endswith(("/look", "/collect"))
            assert status == (404 if open_route else 401), f"{method} {template}"
            seen += 1
    assert seen == 7


def test_a_guest_never_sends(world: World) -> None:
    guest = world.member("gus", "guest")
    for answer in (
        _send(guest, world.ids),
        guest.get("/api/handovers/options"),
        guest.get("/api/handovers"),
    ):
        assert answer.status_code == 403
    assert services_of(world.admin).handovers.list_for(_admin_user(world)) == []


def _admin_user(world: World):  # type: ignore[no-untyped-def]
    services = services_of(world.admin)
    return services.accounts.get_user(user_id_of(world.admin, "admin"))


def test_only_photos_the_sender_sees_and_may_download_can_be_sent(world: World) -> None:
    lea = world.member("lea")
    private, shared = world.ids[0], world.ids[1]
    world.admin.patch(f"/api/assets/{private}/state", json={"private": True})
    assert _send(lea, [shared]).status_code == 201
    assert _send(lea, [shared, private]).status_code == 404, "another person's private photo"
    assert _send(lea, [shared, 999_999]).status_code == 404
    access = {"everyone": "view", "users": []}
    assert world.admin.put(f"/api/sources/{world.source}/access", json=access).is_success
    assert _send(lea, [shared]).status_code == 403, "view only: downloading is not allowed"
    assert _send(world.admin, [private]).status_code == 201, "the marker's own private photo"


def test_too_many_or_no_photos_are_refused(world: World) -> None:
    assert _send(world.admin, []).status_code == 422
    many = _send(world.admin, [*world.ids, *range(1000, 1000 + MAX_PHOTOS)])
    assert many.status_code in (404, 422)
    services_of(world.admin).handovers.check(MAX_PHOTOS, 1, encrypted=True, confirmed=False)
    huge = _send(world.admin, list(range(1, 10 * MAX_PHOTOS + 2)))
    assert huge.status_code == 422


# --- the link -------------------------------------------------------------------------------


def test_a_link_carries_the_senders_address_and_a_token_stored_only_as_a_hash(
    world: World,
) -> None:
    created = _send(world.admin, world.ids)
    body = created.json()
    token = _token(created)
    assert body["url"] == f"{HTTPS}/receive.html#{token}"
    assert (body["state"], body["count"], body["encrypted"]) == ("waiting", 3, True)
    assert body["details_removed"] is True and body["bytes"] > 0
    assert body["sent_by"] == {"id": user_id_of(world.admin, "admin"), "display_name": "C"}
    listed = world.admin.get("/api/handovers")
    assert token not in listed.text and "url" not in listed.json()[0]
    assert token not in world.admin.get(f"/api/handovers/{body['id']}").text
    row = services_of(world.admin).db.writer.execute("SELECT * FROM handover").fetchone()
    assert row["token_hash"] == hashlib.sha256(token.encode()).hexdigest()
    assert token not in str(tuple(row))


def test_the_options_say_where_a_link_can_point(tmp_path: Path) -> None:
    with _world(tmp_path, send_to_device_address=HOME, send_to_device_minutes=5) as world:
        options = world.admin.get("/api/handovers/options").json()
        assert options["addresses"] == [
            {"via": "here", "origin": HTTPS, "encrypted": True},
            {"via": "home", "origin": HOME, "encrypted": False},
        ]
        assert (options["minutes"], options["max_photos"]) == (5, MAX_PHOTOS)
        assert options["unencrypted_allowed"] is True and options["remove_details"] is True
        # at the server's own address no other device can follow the link: only the home one
        local = TestClient(world.admin.app, base_url="http://127.0.0.1")
        local.post("/api/auth/login", json={"username": "admin", "pin": PIN})
        assert [a["via"] for a in local.get("/api/handovers/options").json()["addresses"]] == [
            "home"
        ]
        home = _send(local, world.ids, via="home", unencrypted_ok=True)
        assert home.json()["url"].startswith(f"{HOME}/receive.html#")
        assert home.json()["encrypted"] is False


def test_a_link_to_this_machines_own_address_is_refused_with_what_to_do(world: World) -> None:
    local = TestClient(world.admin.app, base_url="http://127.0.0.1")
    local.post("/api/auth/login", json={"username": "admin", "pin": PIN})
    assert local.get("/api/handovers/options").json()["addresses"] == []
    for via in ("here", "home"):
        status, body = refusal(_send(local, world.ids, via=via, unencrypted_ok=True))
        assert status == 422 and "PA_SEND_TO_DEVICE_ADDRESS" in str(body)


# --- encrypted or not -----------------------------------------------------------------------


def test_over_plain_http_a_link_needs_the_senders_yes_each_time(world: World) -> None:
    plain = TestClient(world.admin.app, base_url=HTTP)
    plain.post("/api/auth/login", json={"username": "admin", "pin": PIN})
    assert plain.get("/api/handovers/options").json()["addresses"] == [
        {"via": "here", "origin": HTTP, "encrypted": False}
    ]
    status, body = refusal(_send(plain, world.ids))
    assert status == 409 and "not encrypted" in str(body)
    sent = _send(plain, world.ids, unencrypted_ok=True)
    assert sent.status_code == 201 and sent.json()["encrypted"] is False
    assert _send(plain, world.ids).status_code == 409, "the yes is not remembered"
    # and it is collected over plain http, with the page told so
    phone = world.client(HTTP)
    assert _look(phone, _token(sent)).json()["encrypted"] is False
    assert _collect(phone, _token(sent)).status_code == 200


def test_an_admin_can_switch_unencrypted_sending_off(tmp_path: Path) -> None:
    with _world(tmp_path, send_to_device_unencrypted=False) as world:
        plain = TestClient(world.admin.app, base_url=HTTP)
        plain.post("/api/auth/login", json={"username": "admin", "pin": PIN})
        assert plain.get("/api/handovers/options").json()["unencrypted_allowed"] is False
        status, body = refusal(_send(plain, world.ids, unencrypted_ok=True))
        assert status == 403 and "https" in str(body)
        assert _send(world.admin, world.ids).status_code == 201


def test_an_https_link_opened_over_plain_http_is_refused_and_cancelled(world: World) -> None:
    created = _send(world.admin, world.ids)
    token = _token(created)
    status, body = refusal(_look(world.client(HTTP), token))
    assert status == 403 and "https" in str(body)
    assert world.admin.get(f"/api/handovers/{created.json()['id']}").json()["state"] == "cancelled"
    assert refusal(_collect(world.client(), token)) == GONE


@pytest.mark.parametrize(("trusted", "believed"), [("172.18.0.1", True), ("127.0.0.1", False)])
def test_https_is_believed_only_from_the_trusted_proxy(
    tmp_path: Path, trusted: str, believed: bool
) -> None:
    """Whoever is not the proxy can write X-Forwarded-Proto too: it then counts for nothing."""
    with _world(tmp_path, trusted_proxies=trusted) as world:
        served = ProxyHeadersMiddleware(world.admin.app, trusted_hosts=trusted)  # type: ignore[arg-type]
        session = world.admin.cookies["pa_session"]
        claims = {
            "X-Forwarded-Proto": "https",
            "Origin": HTTPS if believed else HTTP,
            "Cookie": f"pa_session={session}; pa_session_fresh=1",
        }
        # no ``with``: the app is running already (the admin's client started it)
        c = TestClient(served, base_url=HTTP, client=("172.18.0.1", 40000), headers=claims)  # type: ignore[arg-type]
        (here,) = c.get("/api/handovers/options").json()["addresses"]
        assert here["encrypted"] is believed
        assert _send(c, world.ids).status_code == (201 if believed else 409)


# --- collecting -----------------------------------------------------------------------------


def test_the_page_learns_what_waits_without_using_the_link_up(world: World) -> None:
    lea = world.member("lea")
    created = _send(lea, world.ids[:2], remove_details=False)
    phone = world.client()
    for _ in range(3):
        looked = _look(phone, _token(created))
        assert looked.json() == {
            "count": 2,
            "sent_by": "Lea",
            "expires_at": created.json()["expires_at"],
            "encrypted": True,
            "details_removed": False,
        }
    assert lea.get(f"/api/handovers/{created.json()['id']}").json()["state"] == "waiting"


def test_one_photo_arrives_as_a_file_once(world: World) -> None:
    created = _send(world.admin, world.ids[1:2], remove_details=False)
    phone = world.client(peer="100.64.0.9")
    got = phone.post(
        "/api/handovers/collect",
        data={"token": _token(created)},
        headers={"User-Agent": "Mozilla/5.0 (iPhone)"},
    )
    assert got.status_code == 200 and got.headers["content-type"] == "image/jpeg"
    assert 'filename="IMG_20190704_1.jpg"' in got.headers["content-disposition"]
    assert got.headers["cache-control"] == "no-store"
    assert got.headers["referrer-policy"] == "no-referrer"
    assert got.headers["x-content-type-options"] == "nosniff"
    with Image.open(io.BytesIO(got.content)) as image:
        assert image.format == "JPEG" and image.size == (96, 64)
    after = world.admin.get(f"/api/handovers/{created.json()['id']}").json()
    assert (after["state"], after["redeemed_from"]) == ("redeemed", "100.64.0.9")
    assert after["redeemed_agent"] == "Mozilla/5.0 (iPhone)" and after["redeemed_at"]
    assert refusal(_collect(phone, _token(created))) == GONE
    assert refusal(_look(phone, _token(created))) == GONE


def test_several_photos_arrive_as_a_zip_named_like_a_download(world: World) -> None:
    created = _send(world.admin, world.ids, remove_details=False)
    got = _collect(world.client(), _token(created))
    assert got.headers["content-type"] == "application/zip"
    assert 'filename="photos-3.zip"' in got.headers["content-disposition"]
    assert got.headers["x-skipped"] == "0"
    with zipfile.ZipFile(io.BytesIO(got.content)) as archive:
        assert archive.namelist() == ["side.jpg", "IMG_20190704_1.jpg", "IMG_20190704_2.jpg"]


def test_the_token_is_taken_as_json_too_and_never_from_the_address(world: World) -> None:
    token = _token(_send(world.admin, world.ids[:1]))
    phone = world.client()
    assert refusal(phone.post(f"/api/handovers/collect?token={token}")) == GONE
    assert phone.post("/api/handovers/collect", json={"token": token}).status_code == 200


def test_every_token_that_does_not_work_gets_the_same_answer(world: World) -> None:
    used = _token(_send(world.admin, world.ids[:1]))
    assert _collect(world.client(), used).status_code == 200
    cancelled_one = _send(world.admin, world.ids[:1])
    assert world.admin.delete(f"/api/handovers/{cancelled_one.json()['id']}").status_code == 204
    expired = _send(world.admin, world.ids[:1])
    services_of(world.admin).db.writer.execute(  # its ten minutes are over
        "UPDATE handover SET expires_at = '2020-01-01T00:00:00+00:00' WHERE id = ?",
        (expired.json()["id"],),
    )
    assert world.admin.get(f"/api/handovers/{expired.json()['id']}").json()["state"] == "expired"
    phone = world.client()
    answers = []
    for token in ("never-issued", "", used, _token(cancelled_one), _token(expired)):
        for ask in (_look, _collect):
            answer = ask(phone, token)
            answers.append((refusal(answer), answer.headers["cache-control"]))
    assert answers == [(GONE, "no-store")] * 10
    assert refusal(phone.post("/api/handovers/look", content=b"not json")) == GONE


def test_wrong_tokens_are_limited_per_device(world: World) -> None:
    token = _token(_send(world.admin, world.ids[:1]))
    guesser = world.client(peer="100.64.0.66")
    for _ in range(MAX_WRONG_TOKENS_PER_CLIENT):
        assert refusal(_look(guesser, "guess")) == GONE
    status, body = refusal(_look(guesser, token))
    assert status == 429 and "wait" in str(body)
    assert _collect(guesser, token).status_code == 429
    assert _look(world.client(peer="100.64.0.7"), token).status_code == 200


# --- access is checked again when collecting ------------------------------------------------


def test_a_photo_the_sender_lost_since_is_left_out(world: World) -> None:
    lea = world.member("lea")
    created = _send(lea, world.ids, remove_details=False)
    world.admin.patch(f"/api/assets/{world.ids[0]}/state", json={"private": True})
    phone = world.client()
    assert _look(phone, _token(created)).json()["count"] == 2
    got = _collect(phone, _token(created))
    assert got.headers["x-skipped"] == "1"
    with zipfile.ZipFile(io.BytesIO(got.content)) as archive:
        assert archive.namelist() == ["IMG_20190704_1.jpg", "IMG_20190704_2.jpg"]


def test_nothing_is_sent_once_the_sender_lost_everything_or_was_disabled(world: World) -> None:
    lea = world.member("lea")
    lost, disabled = _send(lea, world.ids), _send(lea, world.ids)
    closed: dict[str, object] = {"everyone": None, "users": []}
    assert world.admin.put(f"/api/sources/{world.source}/access", json=closed).is_success
    assert refusal(_collect(world.client(), _token(lost))) == GONE
    open_again = {"everyone": "download", "users": []}
    assert world.admin.put(f"/api/sources/{world.source}/access", json=open_again).is_success
    lea_id = user_id_of(world.admin, "lea")
    assert world.admin.patch(f"/api/users/{lea_id}", json={"disabled": True}).is_success
    assert refusal(_look(world.client(), _token(disabled))) == GONE
    assert refusal(_collect(world.client(), _token(disabled))) == GONE


# --- details removed ------------------------------------------------------------------------


def _metadata(content: bytes, tmp_path: Path) -> tuple[object, object]:
    out = tmp_path / "received.jpg"
    out.write_bytes(content)
    reader = ExifToolReader()
    try:
        (meta,) = reader.read_many([out])
    finally:
        reader.close()
    return meta.latitude, meta.camera_model


def test_a_copy_without_details_has_no_location_or_camera_and_still_looks_right(
    world: World, tmp_path: Path
) -> None:
    library = services_of(world.admin).store
    view = services_of(world.admin).repo.get_asset(world.ids[0])
    assert view is not None
    original = library.absolute(view.library_path)
    before = hashlib.sha256(original.read_bytes()).hexdigest()

    got = _collect(world.client(), _token(_send(world.admin, world.ids[:1])))
    assert 'filename="photo.jpg"' in got.headers["content-disposition"], "no date, no device"
    assert _metadata(got.content, tmp_path) == (None, None)
    with Image.open(io.BytesIO(got.content)) as image:
        assert image.size == (100, 200), "upright, though the orientation tag is gone"
        assert image.getexif().get(Base.Orientation, 1) == 1
        assert image.info.get("icc_profile"), "the colour profile stays"
        assert "xmp" not in image.info and not image.getexif().get_ifd(0x8825)  # no GPS block
        red, _, blue = image.convert("RGB").getpixel((90, 100))  # type: ignore[misc]
        assert red > 180 and blue < 80, "what was the top is on the right"
        red, _, blue = image.convert("RGB").getpixel((10, 100))  # type: ignore[misc]
        assert blue > 180 and red < 80
    assert hashlib.sha256(original.read_bytes()).hexdigest() == before, "the original is untouched"
    assert not list((tmp_path / "data" / "tmp").glob("download-*")), "temporary copies are gone"


def test_details_stay_when_the_sender_keeps_them(world: World, tmp_path: Path) -> None:
    created = _send(world.admin, world.ids[:1], remove_details=False)
    assert created.json()["details_removed"] is False
    got = _collect(world.client(), _token(created))
    assert 'filename="side.jpg"' in got.headers["content-disposition"]
    latitude, camera = _metadata(got.content, tmp_path)
    assert camera == "Test Cam" and latitude == pytest.approx(48.85, abs=0.01)


def test_files_in_a_zip_without_details_have_neutral_names(world: World) -> None:
    got = _collect(world.client(), _token(_send(world.admin, world.ids)))
    with zipfile.ZipFile(io.BytesIO(got.content)) as archive:
        assert archive.namelist() == ["photo.jpg", "photo_2.jpg", "photo_3.jpg"]


# --- the trail, and Cancel ------------------------------------------------------------------


def test_the_trail_shows_who_sent_what_and_cancel_stops_a_waiting_link(world: World) -> None:
    lea, tom = world.member("lea"), world.member("tom")
    leas = _send(lea, world.ids[:2])
    toms = _send(tom, world.ids[:1], remove_details=False)
    assert [h["id"] for h in lea.get("/api/handovers").json()] == [leas.json()["id"]]
    everyone = world.admin.get("/api/handovers").json()
    assert [(h["sent_by"]["display_name"], h["count"], h["state"]) for h in everyone] == [
        ("Tom", 1, "waiting"),
        ("Lea", 2, "waiting"),
    ]
    assert [h["details_removed"] for h in everyone] == [False, True]
    assert lea.get(f"/api/handovers/{toms.json()['id']}").status_code == 404
    assert lea.delete(f"/api/handovers/{toms.json()['id']}").status_code == 404
    assert world.admin.delete(f"/api/handovers/{toms.json()['id']}").status_code == 204
    assert refusal(_collect(world.client(), _token(toms))) == GONE
    status, body = refusal(world.admin.delete(f"/api/handovers/{toms.json()['id']}"))
    assert (status, body) == (409, {"detail": "this link was already cancelled"})
    assert _collect(world.client(), _token(leas)).status_code == 200
    assert lea.delete(f"/api/handovers/{leas.json()['id']}").status_code == 409


def test_the_daily_clean_up_forgets_hand_overs_after_ninety_days(world: World) -> None:
    services = services_of(world.admin)
    _send(world.admin, world.ids[:1])
    services.db.writer.execute("UPDATE handover SET created_at = '2020-01-01T00:00:00+00:00'")
    _send(world.admin, world.ids[:1])
    services.ops.periodic.tick()
    assert len(world.admin.get("/api/handovers").json()) == 1


# --- the token never reaches a log ----------------------------------------------------------


def test_the_token_is_in_no_log_line(world: World, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    logging.getLogger("photo_assistant").propagate = True
    try:
        created = _send(world.admin, world.ids)
        token = _token(created)
        phone = world.client()
        _look(phone, token)
        _look(world.client(HTTP), "wrong-" + token)
        _collect(phone, token)
        _collect(phone, token)
        world.admin.get("/api/handovers")
    finally:
        logging.getLogger("photo_assistant").propagate = False
    assert caplog.records, "something was logged at all"
    logged = "\n".join(f"{r.getMessage()} {vars(r)}" for r in caplog.records)
    assert token not in logged
    # and no route could put it in an access log: none takes it in its address
    paths = world.admin.app.openapi()["paths"]  # type: ignore[attr-defined]
    for template in ("/api/handovers/look", "/api/handovers/collect"):
        assert list(paths[template]) == ["post"]
        assert "parameters" not in paths[template]["post"]
