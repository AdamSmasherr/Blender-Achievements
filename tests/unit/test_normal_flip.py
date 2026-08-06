"""Unit tests for achievements.achievements._is_normal_flip — the heuristic
that tells a genuine normals-flip apart from vertices simply moving around
(see the docstring on _is_normal_flip for the reasoning)."""

from achievements.achievements import _is_normal_flip


def test_true_for_near_exact_sign_reversal_within_tolerance():
    assert _is_normal_flip(100.0, -99.5) is True   # 0.5% off, well within 2%


def test_false_when_sign_does_not_change():
    assert _is_normal_flip(100.0, 50.0) is False


def test_false_when_magnitude_diverges_too_much_to_be_a_flip():
    assert _is_normal_flip(100.0, -50.0) is False


def test_false_when_either_measurement_is_missing():
    assert _is_normal_flip(None, -100.0) is False
    assert _is_normal_flip(100.0, None) is False
    assert _is_normal_flip(None, None) is False


def test_boundary_of_two_percent_tolerance():
    # |cur + prev| == 0.02 * |prev| exactly -> still counts (<=, not <).
    assert _is_normal_flip(100.0, -98.0) is True
    # Just past the boundary -> no longer a flip.
    assert _is_normal_flip(100.0, -97.9) is False
