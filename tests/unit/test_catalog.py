"""Browsing behavior: combined filters, details access and no progress changes."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from achievements.registry import ACHIEVEMENTS, AchievementDefinition
from achievements.ui import catalog, panels
from achievements.ui.operators import ACHIEVEMENT_OT_details, ACHIEVEMENT_OT_profile_duplicate


DEFINITIONS = [
    AchievementDefinition("CUBE", "Goodbye, Cube!", "Delete the default cube.", category="Basics"),
    AchievementDefinition("RENDER", "First Image", "Render the default cube.", category="Rendering"),
    AchievementDefinition("SAVE", "Good Habit", "Save the file.", category="Basics"),
]


def test_search_matches_titles_and_conditions_case_insensitively():
    result = catalog.filter_achievements(DEFINITIONS, {"CUBE"}, query="  CuBe  ")
    assert [d.id for d in result] == ["CUBE", "RENDER"]
    assert catalog.filter_achievements(DEFINITIONS, set(), query="unfindable") == []


def test_search_status_and_category_are_intersected_without_reordering():
    result = catalog.filter_achievements(
        DEFINITIONS, {"CUBE"}, query="cube", status='LOCKED', category='Rendering')
    assert [d.id for d in result] == ["RENDER"]
    assert catalog.filter_achievements(
        DEFINITIONS, {"CUBE"}, query="cube", status='UNLOCKED', category='Rendering') == []
    assert catalog.filter_achievements(DEFINITIONS, {"CUBE"}) == DEFINITIONS


def test_clear_filters_restores_entire_catalog(monkeypatch):
    browser = SimpleNamespace(query="cube", status='LOCKED', category='Basics')
    context = SimpleNamespace(window_manager=SimpleNamespace(achievement_browser=browser))
    monkeypatch.setattr(catalog, "_tag_redraw_all", lambda: None)
    assert catalog.ACHIEVEMENT_OT_clear_filters().execute(context) == {'FINISHED'}
    assert catalog.filter_achievements(DEFINITIONS, {"CUBE"}, **vars(browser)) == DEFINITIONS


@pytest.mark.parametrize("compact", [False, True])
def test_filtered_list_keeps_overall_count_and_opens_correct_details(monkeypatch, compact):
    browser = SimpleNamespace(query="Unemployed", status='LOCKED', category='Milestones')
    context = SimpleNamespace(window_manager=SimpleNamespace(achievement_browser=browser))
    eng = MagicMock()
    eng.get_stats.return_value = {'unlocked': 1, 'total': len(ACHIEVEMENTS), 'percentage': 1.3}
    eng.get_unlocked_ids.return_value = ["UNEMPLOYED_1"]
    eng.is_unlocked.side_effect = lambda aid: aid == "UNEMPLOYED_1"
    monkeypatch.setattr(panels.engine, "get_engine", lambda: eng)
    monkeypatch.setattr(panels, "get_preferences", lambda _: SimpleNamespace(compact_sidebar=compact))
    monkeypatch.setattr(panels, "get_custom_icons", lambda: {})
    monkeypatch.setattr(panels, "get_achievement_progress", lambda aid: (18_000, ACHIEVEMENTS[aid].goal))
    layout = MagicMock()
    details = []
    labels = []
    progress = []
    for method in ("row", "column", "box", "split"):
        getattr(layout, method).return_value = layout
    layout.label.side_effect = lambda **kw: labels.append(kw.get('text'))
    layout.progress.side_effect = lambda **kw: progress.append(kw['text'])

    def operator(name, **kwargs):
        op = SimpleNamespace()
        if name == 'achievement.details':
            details.append(op)
        return op

    layout.operator.side_effect = operator
    panels.draw_achievements_list(layout, context, is_sidebar=True)
    assert [op.achievement_id for op in details] == ["UNEMPLOYED_2", "UNEMPLOYED_3"]
    assert f"Progress: 1/{len(ACHIEVEMENTS)} (1.3%)" in labels
    assert progress == ["5 h / 100 h", "5 h / 1000 h"]
    eng.unlock.assert_not_called()
    eng.save_state.assert_not_called()


def test_details_include_complete_condition_and_do_not_unlock(monkeypatch):
    definition = ACHIEVEMENTS['CYCLES_ENTHUSIAST']
    eng = MagicMock()
    eng.is_unlocked.return_value = False
    monkeypatch.setattr(panels.engine, "get_engine", lambda: eng)
    monkeypatch.setattr(panels, "get_custom_icons", lambda: {})
    monkeypatch.setattr(panels, "get_achievement_progress", lambda _: (10_000, 10_000))
    layout = MagicMock()
    for method in ("row", "column"):
        getattr(layout, method).return_value = layout
    panels.draw_achievement_details(layout, definition)
    text = ' '.join(call.kwargs.get('text', '') for call in layout.label.call_args_list)
    assert definition.description in text
    assert definition.tracking_hint in text
    assert 'Complete the condition above as well to unlock' in text
    eng.unlock.assert_not_called()
    eng.save_state.assert_not_called()
    tooltip = ACHIEVEMENT_OT_details.description(None, SimpleNamespace(achievement_id=definition.id))
    assert definition.title in tooltip and definition.description in tooltip


def test_stale_details_id_cancels_without_opening_popup():
    op = ACHIEVEMENT_OT_details()
    op.achievement_id = 'REMOVED'
    op.report = MagicMock()
    context = MagicMock()
    assert op.invoke(context, None) == {'CANCELLED'}
    context.window_manager.invoke_popup.assert_not_called()


def test_title_uses_left_aligned_label_and_separate_details_button():
    layout = MagicMock()
    row = MagicMock()
    layout.row.return_value = row
    button = SimpleNamespace()
    row.operator.return_value = button

    panels._draw_title(layout, 'GOODBYE_CUBE', 'Goodbye, Cube!')

    row.label.assert_called_once_with(text='Goodbye, Cube!')
    row.operator.assert_called_once_with(
        'achievement.details', text='', icon='INFO', emboss=False)
    assert button.achievement_id == 'GOODBYE_CUBE'


def test_compact_item_reserves_right_slot_when_progress_is_missing():
    """Empty progress cells must not change the title column's x position."""
    root = MagicMock()
    row = MagicMock()
    outer = MagicMock()
    icon_col = MagicMock()
    content = MagicMock()
    content_split = MagicMock()
    title_col = MagicMock()
    right_col = MagicMock()
    root.row.return_value = row
    row.split.return_value = outer
    outer.column.side_effect = [icon_col, content]
    content.split.return_value = content_split
    content_split.column.side_effect = [title_col, right_col]
    title_row = MagicMock()
    title_col.row.return_value = title_row
    title_row.operator.return_value = SimpleNamespace()
    icon_col.row.return_value = MagicMock()

    panels._draw_compact_item(
        root, 'GOODBYE_CUBE', SimpleNamespace(
            id='GOODBYE_CUBE', title='Goodbye, Cube!', progress_unit='COUNT'),
        {}, title_chars=20, prog=None)

    row.split.assert_called_once_with(factor=panels.COMPACT_ICON_FACTOR, align=True)
    content.split.assert_called_once_with(
        factor=panels.COMPACT_TITLE_FACTOR, align=True)
    assert content_split.column.call_count == 2
    title_row.label.assert_called_once_with(text='Goodbye, Cube!')


def test_duplicating_custom_profile_keeps_its_animation_and_sounds(monkeypatch):
    from achievements.ui import operators
    source = SimpleNamespace(name='My Xbox', animation_style='XBOX')
    for slot in operators.sounds.SLOTS:
        setattr(source, f'{slot}_sound', f'{slot}.wav')
        setattr(source, f'{slot}_volume', 0.4)
    duplicate = SimpleNamespace()
    profiles = MagicMock()
    profiles.add.return_value = duplicate
    profiles.__len__.return_value = 2
    prefs = SimpleNamespace(sound_profiles=profiles)
    monkeypatch.setattr(operators, 'get_preferences', lambda _: prefs)
    monkeypatch.setattr(operators.sounds, 'get_active_profile', lambda _: source)
    assert ACHIEVEMENT_OT_profile_duplicate().execute(None) == {'FINISHED'}
    assert duplicate.animation_style == 'XBOX'
    assert duplicate.unlock_sound == 'unlock.wav'
    assert duplicate.unlock_volume == 0.4
    assert prefs.active_profile_index == 1
