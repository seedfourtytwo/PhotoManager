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
