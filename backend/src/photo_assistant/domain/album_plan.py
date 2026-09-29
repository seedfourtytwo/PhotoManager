"""AlbumPlan: what an AI (or anyone) proposes for an album. Never trusted, always validated.

The LLM's JSON is parsed strictly (``plan_from_json``) and then checked against what the user
may actually use (``validate``). A plan with problems is never shown as a proposal.
"""

from collections.abc import Collection, Mapping
from dataclasses import dataclass, field

MAX_CAPTION_CHARS = 200


class PlanFormatError(ValueError):
    """The data does not have the AlbumPlan shape at all."""


@dataclass(frozen=True, slots=True)
class PlanSection:
    title: str
    asset_ids: tuple[int, ...]
    layout_hint: str
    captions: Mapping[int, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AlbumPlan:
    title: str
    sections: tuple[PlanSection, ...]


@dataclass(frozen=True, slots=True)
class AssetSummary:
    """One photo as the planner sees it: no pixels, no paths."""

    id: int
    date: str  # YYYY-MM-DD
    place: str | None = None
    tags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class LibrarySummary:
    """The photos a plan may use (already filtered to what the user can see) and the layouts."""

    assets: tuple[AssetSummary, ...]
    layouts: tuple[str, ...]

    @property
    def asset_ids(self) -> frozenset[int]:
        return frozenset(a.id for a in self.assets)


def summary_lines(summary: LibrarySummary) -> str:
    """Compact, token-cheap text: ``id|date|place|tag,tag`` per line."""
    return "\n".join(f"{a.id}|{a.date}|{a.place or ''}|{','.join(a.tags)}" for a in summary.assets)


# --- validation ------------------------------------------------------------------------------


def validate(
    plan: AlbumPlan,
    allowed_asset_ids: Collection[int],
    known_layouts: Collection[str],
    max_caption_chars: int = MAX_CAPTION_CHARS,
) -> list[str]:
    """Every problem, in plain words. Empty list = the plan may be shown as a proposal."""
    problems: list[str] = []
    if not plan.title.strip():
        problems.append("the plan has no title")
    if not plan.sections:
        problems.append("the plan has no sections")
    used: set[int] = set()
    for number, section in enumerate(plan.sections, start=1):
        label = f"section {number} ('{section.title.strip()}')"
        found = _section_problems(section, allowed_asset_ids, known_layouts, used)
        found += _caption_problems(section, max_caption_chars)
        problems.extend(f"{label}: {p}" for p in found)
    return problems


def _section_problems(
    section: PlanSection,
    allowed: Collection[int],
    layouts: Collection[str],
    used: set[int],
) -> list[str]:
    problems: list[str] = []
    if not section.title.strip():
        problems.append("has no title")
    if not section.asset_ids:
        problems.append("has no photos")
    if section.layout_hint not in layouts:
        problems.append(f"unknown layout '{section.layout_hint}'")
    for asset_id in section.asset_ids:
        if asset_id not in allowed:
            problems.append(f"unknown photo id {asset_id}")
        elif asset_id in used:
            problems.append(f"photo {asset_id} is used more than once")
        used.add(asset_id)
    return problems


def _caption_problems(section: PlanSection, max_chars: int) -> list[str]:
    problems: list[str] = []
    members = set(section.asset_ids)
    for asset_id, text in section.captions.items():
        if asset_id not in members:
            problems.append(f"caption for photo {asset_id}, which is not in this section")
        elif len(text) > max_chars:
            problems.append(f"caption for photo {asset_id} is longer than {max_chars} characters")
    return problems


# --- parsing the wire shape ------------------------------------------------------------------
# {"title": str, "sections": [{"title": str, "asset_ids": [int], "layout_hint": str,
#                             "captions": [{"asset_id": int, "text": str}]}]}


def plan_from_json(data: object) -> AlbumPlan:
    obj = _mapping(data, "plan")
    sections = obj.get("sections")
    if not isinstance(sections, list):
        raise PlanFormatError("'sections' must be a list")
    return AlbumPlan(_text(obj, "title"), tuple(_section(s) for s in sections))


def _section(data: object) -> PlanSection:
    obj = _mapping(data, "section")
    return PlanSection(
        title=_text(obj, "title"),
        asset_ids=_ids(obj.get("asset_ids")),
        layout_hint=_text(obj, "layout_hint"),
        captions=_captions(obj.get("captions", [])),
    )


def _captions(data: object) -> dict[int, str]:
    if not isinstance(data, list):
        raise PlanFormatError("'captions' must be a list")
    result: dict[int, str] = {}
    for item in data:
        obj = _mapping(item, "caption")
        result[_int(obj.get("asset_id"))] = _text(obj, "text")
    return result


def _ids(data: object) -> tuple[int, ...]:
    if not isinstance(data, list):
        raise PlanFormatError("'asset_ids' must be a list of numbers")
    return tuple(_int(v) for v in data)


def _int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PlanFormatError(f"expected a photo id (whole number), got {value!r}")
    return value


def _mapping(data: object, what: str) -> Mapping[str, object]:
    if not isinstance(data, dict):
        raise PlanFormatError(f"{what} must be an object")
    return data


def _text(obj: Mapping[str, object], key: str) -> str:
    value = obj.get(key)
    if not isinstance(value, str):
        raise PlanFormatError(f"'{key}' must be text")
    return value
