"""
AddonPreferences: settings, colour palettes, sound profiles, and the
Progress Data / Activity Calendar / Achievements sections at the bottom of
the Preferences tab.
"""

import bpy

from .. import sounds
from .. import toast
from .calendar import _calendar_colors_changed, draw_activity_calendar
from .formatters import CALENDAR_COLORS, CALENDAR_LEVEL_LABELS, CALENDAR_LEVEL_SHORT
from .helpers import ADDON_PACKAGE, _tag_redraw_all
from .icons import request_rebuild as _request_icon_rebuild
from .panels import draw_achievements_list
from .widgets import _draw_sound_slots_grid


def _section(layout, idname, title, icon='NONE', default_closed=True):
    """Згортна секція налаштувань. Повертає `(header, body)`.

    `body` дорівнює None, коли секцію згорнуто, і тоді її вміст не малюється
    взагалі. Саме це, а не самі трикутнички, тут головне: список ачивок — це
    79 викликів template_icon, і згорнутим він не коштує нічого. Той самий
    прийом, що вже застосований до панелі календаря в сайдбарі.

    `layout.panel()` є з Blender 4.1, а аддон вимагає 4.4+, тож запасний
    варіант із box'ом — не про старі версії, а щоб малювання не падало в
    layout-заглушках, у яких панель просто не реалізована.
    """
    panel = getattr(layout, "panel", None)
    if panel is None:
        box = layout.box()
        header = box.row(align=True)
        header.label(text=title, icon=icon)
        return header, box

    header, body = panel(idname, default_closed=default_closed)
    header.label(text=title, icon=icon)
    return header, body


def _toast_surfaces_changed(self, context):
    """Перевішує draw-колбеки тоста: набір редакторів щойно змінився.

    Хендлери реєструються один раз на весь набір, тож без переустановки
    перемикач подіяв би аж наступного вмикання аддона.
    """
    toast.remove_handler()
    toast.ensure_handler()
    _tag_redraw_all()


class ACHIEVEMENT_SoundProfile(bpy.types.PropertyGroup):
    """A user-defined profile: pop-up animation + four sound slots."""
    name: bpy.props.StringProperty(name="Profile Name", default="My Profile")

    animation_style: bpy.props.EnumProperty(
        name="Animation",
        items=(
            ('STEAM', "Steam", "Card rises from the bottom; multiple toasts stack"),
            ('XBOX', "Xbox", "Green circle expands into a banner; toasts play one by one"),
            ('PS', "PlayStation", "Card slides in from the right; toasts play one by one"),
        ),
        default='STEAM',
        description="Which pop-up animation this profile uses"
    )

    unlock_sound: bpy.props.StringProperty(
        name="Unlock", subtype='FILE_PATH', default="",
        description="Sound played when a normal achievement unlocks")
    unlock_volume: bpy.props.FloatProperty(
        name="Volume", default=1.0, min=0.0, max=1.0, subtype='FACTOR')

    rare_unlock_sound: bpy.props.StringProperty(
        name="Rare Unlock", subtype='FILE_PATH', default="",
        description="Sound played when a rare achievement unlocks")
    rare_unlock_volume: bpy.props.FloatProperty(
        name="Volume", default=1.0, min=0.0, max=1.0, subtype='FACTOR')

    end_sound: bpy.props.StringProperty(
        name="Notification End", subtype='FILE_PATH', default="",
        description="Sound played when a normal achievement notification starts fading out")
    end_volume: bpy.props.FloatProperty(
        name="Volume", default=1.0, min=0.0, max=1.0, subtype='FACTOR')

    rare_end_sound: bpy.props.StringProperty(
        name="Rare Notification End", subtype='FILE_PATH', default="",
        description="Sound played when a rare achievement notification starts fading out")
    rare_end_volume: bpy.props.FloatProperty(
        name="Volume", default=1.0, min=0.0, max=1.0, subtype='FACTOR')


class ACHIEVEMENT_UL_sound_profiles(bpy.types.UIList):
    """List of custom sound profiles."""

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            layout.prop(item, "name", text="", emboss=False)
        else:
            layout.label(text="")


