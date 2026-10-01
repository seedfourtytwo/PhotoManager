"""Zero-shot auto-tags from CLIP embeddings (FEATURES 2.9, 2.10).

Each tag is a small *prompt ensemble*; the prompts' text embeddings are averaged into one
prototype. An image gets a tag when its similarity to the prototype beats its similarity to a
neutral "background" prototype by at least ``margin`` — CLIP similarities sit in a narrow band
(about 0.15 to 0.35), so a margin against a baseline is steadier than an absolute threshold.
"""

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

from photo_assistant.domain.vectors import Vector, dot, mean_direction


@dataclass(frozen=True, slots=True)
class TagSpec:
    name: str
    prompts: tuple[str, ...]
    screen_or_document: bool = False  # hides the photo from "memories" by default


VOCABULARY: tuple[TagSpec, ...] = (
    TagSpec("beach", ("a photo of a beach.", "a photo of the seaside.", "sand and sea.")),
    TagSpec("snow", ("a photo of snow.", "a snowy landscape.", "people playing in the snow.")),
    TagSpec("mountains", ("a photo of mountains.", "a mountain landscape.", "a hike in the alps.")),
    TagSpec("forest", ("a photo of a forest.", "trees in the woods.", "a path through a forest.")),
    TagSpec("lake", ("a photo of a lake.", "a river.", "calm water by the shore.")),
    TagSpec("garden", ("a photo of a garden.", "flowers in a garden.", "a green lawn.")),
    TagSpec("city", ("a photo of a city street.", "buildings in a city.", "an urban skyline.")),
    TagSpec("sunset", ("a photo of a sunset.", "the sky at sunset.", "a sunrise.")),
    TagSpec("food", ("a photo of food.", "a meal on a plate.", "a dish at a restaurant.")),
    TagSpec("pet", ("a photo of a dog.", "a photo of a cat.", "a pet.")),
    TagSpec("baby", ("a photo of a baby.", "a newborn baby.", "a toddler.")),
    TagSpec("party", ("a birthday party.", "a birthday cake with candles.", "a celebration.")),
    TagSpec("car", ("a photo of a car.", "a road trip in a car.", "a vehicle on a road.")),
    TagSpec("house", ("a photo of a house.", "the outside of a home.", "a room inside a house.")),
    TagSpec(
        "screenshot",
        ("a screenshot of a phone.", "a screenshot of a computer screen.", "a user interface."),
        screen_or_document=True,
    ),
    TagSpec(
        "document",
        ("a photo of a document.", "a page of printed text.", "a scanned letter."),
        screen_or_document=True,
    ),
    TagSpec(
        "receipt",
        ("a photo of a receipt.", "a shop receipt.", "an invoice."),
        screen_or_document=True,
    ),
    TagSpec(
        "meme",
        ("a meme.", "an image with caption text.", "a cartoon joke."),
        screen_or_document=True,
    ),
)

BACKGROUND_PROMPTS: tuple[str, ...] = ("a photo.", "a picture.", "an image of something.")


@dataclass(frozen=True, slots=True)
class TagParams:
    margin: float = 0.03  # tune on the laptop: higher = fewer, surer tags
    max_tags: int = 3

    def __post_init__(self) -> None:
        if self.max_tags < 1:
            raise ValueError(f"max_tags must be ≥ 1, got {self.max_tags}")


@dataclass(frozen=True, slots=True)
class TagScore:
    name: str
    score: float  # similarity margin over the background prototype


@dataclass(frozen=True, slots=True)
class TagModel:
    prototypes: dict[str, Vector]
    background: Vector
    prompt_count: int


def build_tag_model(
    embed_text: Callable[[str], Vector], vocabulary: Sequence[TagSpec] = VOCABULARY
) -> TagModel:
    """Embed every prompt once (the caller caches the result per model)."""
    prototypes = {
        spec.name: mean_direction([embed_text(p) for p in spec.prompts]) for spec in vocabulary
    }
    background = mean_direction([embed_text(p) for p in BACKGROUND_PROMPTS])
    count = sum(len(spec.prompts) for spec in vocabulary) + len(BACKGROUND_PROMPTS)
    return TagModel(prototypes, background, count)


def zero_shot_tags(image: Vector, model: TagModel, params: TagParams) -> list[TagScore]:
    """Tags whose margin clears ``params.margin``, best first. ``image`` must be normalised."""
    baseline = dot(image, model.background)
    scored = [
        TagScore(name, dot(image, prototype) - baseline)
        for name, prototype in model.prototypes.items()
    ]
    kept = [tag for tag in scored if tag.score >= params.margin]
    kept.sort(key=lambda tag: (-tag.score, tag.name))
    return kept[: params.max_tags]


def is_screen_or_document(
    tags: Iterable[TagScore], vocabulary: Sequence[TagSpec] = VOCABULARY
) -> bool:
    flagged = {spec.name for spec in vocabulary if spec.screen_or_document}
    return any(tag.name in flagged for tag in tags)
