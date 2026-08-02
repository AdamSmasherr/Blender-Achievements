"""
Кастомна achievement-нотифікація в стилі Steam, намальована засобами Blender
(модулі gpu / blf). Точна копія Steam Desktop Toast:

  • Картка ~283 × 70 px, темний сланцевий скляний фон (як у реального Steam).
  • Іконка 48×48 ліворуч у майже чорній плитці.
  • Рідкісна ачивка: золотий бурст ПОВЕРХ панелі навколо іконки —
      – м'яке золоте радіальне сяйво (box-shadow rgba(255,184,78,.6/.4));
      – обертові золоті промені (repeating-conic-gradient, 6s linear).
  • Текст праворуч: Title (білий жирний) + Description (сірий).
  • Поява: slide-in справа 300ms cubic-bezier(0,.73,.48,1),
    показ ~5000ms, зникнення: fade-out 300ms.

Публічний API:
    toast.show(title, desc, rare=False, icon_path=None, sound_path=None)
    toast.ensure_handler()
    toast.remove_handler()
"""

import os
import time
import math

import bpy
import blf
import gpu
from gpu_extras.batch import batch_for_shader

from . import debug

# ------------------------------------------------------------------ палітра
# Темний сланцевий фон Steam (виміряно з реального скріншоту).
BG_LIGHT       = (0.00774, 0.01039, 0.01701)  # #1c2028 sRGB (лінійний)
BG_DARK        = (0.00168, 0.00369, 0.00714)  # #0e141b sRGB (лінійний)
PANEL_ALPHA    = 0.985
BORDER         = (0.025, 0.030, 0.040, 1.0)  # ледь помітна рамка картки

ICON_TOP       = (0.075, 0.086, 0.106, 1.0)    # майже чорна плитка іконки
ICON_BOTTOM    = (0.030, 0.035, 0.045, 1.0)
STEEL_FRAME    = (0.20, 0.23, 0.28, 1.0)       # тонка темна рамка іконки (звичайна)

TITLE_COL      = (1.00, 1.00, 1.00, 1.0)       # суцільний білий
DESC_COL       = (0.58, 0.62, 0.68, 1.0)       # трохи світліший плаский сірий опис

# Золото для рідкісних ачивок
GOLD_LIGHT     = (0.9882, 0.7176, 0.3059, 1.0) # #fcb74e
GOLD_DARK      = (0.9882, 0.7176, 0.3059, 1.0) # #fcb74e
GOLD_GLOW      = (0.9882, 0.7176, 0.3059, 1.0) # #fcb74e
RARE_LABEL_COL = (0.9882, 0.7176, 0.3059, 1.0) # #fcb74e

# ------------------------------------------------------------------ базові розміри (до UI-scale)
PANEL_W  = 378
PANEL_H  = 85
PANEL_R  = 8
ICON_SZ  = 56
ICON_M   = 14.5       # (85-56)/2
PAD_TXT  = 21         # відступ тексту від іконки
MARGIN_R = 9
MARGIN_B = 9

# тайминги анімації (секунди) — 300ms in / 5000ms hold / 300ms out
T_IN, T_HOLD, T_OUT = 0.30, 5.00, 0.30
SLIDE_PX = 300

# --- Steam: стек кількох тостів (нові знизу, старі зсуваються вгору) ---
STACK_GAP = 8.0        # проміжок між картками в стеку (px до scale)
STACK_SHIFT_T = 0.25   # тривалість анімації зсуву стека
STEAM_RISE_PX = 90     # наскільки виїжджає знизу / йде вгору при зникненні
STEAM_MAX_VISIBLE = 4  # максимум карток одночасно; решта чекає в черзі
STEAM_GAP_T = 0.5      # пауза між появою сусідніх ачивок

# --- PlayStation: та сама картка, але на 15% нижча, градієнт зліва направо ---
PS_H_FACTOR = 0.85
PS_GRAD_LEFT  = (0.2431, 0.2235, 0.2471)   # #3e393f
PS_GRAD_RIGHT = (0.1412, 0.1294, 0.1412)   # #242124
PS_DESC_TEXT = "Trophy earned!"

# --- Xbox: репліка CodePen-анімації (кола + банер, зелений #39960C) ---
XBOX_GREEN       = (0.2235, 0.5882, 0.0471, 1.0)   # #39960C
XBOX_GREEN_LIGHT = (0.2510, 0.6627, 0.0549, 1.0)   # #40a90e
XBOX_GREEN_DARK  = (0.1961, 0.5137, 0.0392, 1.0)   # #32830a
XBOX_CIRCLE  = 66.0     # діаметр кола (картка трохи менша за оригінал)
XBOX_BANNER_W = 320.0   # повна ширина банера
XBOX_T_IN    = 2.52     # 24% від 10.5s — до повного розкриття
XBOX_T_OUT   = 1.58     # 89%→100%
XBOX_TEXT_HDR = 14.5    # кегль рядка "Achievement unlocked"
XBOX_TEXT_NAME = 16.5   # кегль назви ачивки / опису
XBOX_STAGE1 = 2.0       # скільки тримати назву, перш ніж показати опис
XBOX_SWAP_T = 0.45      # тривалість підміни тексту (назва вгору / опис знизу)
XBOX_SPIN_T = 6.0       # період обертання трофея (rotateY 6s infinite)
# Спрайт-лист діаманта: 60 кадрів 128x128, сітка 4 колонки x 15 рядків,
# відтворення 30 к/с. Програється повністю вперед і завмирає на останньому
# кадрі; коли картка починає згортатись (End) — програється у зворотному
# напрямку з тією ж швидкістю. Альфа-канал вшитий у кадри, тому кругла
# маска більше не потрібна.
XBOX_SPRITE_FRAMES = 60
XBOX_SPRITE_COLS = 4
XBOX_SPRITE_ROWS = 15
XBOX_SPRITE_FPS = 30.0
XBOX_SPRITE_SCALE = 0.6   # діамант на 40% менший за коло
# Спрайт стартує рівно тоді, коли починається кросфейд логотип→діамант
# (див. swap нижче) — інакше він докрутиться до останнього кадру ще до того,
# як стане видимим.
XBOX_SPRITE_SWAP_AT = 0.79
XBOX_SPRITE_DELAY = XBOX_T_IN * XBOX_SPRITE_SWAP_AT
XBOX_SPRITE_END_LEAD = 0.5  # наскільки раніше за згортання стартує реверс
XBOX_BANNER_MIN = 260.0 # мінімальна ширина банера
XBOX_BANNER_MAX = 620.0 # стеля, щоб дуже довгий опис не розтягнув на весь екран
XBOX_TEXT_PAD = 26.0    # правий відступ тексту в банері

# ------------------------------------------------------------------ стан модуля
_pending = []
_toasts = []           # активні тости (Steam може мати кілька одночасно)
_draw_handle = None
_shader_uniform = None
_shader_smooth = None
_shader_conic = None
_shader_radial = None
_shader_image_tint = None

# бінарні ресурси (маска сяйва, іконки Xbox, спрайт-лист блиску)
ASSET_DIR = os.path.join(os.path.dirname(__file__), "assets")
_MASK_PATH = os.path.join(ASSET_DIR, "glow_mask.png")
_mask_tex = None
_mask_failed = False

_asset_tex = {}      # filename -> GPUTexture | None (None = не вдалося)


def _asset(name, premul=True):
    """GPU-текстура з assets/<name> (лениво, з кешем). None, якщо недоступна.

    Більшість іконок збережені з ПРЕМНОЖЕНОЮ альфою, тож малюються у режимі
    ALPHA_PREMULT — прозорі ділянки чорні (RGB=0) і не дають білого квадрата
    навіть якщо альфа десь загубиться. Ресурси зі звичайною (straight) альфою
    передають premul=False і малюються у режимі ALPHA.
    """
    if name in _asset_tex:
        return _asset_tex[name]
    tex = None
    try:
        p = os.path.join(ASSET_DIR, name)
        if os.path.exists(p):
            img = bpy.data.images.load(p, check_existing=True)
            try:
                img.alpha_mode = 'PREMUL' if premul else 'STRAIGHT'
                # 'Non-Color' дає текстуру RGBA8; з 'sRGB' Blender створює
                # SRGB8_A8, і GPU лінеаризує кольори при семплінгу. Ми пишемо
                # їх у фреймбуфер без зворотного кодування, тож картинка
                # виходила темнішою та насиченішою за оригінал. Для
                # премножених іконок це ще й ламало премноження: RGB
                # лінеаризується, а альфа — ні.
                img.colorspace_settings.name = 'Non-Color'
            except Exception as _dbg_err:  # noqa: BLE001
                debug.log("toast.py:140", _dbg_err)
                pass
            tex = gpu.texture.from_image(img)
    except Exception as _dbg_err:  # noqa: BLE001
        debug.log("toast.py:143", _dbg_err)
        tex = None
    _asset_tex[name] = tex
    return tex