class ACHIEVEMENT_AddonPreferences(bpy.types.AddonPreferences):
    bl_idname = ADDON_PACKAGE

    enable_sound: bpy.props.BoolProperty(
        name="Play Notification Sound",
        default=True,
        description="Play audio chime when unlocking achievements"
    )
    enable_toast: bpy.props.BoolProperty(
        name="Show Viewport Notifications",
        default=True,
        description="Show custom GPU achievement notifications in 3D Viewport"
    )
    toast_duration: bpy.props.FloatProperty(
        name="Notification Duration (seconds)",
        default=8.0,
        min=4.0,
        max=20.0,
        description="Display duration for viewport achievement notifications"
    )

    # ---- Sound scheme ----
    sound_preset: bpy.props.EnumProperty(
        name="Sound Preset",
        items=sounds.PRESET_ITEMS,
        default='STEAM',
        description="Which set of achievement sounds to use"
    )
    master_volume: bpy.props.FloatProperty(
        name="Master Volume",
        default=1.0, min=0.0, max=1.0, subtype='FACTOR',
        description="Global volume applied on top of every individual sound volume"
    )
    unlock_volume: bpy.props.FloatProperty(
        name="Volume", default=1.0, min=0.0, max=1.0, subtype='FACTOR')
    rare_unlock_volume: bpy.props.FloatProperty(
        name="Volume", default=1.0, min=0.0, max=1.0, subtype='FACTOR')
    end_volume: bpy.props.FloatProperty(
        name="Volume", default=1.0, min=0.0, max=1.0, subtype='FACTOR')
    rare_end_volume: bpy.props.FloatProperty(
        name="Volume", default=1.0, min=0.0, max=1.0, subtype='FACTOR')

    # Власні файли звуку для вбудованих пресетів. Порожньо → бандлений файл
    # пресету. Кожен пресет тримає свій набір, щоб зміна звуку для Steam не
    # чіпала Xbox/PlayStation.
    _OVERRIDE_DESC = "Leave empty to use the bundled sound for this preset"
    steam_unlock_sound: bpy.props.StringProperty(
        name="Sound", subtype='FILE_PATH', default="", description=_OVERRIDE_DESC)
    steam_rare_unlock_sound: bpy.props.StringProperty(
        name="Sound", subtype='FILE_PATH', default="", description=_OVERRIDE_DESC)
    steam_end_sound: bpy.props.StringProperty(
        name="Sound", subtype='FILE_PATH', default="", description=_OVERRIDE_DESC)
    steam_rare_end_sound: bpy.props.StringProperty(
        name="Sound", subtype='FILE_PATH', default="", description=_OVERRIDE_DESC)

    xbox_unlock_sound: bpy.props.StringProperty(
        name="Sound", subtype='FILE_PATH', default="", description=_OVERRIDE_DESC)
    xbox_rare_unlock_sound: bpy.props.StringProperty(
        name="Sound", subtype='FILE_PATH', default="", description=_OVERRIDE_DESC)
    xbox_end_sound: bpy.props.StringProperty(
        name="Sound", subtype='FILE_PATH', default="", description=_OVERRIDE_DESC)
    xbox_rare_end_sound: bpy.props.StringProperty(
        name="Sound", subtype='FILE_PATH', default="", description=_OVERRIDE_DESC)

    ps_unlock_sound: bpy.props.StringProperty(
        name="Sound", subtype='FILE_PATH', default="", description=_OVERRIDE_DESC)
    ps_rare_unlock_sound: bpy.props.StringProperty(
        name="Sound", subtype='FILE_PATH', default="", description=_OVERRIDE_DESC)
    ps_end_sound: bpy.props.StringProperty(
        name="Sound", subtype='FILE_PATH', default="", description=_OVERRIDE_DESC)
    ps_rare_end_sound: bpy.props.StringProperty(
        name="Sound", subtype='FILE_PATH', default="", description=_OVERRIDE_DESC)

    sound_profiles: bpy.props.CollectionProperty(type=ACHIEVEMENT_SoundProfile)
    active_profile_index: bpy.props.IntProperty(name="Active Profile", default=0)
    show_rare_glow: bpy.props.BoolProperty(
        name="Rare Golden Glow Shader",
        default=True,
        description="Enable GLSL conic golden ray shader for rare achievements"
    )
    show_in_sidebar: bpy.props.BoolProperty(
        name="Show Achievements List in Sidebar (N-panel)",
        default=True,
        description="Display the full achievements list in the N-panel sidebar"
    )
    show_calendar_in_sidebar: bpy.props.BoolProperty(
        name="Show Activity Calendar in Sidebar (N-panel)",
        default=True,
        description="Display the activity heatmap panel in the N-panel sidebar"
    )
    toast_scale: bpy.props.FloatProperty(
        name="Notification Scale",
        default=1.0, min=0.5, max=2.0, step=5, precision=2,
        description="Size of the notification card, on top of Blender's own UI scale"
    )
    toast_anchor: bpy.props.EnumProperty(
        name="Notification Position",
        items=[
            ('STYLE', "Style Default", "Where the chosen style puts it: bottom-right for Steam and PlayStation, bottom-centre for Xbox"),
            ('BOTTOM_LEFT', "Bottom Left", "Bottom left corner of the editor"),
            ('BOTTOM_CENTER', "Bottom Centre", "Bottom centre of the editor"),
            ('BOTTOM_RIGHT', "Bottom Right", "Bottom right corner of the editor"),
            ('TOP_LEFT', "Top Left", "Top left corner of the editor"),
            ('TOP_CENTER', "Top Centre", "Top centre of the editor"),
            ('TOP_RIGHT', "Top Right", "Top right corner of the editor"),
        ],
        default='STYLE',
        description="Corner the notification slides in from and sticks to"
    )
    toast_in_any_editor: bpy.props.BoolProperty(
        name="Show in Any Editor",
        default=True,
        description=("When no 3D Viewport is open in any window, draw the pop-up "
                     "in the largest other editor (Shader/Compositor, Image, "
                     "Sequencer, Text, ...) instead of silently skipping it"),
        update=_toast_surfaces_changed
    )
    compact_sidebar: bpy.props.BoolProperty(
        name="Compact List in Sidebar (N-panel)",
        default=False,
        description=("One line per achievement — small icon, name and progress "
                     "bar, no description. Fits the whole list in a narrow "
                     "sidebar. Does not affect the list in these preferences")
    )
    rounded_corners: bpy.props.BoolProperty(
        name="Rounded Card & Icon Corners",
        default=True,
        description="Round the corners of the notification card and its icon (Steam / PlayStation styles)"
    )

    def _draw_colors(self, layout, active_style):
        """Палітра спливаючої нотифікації + календаря активності.

        Раніше тут була ОКРЕМА вкладка Steam/Xbox/PlayStation для вибору, чию
        палітру редагувати — виглядала майже ідентично до справжнього
        перемикача пресету нижче (Profiles → Sound Preset), і користувачі
        плутали одне з іншим: обирали стиль тут, чекали, що ачивки почнуть
        спливати саме так, а насправді анімацію й далі визначав пресет
        нижче. Тому окремого вибору більше нема — палітра завжди показує
        стиль, який ЗАРАЗ активний (active_style), той самий, що й малює
        спливаюче вікно.
        """
        # --- палітра спливаючої нотифікації
        note = layout.box()
        hdr = note.row(align=True)
        hdr.label(text=f"Pop-up Notification — {toast.STYLE_LABELS.get(active_style, active_style)}",
                  icon='SEQ_STRIP_DUPLICATE')
        hint = hdr.row()
        hint.enabled = False
        hint.alignment = 'RIGHT'
        hint.label(text="change style under Profiles below", icon='INFO')

        grid = note.grid_flow(row_major=True, columns=2, even_columns=True, align=False)
        for key in toast.STYLE_COLOR_KEYS.get(active_style, ()):
            grid.prop(self, toast.color_prop_name(active_style, key))

        actions = note.row(align=True)
        preview = actions.row(align=True)
        preview.operator("achievement.test_toast", text="Preview",
                         icon='PLAY').rare = False
        preview.operator("achievement.test_toast", text="Preview Rare",
                         icon='SOLO_ON').rare = True
        reset = actions.row(align=True)
        reset.alignment = 'RIGHT'
        reset.operator("achievement.reset_colors", text="Reset",
                       icon='LOOP_BACK').target = active_style

        # --- палітра іконки ачивки
        # Спільна для всіх стилів: картинки одні й ті самі, і колір під них
        # підбирають один раз, а не окремо під кожну анімацію.
        ico = layout.box()
        ico.label(text="Achievement Icon", icon='IMAGE_RGB_ALPHA')
        ico_grid = ico.grid_flow(row_major=True, columns=2, even_columns=True, align=False)
        for key in toast.ICON_COLOR_KEYS:
            ico_grid.prop(self, toast.icon_color_prop_name(key))
        ico_reset = ico.row(align=True)
        ico_reset.alignment = 'RIGHT'
        ico_reset.operator("achievement.reset_colors", text="Reset",
                           icon='LOOP_BACK').target = 'ICON'

        # --- палітра календаря активності
        cal = layout.box()
        cal.label(text="Activity Calendar", icon='TIME')
        swatches = cal.grid_flow(row_major=True, columns=len(CALENDAR_COLORS),
                                 even_columns=True, align=True)
        for i in range(len(CALENDAR_COLORS)):
            col_i = swatches.column(align=True)
            col_i.prop(self, f"cal_col_{i}", text="")
            # Без alignment: рядок лежить усередині column(align=True), а саме
            # на такому поєднанні валився ui::item_align (див. календар вище).
            caption = col_i.row()
            caption.enabled = False
            caption.label(text=CALENDAR_LEVEL_SHORT[i])
        cal_reset = cal.row(align=True)
        cal_reset.alignment = 'RIGHT'
        cal_reset.operator("achievement.reset_colors", text="Reset",
                           icon='LOOP_BACK').target = 'CALENDAR'

    def draw(self, context):
        """Шість згортних секцій. Відкриті одразу лише Settings і Colours —
        решта (профілі, скидання прогресу, календар, список ачивок) чекають на
        клік, і доти нічого не малюють."""
        layout = self.layout
        style = toast._get_style()

        _hdr, body = _section(layout, "achievements_settings", "Settings",
                              icon='PREFERENCES', default_closed=False)
        if body:
            self._draw_settings(body, style)

        _hdr, body = _section(layout, "achievements_colours", "Colours",
                              icon='COLOR', default_closed=False)
        if body:
            self._draw_colors(body, style)

        # Export/Import живуть у заголовку, як і раніше жили в рядку назви.
        header, body = _section(layout, "achievements_profiles", "Profiles",
                                icon='SOUND')
        io = header.row(align=True)
        io.alignment = 'RIGHT'
        io.operator("achievement.profiles_export", text="Export", icon='EXPORT')
        io.operator("achievement.profiles_import", text="Import", icon='IMPORT')
        if body:
            self._draw_profiles(body)

        _hdr, body = _section(layout, "achievements_data", "Progress Data",
                              icon='FILE_REFRESH')
        if body:
            self._draw_progress_data(body)

        # Прапорець show_calendar_in_sidebar тут свідомо не діє — він ховає
        # панель у N-сайдбарі, і сховавши її там, історію все одно можна
        # подивитись тут.
        _hdr, body = _section(layout, "achievements_calendar", "Activity Calendar",
                              icon='TIME')
        if body:
            # Вікно налаштувань значно ширше за сайдбар, і сітка на всю ширину
            # виглядала б розігнаною. Обмежуємо її звичайним split'ом — на
            # відміну від alignment він не втручається у вирівнювання кнопок.
            cal_split = body.split(factor=0.5)
            draw_activity_calendar(cal_split.column())
            cal_split.column()      # порожня половина, лише щоб задати ширину

        _hdr, body = _section(layout, "achievements_list", "Achievements",
                              icon='SOLO_ON')
        if body:
            draw_achievements_list(body, context, icon_scale=3.4375)

    def _draw_settings(self, layout, style):
        col_s = layout.column(align=True)
        col_s.prop(self, "enable_sound")
        col_s.prop(self, "enable_toast")
        # Все, що описує саму картку, гасне разом із нею.
        col_toast = col_s.column(align=True)
        col_toast.enabled = self.enable_toast
        col_toast.prop(self, "toast_duration")
        col_toast.prop(self, "toast_scale")
        col_toast.prop(self, "toast_anchor")
        col_toast.prop(self, "toast_in_any_editor")
        # Золоте сяйво є лише в Steam-картці: Xbox малює діамант, а трофеї
        # PlayStation золотого ореолу не мають узагалі (toast.GLOW_STYLES).
        row_rg = col_s.row()
        row_rg.enabled = (style in toast.GLOW_STYLES)
        row_rg.prop(self, "show_rare_glow")
        # Закруглення стосується лише Steam-стилю картки
        row_rc = col_s.row()
        row_rc.enabled = (style == 'STEAM')
        row_rc.prop(self, "rounded_corners")
        col_s.prop(self, "show_in_sidebar")
        row_compact = col_s.row()
        row_compact.enabled = self.show_in_sidebar
        row_compact.prop(self, "compact_sidebar")
        col_s.prop(self, "show_calendar_in_sidebar")

    def _draw_profiles(self, layout):
        row_p = layout.row(align=True)
        row_p.prop(self, "sound_preset", expand=True)
        layout.prop(self, "master_volume", slider=True)

        if not self.enable_sound:
            info = layout.row()
            info.enabled = False
            info.label(text="Sound is disabled above — enable it to hear these.", icon='INFO')

        if self.sound_preset == 'CUSTOM':
            row_l = layout.row()
            row_l.template_list("ACHIEVEMENT_UL_sound_profiles", "", self,
                                "sound_profiles", self, "active_profile_index", rows=3)
            col_b = row_l.column(align=True)
            col_b.operator("achievement.profile_add", text="", icon='ADD')
            col_b.operator("achievement.profile_remove", text="", icon='REMOVE')
            col_b.separator()
            col_b.operator("achievement.profile_duplicate", text="", icon='DUPLICATE')

            profile = sounds.get_active_profile(self)
            if profile is None:
                layout.label(text="Add a profile to define your own animation and sounds.", icon='INFO')
            else:
                anim = layout.box()
                anim.label(text="Pop-up Animation:", icon='SEQ_STRIP_DUPLICATE')
                anim.row().prop(profile, "animation_style", expand=True)
                _draw_sound_slots_grid(layout, self, profile=profile)
        else:
            _draw_sound_slots_grid(layout, self, profile=None)

    def _draw_progress_data(self, layout):
        """Скидання прогресу живе тільки тут, а не в сайдбарі: дія незворотна,
        і їй не місце за один промах миші від списку ачивок."""
        row_reset = layout.row()
        row_reset.alert = True
        row_reset.operator("achievement.reset_progress", text="Reset All Progress", icon='TRASH')
        note = layout.row()
        note.enabled = False
        note.label(text="Erases every unlocked achievement and all cumulative stats.", icon='ERROR')


