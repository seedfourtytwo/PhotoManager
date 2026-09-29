import pytest

from photo_assistant.domain.tags import (
    BACKGROUND_PROMPTS,
    VOCABULARY,
    TagParams,
    TagScore,
    TagSpec,
    build_tag_model,
    is_screen_or_document,
    zero_shot_tags,
)
from photo_assistant.domain.vectors import Vector, normalise

VOCAB = (
    TagSpec("beach", ("a photo of a beach.", "sand and sea.")),
    TagSpec("snow", ("a photo of snow.",)),
    TagSpec("screenshot", ("a screenshot.",), screen_or_document=True),
)

# A fake text encoder: each prompt points along a fixed axis; background sits in the middle.
AXES = {
    "a photo of a beach.": (1.0, 0.1, 0.0, 0.0),
    "sand and sea.": (1.0, -0.1, 0.0, 0.0),
    "a photo of snow.": (0.0, 1.0, 0.0, 0.0),
    "a screenshot.": (0.0, 0.0, 1.0, 0.0),
}


def fake_embed(prompt: str) -> Vector:
    return normalise(AXES.get(prompt, (0.3, 0.3, 0.3, 1.0)))


def test_the_default_vocabulary_covers_the_feature_list() -> None:
    names = {spec.name for spec in VOCABULARY}
    wanted = {"beach", "snow", "mountains", "food", "document", "screenshot", "receipt"}
    assert wanted | {"pet", "baby", "sunset", "city", "forest"} <= names
    assert all(spec.prompts for spec in VOCABULARY)
    assert len(names) == len(VOCABULARY)
    assert BACKGROUND_PROMPTS


def test_prompts_of_a_tag_are_averaged_into_one_prototype() -> None:
    model = build_tag_model(fake_embed, VOCAB)
    assert model.prototypes["beach"] == pytest.approx((1.0, 0.0, 0.0, 0.0))
    assert model.prompt_count == 4 + len(BACKGROUND_PROMPTS)


def test_image_close_to_one_tag_gets_that_tag_only() -> None:
    model = build_tag_model(fake_embed, VOCAB)
    tags = zero_shot_tags(normalise((1.0, 0.05, 0.0, 0.2)), model, TagParams(margin=0.05))
    assert [t.name for t in tags] == ["beach"]
    assert tags[0].score > 0.05


def test_margin_filters_weak_tags_and_max_tags_caps_the_list() -> None:
    model = build_tag_model(fake_embed, VOCAB)
    image = normalise((1.0, 0.9, 0.8, 0.0))
    everything = zero_shot_tags(image, model, TagParams(margin=-1.0, max_tags=10))
    assert [t.name for t in everything] == ["beach", "snow", "screenshot"]
    assert [t.name for t in zero_shot_tags(image, model, TagParams(-1.0, 1))] == ["beach"]
    assert zero_shot_tags(image, model, TagParams(margin=1.5)) == []


def test_params_are_validated() -> None:
    with pytest.raises(ValueError):
        TagParams(margin=0.02, max_tags=0)


def test_screen_or_document_flag_from_tags() -> None:
    assert is_screen_or_document([TagScore("screenshot", 0.1)], VOCAB)
    assert not is_screen_or_document([TagScore("beach", 0.1)], VOCAB)


def test_default_vocabulary_flags_documents_and_receipts() -> None:
    assert is_screen_or_document([TagScore("receipt", 0.1)])
    assert is_screen_or_document([TagScore("document", 0.1)])
    assert not is_screen_or_document([TagScore("food", 0.1)])