# --- Шрифти по стилях: Steam → Inter, PlayStation → IBM Plex Sans,
# Xbox → Selawik. Усі три під SIL OFL 1.1 і забандлені в assets/fonts/;
# перший наявний зі списку виграє.
FONT_DIR = os.path.join(ASSET_DIR, "fonts")

FONT_FAMILIES = {
    'STEAM': {
        'title': ["Inter.ttf"],
        'desc':  ["Inter.ttf"],
    },
    'PS': {
        'title': ["IBMPlexSans.ttf"],
        'desc':  ["IBMPlexSans.ttf"],
    },
    'XBOX': {
        'title': ["selawksb.ttf", "selawk.ttf"],
        'desc':  ["selawk.ttf", "selawkl.ttf"],
    },
}

_fonts = {}               # (style, role) -> font id
_font_paths_loaded = []   # filepaths given to blf.load(), потрібні для blf.unload()


def _get_style():
    """Поточний стиль анімації: 'STEAM' | 'XBOX' | 'PS'.

    Для вбудованих пресетів стиль = пресет. Для CUSTOM — поле animation_style
    активного профілю (щоб користувач міг узяти будь-яку анімацію зі своїми звуками).
    """
    try:
        prefs = get_preferences()
        if prefs is None:
            return 'STEAM'
        preset = getattr(prefs, "sound_preset", 'STEAM')
        if preset == 'CUSTOM':
            from . import sounds
            prof = sounds.get_active_profile(prefs)
            return getattr(prof, "animation_style", 'STEAM') if prof else 'STEAM'
        return preset if preset in ('STEAM', 'XBOX', 'PS') else 'STEAM'
    except Exception as _dbg_err:  # noqa: BLE001
        debug.log("toast.py:191", _dbg_err)
        return 'STEAM'


def _rounded(style=None):
    """Чи закруглювати кути картки/іконки. Опція діє ЛИШЕ для Steam-стилю;
    PlayStation завжди залишається закругленим."""
    try:
        if style is None:
            style = _get_style()
        if style != 'STEAM':
            return True
        prefs = get_preferences()
        return bool(getattr(prefs, "rounded_corners", True)) if prefs else True
    except Exception as _dbg_err:  # noqa: BLE001
        debug.log("toast.py:205", _dbg_err)
        return True


def _load_font(rel_names):
    """Завантажує перший наявний шрифт зі списку імен у assets/fonts; id або None.

    Шукаємо ВИКЛЮЧНО серед забандлених шрифтів — жодних системних тек, інакше
    аддон малювався б по-різному на різних ОС. Якщо не вдалося нічого, викликач
    (_font) відкочується на вбудований шрифт Blender з id 0.
    """
    for n in rel_names:
        p = os.path.join(FONT_DIR, n.replace("/", os.sep))
        try:
            if os.path.exists(p):
                fid = blf.load(p)
                if fid != -1:
                    _font_paths_loaded.append(p)
                    return fid
        except Exception as _dbg_err:  # noqa: BLE001
            debug.log("toast.py:_load_font", _dbg_err)
            pass
    return None


def _font(style, role):
    """Font id для (стиль, роль). Кешується; fallback → вбудований шрифт 0."""
    key = (style, role)
    if key in _fonts:
        fid = _fonts[key]
        return fid if fid is not None else 0
    fam = FONT_FAMILIES.get(style) or FONT_FAMILIES['STEAM']
    _fonts[key] = _load_font(fam.get(role, []))
    fid = _fonts[key]
    return fid if fid is not None else 0


def _ensure_fonts():
    """Прогріває шрифти поточного стилю (безпечно викликати часто)."""
    st = _get_style()
    _font(st, 'title')
    _font(st, 'desc')


def _get_mask_tex():
    """Лінива загрузка ray-маски як GPU-текстури (None, якщо недоступна)."""
    global _mask_tex, _mask_failed
    if _mask_tex is not None:
        return _mask_tex
    if _mask_failed:
        return None
    try:
        img = bpy.data.images.load(_MASK_PATH, check_existing=True)
        _mask_tex = gpu.texture.from_image(img)
    except Exception as _dbg_err:  # noqa: BLE001
        debug.log("toast.py:256", _dbg_err)
        _mask_failed = True
        _mask_tex = None
    return _mask_tex


# =============================================================== easing
def _make_cubic_bezier(p1x, p1y, p2x, p2y):
    """CSS cubic-bezier(p1x,p1y,p2x,p2y) → функція ease(x)->y на [0,1]."""
    def _bez(t, a, b):
        mt = 1.0 - t
        return 3.0 * mt * mt * t * a + 3.0 * mt * t * t * b + t * t * t

    def ease(x):
        x = max(0.0, min(1.0, x))
        lo, hi = 0.0, 1.0
        for _ in range(24):
            mid = (lo + hi) * 0.5
            if _bez(mid, p1x, p2x) < x:
                lo = mid
            else:
                hi = mid
        return _bez((lo + hi) * 0.5, p1y, p2y)

    return ease


_EASE_IN = _make_cubic_bezier(0.0, 0.73, 0.48, 1.0)


# =============================================================== геометрія
def _round_rect_pts(x, y, w, h, r, seg=6):
    """Периметр закругленого прямокутника (CCW), як список (x, y)."""
    r = min(r, w * 0.5, h * 0.5)
    pts = []
    corners = (
        (x + r,     y + r,     math.pi,       math.pi * 1.5),
        (x + w - r, y + r,     math.pi * 1.5, math.pi * 2.0),
        (x + w - r, y + h - r, 0.0,           math.pi * 0.5),
        (x + r,     y + h - r, math.pi * 0.5, math.pi),
    )
    for cx, cy, a0, a1 in corners:
        for i in range(seg + 1):
            a = a0 + (a1 - a0) * i / seg
            pts.append((cx + math.cos(a) * r, cy + math.sin(a) * r))
    return pts


def _fan_tris(pts):
    """Тріангуляція опуклого полігону віялом від pts[0]."""
    tris = []
    for i in range(1, len(pts) - 1):
        tris.append(pts[0])
        tris.append(pts[i])
        tris.append(pts[i + 1])
    return tris


def _lerp4(a, b, t):
    return (a[0] + (b[0] - a[0]) * t,
            a[1] + (b[1] - a[1]) * t,
            a[2] + (b[2] - a[2]) * t,
            a[3] + (b[3] - a[3]) * t)


def _draw_solid(pts, color):
    coords = _fan_tris(pts)
    batch = batch_for_shader(_shader_uniform, 'TRIS', {"pos": coords})
    _shader_uniform.bind()
    _shader_uniform.uniform_float("color", color)
    batch.draw(_shader_uniform)


def _draw_vgrad(pts, y0, h, c_bottom, c_top, alpha=1.0):
    """Вертикальний градієнт від c_bottom (низ) до c_top (верх)."""
    coords = _fan_tris(pts)
    colors = []
    for (_px, py) in coords:
        t = max(0.0, min(1.0, (py - y0) / h))
        c = _lerp4(c_bottom, c_top, t)
        colors.append((c[0], c[1], c[2], c[3] * alpha))
    batch = batch_for_shader(_shader_smooth, 'TRIS',
                             {"pos": coords, "color": colors})
    _shader_smooth.bind()
    batch.draw(_shader_smooth)


