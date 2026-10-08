import pytest

from photo_assistant.domain.remote_source import RemoteConfig, RemoteConfigError


def test_named_remote_and_path_make_the_rclone_target() -> None:
    config = RemoteConfig.from_mapping({"remote": "mega", "path": "Camera Uploads/2019"})
    assert config.target == "mega:Camera Uploads/2019"
    assert config.to_mapping() == {"remote": "mega", "path": "Camera Uploads/2019"}


def test_path_defaults_to_the_remote_root() -> None:
    assert RemoteConfig.from_mapping({"remote": "home-server"}).target == "home-server:"


@pytest.mark.parametrize(
    "remote",
    [
        "",  # missing
        "-mega",  # would read as an option
        " mega",
        ":local:",  # on-the-fly backends could carry credentials: named remotes only
        "mega:x",
        "../etc",
        "a/b",
        "x" * 65,
        "mega\n",
    ],
)
def test_only_plain_named_remotes_are_accepted(remote: str) -> None:
    with pytest.raises(RemoteConfigError):
        RemoteConfig.from_mapping({"remote": remote, "path": ""})


@pytest.mark.parametrize("path", ["a\nb", "x\x00", 5, "p" * 1025])
def test_bad_paths_are_rejected(path: object) -> None:
    with pytest.raises(RemoteConfigError):
        RemoteConfig.from_mapping({"remote": "mega", "path": path})


def test_remote_must_be_text() -> None:
    with pytest.raises(RemoteConfigError):
        RemoteConfig.from_mapping({"remote": 3})


def test_names_with_spaces_dots_and_at_signs_are_fine() -> None:
    assert RemoteConfig.from_mapping({"remote": "my nas.v2@home"}).remote == "my nas.v2@home"


# --- Proton Drive through Proton's own CLI (issue 8) --------------------------------------------


@pytest.mark.parametrize(
    "path", ["/photos", "/my-files", "/my-files/Trips/2019 Alps", "/my-files/été"]
)
def test_a_proton_source_is_the_photos_section_or_a_place_in_my_files(path: str) -> None:
    config = RemoteConfig.proton(path)
    assert (config.provider, config.path) == ("proton", path)
    assert RemoteConfig.from_mapping(config.to_mapping()) == config


@pytest.mark.parametrize(
    "path",
    ["", "photos", "/trash", "/shared-with-me/x", "/photos/album", "/my-files/../trash",
     "/my-files/a\nb", "/my-files/" + "x" * 2000, "/my-filesystem"],
)  # fmt: skip
def test_other_proton_paths_are_refused(path: str) -> None:
    with pytest.raises(RemoteConfigError):
        RemoteConfig.proton(path)


def test_rclone_settings_are_stored_as_before_and_unknown_providers_refused() -> None:
    plain = RemoteConfig.from_mapping({"remote": "mega", "path": "x"})
    assert plain.provider == "rclone" and plain.to_mapping() == {"remote": "mega", "path": "x"}
    with pytest.raises(RemoteConfigError, match="provider"):
        RemoteConfig.from_mapping({"provider": "dropbox", "remote": "x"})


def test_the_place_is_what_the_user_chose() -> None:
    assert RemoteConfig("mega", "Photos").place == "mega:Photos"
    assert RemoteConfig.proton("/my-files/Trips").place == "/my-files/Trips"
