"""A photo's dominant colour: the placeholder a grid shows until the thumbnail arrives."""

from photo_assistant.domain.colour import dominant_colour

RED = (200, 30, 30)
BLUE = (20, 40, 210)


def test_one_colour_is_itself_as_hex() -> None:
    assert dominant_colour([RED] * 10) == "#c81e1e"


def test_the_most_common_colour_wins_over_the_average() -> None:
    # a mean of 60 % blue and 40 % red would be a purple that is in the photo nowhere
    assert dominant_colour([BLUE] * 6 + [RED] * 4) == "#1428d2"


def test_close_shades_count_together_and_give_their_mean() -> None:
    sky = [(100, 150, 200), (104, 152, 206), (98, 148, 198)]
    assert dominant_colour([*sky, RED, (0, 0, 0)]) == "#6596c9"


def test_a_tie_goes_to_the_colour_seen_first() -> None:
    assert dominant_colour([RED, BLUE]) == "#c81e1e"


def test_black_and_white_are_colours_too() -> None:
    assert dominant_colour([(0, 0, 0)] * 3 + [(255, 255, 255)]) == "#000000"
    assert dominant_colour([(255, 255, 255)]) == "#ffffff"


def test_no_pixels_give_no_colour() -> None:
    assert dominant_colour([]) is None