def _draw_glow_disc(cx, cy, radius, color, center_alpha, alpha, seg=40):
    """М'яке радіальне сяйво: яскравий центр → прозорий край (box-shadow)."""
    center = (cx, cy)
    cc = (color[0], color[1], color[2], center_alpha * alpha)
    edge = (color[0], color[1], color[2], 0.0)
    coords, colors = [], []
    for i in range(seg):
        a0 = 2.0 * math.pi * i / seg
        a1 = 2.0 * math.pi * (i + 1) / seg
        coords.append(center); colors.append(cc)
        coords.append((cx + math.cos(a0) * radius, cy + math.sin(a0) * radius)); colors.append(edge)
        coords.append((cx + math.cos(a1) * radius, cy + math.sin(a1) * radius)); colors.append(edge)
    batch = batch_for_shader(_shader_smooth, 'TRIS',
                             {"pos": coords, "color": colors})
    _shader_smooth.bind()
    batch.draw(_shader_smooth)


# =============================================================== GLSL: dark slate background
VERT_UV_SRC = """
void main() {
    v_uv = uv;
    gl_Position = ModelViewProjectionMatrix * vec4(pos, 0.0, 1.0);
}
"""

# Темний сланцевий radial: світліший верхній-лівий кут → темний край.
FRAG_RADIAL_SRC = """
void main() {
    float u = v_uv.x;
    float v = 1.0 - v_uv.y;               // top-left = центр
    float dx = u / 1.5542;
    float dy = v;
    float d = clamp(sqrt(dx * dx + dy * dy), 0.0, 1.0);

    vec3 c0 = vec3(0.00774, 0.01039, 0.01701); // #1c2028 sRGB (лінійний)
    vec3 c1 = vec3(0.00168, 0.00369, 0.00714); // #0e141b sRGB (лінійний)
    vec3 col = mix(c0, c1, d);

    fragColor = vec4(col, 0.985 * u_alpha);
}
"""


def _init_radial_shader():
    global _shader_radial
    if _shader_radial is not None:
        return _shader_radial
    try:
        if hasattr(gpu.types, 'GPUShaderCreateInfo'):
            info = gpu.types.GPUShaderCreateInfo()
            info.vertex_in(0, 'VEC2', 'pos')
            info.vertex_in(1, 'VEC2', 'uv')
            if hasattr(gpu.types, 'GPUStageInterfaceInfo'):
                stage = gpu.types.GPUStageInterfaceInfo('radial_interface')
                stage.smooth('VEC2', 'v_uv')
                info.vertex_out(stage)
            info.push_constant('MAT4', 'ModelViewProjectionMatrix')
            info.push_constant('FLOAT', 'u_alpha')
            info.fragment_out(0, 'VEC4', 'fragColor')
            info.vertex_source(VERT_UV_SRC)
            info.fragment_source(FRAG_RADIAL_SRC)
            _shader_radial = gpu.shader.create_from_info(info)
        else:
            _shader_radial = None
    except Exception as _dbg_err:
        debug.log("toast.py:408", _dbg_err)
        _shader_radial = None
    return _shader_radial


def _draw_radial(pts, X, Y, W, H, alpha):
    shader = _init_radial_shader()
    coords = _fan_tris(pts)
    if shader is None:
        _draw_vgrad(pts, Y, H,
                    (BG_DARK[0], BG_DARK[1], BG_DARK[2], PANEL_ALPHA),
                    (BG_LIGHT[0], BG_LIGHT[1], BG_LIGHT[2], PANEL_ALPHA), alpha)
        return
    uvs = [((px - X) / W, (py - Y) / H) for (px, py) in coords]
    batch = batch_for_shader(shader, 'TRIS', {"pos": coords, "uv": uvs})
    shader.bind()
    shader.uniform_float("u_alpha", alpha)
    batch.draw(shader)


# =============================================================== GLSL: rotating conic rays
# repeating-conic-gradient з rare_achievement.md (точні стопи Steam).
FRAG_CONIC_SRC = """
vec4 sample_conic(float t) {
    vec4 c_dim    = vec4(0.985, 0.620, 0.180, 0.20);
    vec4 c_zero   = vec4(0.985, 0.620, 0.180, 0.02);
    vec4 c_bright = vec4(0.995, 0.780, 0.320, 1.00);

    t = fract(t);

    if (t < 0.06)      return mix(c_dim, c_zero, t / 0.06);
    else if (t < 0.10) return mix(c_zero, c_dim, (t - 0.06) / 0.04);
    else if (t < 0.26) return mix(c_dim, c_bright, (t - 0.10) / 0.16);
    else if (t < 0.35) return mix(c_bright, c_dim, (t - 0.26) / 0.09);
    else if (t < 0.40) return mix(c_dim, c_bright, (t - 0.35) / 0.05);
    else if (t < 0.60) return mix(c_bright, c_dim, (t - 0.40) / 0.20);
    else if (t < 0.82) return mix(c_dim, c_bright, (t - 0.60) / 0.22);
    else               return mix(c_bright, c_dim, (t - 0.82) / 0.18);
}

void main() {
    vec2 p = v_uv - vec2(0.5);

    // яскравість секторів: обертовий conic-градієнт (6s)
    float angle = atan(p.y, p.x);
    float norm_angle = (angle + 3.14159265359) / 6.28318530718;
    float rot_angle = fract(norm_angle - u_angle / 6.28318530718);
    float bright = sample_conic(rot_angle).a;

    // форма променів: ray-маска Steam, що обертається у зворотний бік (18s)
    float cs = cos(u_mask_angle);
    float sn = sin(u_mask_angle);
    vec2 mp = vec2(p.x * cs - p.y * sn, p.x * sn + p.y * cs) + vec2(0.5);
    vec4 mask_val = texture(mask_tex, mp);
    float ray = mask_val.r * mask_val.a;

    // КЛЮЧОВЕ: світло походить від КВАДРАТНОЇ рамки іконки (signed distance)
    vec2 q = abs(p) - vec2(u_icon_half);
    float outside = length(max(q, vec2(0.0))) + min(max(q.x, q.y), 0.0);
    outside = max(outside, 0.0);
    float fall = 1.0 - smoothstep(0.0, u_glow_width, outside);

    // Плавний фейд променів майже одразу від рамки іконки
    float quick_fade = fall * fall * fall;

    float a;
    if (u_mode < 0.5) {
        // М'яке розмите сяйво безпосередньо біля рамки
        a = quick_fade * u_alpha * 0.35;
    } else {
        // Промені світла з швидким м'яким фейдом одразу від рамки
        float s = pow(bright * ray, 1.4);
        a = clamp(s * quick_fade * u_alpha * 0.90, 0.0, 1.0);
    }
    vec3 gold = mix(vec3(0.985, 0.620, 0.180), vec3(0.995, 0.780, 0.320), bright * 0.35);
    fragColor = vec4(gold, a);
}
"""


def _init_conic_shader():
    global _shader_conic
    if _shader_conic is not None:
        return _shader_conic
    try:
        if hasattr(gpu.types, 'GPUShaderCreateInfo'):
            info = gpu.types.GPUShaderCreateInfo()
            info.vertex_in(0, 'VEC2', 'pos')
            info.vertex_in(1, 'VEC2', 'uv')
            if hasattr(gpu.types, 'GPUStageInterfaceInfo'):
                stage = gpu.types.GPUStageInterfaceInfo('conic_interface')
                stage.smooth('VEC2', 'v_uv')
                info.vertex_out(stage)
            info.push_constant('MAT4', 'ModelViewProjectionMatrix')
            info.push_constant('FLOAT', 'u_angle')
            info.push_constant('FLOAT', 'u_mask_angle')
            info.push_constant('FLOAT', 'u_alpha')
            info.push_constant('FLOAT', 'u_mode')
            info.push_constant('FLOAT', 'u_glow_width')
            info.push_constant('FLOAT', 'u_icon_half')
            info.sampler(0, 'FLOAT_2D', 'mask_tex')
            info.fragment_out(0, 'VEC4', 'fragColor')
            info.vertex_source(VERT_UV_SRC)
            info.fragment_source(FRAG_CONIC_SRC)
            _shader_conic = gpu.shader.create_from_info(info)
        else:
            _shader_conic = None
    except Exception as _dbg_err:
        debug.log("toast.py:515", _dbg_err)
        _shader_conic = None
    return _shader_conic


