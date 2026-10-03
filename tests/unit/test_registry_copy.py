"""User-facing achievement copy stays readable and implementation agnostic."""

from achievements.registry import ACHIEVEMENTS


def test_every_achievement_has_a_complete_tracking_explanation():
    for definition in ACHIEVEMENTS.values():
        text = definition.tracking_hint.strip()
        assert text, definition.id
        assert text[-1] in ".!?", definition.id


def test_tracking_explanations_do_not_expose_internal_terms():
    forbidden = ("baseline", "datablock", "depsgraph", "ctx.", "probe(")
    for definition in ACHIEVEMENTS.values():
        text = definition.tracking_hint.casefold()
        assert not any(term in text for term in forbidden), definition.id
        assert "datablock" not in definition.description.casefold(), definition.id


def test_cumulative_and_session_copy_is_explicit():
    assert "all Blender sessions" in ACHIEVEMENTS["GOOD_HABIT_1"].tracking_hint
    assert "finish a render" in ACHIEVEMENTS["DONUT_MASTER"].tracking_hint
