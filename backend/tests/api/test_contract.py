"""Every METHOD + path in docs/contracts/api-v1.md exists in the app (and is documented)."""

import re
from pathlib import Path

from photo_assistant.api.main import create_app
from tests.api.conftest import make_settings

CONTRACT = Path(__file__).parents[3] / "docs" / "contracts" / "api-v1.md"
_METHODS = r"(?:GET|POST|PUT|PATCH|DELETE)"
_TABLE_ROW = re.compile(rf"^\|\s*({_METHODS}(?:/{_METHODS})*)\s*\|\s*`(/api/[^`]*)`(.*?)\|")
_INLINE = re.compile(rf"`({_METHODS}(?:/{_METHODS})*) (/api/[^`]*)`")
_EXTRA_PATH = re.compile(r"·\s*`(/[^`]*)`")


def normalise(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "{}", path.rstrip("/"))


def contract_routes(text: str) -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for line in text.splitlines():
        pairs: list[tuple[str, str]] = []
        row = _TABLE_ROW.match(line)
        if row:
            methods, path, rest = row.groups()
            pairs.append((methods, path))
            # "`/api/assets/{id}/thumb` · `/preview`": a sibling of the previous path
            for extra in _EXTRA_PATH.findall(rest):
                pairs.append((methods, path.rsplit("/", 1)[0] + extra))
        pairs += _INLINE.findall(line)
        for methods, path in pairs:
            for method in methods.split("/"):
                found.add((method, normalise(path)))
    return found


def test_the_parser_reads_every_style_of_the_contract() -> None:
    sample = "\n".join(
        [
            "| GET | `/api/users` | \u2013 | `User[]` |",
            "| GET/PUT | `/api/albums/{id}/members` | x | y |",
            "| GET | `/api/assets/{id}/thumb` · `/preview` | \u2013 | WebP |",
            "Existing: `GET/POST /api/sources`, `POST /api/sources/{id}/scan`.",
        ]
    )
    assert contract_routes(sample) == {
        ("GET", "/api/users"),
        ("GET", "/api/albums/{}/members"),
        ("PUT", "/api/albums/{}/members"),
        ("GET", "/api/assets/{}/thumb"),
        ("GET", "/api/assets/{}/preview"),
        ("GET", "/api/sources"),
        ("POST", "/api/sources"),
        ("POST", "/api/sources/{}/scan"),
    }


def test_every_contract_route_is_served(tmp_path: Path) -> None:
    expected = contract_routes(CONTRACT.read_text(encoding="utf-8"))
    assert len(expected) > 50, "the parser found the tables"
    # with "send to a device" switched on: its routes are in the contract, and only then mounted
    app = create_app(make_settings(tmp_path / "data", send_to_device=True))
    served = {
        (method.upper(), normalise(path))
        for path, operations in app.openapi()["paths"].items()
        for method in operations
    }
    assert expected - served == set()