def _draw_icon_glow(icx, icy, isz, now, alpha):
    """Золотий бурст, що походить від квадратної рамки іконки.

    Два проходи одним шейдером:
      • ореол (u_mode=0) — м'яке квадратне сяйво (box-shadow);
      • промені (u_mode=1) — conic 6s × ray-маска Steam (зворотні 18s),
        обидва обмежені квадратним signed-distance полем рамки.
    Повертає True, якщо намалював (інакше — запасний варіант у _draw).
    """
    shader = _init_conic_shader()
    mask = _get_mask_tex()
    if shader is None or mask is None:
        return False
    try:
        half = isz * 1.05                       # поле сяйва (як у 1.11)
        icon_half = (isz * 0.5) / (2.0 * half)  # нормалізована півширина іконки
        u_angle = (now * (2.0 * math.pi / 6.0)) % (2.0 * math.pi)
        u_mask_angle = (-now * (2.0 * math.pi / 18.0)) % (2.0 * math.pi)  # reverse 18s
        qx, qy = icx - half, icy - half
        s = 2.0 * half
        coords = [(qx, qy), (qx + s, qy), (qx + s, qy + s),
                  (qx, qy), (qx + s, qy + s), (qx, qy + s)]
        uvs = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0),
               (0.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
        batch = batch_for_shader(shader, 'TRIS', {"pos": coords, "uv": uvs})
        # (u_mode, u_glow_width): менший м'який ореол + промені
        for mode, gw in ((0.0, 0.10), (1.0, 0.14)):
            shader.bind()
            shader.uniform_float("u_angle", u_angle)
            shader.uniform_float("u_mask_angle", u_mask_angle)
            shader.uniform_float("u_alpha", alpha)
            shader.uniform_float("u_mode", mode)
            shader.uniform_float("u_glow_width", gw)
            shader.uniform_float("u_icon_half", icon_half)
            shader.uniform_sampler("mask_tex", mask)
            batch.draw(shader)
        return True
    except Exception as _dbg_err:
        debug.log("toast.py:557", _dbg_err)
        return False


# =============================================================== текст
def _wrap(font, text, max_w, max_lines=2):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        trial = w if not cur else cur + " " + w
        if blf.dimensions(font, trial)[0] <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
            if len(lines) == max_lines:
                break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    if len(lines) == max_lines and cur and blf.dimensions(font, cur)[0] > max_w:
        while cur and blf.dimensions(font, cur + "…")[0] > max_w:
            cur = cur[:-1]
        lines[-1] = cur + "…"
    return lines


def _draw_clipped(font, text, max_w):
    if blf.dimensions(font, text)[0] <= max_w:
        blf.draw(font, text)
        return
    s = text
    while s and blf.dimensions(font, s + "…")[0] > max_w:
        s = s[:-1]
    blf.draw(font, s + "…")


def _draw_glyph_center(font, glyph, x, y, w, h, size, color, alpha):
    blf.size(font, size)
    blf.color(font, color[0], color[1], color[2], color[3] * alpha)
    gw, gh = blf.dimensions(font, glyph)
    blf.position(font, x + (w - gw) / 2.0, y + (h - gh) / 2.0, 0)
    blf.draw(font, glyph)


def _image_shader():
    """Шейдер 'текстура × колір' — потрібен, щоб іконки могли плавно згасати
    (вбудований IMAGE малює завжди на повну непрозорість)."""
    global _shader_image_tint
    if _shader_image_tint is not None:
        return _shader_image_tint
    try:
        info = gpu.types.GPUShaderCreateInfo()
        info.vertex_in(0, 'VEC2', 'pos')
        info.vertex_in(1, 'VEC2', 'uv')
        stage = gpu.types.GPUStageInterfaceInfo('img_tint_iface')
        stage.smooth('VEC2', 'v_uv')
        info.vertex_out(stage)
        info.push_constant('MAT4', 'ModelViewProjectionMatrix')
        info.push_constant('VEC4', 'u_tint')
        info.sampler(0, 'FLOAT_2D', 'image')
        info.fragment_out(0, 'VEC4', 'fragColor')
        info.vertex_source(
            "void main() { v_uv = uv;"
            " gl_Position = ModelViewProjectionMatrix * vec4(pos, 0.0, 1.0); }")
        info.fragment_source(
            "void main() { fragColor = texture(image, v_uv) * u_tint; }")
        _shader_image_tint = gpu.shader.create_from_info(info)
    except Exception as _dbg_err:  # noqa: BLE001
        debug.log("toast.py:624", _dbg_err)
        _shader_image_tint = None
    return _shader_image_tint


def _draw_image_uv(texture, x, y, w, h, u0=0.0, u1=1.0, v0=0.0, v1=1.0, alpha=1.0):
    """Малює (під)ділянку текстури. Використовується для кадрів спрайт-листа."""
    coords = [(x, y), (x + w, y), (x + w, y + h),
              (x, y), (x + w, y + h), (x, y + h)]
    uvs = [(u0, v0), (u1, v0), (u1, v1),
           (u0, v0), (u1, v1), (u0, v1)]
    sh = _image_shader() if alpha < 0.999 else None
    if sh is not None:
        batch = batch_for_shader(sh, 'TRIS', {"pos": coords, "uv": uvs})
        sh.bind()
        sh.uniform_float("u_tint", (alpha, alpha, alpha, alpha))
        sh.uniform_sampler("image", texture)
        batch.draw(sh)
        return
    shader = gpu.shader.from_builtin('IMAGE')
    batch = batch_for_shader(shader, 'TRIS', {"pos": coords, "texCoord": uvs})
    shader.bind()
    shader.uniform_sampler("image", texture)
    batch.draw(shader)


def _sprite_uv(frame):
    """UV-межі (u0, u1, v0, v1) кадру спрайт-листа діаманта.

    Кадри йдуть зліва направо, зверху вниз. У GPU-текстурі v=0 — це НИЗ
    зображення, тож рядок 0 (верхній) відповідає найбільшим v.
    """
    frame = max(0, min(XBOX_SPRITE_FRAMES - 1, int(frame)))
    col = frame % XBOX_SPRITE_COLS
    row = frame // XBOX_SPRITE_COLS
    u0 = col / float(XBOX_SPRITE_COLS)
    u1 = (col + 1) / float(XBOX_SPRITE_COLS)
    v1 = 1.0 - row / float(XBOX_SPRITE_ROWS)
    v0 = 1.0 - (row + 1) / float(XBOX_SPRITE_ROWS)
    return u0, u1, v0, v1


def _draw_ring_pulse(cx, cy, r, color, alpha):
    """Пульсуюче коло-хвиля (::before / ::after з scale_circle_1)."""
    if alpha <= 0.001 or r <= 0.5:
        return
    _draw_circle(cx, cy, r, (color[0], color[1], color[2], alpha))


def _pulse_phase(p):
    """scale_circle_1: (scale, opacity) за нормалізованим часом 0..1 циклу.

    0%→5%: scale 0→1, opacity 1→0.8; 6%→100%: opacity 0.
    """
    if p < 0.0 or p > 1.0:
        return (0.0, 0.0)
    if p < 0.05:
        k = p / 0.05
        return (k, 0.8 + 0.2 * (1.0 - k))
    if p < 0.12:
        return (1.0, max(0.0, 0.8 * (1.0 - (p - 0.05) / 0.07)))
    return (1.0, 0.0)


def _draw_icon_image(texture, x, y, w, h, alpha):
    """Іконка ачивки — повна текстура з урахуванням прозорості картки.

    Раніше тут стояв вбудований IMAGE-шейдер, який ігнорував `alpha`: картка
    плавно виїжджала й згасала, а іконка стрибком з'являлась і зникала на
    повній непрозорості. `_draw_image_uv` уже вміє тінтувати — це той самий
    малюнок з u/v на всю текстуру.
    """
    _draw_image_uv(texture, x, y, w, h, alpha=alpha)


def _init_shaders():
    global _shader_uniform, _shader_smooth
    _shader_uniform = gpu.shader.from_builtin('UNIFORM_COLOR')
    _shader_smooth = gpu.shader.from_builtin('SMOOTH_COLOR')


# =============================================================== малювання
def _is_largest_view3d_region(region):
    """True, якщо region — найбільший WINDOW-регіон 3D-в'юпорта серед усіх вікон."""
    try:
        ctx = getattr(bpy, "context", None)
        wm = getattr(ctx, "window_manager", None)
        if not wm or "Mock" in type(wm).__name__ or not hasattr(region, "as_pointer"):
            return True
        target = region.as_pointer()
        best_ptr, best_area = None, -1
        windows = getattr(wm, "windows", [])
        for win in windows:
            screen = getattr(win, "screen", None)
            areas = getattr(screen, "areas", []) if screen else []
            for area in areas:
                if getattr(area, "type", None) != 'VIEW_3D':
                    continue
                regions = getattr(area, "regions", []) if area else []
                for r in regions:
                    if getattr(r, "type", None) == 'WINDOW':
                        w = getattr(r, "width", 0)
                        h = getattr(r, "height", 0)
                        a = w * h
                        if a > best_area:
                            best_area = a
                            best_ptr = r.as_pointer() if hasattr(r, "as_pointer") else None
        return best_ptr is None or target is None or best_ptr == target
    except Exception as _dbg_err:
        debug.log("toast.py:746", _dbg_err)
        return True


def _draw_circle(cx, cy, r, color, seg=48):
    """Суцільне коло."""
    coords = []
    for i in range(seg):
        a0 = 2.0 * math.pi * i / seg
        a1 = 2.0 * math.pi * (i + 1) / seg
        coords.append((cx, cy))
        coords.append((cx + math.cos(a0) * r, cy + math.sin(a0) * r))
        coords.append((cx + math.cos(a1) * r, cy + math.sin(a1) * r))
    batch = batch_for_shader(_shader_uniform, 'TRIS', {"pos": coords})
    _shader_uniform.bind()
    _shader_uniform.uniform_float("color", color)
    batch.draw(_shader_uniform)


def _draw_hgrad(pts, x0, w, c_left, c_right, alpha=1.0, mid=0.5):
    """Горизонтальний градієнт: c_left → c_right на ділянці [x0, x0+w*mid],
    далі суцільний c_right (як у PlayStation-картці)."""
    coords = _fan_tris(pts)
    colors = []
    span = max(1e-6, w * mid)
    for (px, _py) in coords:
        t = max(0.0, min(1.0, (px - x0) / span))
        c = _lerp4(c_left, c_right, t)
        colors.append((c[0], c[1], c[2], c[3] * alpha))
    batch = batch_for_shader(_shader_smooth, 'TRIS', {"pos": coords, "color": colors})
    _shader_smooth.bind()
    batch.draw(_shader_smooth)


def _viewport_geom():
    """(region, scale, shelf_h) або None, якщо малювати не тут."""
    region = bpy.context.region
    area = bpy.context.area
    if region is None or area is None:
        return None
    if not _is_largest_view3d_region(region):
        return None
    scale = max(0.5, bpy.context.preferences.system.ui_scale)
    shelf_h = 0
    try:
        for r in (getattr(area, "regions", []) or []):
            if getattr(r, "type", None) in ('ASSET_SHELF', 'ASSET_SHELF_HEADER') and getattr(r, "height", 0) > 1:
                shelf_h += r.height
    except Exception as _dbg_err:
        debug.log("toast.py:794", _dbg_err)
        pass
    return (region, scale, shelf_h)


def _stack_offset(t, now, scale, card_h):
    """Плавно анімований вертикальний зсув тоста в стеку (Steam)."""
    slot = t.get('slot', 0)
    prev = t.get('slot_prev', slot)
    t0 = t.get('slot_t0', 0.0)
    step = card_h + STACK_GAP * scale
    if prev != slot and t0:
        k = min(1.0, (now - t0) / STACK_SHIFT_T)
        k = k * k * (3.0 - 2.0 * k)   # smoothstep
        cur = prev + (slot - prev) * k
    else:
        cur = slot
    return cur * step


def _ensure_icon_tex(t):
    """Створює GPU-текстуру іконки один раз, у валідному draw-контексті."""
    if t.get('icon_tex') is None and not t.get('icon_done'):
        img = t.get('icon_img')
        if img is not None:
            try:
                # 'Non-Color' -> текстура RGBA8 замість SRGB8_A8. Інакше GPU
                # лінеаризує кольори при семплінгу, а ми пишемо їх у фреймбуфер
                # без зворотного кодування — іконка виходить темнішою за оригінал.
                img.colorspace_settings.name = 'Non-Color'
                t['icon_tex'] = gpu.texture.from_image(img)
            except Exception as _dbg_err:  # noqa: BLE001
                debug.log("toast.py:821", _dbg_err)
                t['icon_tex'] = None
        t['icon_done'] = True


def _draw_card(t, now, region, scale, shelf_h, style):
    """Steam / PlayStation картка. Steam виїжджає знизу вгору й зникає вгору,
    PlayStation — виїжджає справа (як класичний Steam-тост)."""
    e = now - t['t0']
    hold = t.get('duration', T_HOLD)
    if e >= T_IN + hold + T_OUT:
        return

    is_ps = (style == 'PS')
    H = PANEL_H * (PS_H_FACTOR if is_ps else 1.0) * scale
    W = PANEL_W * scale
    R = (PANEL_R * scale) if _rounded(style) else 0.0
    mr, mb = MARGIN_R * scale, MARGIN_B * scale

    # --- фаза: вхід / утримання / вихід
    dx = dy = 0.0
    alpha = 1.0
    if e < T_IN:
        k = _EASE_IN(e / T_IN)
        if is_ps:
            dx = (1.0 - k) * SLIDE_PX * scale          # справа наліво
        else:
            dy = -(1.0 - k) * STEAM_RISE_PX * scale    # знизу вгору
            alpha = k
    elif e >= T_IN + hold:
        k = min(1.0, (e - T_IN - hold) / T_OUT)
        alpha = max(0.0, 1.0 - k)
        if not is_ps:
            dy = k * STEAM_RISE_PX * scale             # зникає вгору

    X = max(mr, region.width - mr - W) + dx
    Y = mb + shelf_h + dy
    if style == 'STEAM':
        Y += _stack_offset(t, now, scale, H)

    rare = t['rare']
    gpu.state.blend_set('ALPHA')

    isz = (ICON_SZ * (PS_H_FACTOR if is_ps else 1.0)) * scale
    ix = X + ICON_M * (PS_H_FACTOR if is_ps else 1.0) * scale
    iy = Y + (H - isz) / 2.0
    icx, icy = ix + isz / 2.0, iy + isz / 2.0

    # --- фон картки
    body = _round_rect_pts(X, Y, W, H, R)
    if is_ps:
        _draw_hgrad(body, X, W,
                    (PS_GRAD_LEFT[0], PS_GRAD_LEFT[1], PS_GRAD_LEFT[2], PANEL_ALPHA),
                    (PS_GRAD_RIGHT[0], PS_GRAD_RIGHT[1], PS_GRAD_RIGHT[2], PANEL_ALPHA),
                    alpha, mid=0.5)
    else:
        _draw_radial(body, X, Y, W, H, alpha)

    # --- рідкісний золотий бурст навколо іконки (не для PlayStation-стилю)
    if rare and not is_ps:
        if not _draw_icon_glow(icx, icy, isz, now, alpha):
            for off, ga in ((9, 0.16), (5, 0.22), (2, 0.30)):
                o = off * scale
                gp = _round_rect_pts(ix - o, iy - o, isz + 2 * o, isz + 2 * o, 5 * scale)
                _draw_solid(gp, (GOLD_GLOW[0], GOLD_GLOW[1], GOLD_GLOW[2], ga * alpha))

    _ensure_icon_tex(t)

    # --- рамка іконки
    ir = (3.5 * scale) if _rounded(style) else 0.0
    if rare and not is_ps:
        for r_off, r_alpha in ((1.5, 0.12), (1.0, 0.30), (0.6, 0.60), (0.2, 0.90), (-0.2, 0.70), (-0.6, 0.35)):
            o = r_off * scale
            fr_layer = _round_rect_pts(ix - (0.5 + o) * scale, iy - (0.5 + o) * scale,
                                       isz + (1.0 + 2 * o) * scale, isz + (1.0 + 2 * o) * scale,
                                       max(0.0, (3.8 + o * 0.5) * scale) if _rounded(style) else 0.0)
            _draw_solid(fr_layer, (GOLD_GLOW[0], GOLD_GLOW[1], GOLD_GLOW[2], r_alpha * alpha))
    else:
        fr = _round_rect_pts(ix - 1 * scale, iy - 1 * scale,
                             isz + 2 * scale, isz + 2 * scale, (4 * scale) if _rounded(style) else 0.0)
        _draw_solid(fr, (STEEL_FRAME[0], STEEL_FRAME[1], STEEL_FRAME[2], alpha))

    if t.get('icon_tex') is not None:
        _draw_icon_image(t['icon_tex'], ix, iy, isz, isz, alpha)
    else:
        ib = _round_rect_pts(ix, iy, isz, isz, ir)
        _draw_vgrad(ib, iy, isz, ICON_BOTTOM, ICON_TOP, alpha)
        star_col = GOLD_GLOW if rare else (0.78, 0.82, 0.88, 1.0)
        _draw_glyph_center(0, "★", ix, iy, isz, isz, int(isz * 0.60), star_col, alpha)

    # --- текст
    ft = _font(style, 'title')
    fd = _font(style, 'desc')
    tx = ix + isz + PAD_TXT * (PS_H_FACTOR if is_ps else 1.0) * scale
    text_w = X + W - tx - 12 * scale

    f = (PS_H_FACTOR if is_ps else 1.0)
    title_sz = max(8, int(15.75 * f * scale))
    desc_sz = max(7, int(13.5 * f * scale))
    desc_text = PS_DESC_TEXT if is_ps else t['desc']

    blf.size(fd, desc_sz)
    dlines = _wrap(fd, desc_text, text_w, max_lines=1 if is_ps else 2)

    line_h = desc_sz + 5.4 * f * scale
    block_h = (20.7 * f * scale) + line_h * len(dlines)
    top = Y + (H + block_h) / 2.0

    blf.size(ft, title_sz)
    blf.color(ft, TITLE_COL[0], TITLE_COL[1], TITLE_COL[2], TITLE_COL[3] * alpha)
    ty = top - (15.3 * f * scale)
    blf.position(ft, tx, ty, 0)
    _draw_clipped(ft, t['title'], text_w)

    blf.size(fd, desc_sz)
    blf.color(fd, DESC_COL[0], DESC_COL[1], DESC_COL[2], DESC_COL[3] * alpha)
    dy2 = ty - (20.7 * f * scale)
    for ln in dlines:
        blf.position(fd, tx, dy2, 0)
        blf.draw(fd, ln)
        dy2 -= line_h

    gpu.state.blend_set('NONE')


def _smooth01(x):
    """clamp(x,0,1) зі smoothstep-згладжуванням."""
    x = max(0.0, min(1.0, x))
    return x * x * (3.0 - 2.0 * x)


def _xbox_banner_width(t, scale):
    """(3) Ширина банера підлаштовується під найдовший рядок, щоб опис вмістився."""
    key = ('xbox_bw', round(scale, 3))
    if t.get('_bw_key') == key:
        return t['_bw']
    ft = _font('XBOX', 'title')
    fd = _font('XBOX', 'desc')
    hsz = max(8, int(XBOX_TEXT_HDR * scale))
    nsz = max(8, int(XBOX_TEXT_NAME * scale))
    widest = 0.0
    try:
        blf.size(fd, hsz)
        widest = max(widest, blf.dimensions(
            fd, "Rare achievement unlocked" if t.get('rare') else "Achievement unlocked")[0])
        blf.size(ft, nsz)
        widest = max(widest, blf.dimensions(ft, t.get('title', ""))[0])
        blf.size(fd, nsz)
        widest = max(widest, blf.dimensions(fd, t.get('desc', ""))[0])
    except Exception as _dbg_err:  # noqa: BLE001
        debug.log("toast.py:970", _dbg_err)
        widest = XBOX_BANNER_W * 0.5 * scale
    cd = XBOX_CIRCLE * scale
    bw = cd + 18 * scale + widest + XBOX_TEXT_PAD * scale
    bw = max(XBOX_BANNER_MIN * scale, min(XBOX_BANNER_MAX * scale, bw))
    t['_bw_key'] = key
    t['_bw'] = bw
    return bw


def _xbox_text_stages(e, hold):
    """(зсув/альфа назви, зсув/альфа опису) — двоетапний текст усередині банера.

    Спершу видно 'Achievement unlocked' + назву. Приблизно через XBOX_STAGE1
    секунд цей блок їде вгору й зникає, а знизу виїжджає опис ачивки, з яким
    картка потім і закривається.
    """
    t_open = XBOX_T_IN
    if e < t_open:
        return (0.0, 0.0, 0.0, 0.0)
    s = e - t_open
    swap_at = min(XBOX_STAGE1, max(0.0, hold - XBOX_SWAP_T - 0.3))
    if s < swap_at:
        return (0.0, 1.0, 0.0, 0.0)
    k = min(1.0, (s - swap_at) / XBOX_SWAP_T)
    k = k * k * (3.0 - 2.0 * k)
    return (k, 1.0 - k, 1.0 - k, k)


def _draw_xbox(t, now, region, scale, shelf_h):
    """Репліка Xbox One CodePen-анімації: зелене коло виїжджає, зсувається вліво,
    з-під нього розкривається банер-пігулка, текст виїжджає знизу вгору.
    Рідкісні ачивки отримують спрайтовий блиск (brilliant) поверх кола."""
    e = now - t['t0']
    hold = t.get('duration', T_HOLD)
    total = XBOX_T_IN + hold + XBOX_T_OUT
    if e >= total:
        return

    cd = XBOX_CIRCLE * scale
    cr = cd / 2.0
    bw_full = _xbox_banner_width(t, scale)   # (3) під довжину тексту
    shift = (bw_full - cd) * 0.5             # коло зміщується так, щоб банер лишався по центру

    # --- фази (пропорції з CSS keyframes, нормалізовані до XBOX_T_IN/OUT)
    if e < XBOX_T_IN:
        p = e / XBOX_T_IN
        if p < 0.04:
            cs, ca = 0.1, 0.0
        elif p < 0.17:
            k = (p - 0.04) / 0.13
            cs, ca = 0.1 + 1.0 * k, min(1.0, k * 2.0)
        elif p < 0.21:
            cs, ca = 1.1 - 0.1 * ((p - 0.17) / 0.04), 1.0
        else:
            cs, ca = 1.0, 1.0
        k_open = 0.0 if p < 0.46 else (p - 0.46) / 0.54
        k_open = k_open * k_open * (3.0 - 2.0 * k_open)
        alpha = 1.0
    elif e < XBOX_T_IN + hold:
        cs, ca, k_open, alpha = 1.0, 1.0, 1.0, 1.0
    else:
        p = (e - XBOX_T_IN - hold) / XBOX_T_OUT
        k_open = max(0.0, 1.0 - p / 0.55)
        k_open = k_open * k_open * (3.0 - 2.0 * k_open)
        if p < 0.55:
            cs, ca, alpha = 1.0, 1.0, 1.0
        else:
            q = (p - 0.55) / 0.45
            cs = 1.0 + 0.1 * math.sin(q * math.pi) - q * 0.9
            ca = max(0.0, 1.0 - max(0.0, (q - 0.7) / 0.3))
            alpha = 1.0
        cs = max(0.05, cs)

    # --- геометрія: все по центру знизу
    base_y = shelf_h + (MARGIN_B + 16) * scale
    cy = base_y + cr
    center_x = region.width / 2.0
    cx = center_x - shift * k_open          # коло їде вліво
    bw = cd + (bw_full - cd) * k_open       # банер росте від діаметра кола

    gpu.state.blend_set('ALPHA')

    ft = _font('XBOX', 'title')
    fd = _font('XBOX', 'desc')
    hsz = max(8, int(XBOX_TEXT_HDR * scale))
    nsz = max(8, int(XBOX_TEXT_NAME * scale))

    # --- банер (пігулка) під колом
    if k_open > 0.001:
        bx = cx - cr                     # банер починається від лівого краю кола
        bpts = _round_rect_pts(bx, cy - cr, bw, cd, cr)
        _draw_solid(bpts, (XBOX_GREEN[0], XBOX_GREEN[1], XBOX_GREEN[2], XBOX_GREEN[3] * alpha))

        # --- текст банера, жорстко обрізаний межами банера (blf CLIPPING),
        #     щоб під час розкриття / згортання нічого не вилазило за картку
        tx = bx + cd + 18 * scale
        tw = bw - cd - XBOX_TEXT_PAD * scale
        if tw > 12:
            for f in {ft, fd}:
                blf.clipping(f, tx, cy - cr + 1 * scale, tx + tw, cy + cr - 1 * scale)
                blf.enable(f, blf.CLIPPING)

            up_off, up_a, dn_off, dn_a = _xbox_text_stages(e, hold)
            # (1) плавна поява тексту (як textSlide 20%→25%), а не миттєва
            appear = _smooth01((e - (XBOX_T_IN - 0.42)) / 0.52)
            # (2) на згортанні текст НЕ їде вгору — лише згасає разом із банером
            closing = _smooth01((e - (XBOX_T_IN + hold)) / (XBOX_T_OUT * 0.5))
            text_a = appear * (1.0 - closing) * alpha
            slide_in = (1.0 - appear) * 46.0 * scale
            rise = cd * 0.95

            a1 = text_a * up_a
            if a1 > 0.01:
                dy1 = -slide_in - up_off * rise
                blf.size(fd, hsz)
                blf.color(fd, 1, 1, 1, a1)
                blf.position(fd, tx, cy + 4 * scale + dy1, 0)
                _draw_clipped(fd, "Rare achievement unlocked" if t['rare'] else "Achievement unlocked", tw)
                blf.size(ft, nsz)
                blf.color(ft, 1, 1, 1, a1)
                blf.position(ft, tx, cy - 17 * scale + dy1, 0)
                _draw_clipped(ft, t['title'], tw)

            a2 = text_a * dn_a
            if a2 > 0.01:
                dy2 = dn_off * rise - slide_in
                blf.size(fd, nsz)
                blf.color(fd, 1, 1, 1, a2)
                blf.position(fd, tx, cy - 6 * scale - dy2, 0)
                _draw_clipped(fd, t.get('desc', ""), tw)

            for f in {ft, fd}:
                blf.disable(f, blf.CLIPPING)

    # --- коло поверх банера
    if ca > 0.01:
        rr = cr * cs
        # (6) пульсуючі кола-хвилі ::before / ::after (scale_circle_1)
        for delay, col in ((0.0, XBOX_GREEN_LIGHT), (0.1, XBOX_GREEN_DARK)):
            pp = -1.0
            if e >= delay and e < XBOX_T_IN:                 # пульс на початку
                pp = (e - delay) / max(0.001, XBOX_T_IN)
            elif e >= XBOX_T_IN + hold:                       # і на закритті
                pp = (e - (XBOX_T_IN + hold) - delay) / max(0.001, XBOX_T_OUT)
            if 0.0 <= pp <= 1.0:
                ps, po = _pulse_phase(pp)
                _draw_ring_pulse(cx, cy, rr * (1.0 + 0.45 * ps), col, po * 0.85 * alpha)

        _draw_circle(cx, cy, rr, (XBOX_GREEN[0], XBOX_GREEN[1], XBOX_GREEN[2], ca * alpha))

        isz = cd * 0.52 * cs
        # Іконка аддона на початку, далі кросфейд у трофей/діамант (CSS 19%→24%)
        if e < XBOX_T_IN:
            swap = _smooth01((e / XBOX_T_IN - XBOX_SPRITE_SWAP_AT) / 0.17)
        else:
            swap = 1.0
        if e >= XBOX_T_IN + hold:
            q = (e - XBOX_T_IN - hold) / XBOX_T_OUT
            if q > 0.55:
                swap = max(0.0, 1.0 - (q - 0.55) / 0.3)

        # іконки збережені з премноженою альфою
        gpu.state.blend_set('ALPHA_PREMULT')

        # X_icon.png збережена зі звичайною (straight) альфою, тож на час її
        # малювання перемикаємось на ALPHA — інакше прозорі краї дали б ореол.
        xbox_tex = _asset("X_icon.png", premul=False)
        if swap < 0.999 and xbox_tex is not None:
            gpu.state.blend_set('ALPHA')
            _draw_image_uv(xbox_tex, cx - isz/2.0, cy - isz/2.0, isz, isz,
                           alpha=(1.0 - swap) * ca * alpha)
            gpu.state.blend_set('ALPHA_PREMULT')

        if swap > 0.001:
            if t.get('rare'):
                # (4,5) рідкісна → ДІАМАНТ зі спрайту. Програється повністю
                # вперед на 30 к/с і завмирає на останньому кадрі; щойно картка
                # починає згортатись (End) — той самий спрайт іде у зворотному
                # напрямку з тією ж швидкістю.
                sprite = _asset("diamond_spritesheet.png", premul=False)
                if sprite is not None:
                    fwd_dur = XBOX_SPRITE_FRAMES / XBOX_SPRITE_FPS
                    # Реверс стартує ще ДО згортання картки, щоб встигнути
                    # догратись, поки коло видиме (само згортання коротше за
                    # повний прохід спрайту). Не раніше, ніж закінчився прямий
                    # прохід — інакше на коротких тостах вони б наклались.
                    rev_start = max(XBOX_SPRITE_DELAY + fwd_dur,
                                    XBOX_T_IN + hold - XBOX_SPRITE_END_LEAD)
                    if e < rev_start:
                        fr = int(max(0.0, e - XBOX_SPRITE_DELAY) * XBOX_SPRITE_FPS)
                    else:
                        fr = (XBOX_SPRITE_FRAMES - 1
                              - int((e - rev_start) * XBOX_SPRITE_FPS))
                    fr = max(0, min(XBOX_SPRITE_FRAMES - 1, fr))
                    u0, u1, v0, v1 = _sprite_uv(fr)
                    ds = rr * XBOX_SPRITE_SCALE
                    # альфа вшита у кадри → звичайне ALPHA-змішування;
                    # swap дає короткий фейд появи (як у трофея)
                    gpu.state.blend_set('ALPHA')
                    _draw_image_uv(sprite, cx - ds, cy - ds, ds * 2.0, ds * 2.0,
                                   u0=u0, u1=u1, v0=v0, v1=v1,
                                   alpha=swap * ca * alpha)
                    gpu.state.blend_set('ALPHA_PREMULT')
            else:
                # (4) звичайна → анімація кубка: статична версія без ручок ззаду,
                # повна версія масштабується по X як |cos| (rotateY 6s infinite)
                tro_full = _asset("trophy_full.png")
                tro_plain = _asset("trophy_no_handles.png")
                ang = (now * 2.0 * math.pi / XBOX_SPIN_T) % (2.0 * math.pi)
                c = abs(math.cos(ang))
                ta = swap * ca * alpha
                if tro_plain is not None:
                    _draw_image_uv(tro_plain, cx - isz/2.0, cy - isz/2.0, isz, isz, alpha=ta)
                if tro_full is not None and c > 0.02:
                    w2 = isz * c
                    _draw_image_uv(tro_full, cx - w2/2.0, cy - isz/2.0, w2, isz, alpha=ta)

    gpu.state.blend_set('NONE')


def _draw():
    if not _toasts:
        return
    if _shader_uniform is None:
        _init_shaders()
    _ensure_fonts()

    geom = _viewport_geom()
    if geom is None:
        return
    region, scale, shelf_h = geom
    now = time.monotonic()
    style = _get_style()

    if style == 'XBOX':
        if _toasts:
            _draw_xbox(_toasts[0], now, region, scale, shelf_h)
    else:
        for t in list(_toasts):
            _draw_card(t, now, region, scale, shelf_h, style)


# =============================================================== аудіо
def _play_sound(path):
    """Сумісність: програти конкретний файл (шлях) через систему звуків."""
    if not path:
        return
    try:
        from . import sounds
        sounds.play(path, 1.0)
    except Exception as _dbg_err:  # noqa: BLE001
        debug.log("toast.py:1209", _dbg_err)
        pass


def _play_slot(slot):
    """Програти звук слоту ('unlock' / 'rare_unlock' / 'end' / 'rare_end')."""
    try:
        from . import sounds
        sounds.play_slot(slot)
    except Exception as _dbg_err:  # noqa: BLE001
        debug.log("toast.py:1218", _dbg_err)
        pass


# =============================================================== таймер / черга
def _redraw_all():
    for win in bpy.context.window_manager.windows:
        for area in win.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


def _total_time(style, hold):
    if style == 'XBOX':
        return XBOX_T_IN + hold + XBOX_T_OUT
    return T_IN + hold + T_OUT


def _in_time(style):
    return XBOX_T_IN if style == 'XBOX' else T_IN


_last_spawn = 0.0     # час появи останньої картки (для паузи між ачивками)


def _activate(item, now, style):
    """Переводить тост із черги в активні та планує звук розблокування."""
    global _last_spawn
    item['t0'] = now
    item['slot'] = 0
    item['slot_prev'] = 0
    item['slot_t0'] = 0.0
    # Steam: нові знизу — усі наявні зсуваються на слот вище.
    if style == 'STEAM':
        for other in _toasts:
            other['slot_prev'] = other.get('slot', 0)
            other['slot'] = other.get('slot', 0) + 1
            other['slot_t0'] = now
    _toasts.append(item)
    _last_spawn = now

    if item.get('sound'):
        _play_sound(item['sound'])
    else:
        _play_slot('rare_unlock' if item.get('rare') else 'unlock')


def _tick():
    now = time.monotonic()
    style = _get_style()

    # 1) звук "закінчення" + зняття померлих тостів (у кожного свій таймер)
    for t in list(_toasts):
        hold = t.get('duration', T_HOLD)
        if not t.get('end_played') and (now - t['t0']) >= (_in_time(style) + hold):
            t['end_played'] = True
            _play_slot('rare_end' if t.get('rare') else 'end')
        if (now - t['t0']) >= _total_time(style, hold):
            try:
                _toasts.remove(t)
            except ValueError:
                pass
            # решта опускається на слот нижче (Steam)
            if style == 'STEAM':
                for other in _toasts:
                    if other.get('slot', 0) > t.get('slot', 0):
                        other['slot_prev'] = other.get('slot', 0)
                        other['slot'] = other.get('slot', 0) - 1
                        other['slot_t0'] = now

    # 2) запуск нових
    if _pending:
        if style == 'STEAM':
            # Steam: паралельно, але не більше STEAM_MAX_VISIBLE карток і не
            # частіше ніж раз на STEAM_GAP_T — решта чекає в черзі.
            if (len(_toasts) < STEAM_MAX_VISIBLE
                    and (now - _last_spawn) >= STEAM_GAP_T):
                _activate(_pending.pop(0), now, style)
        else:
            # Xbox / PlayStation: строго по черзі, одна за одною.
            if not _toasts:
                _activate(_pending.pop(0), now, style)

    _redraw_all()

    if _toasts or _pending:
        return 1.0 / 60.0
    return None


# =============================================================== публічний API
def get_preferences():
    """Returns AddonPreferences for achievements if registered."""
    try:
        addon_name = __package__ or "achievements"
        prefs = getattr(bpy.context, "preferences", None)
        if prefs and hasattr(prefs, "addons") and addon_name in prefs.addons:
            return prefs.addons[addon_name].preferences
    except Exception as _dbg_err:
        debug.log("toast.py:1327", _dbg_err)
        pass
    return None


def ensure_handler():
    global _draw_handle
    if _draw_handle is None:
        _draw_handle = bpy.types.SpaceView3D.draw_handler_add(
            _draw, (), 'WINDOW', 'POST_PIXEL')


def _unload_fonts():
    """Вивільняє шрифти, завантажені _load_font (blf.unload приймає шлях до
    файлу, не font id), та скидає стан, щоб наступний register() довантажив
    їх заново замість накопичення font-ID при циклах увімк/вимк аддона."""
    global _font_paths_loaded, _fonts
    for p in _font_paths_loaded:
        try:
            blf.unload(p)
        except Exception as _dbg_err:  # noqa: BLE001
            debug.log("toast.py:1347", _dbg_err)
            pass
    _font_paths_loaded = []
    _fonts = {}


def invalidate_textures():
    """Скидає кеш GPU-текстур. Викликається при завантаженні іншого .blend.

    `gpu.texture.from_image()` прив'язана до датаблоку `bpy.data.images`, а
    відкриття нового файлу зносить увесь bpy.data разом із ним. Кеш при цьому
    лишався б із текстурами, чиї джерела вже мертві — артефакти в кадрі або
    падіння на семплінгу. Скидання лише кеш-словників: наступний малюнок
    перезавантажить зображення й створить текстури заново.

    Тости, що вже висять, теж чистимо: у кожного свій `icon_img`/`icon_tex` із
    datablock'ів попереднього файлу.
    """
    global _asset_tex, _mask_tex, _mask_failed
    _asset_tex = {}
    _mask_tex = None
    _mask_failed = False
    for t in list(_toasts) + list(_pending):
        try:
            t['icon_tex'] = None
            t['icon_img'] = None
            t['icon_done'] = True     # без датаблоку відновлювати нічого
        except Exception as _dbg_err:  # noqa: BLE001
            debug.log("toast.py:invalidate_textures", _dbg_err)


def remove_handler():
    global _draw_handle, _pending, _shader_uniform, _shader_smooth
    global _shader_conic, _shader_radial, _shader_image_tint, _mask_tex, _mask_failed
    global _asset_tex, _last_spawn
    _pending.clear()
    _toasts.clear()
    _asset_tex = {}
    _last_spawn = 0.0
    _unload_fonts()
    if _draw_handle is not None:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(_draw_handle, 'WINDOW')
        except (ValueError, RuntimeError):
            pass
        _draw_handle = None
    if hasattr(bpy.app.timers, "is_registered"):
        if bpy.app.timers.is_registered(_tick):
            bpy.app.timers.unregister(_tick)
    else:
        try:
            bpy.app.timers.unregister(_tick)
        except (ValueError, RuntimeError):
            pass
    _shader_uniform = None
    _shader_smooth = None
    _shader_conic = None
    _shader_radial = None
    _shader_image_tint = None
    _mask_tex = None
    _mask_failed = False


def show(title, desc, rare=False, icon_path=None, sound_path=None,
         percent=None, header=None):
    """Поставити нотифікацію в чергу на показ.

    percent/header — приймаються для сумісності, але у Steam-стилі
    (як на референсному скріншоті) показуються лише Title + Description.
    """
    prefs = get_preferences()
    if prefs is not None:
        if not getattr(prefs, "enable_toast", True):
            return
        if not getattr(prefs, "enable_sound", True):
            sound_path = None
        if not getattr(prefs, "show_rare_glow", True):
            rare = False

    duration = getattr(prefs, "toast_duration", T_HOLD) if prefs is not None else T_HOLD

    ensure_handler()

    # Тут вантажимо ЛИШЕ датаблок зображення (безпечно в будь-якому контексті).
    # GPU-текстуру створюємо ліниво у draw-колбеку — інакше gpu.texture.from_image
    # у render/depsgraph-хендлері крашить Blender і ламає рендер тексту.
    icon_img = None
    if icon_path:
        try:
            icon_img = bpy.data.images.load(icon_path, check_existing=True)
        except Exception as _dbg_err:  # noqa: BLE001
            debug.log("toast.py:1419", _dbg_err)
            icon_img = None

    _pending.append({
        'title': title,
        'desc': desc,
        'rare': bool(rare),
        'icon_img': icon_img,
        'icon_tex': None,
        'icon_done': False,
        'sound': sound_path,
        'end_played': False,
        'duration': float(duration),
    })

    if not bpy.app.timers.is_registered(_tick):
        bpy.app.timers.register(_tick, first_interval=0.0)