def _toast_colors_changed(self, context):
    _tag_redraw_all()


def _icon_colors_changed(self, context):
    """Колір іконок змінився.

    Картка фарбує іконку шейдером і підхопить новий колір сама; прев'юшки
    списку намальовані пікселями, тож їх треба перепекти — із затримкою, щоб
    перетягування пікера не спинало інтерфейс (див. icons.request_rebuild).
    """
    _request_icon_rebuild()
    _tag_redraw_all()


def _install_color_props(cls):
    """Додає властивості кольорів у AddonPreferences циклом.

    Полів вісімнадцять і всі однакові з точністю до назви й дефолту —
    записані руками, вони зайняли б пів файлу й розсинхронізувалися б із
    палітрами в toast.py при першій же правці.
    """
    ann = cls.__annotations__
    for style, keys in toast.STYLE_COLOR_KEYS.items():
        for key in keys:
            ann[toast.color_prop_name(style, key)] = bpy.props.FloatVectorProperty(
                name=toast.STYLE_COLOR_LABELS.get(key, key),
                description=toast.STYLE_COLOR_DESCRIPTIONS.get(key, ""),
                subtype='COLOR_GAMMA',
                size=3, min=0.0, max=1.0, default=toast.STYLE_COLOR_DEFAULTS[style][key],
                update=_toast_colors_changed,
            )
    for key in toast.ICON_COLOR_KEYS:
        ann[toast.icon_color_prop_name(key)] = bpy.props.FloatVectorProperty(
            name=toast.ICON_COLOR_LABELS.get(key, key),
            description=toast.ICON_COLOR_DESCRIPTIONS.get(key, ""),
            subtype='COLOR_GAMMA',
            size=3, min=0.0, max=1.0, default=toast.ICON_COLOR_DEFAULTS[key],
            update=_icon_colors_changed,
        )
    for i, rgb in enumerate(CALENDAR_COLORS):
        ann[f"cal_col_{i}"] = bpy.props.FloatVectorProperty(
            name=CALENDAR_LEVEL_LABELS[i],
            description=f"Colour of a day with {CALENDAR_LEVEL_LABELS[i].lower()}",
            subtype='COLOR_GAMMA',
            size=3, min=0.0, max=1.0, default=rgb,
            update=_calendar_colors_changed,
        )
    return cls


_install_color_props(ACHIEVEMENT_AddonPreferences)
