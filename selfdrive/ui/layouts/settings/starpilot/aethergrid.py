from __future__ import annotations
from dataclasses import dataclass, replace
import math
import random
import time
import pyray as rl
from collections.abc import Callable
from openpilot.system.ui.lib.application import gui_app, FontWeight, MousePos, MouseEvent, FONT_SCALE, font_fallback
from openpilot.system.ui.lib.multilang import tr
from openpilot.system.ui.lib.scroll_panel2 import GuiScrollPanel2
from openpilot.system.ui.lib.text_measure import measure_text_cached
from openpilot.system.ui.lib.wrap_text import wrap_text as wrap_body_text
from openpilot.system.ui.widgets import Widget, DialogResult
from openpilot.system.ui.widgets.label import gui_label

from openpilot.selfdrive.ui.layouts.settings.starpilot.scribble import draw_custom_icon
from openpilot.selfdrive.ui.lib import aether_style as AS
from openpilot.selfdrive.ui.lib.ui_param_cache import shared_ui_params


GEOMETRY_OFFSET = 10
PLATE_TAU = 0.060
SLIDER_BUTTON_SIZE = 87
TILE_RADIUS_PX = 18.0
MIN_TILE_WIDTH = 300
TOGGLE_MIN_HEIGHT = 80

_HUD_BG_ON = AS.SETTINGS_CARD_FILL
_HUD_BG_DISABLED = rl.Color(8, 10, 14, 255)
_HUD_BORDER_OFF = AS.SETTINGS_TILE_BORDER
SHOW_CONSTELLATIONS = False  # Aether Cards: plain cards; True restores the starfield on tiles and switches
_HUD_TEXT_DIM = rl.Color(220, 220, 230, 220)
# Constellation accent node colors (replaces top dash LED)
_CONST_PRIMARY = rl.Color(235, 240, 255, 255)
_CONST_SECONDARY = rl.Color(180, 195, 220, 255)
_CONST_TERTIARY = rl.Color(145, 155, 175, 255)

_NODE_NUM_MIN = 3
_NODE_NUM_MAX = 5


_GLOBAL_SCISSOR_LIMIT: rl.Rectangle | None = None

def aether_begin_scissor_mode(x: int, y: int, w: int, h: int) -> None:
  global _GLOBAL_SCISSOR_LIMIT
  if _GLOBAL_SCISSOR_LIMIT is not None:
    limit = _GLOBAL_SCISSOR_LIMIT
    ix1 = max(x, int(limit.x))
    iy1 = max(y, int(limit.y))
    ix2 = min(x + w, int(limit.x + limit.width))
    iy2 = min(y + h, int(limit.y + limit.height))
    iw = max(0, ix2 - ix1)
    ih = max(0, iy2 - iy1)
    rl.begin_scissor_mode(ix1, iy1, iw, ih)
  else:
    rl.begin_scissor_mode(x, y, w, h)

def aether_end_scissor_mode() -> None:
  global _GLOBAL_SCISSOR_LIMIT
  if _GLOBAL_SCISSOR_LIMIT is not None:
    limit = _GLOBAL_SCISSOR_LIMIT
    rl.begin_scissor_mode(int(limit.x), int(limit.y), int(limit.width), int(limit.height))
  else:
    rl.end_scissor_mode()

# Custom vector icon layout constants (scribble.py coordinate system)
CUSTOM_ICON_BASE_SIZE = 100.0
CUSTOM_ICON_SCALE_MULT = 1.60
CUSTOM_ICON_CANVAS_SIZE = 60.0


class SPACING:
  xs: int = 4
  sm: int = 8
  md: int = 12
  lg: int = 16
  xl: int = 24
  xxl: int = 32
  xxxl: int = 48

  tile_gap: int = AS.SETTINGS_TILE_GAP
  tile_content: int = 16
  line_gap: int = 8


def hex_to_color(hex_str: str) -> rl.Color:
  hex_str = hex_str.lstrip('#')
  return rl.Color(int(hex_str[0:2], 16), int(hex_str[2:4], 16), int(hex_str[4:6], 16), 255)


def _resolve_value(value, default=""):
  if callable(value):
    return value()
  return value if value is not None else default


def _get_rgba(color) -> tuple[int, int, int, int]:
  if hasattr(color, "r"):
    return color.r, color.g, color.b, color.a
  if isinstance(color, (tuple, list)) and len(color) >= 3:
    return color[0], color[1], color[2], color[3] if len(color) > 3 else 255
  return 255, 255, 255, 255


def with_alpha(color, alpha: int) -> rl.Color:
  r, g, b, a = _get_rgba(color)
  return rl.Color(r, g, b, max(0, min(a, int(alpha))))


def clamp_and_snap(value: float, min_val: float, max_val: float, step: float) -> float:
    if step <= 0:
        return max(min_val, min(max_val, value))
    snapped = round((value - min_val) / step) * step + min_val
    return max(min_val, min(max_val, snapped))


def value_fraction(value: float, min_val: float, max_val: float) -> float:
    val_range = max_val - min_val
    if val_range == 0:
        return 0.0
    return max(0.0, min(1.0, (value - min_val) / val_range))


def update_val_from_mouse(mouse_pos: MousePos, track_rect: rl.Rectangle, min_val: float, max_val: float, step: float) -> float:
    if track_rect.width <= 0:
        return min_val
    rel_x = max(0.0, min(1.0, (mouse_pos.x - track_rect.x) / track_rect.width))
    val = min_val + rel_x * (max_val - min_val)
    return clamp_and_snap(val, min_val, max_val, step)


def mix_colors(base, accent, weight: float, alpha: int | None = None) -> rl.Color:
  br, bg, bb, ba = _get_rgba(base)
  ar, ag, ab, aa = _get_rgba(accent)
  w = max(0.0, min(1.0, weight))
  return rl.Color(
    int(round(br + (ar - br) * w)),
    int(round(bg + (ag - bg) * w)),
    int(round(bb + (ab - bb) * w)),
    ba if alpha is None else alpha,
  )



def _snap(value: float) -> float:
  return float(round(value))


def snap_rect(rect: rl.Rectangle) -> rl.Rectangle:
  return rl.Rectangle(
    _snap(rect.x), _snap(rect.y),
    _snap(rect.width), _snap(rect.height),
  )


def _inset_rect(rect: rl.Rectangle, inset: float) -> rl.Rectangle:
  return snap_rect(rl.Rectangle(rect.x + inset, rect.y + inset, rect.width - inset * 2, rect.height - inset * 2))


def _intersect_rect(a: rl.Rectangle, b: rl.Rectangle) -> rl.Rectangle:
  left = max(a.x, b.x)
  top = max(a.y, b.y)
  right = min(a.x + a.width, b.x + b.width)
  bottom = min(a.y + a.height, b.y + b.height)
  if right <= left or bottom <= top:
    return rl.Rectangle(left, top, 0, 0)
  return rl.Rectangle(left, top, right - left, bottom - top)


def _roundness_for(rect: rl.Rectangle, radius_px: float = TILE_RADIUS_PX) -> float:
  min_dim = max(1.0, min(rect.width, rect.height))
  return max(0.0, min(0.5, radius_px / min_dim))


def _segments_for(rect: rl.Rectangle, radius_px: float = TILE_RADIUS_PX) -> int:
  effective_radius = max(2.0, min(radius_px, min(rect.width, rect.height) / 2))
  return max(12, min(28, int(round(effective_radius * 1.25))))


def draw_text_fit_common(
  font: rl.Font,
  text: str,
  pos: rl.Vector2,
  max_width: float,
  font_size: float,
  *,
  align_center: bool = False,
  align_right: bool = False,
  letter_spacing: float = 0,
  uppercase: bool = False,
  color: rl.Color = rl.WHITE,
  shadow_alpha: int = 0,
):
  if uppercase:
    text = text.upper()
  requested_spacing = letter_spacing * FONT_SCALE
  spacing = round(requested_spacing)
  base_font_size = max(1, int(round(font_size)))
  size = measure_text_cached(font, text, base_font_size, spacing=spacing)
  actual_font_size = base_font_size
  if size.x > max_width:
    MIN_FONT = 16
    hi = max(MIN_FONT, int(round(font_size * (max_width / size.x))))
    lo = MIN_FONT
    actual_font_size = hi
    while lo < hi:
      mid = (lo + hi + 1) // 2
      fitted_spacing = round(requested_spacing * (mid / base_font_size))
      if measure_text_cached(font, text, mid, spacing=fitted_spacing).x <= max_width:
        lo = mid
        actual_font_size = mid
      else:
        hi = mid - 1
    fitted_spacing = round(requested_spacing * (actual_font_size / base_font_size))
    spacing = fitted_spacing
    render_width = measure_text_cached(font, text, actual_font_size, spacing=spacing).x
  else:
    render_width = size.x
  nudge_y = (font_size - actual_font_size) * FONT_SCALE / 2
  draw_x = pos.x
  if align_center:
    draw_x = pos.x + (max_width - render_width) / 2
  elif align_right:
    draw_x = pos.x + max_width - render_width
  if shadow_alpha > 0:
    shadow_pos = rl.Vector2(round(draw_x + 1), round(pos.y + nudge_y + 1))
    rl.draw_text_ex(font, text, shadow_pos, actual_font_size, spacing, rl.Color(0, 0, 0, shadow_alpha))
  rl.draw_text_ex(font, text, rl.Vector2(round(draw_x), round(pos.y + nudge_y)), actual_font_size, spacing, color)


def text_ink_bounds(font: rl.Font, text: str, font_size: float) -> rl.Rectangle:
  """Visible bounds of a single line, excluding the font's ascent/descent space."""
  if not getattr(font, "baseSize", 0) or not getattr(font, "glyphs", None) or not getattr(font, "recs", None):
    measured = measure_text_cached(font, text, int(font_size))
    return rl.Rectangle(0, 0, measured.x, measured.y)
  scale = font_size * FONT_SCALE / font.baseSize
  cursor = 0.0
  left = top = math.inf
  right = bottom = -math.inf
  for character in text:
    index = rl.get_glyph_index(font, ord(character))
    glyph, glyph_rect = font.glyphs[index], font.recs[index]
    if not character.isspace() and glyph_rect.width > 0 and glyph_rect.height > 0:
      left = min(left, cursor + glyph.offsetX * scale)
      right = max(right, cursor + (glyph.offsetX + glyph_rect.width) * scale)
      top = min(top, glyph.offsetY * scale)
      bottom = max(bottom, (glyph.offsetY + glyph_rect.height) * scale)
    cursor += (glyph.advanceX or glyph_rect.width + glyph.offsetX) * scale
  if left == math.inf:
    return rl.Rectangle()
  return rl.Rectangle(left, top, right - left, bottom - top)


def draw_centered_text(rect: rl.Rectangle, text: str, font_size: int, color: rl.Color, font_weight=FontWeight.BOLD):
  """Center the visible glyphs, including short values such as Auto or 50%."""
  font = font_fallback(gui_app.font(font_weight))
  measured = measure_text_cached(font, text, font_size)
  if measured.x > rect.width:
    font_size = max(16, int(font_size * rect.width / measured.x))
  ink = text_ink_bounds(font, text, font_size)
  position = rl.Vector2(round(rect.x + (rect.width - ink.width) / 2 - ink.x),
                        round(rect.y + (rect.height - ink.height) / 2 - ink.y))
  rl.draw_text_ex(font, text, position, font_size, 0, color)


def draw_stepper_symbol(rect: rl.Rectangle, *, increment: bool, color: rl.Color = rl.WHITE):
  """Font-independent plus/minus, centered in the actual button face."""
  center = rl.Vector2(rect.x + rect.width / 2, rect.y + rect.height / 2)
  half_span = min(rect.width, rect.height) * 0.15
  thickness = max(3.0, half_span * 0.24)
  rl.draw_line_ex(rl.Vector2(center.x - half_span, center.y), rl.Vector2(center.x + half_span, center.y), thickness, color)
  if increment:
    rl.draw_line_ex(rl.Vector2(center.x, center.y - half_span), rl.Vector2(center.x, center.y + half_span), thickness, color)


def draw_rounded_fill(rect: rl.Rectangle, color: rl.Color, radius_px: float = TILE_RADIUS_PX, segments: int | None = None):
  snapped = snap_rect(rect)
  rl.draw_rectangle_rounded(snapped, _roundness_for(snapped, radius_px), segments or _segments_for(snapped, radius_px), color)


def aether_roundness(rect: rl.Rectangle, radius_px: float) -> float:
  """raylib roundness for a true pixel corner radius (raylib's radius is roundness * shorter side / 2).

  _roundness_for() predates Aether Cards and yields half the requested radius; existing widgets keep it.
  """
  return max(0.0, min(1.0, 2.0 * radius_px / max(1.0, min(rect.width, rect.height))))


def aether_fill(rect: rl.Rectangle, color: rl.Color, radius_px: float, segments: int = 24):
  rl.draw_rectangle_rounded(snap_rect(rect), aether_roundness(rect, radius_px), segments, color)


def draw_rounded_stroke(rect: rl.Rectangle, color: rl.Color, thickness: int = 1, radius_px: float = TILE_RADIUS_PX, segments: int | None = None):
  snapped = snap_rect(rect)
  rl.draw_rectangle_rounded_lines_ex(snapped, _roundness_for(snapped, radius_px), segments or _segments_for(snapped, radius_px), thickness, color)


def truncate_text_ellipsis(
  font: rl.Font, text: str, max_width: float, font_size: int
) -> str:
  if measure_text_cached(font, text, font_size).x <= max_width:
    return text
  shortened = text.rstrip()
  candidate = f"{shortened}..."
  while shortened and measure_text_cached(font, candidate, font_size).x > max_width:
    shortened = shortened[:-1].rstrip()
    candidate = f"{shortened}..." if shortened else "..."
  return candidate


class AetherListColors:
  PANEL_BG = AS.SETTINGS_BG
  PANEL_BORDER = rl.Color(255, 255, 255, 22)
  PANEL_GLOW = rl.Color(92, 116, 151, 34)
  HEADER = rl.Color(236, 242, 250, 255)
  SUBTEXT = rl.Color(200, 210, 225, 255)
  MUTED = rl.Color(160, 170, 185, 255)
  ROW_BG = rl.Color(255, 255, 255, 0)
  ROW_BORDER = rl.Color(255, 255, 255, 0)
  ROW_SEPARATOR = rl.Color(255, 255, 255, 16)
  ROW_HOVER = rl.Color(255, 255, 255, 8)
  CURRENT_BG = rl.Color(139, 92, 246, 18)
  CURRENT_BORDER = rl.Color(139, 92, 246, 44)
  ACTION_BG = rl.Color(255, 255, 255, 0)
  ACTION_SEPARATOR = rl.Color(255, 255, 255, 18)
  PRIMARY = AS.ACCENT_SOLID
  PRIMARY_SOFT = rl.Color(89, 116, 151, 48)
  DANGER = rl.Color(173, 78, 90, 255)
  DANGER_SOFT = rl.Color(173, 78, 90, 44)
  SUCCESS = rl.Color(94, 168, 130, 255)
  SUCCESS_SOFT = rl.Color(94, 168, 130, 44)
  WARNING = rl.Color(204, 158, 83, 255)
  SCROLL_TRACK = rl.Color(255, 255, 255, 10)
  SCROLL_THUMB = rl.Color(255, 255, 255, 90)


@dataclass(frozen=True)
class AetherListMetrics:
  max_content_width: int = 100000
  outer_margin_x: int = 0
  outer_margin_y: int = 0
  panel_padding_x: int = 0
  panel_padding_top: int = 0
  panel_padding_bottom: int = 0
  header_height: int = 0
  section_gap: int = 24
  section_header_height: int = AS.SETTINGS_GROUP_HEADING_HEIGHT
  section_header_gap: int = AS.SETTINGS_GROUP_HEADING_GAP
  row_height: int = AS.SETTINGS_ROW_CARD_HEIGHT + AS.SETTINGS_ROW_GAP  # a card plus the gap between cards
  utility_row_height: int = 128
  row_radius: float = 0.12
  action_width: int = 235
  header_button_height: int = 84
  header_button_gap: int = 14  # used by driving_model
  fade_height: int = 24
  content_right_gutter: int = 0
  toggle_width: int = AS.SWITCH_WIDTH
  toggle_height: int = AS.SWITCH_HEIGHT
  toggle_right_inset: int = AS.SETTINGS_CARD_INSET
  adjustor_row_height: int = 136
  adjustor_row_active_height: int = 223
  adjustor_preset_height: int = 64
  adjustor_preset_gap: int = 14
  adjustor_scrubber_height: int = 75

  utility_value_right: int = 391
  utility_value_width: int = 319
  utility_chevron_right: int = 90
  menu_button_font_size: int = 46
  menu_button_roundness: float = 1.0
  menu_button_segments: int = 12


@dataclass(frozen=True)
class AetherListFrame:
  shell: rl.Rectangle
  header: rl.Rectangle
  scroll: rl.Rectangle


@dataclass(frozen=True)
class SettingsPageFrame:
  header: rl.Rectangle
  content: rl.Rectangle


def build_settings_page_frame(rect: rl.Rectangle) -> SettingsPageFrame:
  """Apply the page gutter once, outside every hub/list and at every depth."""
  x = rect.x + AS.SETTINGS_PAGE_MARGIN
  y = rect.y + AS.SETTINGS_PAGE_TOP
  width = max(0.0, rect.width - AS.SETTINGS_PAGE_MARGIN * 2)
  content_y = y + AS.SETTINGS_HEADER_HEIGHT + AS.SETTINGS_HEADER_GAP
  return SettingsPageFrame(
    rl.Rectangle(x, y, width, AS.SETTINGS_HEADER_HEIGHT),
    rl.Rectangle(x, content_y, width, max(0.0, rect.y + rect.height - AS.SETTINGS_PAGE_MARGIN - content_y)),
  )


AETHER_LIST_METRICS = AetherListMetrics()
AETHER_COMPACT_ROW_HEIGHT = AETHER_LIST_METRICS.utility_row_height
COMPACT_PANEL_METRICS = replace(AETHER_LIST_METRICS, header_height=0)


@dataclass(frozen=True, slots=True)
class PanelStyle:
  shell_bg: rl.Color
  shell_border: rl.Color
  shell_glow: rl.Color
  surface_fill: rl.Color
  surface_border: rl.Color
  current_fill: rl.Color
  current_border: rl.Color
  title_color: rl.Color
  subtitle_color: rl.Color
  muted_color: rl.Color
  divider_color: rl.Color
  underline_color: rl.Color
  accent: rl.Color
  danger_fill: rl.Color
  danger_border: rl.Color
  danger_text: rl.Color
  toggle_row_mode: bool = False


DEFAULT_PANEL_STYLE = PanelStyle(
  shell_bg=AetherListColors.PANEL_BG,
  shell_border=AetherListColors.PANEL_BORDER,
  shell_glow=AetherListColors.PANEL_GLOW,
  surface_fill=rl.Color(255, 255, 255, 4),
  surface_border=rl.Color(255, 255, 255, 14),
  current_fill=rl.Color(255, 255, 255, 12),
  current_border=rl.Color(255, 255, 255, 20),
  title_color=AetherListColors.HEADER,
  subtitle_color=AetherListColors.SUBTEXT,
  muted_color=AetherListColors.MUTED,
  divider_color=rl.Color(255, 255, 255, 14),
  underline_color=rl.Color(116, 136, 168, 150),
  accent=AetherListColors.PRIMARY,
  danger_fill=AetherListColors.DANGER_SOFT,
  danger_border=rl.Color(173, 78, 90, 50),
  danger_text=AetherListColors.DANGER,
  toggle_row_mode=True,
)


def _inflate_rect(rect: rl.Rectangle, pad_x: float = 10, pad_y: float = 6) -> rl.Rectangle:
  return rl.Rectangle(rect.x - pad_x, rect.y - pad_y, rect.width + pad_x * 2, rect.height + pad_y * 2)


def _hit_rect(rect: rl.Rectangle, parent_rect: rl.Rectangle | None = None, pad_x: float = 10, pad_y: float = 6) -> rl.Rectangle:
  hit = _inflate_rect(rect, pad_x, pad_y)
  if parent_rect is not None:
    return rl.get_collision_rec(hit, parent_rect)
  return hit


def point_hits(mouse_pos: MousePos, rect: rl.Rectangle, parent_rect: rl.Rectangle | None = None, pad_x: float = 10, pad_y: float = 6) -> bool:
  hit = _hit_rect(rect, parent_rect, pad_x, pad_y)
  return hit.width > 0 and hit.height > 0 and rl.check_collision_point_rec(mouse_pos, hit)


def wrap_text(font: rl.Font, text: str, max_width: float, font_size: float, max_lines: int = 2,
              *, spacing: float | None = None) -> list[str]:
  spacing = font_size * 0.15 if spacing is None else spacing
  words = text.split()
  lines: list[str] = []
  current = ""
  for word in words:
    candidate = f"{current} {word}".strip() if current else word
    if measure_text_cached(font, candidate, int(font_size), spacing=spacing).x <= max_width:
      current = candidate
    else:
      if current:
        lines.append(current)
      current = word
      if len(lines) >= max_lines:
        break
  if current and len(lines) < max_lines:
    lines.append(current)
  return lines if lines else [text]


def build_list_panel_frame(rect: rl.Rectangle, metrics: AetherListMetrics = AETHER_LIST_METRICS) -> AetherListFrame:
  shell_w = min(rect.width - metrics.outer_margin_x * 2, metrics.max_content_width)
  shell_x = rect.x + (rect.width - shell_w) / 2
  shell_y = rect.y + metrics.outer_margin_y
  shell_h = rect.height - metrics.outer_margin_y * 2
  shell_rect = rl.Rectangle(shell_x, shell_y, shell_w, shell_h)

  header_rect = rl.Rectangle(
    shell_x + metrics.panel_padding_x,
    shell_y + metrics.panel_padding_top,
    shell_w - metrics.panel_padding_x * 2,
    metrics.header_height,
  )

  scroll_rect = rl.Rectangle(
    shell_x + metrics.panel_padding_x,
    header_rect.y + header_rect.height,
    shell_w - metrics.panel_padding_x * 2,
    shell_h - metrics.header_height - metrics.panel_padding_top - metrics.panel_padding_bottom,
  )

  return AetherListFrame(shell_rect, header_rect, scroll_rect)


def draw_list_panel_shell(frame: AetherListFrame, style: PanelStyle | None = None, *, bg: rl.Color = AetherListColors.PANEL_BG, border: rl.Color = AetherListColors.PANEL_BORDER, glow: rl.Color = AetherListColors.PANEL_GLOW):
  if style is not None:
    bg = style.shell_bg
    border = style.shell_border
    glow = style.shell_glow
  if style is DEFAULT_PANEL_STYLE:
    # Cards supply the visible containers; a second shell crowds their edges.
    rl.draw_rectangle_rec(snap_rect(frame.shell), AS.SETTINGS_BG)
    return
  shell = snap_rect(frame.shell)
  draw_rounded_fill(shell, bg, radius_px=32)
  draw_rounded_stroke(shell, border, radius_px=32)
  if glow.a > 0:
    glow_rect = _inset_rect(shell, 2)
    draw_rounded_stroke(glow_rect, with_alpha(glow, 14), radius_px=29)


def init_list_panel(rect: rl.Rectangle, style: PanelStyle | None = None, metrics: AetherListMetrics = AETHER_LIST_METRICS) -> tuple[AetherListFrame, rl.Rectangle, float]:
  frame = build_list_panel_frame(rect, metrics)
  draw_list_panel_shell(frame, style)
  scroll_rect = frame.scroll
  content_width = scroll_rect.width - AETHER_LIST_METRICS.content_right_gutter
  return frame, scroll_rect, content_width


def draw_hud_background(rect: rl.Rectangle, accent: rl.Color, glow: float = 1.0, *, radius_px: float = AS.SETTINGS_TILE_RADIUS,
                        bg_color: rl.Color | None = None) -> tuple[rl.Rectangle, rl.Color]:
  """Aether card: opaque card fill with a light outline that warms to the accent as `glow` rises."""
  snapped = snap_rect(rect)
  face = rl.Rectangle(int(snapped.x), int(snapped.y), int(snapped.width), int(snapped.height))
  radius_px = min(radius_px, face.height / 2, face.width / 2)
  aether_fill(face, bg_color if bg_color is not None else _HUD_BG_ON, radius_px)
  g = max(0.0, min(1.0, glow))
  edge = mix_colors(_HUD_BORDER_OFF, rl.Color(accent.r, accent.g, accent.b, 255), g, alpha=int(_HUD_BORDER_OFF.a + (220 - _HUD_BORDER_OFF.a) * g))
  _draw_card_outline(face, edge, radius_px)
  return face, accent


def _draw_card_outline(face: rl.Rectangle, color: rl.Color, radius_px: float, width: float = AS.SETTINGS_CARD_BORDER_WIDTH):
  # Raylib expands its outline outside the supplied rectangle. Keep it inside
  # the component so gaps and scroll clipping agree with the layout bounds.
  outline = _inset_rect(face, width)
  rl.draw_rectangle_rounded_lines_ex(outline, aether_roundness(outline, max(0, radius_px - width)), 24, width, color)


def draw_settings_card(rect: rl.Rectangle, *, border: rl.Color = AS.SETTINGS_CARD_BORDER_IDLE,
                       fill: rl.Color = AS.SETTINGS_CARD_FILL, radius_px: float = AS.SETTINGS_CARD_RADIUS) -> rl.Rectangle:
  """One settings row or control drawn as an Aether card; returns the card face."""
  face = snap_rect(rect)
  radius_px = min(radius_px, face.height / 2, face.width / 2)
  aether_fill(face, fill, radius_px)
  _draw_card_outline(face, border, radius_px)
  return face


def draw_interactive_rect(target_id: str, rect: rl.Rectangle, interactive_rects: dict[str, rl.Rectangle],
                           pressed_target: str | None, scroll_rect: rl.Rectangle | None = None,
                           pad_x: float = 6, pad_y: float = 0) -> tuple[bool, bool]:
  interactive_rects[target_id] = rect
  mouse_pos = gui_app.last_mouse_event.pos
  hovered = point_hits(mouse_pos, rect, scroll_rect, pad_x=pad_x, pad_y=pad_y)
  pressed = pressed_target == target_id and hovered
  return hovered, pressed


def resolve_interactive_target(mouse_pos: MousePos, interactive_rects: dict[str, rl.Rectangle],
                                scroll_rect: rl.Rectangle | None = None,
                                pad_x: float = 6, pad_y: float = 0) -> str | None:
  for target_id, rect in interactive_rects.items():
    if point_hits(mouse_pos, rect, scroll_rect, pad_x=pad_x, pad_y=pad_y):
      return target_id
  return None


class AetherInteractiveMixin:
  """Standard interactive target system for list-panel ManagerViews.

  Provides centralized _interactive_rects management, _pressed_target tracking,
  touch validation through the owning scroll region, and standard mouse
  handling dispatch.

  Subclasses MUST define:
    - self._scroll_rect (rl.Rectangle) — for parent clipping in hit tests
    - self._scroll_panel (GuiScrollPanel2) — for touch validation

  Subclasses SHOULD override:
    - _activate_target(target_id) — custom action dispatch
    - _target_at(mouse_pos) — custom hit target resolution
  """

  def __init__(self, *args, **kwargs):
    self._interactive_rects: dict[str, rl.Rectangle] = {}
    self._interactive_viewports: dict[str, rl.Rectangle] = {}
    self._pressed_target: str | None = None
    self._can_click = True
    self._breadcrumbs = BreadcrumbController()
    super().__init__(*args, **kwargs)

  def _interactive_state(self, target_id: str, rect: rl.Rectangle, *, pad_y: float = 0) -> tuple[bool, bool]:
    self._interactive_rects[target_id] = rect
    self._interactive_viewports[target_id] = self._scroll_rect
    hovered = point_hits(gui_app.last_mouse_event.pos, rect, self._scroll_rect, pad_x=6, pad_y=pad_y)
    return hovered, self._pressed_target == target_id

  def _target_at(self, mouse_pos: MousePos) -> str | None:
    for target_id, rect in self._interactive_rects.items():
      if point_hits(mouse_pos, rect, self._interactive_viewports.get(target_id, self._scroll_rect), pad_x=6, pad_y=0):
        return target_id
    return None

  def _activate_target(self, target_id: str | None):
    pass

  def _scroll_touch_valid(self) -> bool:
    return self._scroll_panel.is_touch_valid()

  def _handle_mouse_press(self, mouse_pos: MousePos):
    self._breadcrumbs.init_interaction(mouse_pos)
    self._pressed_target = self._target_at(mouse_pos)
    self._can_click = True

  def _handle_mouse_event(self, mouse_event: MouseEvent):
    if not self._scroll_touch_valid():
      self._can_click = False
      return
    if self._pressed_target is not None and self._target_at(mouse_event.pos) != self._pressed_target:
      self._pressed_target = None
    self._breadcrumbs.update_interaction(mouse_event.pos)

  def _handle_mouse_release(self, mouse_pos: MousePos):
    target = self._target_at(mouse_pos) if self._scroll_touch_valid() else None

    action = self._breadcrumbs.finish_interaction(mouse_pos)
    if action and self._can_click:
      self._breadcrumbs.handle_click(action)

    if self._pressed_target is not None and self._pressed_target == target and self._can_click:
      self._activate_target(target)
    self._pressed_target = None
    self._can_click = True

  def show_event(self):
    super().show_event()
    self._pressed_target = None
    self._can_click = True
    self._breadcrumbs.cancel_interaction()

  def hide_event(self):
    super().hide_event()
    self._pressed_target = None
    self._can_click = True
    self._breadcrumbs.cancel_interaction()


@dataclass
class SettingsColumn:
  key: str
  height: float
  draw: Callable[[rl.Rectangle], None]


class SettingsColumnScroll:
  def __init__(self):
    self.panel = GuiScrollPanel2(horizontal=False)
    self.scrollbar = AetherScrollbar()
    self.rect = rl.Rectangle(0, 0, 0, 0)
    self.height = 0.0
    self.offset = 0.0


class PanelManagerView(AetherInteractiveMixin, Widget):
  """Shared base for list-panel ManagerViews used by some panels.

  Encapsulates scroll infrastructure, the standard ``_render`` pipeline,
  shared two-column layout helpers, and a convenience toggle-tile factory.
  Subclasses declare panel-specific metrics via ``METRICS`` and override
  ``_draw_header``, ``_measure_content_height``, and
  ``_draw_scroll_content`` (at minimum).
  """

  METRICS: AetherListMetrics = AETHER_LIST_METRICS
  PANEL_STYLE: PanelStyle = DEFAULT_PANEL_STYLE
  TWO_COLUMN_BREAKPOINT: int = 1180
  COLUMN_GAP: float = AS.SETTINGS_ROW_GAP

  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self._scroll_panel = GuiScrollPanel2(horizontal=False)
    self._scrollbar = AetherScrollbar()
    self._content_height = 0.0
    self._scroll_offset = 0.0
    self._scroll_rect = rl.Rectangle(0, 0, 0, 0)
    self._scroll_grid: TileGrid | None = None
    self._column_scrolls: dict[str, SettingsColumnScroll] = {}
    self._active_scroll_columns: list[str] = []
    self._gesture_column: str | None = None
    self._rendering_scroll_panel = self._scroll_panel

  # ── hooks ─────────────────────────────────────────────────

  def _on_frame_created(self, frame: AetherListFrame) -> None:
    """Called after ``init_list_panel`` builds the panel frame.
    Override to store ``frame.shell`` or perform per-frame setup."""

  def _draw_header(self, header_rect: rl.Rectangle) -> None:
    """Override to render the panel header."""

  def _measure_content_height(self, content_width: float) -> float:
    """Override to compute total scrollable content height."""

  def _draw_scroll_content(self, scroll_rect: rl.Rectangle, content_width: float) -> None:
    """Override to render visible content rows inside the scissor region."""

  def _build_scroll_columns(self, width: float) -> list[SettingsColumn]:
    return []

  def reset_scroll(self) -> None:
    self._scroll_panel = GuiScrollPanel2(horizontal=False)
    self._rendering_scroll_panel = self._scroll_panel
    self._scroll_offset = 0.0
    for column in self._column_scrolls.values():
      column.panel = GuiScrollPanel2(horizontal=False)
      column.offset = 0.0
    self._gesture_column = None

  def _handle_mouse_press(self, mouse_pos: MousePos):
    self._gesture_column = next((key for key in self._active_scroll_columns
                                 if rl.check_collision_point_rec(mouse_pos, self._column_scrolls[key].rect)), None)
    super()._handle_mouse_press(mouse_pos)

  def _handle_mouse_release(self, mouse_pos: MousePos):
    super()._handle_mouse_release(mouse_pos)
    self._gesture_column = None

  def _scroll_touch_valid(self) -> bool:
    if self._gesture_column in self._active_scroll_columns:
      return self._column_scrolls[self._gesture_column].panel.is_touch_valid()
    if self._active_scroll_columns:
      return True  # fixed headers and the gutter do not belong to either gesture
    return super()._scroll_touch_valid()

  def _bind_scroll_widget(self, widget: Widget) -> None:
    widget.set_parent_rect(self._scroll_rect)
    widget.set_touch_valid_callback(self._rendering_scroll_panel.is_touch_valid)

  def _render_scroll_area(self, rect: rl.Rectangle, width: float, *, fade_height: int = AETHER_LIST_METRICS.fade_height) -> None:
    columns = self._build_scroll_columns(width)
    self._active_scroll_columns = [column.key for column in columns]
    if not columns:
      self._rendering_scroll_panel = self._scroll_panel
      self._scroll_panel.set_enabled(self.is_visible)
      self._scroll_offset = self._scroll_panel.update(rect, max(self._content_height, rect.height))
      aether_begin_scissor_mode(int(rect.x), int(rect.y), int(rect.width), int(rect.height))
      self._draw_scroll_content(rect, width)
      aether_end_scissor_mode()
      self._scrollbar.render(rect, self._content_height, self._scroll_offset)
      draw_list_scroll_fades(rect, self._content_height, self._scroll_offset, AetherListColors.PANEL_BG, fade_height=fade_height)
      return

    column_width = (width - self.COLUMN_GAP * (len(columns) - 1)) / len(columns)
    self._content_height = max(column.height for column in columns)
    page_offset = self._scroll_offset
    try:
      for index, content in enumerate(columns):
        if content.key not in self._column_scrolls:
          self._column_scrolls[content.key] = SettingsColumnScroll()
        column = self._column_scrolls[content.key]
        viewport = rl.Rectangle(rect.x + index * (column_width + self.COLUMN_GAP), rect.y, column_width, rect.height)
        column.rect, column.height = viewport, content.height
        column.panel.set_enabled(self.is_visible)
        column.offset = column.panel.update(viewport, max(content.height, viewport.height))
        self._scroll_rect = viewport
        self._scroll_offset = column.offset
        self._rendering_scroll_panel = column.panel
        aether_begin_scissor_mode(int(viewport.x), int(viewport.y), int(viewport.width), int(viewport.height))
        content.draw(rl.Rectangle(viewport.x, viewport.y + column.offset, viewport.width, viewport.height))
        aether_end_scissor_mode()
        column.scrollbar.render(viewport, content.height, column.offset)
        draw_list_scroll_fades(viewport, content.height, column.offset, AetherListColors.PANEL_BG, fade_height=fade_height)
    finally:
      self._scroll_rect = rect
      self._scroll_offset = page_offset
      self._rendering_scroll_panel = self._scroll_panel

  def _draw_static_elements(self, scroll_rect: rl.Rectangle, content_width: float) -> None:
    """Override to render fixed-position elements above the scroll area (outside scissor)."""

  def _draw_bottombar(self, bottombar_rect: rl.Rectangle) -> None:
    """Override to render a fixed bottom bar below the scroll area."""

  @property
  def bottombar_height(self) -> float:
    return 0.0

  # ── render pipeline ───────────────────────────────────────

  def _render(self, rect: rl.Rectangle) -> None:
    self._interactive_rects.clear()
    self._interactive_viewports.clear()
    self.set_rect(rect)

    frame, scroll_rect, content_width = init_list_panel(rect, self.PANEL_STYLE, self.METRICS)
    self._scroll_rect = scroll_rect
    self._on_frame_created(frame)

    self._draw_header(frame.header)

    btm_h = self.bottombar_height
    if btm_h > 0:
      scroll_rect.height = max(0.0, scroll_rect.height - btm_h)

    self._content_height = self._measure_content_height(content_width)
    self._render_scroll_area(scroll_rect, content_width)

    self._draw_static_elements(scroll_rect, content_width)

    if btm_h > 0:
      btm_rect = rl.Rectangle(scroll_rect.x, scroll_rect.y + scroll_rect.height,
                              content_width, btm_h)
      self._draw_bottombar(btm_rect)

  # ── shared layout helpers ─────────────────────────────────

  def _uses_two_columns(self, width: float) -> bool:
    return width >= self.TWO_COLUMN_BREAKPOINT

  def _column_width(self, width: float) -> float:
    return (width - self.COLUMN_GAP) / 2 if self._uses_two_columns(width) else width

  def _section_height(self, count: int, row_height: float) -> float:
    return 0.0 if count <= 0 else count * row_height

  def _section_block_height(self, content_height: float) -> float:
    if content_height <= 0:
      return 0.0
    return self.METRICS.section_header_height + self.METRICS.section_header_gap + content_height

  def _stacked_section_height(self, sections: list[float]) -> float:
    if not sections:
      return 0.0
    return sum(sections) + self.METRICS.section_gap * (len(sections) - 1)

  def _compute_two_column_height(self, left_height: float) -> float:
    return max(self._scroll_rect.height if self._scroll_rect else 0.0, left_height)

  def _draw_two_column_tile_grid(self, grid: TileGrid, x: float, y: float, column_width: float, matching_height: float, title: str | None = None, style: PanelStyle | None = None, columns: int = 2):
    if style is None:
      style = self.PANEL_STYLE
    grid._columns = columns
    grid_rect = rl.Rectangle(x, y, column_width, max(0.0, matching_height))
    if title:
      grid_rect = draw_settings_group(grid_rect, title, style=style, kind="tiles")
    self._render_scroll_grid(grid, grid_rect)

  # ── convenience builders ──────────────────────────────────

  def _make_toggle_tile(self, d: dict) -> ToggleTile:
    cls = RowToggleTile if self.PANEL_STYLE.toggle_row_mode else ToggleTile
    return cls(
      title=d["title"],
      get_state=d["get_state"],
      set_state=d["set_state"],
      bg_color=self.PANEL_STYLE.accent,
      desc=d.get("subtitle", ""),
      is_enabled=d.get("is_enabled"),
      disabled_label=d.get("disabled_label", ""),
    )

  def _make_multi_select_tile(self, d: dict) -> AetherMultiSelectTile:
    return AetherMultiSelectTile(
      title=d["title"],
      options=d["options"],
      get_values=d["get_values"],
      set_values=d["set_values"],
      bg_color=self.PANEL_STYLE.accent,
      desc=d.get("subtitle", ""),
      is_enabled=d.get("is_enabled"),
    )

  # ── continuous grids ──────────────────────────────────────

  def measure_scroll_grid_height(self, grid: TileGrid, width: float) -> float:
    return grid.measure_height(width)

  def register_scroll_grid(self, grid: TileGrid) -> None:
    self._scroll_grid = grid
    # Toggle cards retain their shared dimensions when the list grows.
    grid._tile_height = AS.SETTINGS_ROW_CARD_HEIGHT
    grid._gap = AS.SETTINGS_ROW_GAP
    grid.align_top = True
    if grid not in self._children:
      self._child(grid)
    grid.set_touch_valid_callback(lambda: self._scroll_panel.is_touch_valid())

  def set_toggle_items(self, items: list[dict]) -> None:
    if self._scroll_grid is None:
      return
    self._scroll_grid.clear()
    for item in items:
      self._scroll_grid.add_tile(self._make_toggle_tile(item))
    self.reset_scroll()

  def _render_scroll_grid(self, grid: TileGrid, rect: rl.Rectangle) -> None:
    self._bind_scroll_widget(grid)
    height = max(rect.height, self.measure_scroll_grid_height(grid, rect.width))
    grid.render(rl.Rectangle(rect.x, rect.y, rect.width, height))


# ═══════════════════════════════════════════════════════════════
# AdjustorTogglesPanelView — shared adjustor+toggle-grid base
# ═══════════════════════════════════════════════════════════════

class AdjustorTogglesPanelView(PanelManagerView):
    """PanelManagerView with AetherAdjustorRow sliders and scrolling toggle cards.

    Subclasses must set ``self._adjustor_rows``, ``self._toggle_grid``,
    and call ``super().__init__()``.  May override ``_get_active_elements()``
    to control which children receive mouse events.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._pressed_target: str | None = None
        self._adjustor_rows: dict[str, AetherAdjustorRow] = {}
        self._can_click = True
        self._active_adjustor_key = None

    def _set_active_adjustor(self, key: str, active: bool):
        if active:
            if self._active_adjustor_key and self._active_adjustor_key != key:
                old = self._adjustor_rows.get(self._active_adjustor_key)
                if old:
                    old.reset_interaction()
            self._active_adjustor_key = key
        elif self._active_adjustor_key == key:
            self._active_adjustor_key = None

    def show_event(self):
        super().show_event()
        self._pressed_target = None
        self._can_click = True

    def hide_event(self):
        super().hide_event()
        self._pressed_target = None
        self._can_click = True

    def _get_active_elements(self):
        elems = list(self._adjustor_rows.values())
        if hasattr(self, '_toggle_grid'):
            elems.append(self._toggle_grid)
        return elems

    def _handle_mouse_press(self, mouse_pos):
        super()._handle_mouse_press(mouse_pos)
        for el in self._get_active_elements():
            el._handle_mouse_press(mouse_pos)

    def _handle_mouse_release(self, mouse_pos):
        for el in self._get_active_elements():
            el._handle_mouse_release(mouse_pos)
        super()._handle_mouse_release(mouse_pos)

    def _handle_mouse_event(self, mouse_event):
        super()._handle_mouse_event(mouse_event)
        for el in self._get_active_elements():
            el._handle_mouse_event(mouse_event)


class BreadcrumbController:
  EXPAND_DURATION: float = 2.5

  def __init__(self):
    self._rects: dict[str, rl.Rectangle] = {}
    self._pressed: str | None = None
    self._expanded: bool = False
    self._expand_alpha: float = 0.0
    self._last_interact: float = 0.0
    self._bounds: rl.Rectangle | None = None
    self._header_toggle: ParentToggle | None = None

  @property
  def rects(self) -> dict[str, rl.Rectangle]:
    return self._rects

  @property
  def pressed(self) -> str | None:
    return self._pressed

  @property
  def expanded(self) -> bool:
    return self._expanded

  @property
  def expand_alpha(self) -> float:
    return self._expand_alpha

  def init_interaction(self, mouse_pos: MousePos, *, pad_x: float = 12, pad_y: float = 16) -> None:
    target = resolve_interactive_target(mouse_pos, self._rects, self._bounds, pad_x=pad_x, pad_y=pad_y)
    if target:
      self._pressed = target

  def update_interaction(self, mouse_pos: MousePos, *, pad_x: float = 12, pad_y: float = 16) -> None:
    if self._pressed and resolve_interactive_target(mouse_pos, self._rects, self._bounds, pad_x=pad_x, pad_y=pad_y) != self._pressed:
      self._pressed = None

  def finish_interaction(self, mouse_pos: MousePos, *, pad_x: float = 12, pad_y: float = 16) -> str | None:
    target = resolve_interactive_target(mouse_pos, self._rects, self._bounds, pad_x=pad_x, pad_y=pad_y)
    if target and target == self._pressed:
      self._pressed = None
      return target
    self._pressed = None
    return None

  def cancel_interaction(self) -> None:
    self._pressed = None

  def handle_click(self, target: str) -> None:
    if target == "action:page_toggle" and self._header_toggle:
      toggle = self._header_toggle
      toggle.set_state(not toggle.get_state())
      return
    if target == "action:back":
      import openpilot.selfdrive.ui.layouts.settings.starpilot.main_panel as main_panel
      nav_stack = getattr(gui_app, "_nav_stack", [])
      if len(nav_stack) > 1:
        gui_app.pop_widget()
        return
      layout = getattr(main_panel.StarPilotLayout, "active_instance", None)
      if layout:
        layout.navigate_back()
      return
    if target == "action:breadcrumb_history":
      self._expanded = not self._expanded
      if self._expanded:
        self._last_interact = time.monotonic()
      return

    self._expanded = False

    import openpilot.selfdrive.ui.layouts.settings.starpilot.main_panel as main_panel
    from openpilot.selfdrive.ui.layouts.settings.starpilot.panel import StarPilotPanelType
    layout = getattr(main_panel.StarPilotLayout, "active_instance", None)
    if not layout:
      return

    nav_stack = getattr(gui_app, "_nav_stack", [])

    if target == "action:home":
      while len(nav_stack) > 1:
        gui_app.pop_widget()
      layout.reset_to_root()
    elif target.startswith("action:hub:"):
      target_depth = int(target.split(":")[-1])
      while len(nav_stack) > 1:
        gui_app.pop_widget()
      layout.navigate_to_hub_depth(target_depth)
    elif target == "action:category":
      while len(nav_stack) > 1:
        gui_app.pop_widget()
      if getattr(layout, "_hub_path", None):
        layout.navigate_to_hub_depth(1)
      elif layout._current_panel != StarPilotPanelType.MAIN:
        layout._panel_stack.clear()
        layout._commit_navigation()
      else:
        layout.reset_to_root()
    elif target == "action:panel":
      while len(nav_stack) > 1:
        gui_app.pop_widget()
      layout._panel_stack.clear()
      layout._commit_navigation()
    elif target.startswith("action:nav_stack:"):
      target_idx = int(target.split(":")[-1])
      while len(nav_stack) > target_idx + 1:
        gui_app.pop_widget()
    elif target.startswith("action:panel_stack:"):
      while len(nav_stack) > 1:
        gui_app.pop_widget()
      target_idx = int(target.split(":")[-1])
      while len(layout._panel_stack) > target_idx + 1:
        layout._panel_stack.pop()
      layout._commit_navigation()

  @staticmethod
  def build_path() -> list[tuple[str, str]]:
    import openpilot.selfdrive.ui.layouts.settings.starpilot.main_panel as main_panel
    from openpilot.selfdrive.ui.layouts.settings.starpilot.panel import StarPilotPanelType
    layout = getattr(main_panel.StarPilotLayout, "active_instance", None)

    path = [(tr("StarPilot"), "action:home")]
    if not layout:
      return path

    hub_path = getattr(layout, "_hub_path", [])
    for i, folder in enumerate(hub_path, start=1):
      path.append((tr(folder["title"]), f"action:hub:{i}"))

    if layout._current_panel != StarPilotPanelType.MAIN:
      selected_leaf = getattr(layout, "_selected_leaf", None)
      if selected_leaf is not None:
        panel_title = selected_leaf["title"]
      else:
        panel_title = layout._panels[layout._current_panel].name
      if panel_title:
        path.append((tr(panel_title), "action:panel"))

    pushed_widgets = getattr(gui_app, "_nav_stack", [])[1:]

    for i, widget in enumerate(pushed_widgets):
      if hasattr(widget, '_header_title') and widget._header_title:
        path.append((tr(widget._header_title), f"action:nav_stack:{i+1}"))

    for i, (panel_type, sub_panel_name) in enumerate(layout._panel_stack):
      panel = layout._panels[panel_type].instance
      if not panel or not hasattr(panel, '_sub_panels') or sub_panel_name not in panel._sub_panels:
        continue
      sub = panel._sub_panels[sub_panel_name]
      label = tr(sub._header_title) if hasattr(sub, '_header_title') and sub._header_title else tr(sub_panel_name)
      path.append((label, f"action:panel_stack:{i}"))

    return path

  HEADER_HEIGHT = AS.SETTINGS_HEADER_HEIGHT
  CRUMB_SIZE = 28
  TITLE_SIZE = 56
  ROOT_TITLE_SIZE = 60
  ROOT_SUBTITLE_SIZE = 30

  def draw_header(self, rect: rl.Rectangle, *, root_subtitle: str = "",
                  header_control: ParentToggle | AetherButton | None = None) -> None:
    """Aether Cards header: round back button, purple breadcrumb trail and a large page title."""
    self._rects.clear()
    self._bounds = rect
    self._header_toggle = header_control if isinstance(header_control, ParentToggle) else None
    path = self.build_path()
    if not path:
      return
    cy = rect.y + rect.height / 2
    x = rect.x
    right = rect.x + rect.width
    bold = gui_app.font(FontWeight.BOLD)
    semi = gui_app.font(FontWeight.SEMI_BOLD)

    if isinstance(header_control, AetherButton):
      width = min(header_control.measure_width(), rect.width * 0.4)
      height = header_control.measure_height()
      button_rect = rl.Rectangle(right - width, cy - height / 2, width, height)
      header_control.set_parent_rect(rect)
      header_control.render(button_rect)
      right = button_rect.x - AS.SETTINGS_CONTROL_GAP
    elif self._header_toggle:
      toggle_rect = rl.Rectangle(right - AS.SWITCH_WIDTH, rect.y, AS.SWITCH_WIDTH, rect.height)
      draw_toggle_switch(toggle_rect, self._header_toggle.get_state(), right_inset=0)
      self._rects["action:page_toggle"] = toggle_rect
      right = toggle_rect.x - AS.SETTINGS_CONTROL_GAP

    if len(path) == 1:
      sub_font = gui_app.font(FontWeight.NORMAL)
      total = self.ROOT_TITLE_SIZE * FONT_SCALE + (SPACING.xs + self.ROOT_SUBTITLE_SIZE * FONT_SCALE if root_subtitle else 0)
      y = cy - total / 2
      draw_text_fit_common(bold, path[0][0], rl.Vector2(x, y), right - x, self.ROOT_TITLE_SIZE, color=AS.TEXT)
      if root_subtitle:
        draw_text_fit_common(sub_font, root_subtitle, rl.Vector2(x, y + self.ROOT_TITLE_SIZE * FONT_SCALE + SPACING.xs),
                             right - x, self.ROOT_SUBTITLE_SIZE, color=AS.TEXT_SECONDARY)
      return

    size = AS.ROUND_BUTTON
    back = rl.Rectangle(x, cy - size / 2, size, size)
    draw_round_icon_button(back, "back", pressed=self._pressed == "action:back")
    self._rects["action:back"] = back
    x += size + AS.SETTINGS_HEADER_GAP

    total = self.CRUMB_SIZE * FONT_SCALE + SPACING.xs + self.TITLE_SIZE * FONT_SCALE
    y = cy - total / 2
    crumbs = list(path[:-1])
    sep_w = 40.0  # gap + chevron + gap
    widths = [measure_text_cached(semi, text, self.CRUMB_SIZE).x for text, _ in crumbs]
    elided = False
    while len(crumbs) > 1 and sum(widths) + sep_w * (len(crumbs) - 1) + (sep_w if elided else 0) > right - x:
      crumbs.pop(0)
      widths.pop(0)
      elided = True
    cx = x
    crumb_h = self.CRUMB_SIZE * FONT_SCALE

    def draw_sep(at_x: float) -> None:
      draw_breadcrumb_chevron(rl.Rectangle(at_x + 14, y + crumb_h / 2 - 9, 12, 18), AS.ACCENT_TEXT, thickness=3.0)

    if elided:
      rl.draw_text_ex(semi, "...", rl.Vector2(cx, y), self.CRUMB_SIZE, 0, AS.ACCENT_TEXT)
      cx += measure_text_cached(semi, "...", self.CRUMB_SIZE).x
      draw_sep(cx)
      cx += sep_w
    for i, ((text, action), w) in enumerate(zip(crumbs, widths, strict=True)):
      color = AS.TEXT if self._pressed == action else AS.ACCENT_TEXT
      rl.draw_text_ex(semi, text, rl.Vector2(cx, y), self.CRUMB_SIZE, 0, color)
      self._rects[action] = rl.Rectangle(cx - 8, rect.y, w + 16, rect.height / 2)
      cx += w
      if i < len(crumbs) - 1:
        draw_sep(cx)
        cx += sep_w
    title_y = y + self.CRUMB_SIZE * FONT_SCALE + SPACING.xs
    draw_text_fit_common(bold, path[-1][0], rl.Vector2(x, title_y), right - x, self.TITLE_SIZE, color=AS.TEXT)

  def draw(self, rect: rl.Rectangle, *, bg_color: rl.Color = rl.Color(12, 10, 18, 255)) -> None:
    self._rects.clear()
    self._bounds = rect
    path = self.build_path()
    if not path:
      return

    now = time.monotonic()

    if self._expanded and now - self._last_interact > self.EXPAND_DURATION:
      self._expanded = False

    ANIM_LERP = 0.2
    target = 1.0 if self._expanded else 0.0
    self._expand_alpha += (target - self._expand_alpha) * ANIM_LERP

    ACTIVE_SIZE = 34
    PAST_SIZE = 28
    MIN_ACTIVE_SIZE = 26
    CHEVRON_SIZE = 20
    CHEVRON_W = 12
    GAP = 12
    LEFT_INSET = 34
    CAPSULE_W = 64
    CAPSULE_H = 34

    center_y = rect.y + rect.height / 2
    color_sep = rl.Color(140, 150, 175, 220)
    active_normal = AetherListColors.HEADER
    past_normal = AetherListColors.SUBTEXT
    past_hover = AetherListColors.HEADER
    past_pressed = rl.Color(190, 185, 215, 255)

    mouse_pos = gui_app.last_mouse_event.pos

    sep = GAP + CHEVRON_W + GAP
    capsule_need = CAPSULE_W + sep
    available_w = rect.width - LEFT_INSET - 24

    med_font = gui_app.font(FontWeight.MEDIUM)
    semi_font = gui_app.font(FontWeight.SEMI_BOLD)

    k = len(path)
    if self._expanded:
      display_path = [(item[0], item[1], ACTIVE_SIZE if i == k - 1 else PAST_SIZE, False) for i, item in enumerate(path)]
      overflow_alpha = max(0.0, 1.0 - self._expand_alpha)
    elif k == 1:
      display_path = [(path[0][0], path[0][1], ACTIVE_SIZE, False)]
      overflow_alpha = 0.0
    else:
      past_w_sum = sum(measure_text_cached(med_font, item[0], PAST_SIZE).x for item in path[:-1]) + (k - 1) * sep
      active_text, active_action = path[-1]
      direct_fit = False
      active_size = ACTIVE_SIZE

      for f in (34, 32, 30, 28, 26):
        w_active = measure_text_cached(semi_font, active_text, f).x
        if past_w_sum + w_active <= available_w:
          active_size = f
          direct_fit = True
          break

      if direct_fit:
        display_path = [(item[0], item[1], PAST_SIZE, False) for item in path[:-1]] + [(active_text, active_action, active_size, False)]
        overflow_alpha = 0.0
      else:
        active_size = MIN_ACTIVE_SIZE
        w_active = measure_text_cached(semi_font, active_text, active_size).x
        w_active_max = available_w - capsule_need

        if w_active > w_active_max and w_active_max > 60:
          active_text = truncate_text_ellipsis(semi_font, active_text, w_active_max, active_size)
          w_active = measure_text_cached(semi_font, active_text, active_size).x
          display_path = [("...", "action:breadcrumb_history", PAST_SIZE, True), (active_text, active_action, active_size, False)]
        else:
          ancestor_budget = available_w - w_active - capsule_need
          ancestors = []
          for i in range(k - 2, -1, -1):
            item_text, item_action = path[i]
            item_w = measure_text_cached(med_font, item_text, PAST_SIZE).x
            slot_needed = item_w + sep
            if slot_needed <= ancestor_budget:
              ancestors.insert(0, (item_text, item_action, PAST_SIZE, False))
              ancestor_budget -= slot_needed
            else:
              slot = ancestor_budget - sep
              if slot > 30:
                trunc = truncate_text_ellipsis(med_font, item_text, slot, PAST_SIZE)
                visible = trunc.removesuffix("...").rstrip()
                if len(visible) >= 3:
                  ancestors.insert(0, (trunc, item_action, PAST_SIZE, False))
              break

          display_path = [("...", "action:breadcrumb_history", PAST_SIZE, True)] + ancestors + [(active_text, active_action, active_size, False)]
        overflow_alpha = max(0.0, 1.0 - self._expand_alpha)

    current_x = rect.x + LEFT_INSET

    aether_begin_scissor_mode(int(rect.x), int(rect.y), int(rect.width), int(rect.height))

    for i, (text, action, font_size, is_capsule) in enumerate(display_path):
      is_last = (i == len(display_path) - 1)
      pressed = (self._pressed == action)

      if is_capsule:
        if overflow_alpha <= 0.01:
          current_x += GAP
          continue

        cap_rect = rl.Rectangle(current_x, center_y - CAPSULE_H / 2, CAPSULE_W, CAPSULE_H)
        touch_hit = rl.Rectangle(current_x - GAP / 2, rect.y, CAPSULE_W + GAP, rect.height)
        hovered = bool(point_hits(mouse_pos, touch_hit, rect, pad_x=0, pad_y=0))

        if cap_rect.x < rect.x + rect.width:
          self._rects[action] = touch_hit

        oa = overflow_alpha
        if pressed:
          fill = rl.Color(45, 38, 62, int(230 * oa))
          outline = rl.Color(167, 152, 210, int(180 * oa))
          glow = rl.Color(167, 152, 210, int(90 * oa))
          dots_c = rl.Color(255, 255, 255, int(255 * oa))
        elif hovered:
          fill = rl.Color(38, 34, 54, int(200 * oa))
          outline = rl.Color(148, 142, 168, int(120 * oa))
          glow = rl.Color(148, 142, 168, int(60 * oa))
          dots_c = rl.Color(255, 255, 255, int(255 * oa))
        else:
          fill = rl.Color(24, 20, 36, int(180 * oa))
          outline = rl.Color(120, 115, 160, int(70 * oa))
          glow = rl.Color(120, 115, 160, int(25 * oa))
          dots_c = rl.Color(200, 210, 225, int(200 * oa))

        if oa > 0.05:
          rl.draw_rectangle_rounded_lines_ex(
            rl.Rectangle(cap_rect.x - 2, cap_rect.y - 2, cap_rect.width + 4, cap_rect.height + 4),
            1.0, 16, 1.5, glow)
          rl.draw_rectangle_rounded(cap_rect, 1.0, 16, fill)
          rl.draw_rectangle_rounded_lines_ex(cap_rect, 1.0, 16, 1.0, outline)

          font_dots = gui_app.font(FontWeight.SEMI_BOLD)
          dots_ts = measure_text_cached(font_dots, "...", 24)
          rl.draw_text_ex(font_dots, "...",
            rl.Vector2(cap_rect.x + (cap_rect.width - dots_ts.x) / 2, center_y - dots_ts.y / 2),
            24, 0, dots_c)
        current_x += CAPSULE_W + GAP

      else:
        font = semi_font if is_last else med_font
        ts = measure_text_cached(font, text, font_size)
        touch_hit = rl.Rectangle(current_x - GAP / 2, rect.y, ts.x + GAP, rect.height)
        hovered = bool(point_hits(mouse_pos, touch_hit, rect, pad_x=0, pad_y=0))

        if not is_last and touch_hit.x < rect.x + rect.width:
          self._rects[action] = touch_hit

        color = past_pressed if pressed else (past_hover if hovered else (active_normal if is_last else past_normal))

        if hovered and not is_last:
          highlight_h = 44
          highlight_rect = rl.Rectangle(current_x - 6, center_y - highlight_h / 2, ts.x + 12, highlight_h)
          rl.draw_rectangle_rounded(highlight_rect, 0.35, 10, rl.Color(255, 255, 255, 14))

        text_y = center_y - ts.y / 2
        rl.draw_text_ex(font, text, rl.Vector2(current_x, text_y), font_size, 0, color)
        current_x += ts.x + GAP

      if i < len(display_path) - 1:
        chev_rect = rl.Rectangle(current_x, center_y - CHEVRON_SIZE / 2, CHEVRON_W, CHEVRON_SIZE)
        draw_breadcrumb_chevron(chev_rect, color_sep, thickness=3.0)
        current_x += CHEVRON_W + GAP

    if current_x > rect.x + rect.width - 20:
      fade_w = 48
      fade_x = rect.x + rect.width - fade_w
      transparent_bg = rl.Color(bg_color.r, bg_color.g, bg_color.b, 0)
      rl.draw_rectangle_gradient_h(int(fade_x), int(rect.y), int(fade_w), int(rect.height), transparent_bg, bg_color)

    aether_end_scissor_mode()
PANEL_HEADER_TITLE_Y: int = 34
PANEL_HEADER_SUBTITLE_Y: int = 78
PANEL_HEADER_TITLE_FONT_SIZE: int = 44
PANEL_HEADER_SUBTITLE_FONT_SIZE: int = 32
PANEL_HEADER_TITLE_FONT: FontWeight = FontWeight.SEMI_BOLD
PANEL_HEADER_SUBTITLE_FONT: FontWeight = FontWeight.NORMAL
SETTINGS_ROW_TITLE_FONT_SIZE: int = 40
SETTINGS_ROW_SUBTITLE_FONT_SIZE: int = 28
SETTINGS_ROW_VALUE_FONT_SIZE: int = 34


def _settings_panel_header_layout(width: float, subtitle: str | None, title_size: int, subtitle_size: int,
                                  subtitle_weight: FontWeight = PANEL_HEADER_SUBTITLE_FONT,
                                  min_title_height: float = 0.0) -> tuple[float, list[str], float, float]:
  title_height = max(title_size * FONT_SCALE, min_title_height)
  line_height = subtitle_size * FONT_SCALE + SPACING.xs
  lines = wrap_text(gui_app.font(subtitle_weight), subtitle, width, subtitle_size, max_lines=4, spacing=0) if subtitle else []
  height = title_height + (SPACING.sm + len(lines) * line_height - SPACING.xs if lines else 0.0)
  return title_height, lines, line_height, height


def draw_settings_panel_header(header_rect: rl.Rectangle, title: str, subtitle: str | None = None,
                                *,
                                title_size: int = PANEL_HEADER_TITLE_FONT_SIZE,
                                subtitle_size: int = PANEL_HEADER_SUBTITLE_FONT_SIZE,
                                max_title_width: float = 0.55,
                                max_subtitle_width: float = 0.58,
                                title_color: rl.Color = AetherListColors.HEADER,
                                subtitle_color: rl.Color = AetherListColors.SUBTEXT,
                                title_weight: FontWeight = PANEL_HEADER_TITLE_FONT,
                                subtitle_weight: FontWeight = PANEL_HEADER_SUBTITLE_FONT,
                                min_title_height: float = 0.0):
  if not title:
    return
  title_font = gui_app.font(title_weight)
  title_height, desc_lines, line_height, _ = _settings_panel_header_layout(
    header_rect.width * max_subtitle_width, subtitle, title_size, subtitle_size, subtitle_weight, min_title_height,
  )
  y = header_rect.y + (title_height - title_size * FONT_SCALE) / 2
  draw_text_fit_common(title_font, title, rl.Vector2(header_rect.x, y), header_rect.width * max_title_width, title_size, color=title_color)
  y = header_rect.y + title_height + SPACING.sm
  if desc_lines:
    desc_font = gui_app.font(subtitle_weight)
    for line in desc_lines:
      draw_text_fit_common(desc_font, line, rl.Vector2(header_rect.x, y), header_rect.width * max_subtitle_width, subtitle_size, color=subtitle_color)
      y += line_height



def draw_soft_card(rect: rl.Rectangle, fill: rl.Color, border: rl.Color, radius: float = 0.08, segments: int = 18):
  radius_px = radius * min(rect.width, rect.height)
  draw_rounded_fill(rect, fill, radius_px=radius_px, segments=segments)
  draw_rounded_stroke(rect, border, radius_px=radius_px, segments=segments)


def draw_list_row_shell(
  rect: rl.Rectangle,
  *,
  current: bool = False,
  hovered: bool = False,
  pressed: bool = False,
  is_last: bool = False,
  alpha: int = 255,
  row_bg: rl.Color = AetherListColors.ROW_BG,
  row_border: rl.Color = AetherListColors.ROW_BORDER,
  row_separator: rl.Color = AetherListColors.ROW_SEPARATOR,
  row_hover: rl.Color = AetherListColors.ROW_HOVER,
  current_bg: rl.Color = AetherListColors.CURRENT_BG,
  current_border: rl.Color = AetherListColors.CURRENT_BORDER,
  row_radius: float = AetherListMetrics.row_radius,
  segments: int = 18,
  separator_inset: int = 22,
  emphasis: bool = False,
  card: bool = False,
):
  """Aether Cards row background.

  card=True (full settings pages): the row is its own card, separated from the next by a gap.
  card=False (compact grouped lists): rows share one container card (draw_list_group_shell) and are
  separated by thin dividers. The legacy colour arguments are accepted for API compatibility.
  """
  if not card:
    if pressed or current:
      tint = rl.Color(255, 255, 255, 22) if pressed else AS.ACCENT_TINT
      aether_fill(rl.Rectangle(rect.x + 8, rect.y + 6, rect.width - 16, rect.height - 12), with_alpha(tint, tint.a * alpha // 255), 28)
    if not is_last:
      inset = max(24, separator_inset)
      rl.draw_rectangle_rec(rl.Rectangle(rect.x + inset, rect.y + rect.height - AS.SETTINGS_DIVIDER_WIDTH / 2,
                                         rect.width - inset * 2, AS.SETTINGS_DIVIDER_WIDTH),
                            with_alpha(AS.SETTINGS_DIVIDER, AS.SETTINGS_DIVIDER.a * alpha // 255))
    return
  draw_settings_row_shell(row_card_rect(rect), current=current, hovered=hovered, pressed=pressed, emphasis=emphasis, alpha=alpha)


def draw_settings_row_shell(face: rl.Rectangle, *, current: bool = False, hovered: bool = False, pressed: bool = False,
                            emphasis: bool = False, alpha: int = 255):
  if pressed:
    border = AS.SETTINGS_CARD_BORDER_PRESSED
  elif current:
    border = AS.ACCENT_EDGE
  elif emphasis or hovered:
    border = AS.SETTINGS_CARD_BORDER_ON
  else:
    border = AS.SETTINGS_CARD_BORDER_IDLE
  fill = mix_colors(AS.SETTINGS_CARD_FILL, AS.ACCENT, 0.12) if current else AS.SETTINGS_CARD_FILL
  draw_settings_card(face, border=with_alpha(border, border.a * alpha // 255), fill=with_alpha(fill, alpha))


def row_card_rect(rect: rl.Rectangle) -> rl.Rectangle:
  """A row slot owns its trailing gap; its visible card starts at the slot origin."""
  gap = min(AS.SETTINGS_ROW_GAP, max(0.0, rect.height - AS.MIN_TOUCH))
  return rl.Rectangle(rect.x, rect.y, rect.width, rect.height - gap)


def draw_action_rail(
  rect: rl.Rectangle,
  action_width: int,
  *,
  current: bool = False,
  alpha: int = 255,
  fill: rl.Color = AetherListColors.ACTION_BG,
  current_fill: rl.Color = rl.Color(255, 255, 255, 6),
  separator: rl.Color = AetherListColors.ACTION_SEPARATOR,
  inset_y: int = 18,
):
  action_x = rect.x + rect.width - action_width
  action_rect = rl.Rectangle(action_x, rect.y, action_width, rect.height)
  action_fill = current_fill if current else fill
  if action_fill.a > 0:
    rl.draw_rectangle_rec(action_rect, with_alpha(action_fill, alpha))
  rl.draw_line(int(action_x), int(rect.y + inset_y), int(action_x), int(rect.y + rect.height - inset_y), with_alpha(separator, alpha))
  return action_rect


def draw_list_scroll_fades(
  scroll_rect: rl.Rectangle,
  content_height: float,
  scroll_offset: float,
  bg_color: rl.Color,
  *,
  fade_height: int = AETHER_LIST_METRICS.fade_height,
  right_trim: int = 12,
  threshold: int = 4,
):
  if content_height <= scroll_rect.height + threshold:
    return

  fade_h = min(fade_height, int(scroll_rect.height / 4))
  if scroll_offset < -threshold:
    rl.draw_rectangle_gradient_v(
      int(scroll_rect.x), int(scroll_rect.y), int(scroll_rect.width - right_trim), fade_h, with_alpha(bg_color, 255), with_alpha(bg_color, 0)
    )

  if (-scroll_offset + scroll_rect.height) < (content_height - threshold):
    bottom_y = int(scroll_rect.y + scroll_rect.height - fade_h)
    rl.draw_rectangle_gradient_v(
      int(scroll_rect.x), bottom_y, int(scroll_rect.width - right_trim), fade_h, with_alpha(bg_color, 0), with_alpha(bg_color, 255)
    )


def draw_busy_ring(
  center: rl.Vector2,
  phase: float,
  accent_color: rl.Color,
  *,
  track_color: rl.Color = rl.Color(255, 255, 255, 26),
  inner_radius: float = 29,
  outer_radius: float = 38,
  sweep: float = 260,
  thickness: int = 48,
):
  rl.draw_ring(center, inner_radius, outer_radius, 0, 360, thickness, track_color)
  rl.draw_ring(center, inner_radius, outer_radius, phase, phase + sweep, thickness, accent_color)


def draw_standard_toggle_row(
  rect: rl.Rectangle,
  title: str,
  subtitle: str,
  toggle_value: bool,
  *,
  enabled: bool = True,
  hovered: bool = False,
  pressed: bool = False,
  is_last: bool = False,
  style: PanelStyle = DEFAULT_PANEL_STYLE,
  card: bool = False,
):
  """Draw a standard toggle settings row with consistent sizing."""
  draw_settings_list_row(
    rect,
    title=title,
    subtitle=subtitle,
    toggle_value=toggle_value,
    enabled=enabled,
    hovered=hovered,
    pressed=pressed,
    is_last=is_last,
    show_chevron=False,
    style=style,
    card=card,
  )


_KNOB_ANIMATION_STATES: dict[str, float] = {}
_TOGGLE_CONSTELLATION_CACHE: dict[str, tuple[list[dict], list[tuple[int, int]]]] = {}

# Anchor-zone regions for tile (near-square) vs pill (wide/short)
_CONST_REGIONS_TILE = [
  (0.18, 0.30, 0.18, 0.30),  # top-left corner
  (0.70, 0.82, 0.18, 0.30),  # top-right corner
  (0.18, 0.30, 0.70, 0.82),  # bottom-left corner
  (0.70, 0.82, 0.70, 0.82),  # bottom-right corner
  (0.38, 0.62, 0.18, 0.28),  # top-center edge
  (0.38, 0.62, 0.72, 0.82),  # bottom-center edge
  (0.18, 0.28, 0.38, 0.62),  # left-center edge
  (0.72, 0.82, 0.38, 0.62),  # right-center edge
]
_CONST_REGIONS_PILL = [
  (0.15, 0.30, 0.22, 0.42),  # left cluster
  (0.70, 0.85, 0.22, 0.42),  # right cluster
  (0.15, 0.30, 0.58, 0.78),  # left cluster low
  (0.70, 0.85, 0.58, 0.78),  # right cluster low
  (0.38, 0.62, 0.20, 0.35),  # top-center
  (0.38, 0.62, 0.65, 0.80),  # bottom-center
  (0.20, 0.35, 0.38, 0.62),  # left-mid
  (0.65, 0.80, 0.38, 0.62),  # right-mid
]

def _build_constellation_nodes(
  rng: random.Random,
  num: int,
  regions: list[tuple[float, float, float, float]],
  *,
  r_min: float,
  r_max: float,
  min_sep: float,
  x_margin: float,
  y_margin: float,
) -> tuple[list[dict], list[tuple[int, int]]]:
  """Shared constellation node generator used by both tiles and toggle pills."""
  ax_min, ax_max, ay_min, ay_max = regions[rng.randint(0, len(regions) - 1)]
  ax = ax_min + rng.random() * (ax_max - ax_min)
  ay = ay_min + rng.random() * (ay_max - ay_min)
  nodes: list[dict] = []
  for _ in range(num):
    for _ in range(20):
      a = rng.random() * 2.0 * math.pi
      r = r_min + rng.random() * r_max
      x = max(x_margin, min(1.0 - x_margin, ax + r * math.cos(a)))
      y = max(y_margin, min(1.0 - y_margin, ay + r * math.sin(a)))
      if all(math.sqrt((x - n['x'])**2 + (y - n['y'])**2) >= min_sep for n in nodes):
        nodes.append({'x': x, 'y': y})
        break
    else:
      nodes.append({'x': x, 'y': y})
  nodes.sort(key=lambda n: -(abs(n['x'] - 0.5) + abs(n['y'] - 0.5)))
  for i, n in enumerate(nodes):
    n['w'] = 0 if i == 0 else 1 if i == 1 else 2
  vecs: list[tuple[int, int]] = [(0, j) for j in range(1, len(nodes))]
  return nodes, vecs


def draw_constellation_nodes(
  nodes: list[dict],
  vecs: list[tuple[int, int]],
  rect: rl.Rectangle,
  accent: rl.Color,
  glow: float,
  *,
  scale: float = 1.0,
) -> None:
  """Shared constellation renderer used by both tiles and toggle pills.

  `scale` shrinks core/glow radii for smaller surfaces (e.g. 0.45 for pills).
  """
  rx, ry, rw, rh = int(rect.x), int(rect.y), int(rect.width), int(rect.height)
  va = int(10 + glow * 25)
  if va > 2:
    vc = rl.Color(accent.r, accent.g, accent.b, min(255, va))
    for i, j in vecs:
      rl.draw_line_ex(
        rl.Vector2(int(rx + nodes[i]['x'] * rw), int(ry + nodes[i]['y'] * rh)),
        rl.Vector2(int(rx + nodes[j]['x'] * rw), int(ry + nodes[j]['y'] * rh)),
        1.0, vc,
      )
  for nd in nodes:
    nx = int(rx + nd['x'] * rw)
    ny = int(ry + nd['y'] * rh)
    w = nd.get('w', 2)
    if w == 0:
      core_r, diff_r, col = 3.0 * scale, 12.0 * scale, _CONST_PRIMARY
    elif w == 1:
      core_r, diff_r, col = 2.0 * scale, 8.0 * scale, _CONST_SECONDARY
    else:
      core_r, diff_r, col = 1.2 * scale, 0.0, _CONST_TERTIARY
    da = int(5 + glow * 20)
    if diff_r > 0 and da > 2:
      rl.draw_circle(nx, ny, max(1.0, diff_r), rl.Color(col.r, col.g, col.b, min(255, da)))
    ca = int(130 + glow * 125)
    rl.draw_circle(nx, ny, max(1.0, core_r), rl.Color(col.r, col.g, col.b, min(255, ca)))


def _get_or_create_toggle_constellation(seed_id: str) -> tuple[list[dict], list[tuple[int, int]]]:
  if seed_id in _TOGGLE_CONSTELLATION_CACHE:
    return _TOGGLE_CONSTELLATION_CACHE[seed_id]
  rng = random.Random(seed_id)
  nodes, vecs = _build_constellation_nodes(
    rng, rng.randint(2, 4), _CONST_REGIONS_PILL,
    r_min=0.06, r_max=0.22, min_sep=0.12, x_margin=0.10, y_margin=0.18,
  )
  _TOGGLE_CONSTELLATION_CACHE[seed_id] = (nodes, vecs)
  return nodes, vecs

def draw_toggle_switch(
  rect: rl.Rectangle,
  enabled: bool,
  *,
  knob_progress: float | None = None,
  is_enabled: bool = True,
  track_color: rl.Color = AetherListColors.PRIMARY,
  knob_color: rl.Color = rl.WHITE,
  width: int = AETHER_LIST_METRICS.toggle_width,
  height: int = AETHER_LIST_METRICS.toggle_height,
  right_inset: int = AETHER_LIST_METRICS.toggle_right_inset,
  knob_offset: int = 29,
  seed_id: str = "",
  radius_px: float = TILE_RADIUS_PX,
  bg_color: rl.Color | None = None,
):
  """Aether Cards switch: an accent pill when on, a grey pill when off, with a round white knob."""
  toggle_rect = snap_rect(rl.Rectangle(rect.x + rect.width - width - right_inset, rect.y + (rect.height - height) / 2, width, height))
  if knob_progress is None:
    knob_progress = 1.0 if enabled else 0.0
  t = max(0.0, min(1.0, knob_progress))

  on_color = rl.Color(track_color.r, track_color.g, track_color.b, 255)
  track = mix_colors(AS.TRACK_OFF, on_color, t, alpha=255)
  if not is_enabled:
    track = with_alpha(track, 110)
    knob_color = with_alpha(knob_color, 140)
  radius = toggle_rect.height / 2
  aether_fill(toggle_rect, track, radius, segments=32)

  pad = 8.0
  knob_r = radius - pad
  knob_x = toggle_rect.x + pad + knob_r + t * (toggle_rect.width - 2 * (pad + knob_r))
  rl.draw_circle_v(rl.Vector2(knob_x, toggle_rect.y + radius), knob_r, knob_color)


def draw_action_pill(
  rect: rl.Rectangle,
  text: str,
  fill: rl.Color,
  border: rl.Color,
  text_color: rl.Color,
  *,
  font_size: int = AETHER_LIST_METRICS.menu_button_font_size,
  roundness: float = AETHER_LIST_METRICS.menu_button_roundness,
  segments: int = AETHER_LIST_METRICS.menu_button_segments,
  padding_x: float = 12,
):
  radius = min(rect.width, rect.height) * roundness / 2
  aether_fill(rect, fill, radius, segments=max(24, segments))
  _draw_card_outline(rect, border, radius, width=4)
  draw_text_fit_common(
    gui_app.font(FontWeight.SEMI_BOLD),
    text,
    rl.Vector2(rect.x + padding_x, rect.y + (rect.height - font_size * FONT_SCALE) / 2),
    max(1.0, rect.width - padding_x * 2),
    font_size,
    align_center=True,
    color=text_color,
  )


def draw_chevron_icon(rect: rl.Rectangle, color: rl.Color, *, thickness: float = 4.0, direction: str = "right"):
  snapped = snap_rect(rect)
  center_x = snapped.x + snapped.width / 2
  center_y = snapped.y + snapped.height / 2
  size = max(6.0, min(snapped.width, snapped.height) * 0.28)
  if direction == "left":
    left_x = center_x - size * 0.35
    right_x = center_x + size * 0.6
    top_y = center_y - size
    bottom_y = center_y + size
    rl.draw_line_ex(rl.Vector2(right_x, top_y), rl.Vector2(left_x, center_y), thickness, color)
    rl.draw_line_ex(rl.Vector2(right_x, bottom_y), rl.Vector2(left_x, center_y), thickness, color)
  else:
    left_x = center_x - size * 0.6
    right_x = center_x + size * 0.35
    top_y = center_y - size
    bottom_y = center_y + size
    rl.draw_line_ex(rl.Vector2(left_x, top_y), rl.Vector2(right_x, center_y), thickness, color)
    rl.draw_line_ex(rl.Vector2(left_x, bottom_y), rl.Vector2(right_x, center_y), thickness, color)


def draw_breadcrumb_chevron(rect: rl.Rectangle, color: rl.Color, *, thickness: float = 3.0):
  snapped = snap_rect(rect)
  center_x = snapped.x + snapped.width / 2
  center_y = snapped.y + snapped.height / 2
  w = 12.0
  h = 20.0
  left_x = center_x - w * 0.45
  right_x = center_x + w * 0.45
  top_y = center_y - h / 2
  bottom_y = center_y + h / 2
  rl.draw_line_ex(rl.Vector2(left_x, top_y), rl.Vector2(right_x, center_y), thickness, color)
  rl.draw_line_ex(rl.Vector2(left_x, bottom_y), rl.Vector2(right_x, center_y), thickness, color)


TAB_HEIGHT = 98
TAB_GAP = 14
TAB_BOTTOM_GAP = 26


def draw_tab_bar(
  rect: rl.Rectangle,
  tab_defs: list[dict],
  active_tab_key: str,
  interactive_fn: Callable,
  *,
  subtitle_fn: Callable[[str], str] | None = None,
  style: PanelStyle = DEFAULT_PANEL_STYLE,
  tab_height: int = TAB_HEIGHT,
  tab_gap: int = TAB_GAP,
  tab_bottom_gap: int = TAB_BOTTOM_GAP,
) -> float:
  """Draw tab cards and register interactive targets.

  Returns the y position after the tab bar + bottom gap."""
  if not tab_defs:
    return rect.y
  n = len(tab_defs)
  tab_w = (rect.width - tab_gap * max(0, n - 1)) / max(1, n)
  for i, tab in enumerate(tab_defs):
    tab_rect = rl.Rectangle(rect.x + i * (tab_w + tab_gap), rect.y, tab_w, tab_height)
    hovered, pressed = interactive_fn(f"tab:{tab['id']}", tab_rect, pad_y=4)
    subtitle = subtitle_fn(tab["id"]) if subtitle_fn else tab.get("subtitle", "")
    draw_tab_card(
      tab_rect, tab["title"], subtitle,
      current=active_tab_key == tab["id"],
      hovered=hovered, pressed=pressed,
      title_size=38, subtitle_size=25, show_underline=True, style=style,
    )
  return rect.y + tab_height + tab_bottom_gap


def draw_tab_card(
  rect: rl.Rectangle,
  title: str,
  subtitle: str = "",
  *,
  current: bool = False,
  hovered: bool = False,
  pressed: bool = False,
  title_size: int = 28,
  subtitle_size: int = 20,
  show_underline: bool = False,
  underline_inset: int = 18,
  title_color: rl.Color | None = None,
  subtitle_color: rl.Color | None = None,
  style: PanelStyle = DEFAULT_PANEL_STYLE,
):
  fill = style.current_fill if current else style.surface_fill
  border = style.current_border if current else style.surface_border
  if not current and hovered:
    fill = rl.Color(fill.r, fill.g, fill.b, min(fill.a + 3, 255))
  if pressed:
    fill = rl.Color(fill.r, fill.g, fill.b, min(fill.a + 6, 22))

  draw_soft_card(rect, fill, border)

  if subtitle:
    resolved_title_color = title_color or (style.title_color if current else style.subtitle_color)
    resolved_subtitle_color = subtitle_color or (style.title_color if current else style.muted_color)
    gap = 4
    total_text_h = title_size + gap + subtitle_size
    text_start_y = rect.y + (rect.height - total_text_h) / 2
    draw_text_fit_common(
      gui_app.font(FontWeight.MEDIUM),
      title,
      rl.Vector2(rect.x + 12, text_start_y),
      max(1.0, rect.width - 24),
      title_size,
      align_center=True,
      color=resolved_title_color,
    )
    draw_text_fit_common(
      gui_app.font(FontWeight.NORMAL),
      subtitle,
      rl.Vector2(rect.x + 12, text_start_y + title_size + gap),
      max(1.0, rect.width - 24),
      subtitle_size,
      align_center=True,
      color=resolved_subtitle_color,
    )
  else:
    resolved_title_color = title_color or (style.title_color if current else style.subtitle_color)
    draw_text_fit_common(
      gui_app.font(FontWeight.MEDIUM),
      title,
      rl.Vector2(rect.x + 12, rect.y + (rect.height - title_size) / 2),
      max(1.0, rect.width - 24),
      title_size,
      align_center=True,
      color=resolved_title_color,
    )

  if show_underline and current:
    rl.draw_rectangle_rec(
      rl.Rectangle(rect.x + underline_inset, rect.y + rect.height - 4, rect.width - underline_inset * 2, 2),
      style.underline_color,
    )


def draw_metric_strip(
  rect: rl.Rectangle,
  metrics: list[tuple[str, str]],
  *,
  gap: int = 26,
  min_col_width: float = 104.0,
  label_size: int = 23,
  value_size: int = 28,
  style: PanelStyle = DEFAULT_PANEL_STYLE,
  label_top_offset: int = 0,
  value_top_offset: int = 20,
  divider_top_offset: int = 3,
  divider_bottom_offset: int = 23,
):
  if not metrics:
    return

  available_w = max(1.0, rect.width)
  col_w = max(min_col_width, (available_w - gap * max(0, len(metrics) - 1)) / max(1, len(metrics)))
  label_font = gui_app.font(FontWeight.MEDIUM)
  value_font = gui_app.font(FontWeight.SEMI_BOLD)

  for index, (label, value) in enumerate(metrics):
    metric_x = rect.x + index * (col_w + gap)
    draw_text_fit_common(
      label_font,
      label,
      rl.Vector2(metric_x, rect.y + label_top_offset),
      col_w,
      label_size,
      color=style.muted_color,
    )
    draw_text_fit_common(
      value_font,
      value,
      rl.Vector2(metric_x, rect.y + value_top_offset),
      col_w,
      value_size,
      color=style.title_color,
    )
    if index < len(metrics) - 1:
      divider_x = metric_x + col_w + gap / 2
      rl.draw_line(
        int(divider_x),
        int(rect.y + divider_top_offset),
        int(divider_x),
        int(rect.y + value_top_offset + divider_bottom_offset),
        style.divider_color,
      )


GROUP_OVERHEAD = AS.SETTINGS_GROUP_HEADING_HEIGHT + AS.SETTINGS_GROUP_HEADING_GAP


@dataclass(frozen=True)
class SettingsGroupFrame:
  heading: rl.Rectangle
  body: rl.Rectangle


def build_settings_group_frame(rect: rl.Rectangle) -> SettingsGroupFrame:
  """Keep group headings outside the outline and aligned with the control text."""
  inset = AS.SETTINGS_CARD_INSET
  heading = rl.Rectangle(rect.x + inset, rect.y, max(1.0, rect.width - inset * 2), AS.SETTINGS_GROUP_HEADING_HEIGHT)
  body = rl.Rectangle(rect.x, rect.y + GROUP_OVERHEAD, rect.width, max(0.0, rect.height - GROUP_OVERHEAD))
  return SettingsGroupFrame(heading, body)


def draw_settings_group_heading(rect: rl.Rectangle, title: str, *, style: PanelStyle = DEFAULT_PANEL_STYLE) -> rl.Rectangle:
  """Draw the standard left-aligned group heading; return the controls' bounds."""
  frame = build_settings_group_frame(rect)
  draw_section_header(frame.heading, title, title_size=AS.SETTINGS_GROUP_HEADING_SIZE, style=style)
  return frame.body


def draw_settings_group(rect: rl.Rectangle, title: str, *, kind: str = "rows",
                        style: PanelStyle = DEFAULT_PANEL_STYLE) -> rl.Rectangle:
  """Draw a shared section heading and its group; return the controls' bounds."""
  body = draw_settings_group_heading(rect, title, style=style)
  draw_list_group_shell(body, kind=kind, style=style)
  return body


def draw_section_header(
  rect: rl.Rectangle,
  title: str = "",
  *,
  trailing_text: str = "",
  title_size: int = 30,
  trailing_size: int = 26,
  title_color: rl.Color | None = None,
  trailing_color: rl.Color | None = None,
  style: PanelStyle = DEFAULT_PANEL_STYLE,
  align_center: bool = False,
):
  if title:
    trailing_reserved = min(320.0, rect.width * 0.38) if trailing_text else 0.0
    title_rect = rl.Rectangle(rect.x, rect.y, max(1.0, rect.width - trailing_reserved), rect.height)
    alignment = rl.GuiTextAlignment.TEXT_ALIGN_CENTER if align_center else rl.GuiTextAlignment.TEXT_ALIGN_LEFT
    gui_label(title_rect, title, title_size, title_color or style.subtitle_color, FontWeight.SEMI_BOLD, alignment=alignment)

  if trailing_text:
    trailing_rect = rect
    gui_label(
      trailing_rect,
      trailing_text,
      trailing_size,
      trailing_color or style.subtitle_color,
      FontWeight.NORMAL,
      alignment=rl.GuiTextAlignment.TEXT_ALIGN_RIGHT,
    )


def draw_empty_state_card(
  rect: rl.Rectangle,
  title: str,
  body: str,
  *,
  title_size: int = 34,
  body_size: int = 26,
  body_inset_x: int = 70,
  title_gap: int = 16,
  title_top_padding: float | None = None,
  body_height: float | None = None,
  fill: rl.Color | None = None,
  border: rl.Color | None = None,
  radius: float = 0.08,
  segments: int = 18,
  style: PanelStyle = DEFAULT_PANEL_STYLE,
):
  card_rect = snap_rect(rect)
  resolved_fill = fill if fill is not None else style.surface_fill
  resolved_border = border if border is not None else style.surface_border
  draw_soft_card(card_rect, resolved_fill, resolved_border, radius=radius, segments=segments)

  title_h = max(38.0, title_size + 8)
  title_y = card_rect.y + (title_top_padding if title_top_padding is not None else max(35.0, min(61.0, card_rect.height * 0.22)))
  inset_x = min(float(body_inset_x), max(18.0, card_rect.width * 0.22))
  body_y = title_y + title_h + title_gap
  resolved_body_h = body_height if body_height is not None else max(40.0, card_rect.height - (body_y - card_rect.y) - 35.0)

  gui_label(
    rl.Rectangle(card_rect.x, title_y, card_rect.width, title_h),
    title,
    title_size,
    style.title_color,
    FontWeight.MEDIUM,
    alignment=rl.GuiTextAlignment.TEXT_ALIGN_CENTER,
  )
  resolved_body_h = min(resolved_body_h, max(0.0, card_rect.y + card_rect.height - body_y))
  font = gui_app.font(FontWeight.NORMAL)
  line_height = body_size * FONT_SCALE
  line_gap = 4.0
  max_lines = int((resolved_body_h + line_gap) // (line_height + line_gap))
  if not body or max_lines < 1:
    return
  body_width = max(1.0, card_rect.width - inset_x * 2)
  if "\n" not in body and measure_text_cached(font, body, body_size).x <= body_width:
    lines = [body]
  else:
    lines = wrap_body_text(font, body, body_size, int(body_width))
  if len(lines) > max_lines:
    lines = lines[:max_lines - 1] + [truncate_text_ellipsis(font, " ".join(lines[max_lines - 1:]), body_width, body_size)]
  text_y = body_y + (resolved_body_h - len(lines) * line_height - (len(lines) - 1) * line_gap) / 2
  for line in lines:
    gui_label(
      rl.Rectangle(card_rect.x + inset_x, text_y, body_width, line_height),
      line, body_size, style.subtitle_color, FontWeight.NORMAL,
      alignment=rl.GuiTextAlignment.TEXT_ALIGN_CENTER,
    )
    text_y += line_height + line_gap


def draw_list_group_shell(
  rect: rl.Rectangle,
  *,
  kind: str = "rows",
  fill: rl.Color | None = None,
  border: rl.Color | None = None,
  radius: float = 0.08,
  segments: int = 18,
  style: PanelStyle = DEFAULT_PANEL_STYLE,
):
  if fill is None and border is None:
    if kind == "tiles":
      return  # tiles are cards already
    # Aether Cards: one container card around a grouped list; the rows inside draw thin dividers.
    draw_settings_card(rect, border=AS.SETTINGS_TILE_BORDER)
    return
  draw_soft_card(rect, fill if fill is not None else style.surface_fill, border if border is not None else style.surface_border, radius=radius, segments=segments)


def draw_settings_list_row(
  rect: rl.Rectangle,
  *,
  title: str,
  subtitle: str = "",
  value: str = "",
  toggle_value: bool | None = None,
  enabled: bool = True,
  hovered: bool = False,
  pressed: bool = False,
  is_last: bool = False,
  show_chevron: bool = True,
  title_size: int = SETTINGS_ROW_TITLE_FONT_SIZE,
  subtitle_size: int = SETTINGS_ROW_SUBTITLE_FONT_SIZE,
  value_size: int = SETTINGS_ROW_VALUE_FONT_SIZE,
  separator_inset: int = 24,
  title_color: rl.Color | None = None,
  subtitle_color: rl.Color | None = None,
  value_color: rl.Color | None = None,
  style: PanelStyle = DEFAULT_PANEL_STYLE,
  card: bool = False,
):
  if card:
    return draw_settings_card_row(
      row_card_rect(rect), title=title, subtitle=subtitle, value=value, toggle_value=toggle_value,
      enabled=enabled, hovered=hovered, pressed=pressed, show_chevron=show_chevron,
      title_size=title_size, subtitle_size=subtitle_size, value_size=value_size,
      title_color=title_color, subtitle_color=subtitle_color, value_color=value_color, style=style,
    )
  draw_rect = snap_rect(rect)
  resolved_title_color = title_color or (style.title_color if enabled else style.muted_color)
  resolved_subtitle_color = subtitle_color or (style.subtitle_color if enabled else style.muted_color)
  resolved_value_color = value_color or (style.title_color if enabled else style.muted_color)

  is_narrow = draw_rect.width < 1000
  chevron_right_inset = 28 if is_narrow else AETHER_LIST_METRICS.utility_chevron_right
  chevron_y = draw_rect.y + (draw_rect.height - 26) / 2
  chevron_rect = rl.Rectangle(draw_rect.x + draw_rect.width - chevron_right_inset, chevron_y, 26, 26)

  draw_list_row_shell(
    draw_rect,
    hovered=hovered and enabled,
    pressed=pressed and enabled,
    is_last=is_last,
    row_bg=rl.Color(255, 255, 255, 0),
    row_border=rl.Color(255, 255, 255, 0),
    row_separator=style.divider_color,
    current_bg=rl.Color(255, 255, 255, 0),
    current_border=rl.Color(255, 255, 255, 0),
    separator_inset=separator_inset,
    emphasis=bool(toggle_value) or bool(value and show_chevron),
    card=card,
  )

  text_left = draw_rect.x + 44

  if toggle_value is not None:
    toggle_right_inset = AETHER_LIST_METRICS.toggle_right_inset
    text_right = draw_rect.x + draw_rect.width - AETHER_LIST_METRICS.toggle_width - toggle_right_inset - 12
    text_width = max(100.0, text_right - text_left)

    draw_row_title_subtitle(draw_rect, text_left, text_width, title, subtitle, title_size, subtitle_size,
                            resolved_title_color, resolved_subtitle_color)

    target = 1.0 if toggle_value else 0.0
    current_progress = _KNOB_ANIMATION_STATES.get(title, target)
    dt = rl.get_frame_time()
    current_progress += (target - current_progress) * 12.0 * dt
    if abs(current_progress - target) < 0.001:
      current_progress = target
    _KNOB_ANIMATION_STATES[title] = current_progress

    draw_toggle_switch(
      draw_rect, 
      bool(toggle_value), 
      knob_progress=current_progress,
      is_enabled=enabled, 
      track_color=style.accent,
      seed_id=title,
      right_inset=toggle_right_inset,
    )
    return

  if value:
    if is_narrow and draw_rect.height >= 86 and not subtitle and not show_chevron:
      # Adaptive Two-Line Stacked Layout: Title on top, Value spanning full width below
      eff_title_size = min(SETTINGS_ROW_TITLE_FONT_SIZE, title_size)
      eff_value_size = min(SETTINGS_ROW_VALUE_FONT_SIZE, value_size)
      available_w = max(100.0, draw_rect.width - 48 - (32 if show_chevron else 0))

      total_h = (eff_title_size + eff_value_size) * FONT_SCALE + 6
      start_y = draw_rect.y + (draw_rect.height - total_h) / 2

      draw_text_fit_common(
        gui_app.font(FontWeight.SEMI_BOLD), title,
        rl.Vector2(text_left, start_y),
        available_w, eff_title_size,
        color=resolved_title_color,
      )
      draw_text_fit_common(
        gui_app.font(FontWeight.MEDIUM), value,
        rl.Vector2(text_left, start_y + eff_title_size * FONT_SCALE + 6),
        available_w, eff_value_size,
        color=resolved_subtitle_color if resolved_value_color == resolved_title_color else resolved_value_color,
      )
    else:
      # Proportional Side-by-Side
      if is_narrow:
        content_w = max(100.0, draw_rect.width - 48 - (32 if show_chevron else 0))
        t_width = content_w * 0.46
        v_width = content_w * 0.52
        v_right = draw_rect.x + 24 + content_w
      else:
        v_width = max(100.0, float(AETHER_LIST_METRICS.utility_value_right - (AETHER_LIST_METRICS.utility_chevron_right if show_chevron else 24) - 16))
        t_width = max(100.0, draw_rect.width - 48 - v_width - (32 if show_chevron else 0))
        v_right = chevron_rect.x - 16 if show_chevron else draw_rect.x + draw_rect.width - 24
      if show_chevron:
        pill_max = v_width + (0 if is_narrow else AETHER_LIST_METRICS.utility_chevron_right)
        t_width = max(100.0, draw_rect.width - 44 - value_pill_width(value, pill_max) - 36 - 24)

      eff_value_size = min(SETTINGS_ROW_VALUE_FONT_SIZE, value_size)
      value_y = draw_rect.y + (draw_rect.height - eff_value_size * FONT_SCALE) / 2

      if subtitle:
        draw_row_title_subtitle(draw_rect, text_left, t_width, title, subtitle, title_size, subtitle_size,
                                resolved_title_color, resolved_subtitle_color)
      else:
        eff_title_size = min(SETTINGS_ROW_TITLE_FONT_SIZE, title_size) if is_narrow else title_size
        title_y = draw_rect.y + (draw_rect.height - eff_title_size * FONT_SCALE) / 2

        draw_text_fit_common(
          gui_app.font(FontWeight.SEMI_BOLD), title,
          rl.Vector2(text_left, title_y),
          t_width, eff_title_size,
          color=resolved_title_color,
        )

      if show_chevron:
        # Aether Cards: a tappable value reads as a pill button that opens its picker.
        draw_value_pill(draw_rect.x + draw_rect.width - 36, draw_rect.y + draw_rect.height / 2, value,
                        max_width=v_width + (0 if is_narrow else AETHER_LIST_METRICS.utility_chevron_right), enabled=enabled,
                        pressed=pressed, font_size=eff_value_size,
                        max_height=row_card_rect(draw_rect).height - 24)
        return
      draw_text_fit_common(
        gui_app.font(FontWeight.MEDIUM), value,
        rl.Vector2(v_right - v_width, value_y),
        v_width, eff_value_size,
        align_right=True,
        color=resolved_value_color,
      )

    if show_chevron:
      draw_chevron_icon(chevron_rect, style.muted_color)
    return

  # Generic row without value or toggle
  text_right = chevron_rect.x - 12 if show_chevron else draw_rect.x + draw_rect.width - 24
  text_width = max(100.0, text_right - text_left)
  if subtitle:
    draw_row_title_subtitle(draw_rect, text_left, text_width, title, subtitle, title_size, subtitle_size,
                            resolved_title_color, resolved_subtitle_color)
  else:
    eff_title_size = min(SETTINGS_ROW_TITLE_FONT_SIZE, title_size)
    title_y = draw_rect.y + (draw_rect.height - eff_title_size * FONT_SCALE) / 2
    draw_text_fit_common(
      gui_app.font(FontWeight.SEMI_BOLD), title,
      rl.Vector2(text_left, title_y),
      text_width, eff_title_size,
      color=resolved_title_color,
    )

  if show_chevron:
    draw_chevron_icon(chevron_rect, style.muted_color)


VALUE_PILL_HEIGHT = AS.VALUE_PILL_HEIGHT
ROW_SUBTITLE_MAX_LINES = 2


@dataclass(frozen=True)
class SettingsRowLayout:
  face: rl.Rectangle
  text: rl.Rectangle
  control: rl.Rectangle


@dataclass(frozen=True)
class RowStatus:
  """Configured status, independent of whether the row is being edited."""
  icon_key: str
  text: str
  is_on: bool


def build_settings_row_layout(rect: rl.Rectangle, control_width: float = 0) -> SettingsRowLayout:
  """Geometry shared by toggle, value, action and navigation cards."""
  face = snap_rect(rect)
  inset = AS.SETTINGS_CARD_INSET
  control_width = min(control_width, max(0.0, face.width - inset * 2))
  right = face.x + face.width - inset
  control = rl.Rectangle(right - control_width, face.y, control_width, face.height)
  gap = AS.SETTINGS_CONTROL_GAP if control_width else 0
  text = rl.Rectangle(face.x + inset, face.y, max(1.0, face.width - inset * 2 - control_width - gap), face.height)
  return SettingsRowLayout(face, text, control)


def draw_status_value_row(rect: rl.Rectangle, *, title: str, value: str, status: RowStatus,
                          style: PanelStyle = DEFAULT_PANEL_STYLE) -> None:
  """Shared grouped-row content: status well, title/subtitle, value and chevron."""
  value_size = SETTINGS_ROW_VALUE_FONT_SIZE
  value_font = gui_app.font(FontWeight.MEDIUM)
  value_width = min(measure_text_cached(value_font, value, value_size).x, rect.width * 0.28)
  chevron_width = 28
  layout = build_settings_row_layout(rect, value_width + AS.SETTINGS_TEXT_GAP + chevron_width)
  size = min(AS.SETTINGS_STATUS_ICON_SIZE, rect.height - AS.SETTINGS_ROW_GAP * 2)
  well = snap_rect(rl.Rectangle(layout.text.x, rect.y + (rect.height - size) / 2, size, size))
  aether_fill(well, AS.ACCENT_TINT if status.is_on else with_alpha(AS.TRACK_OFF, 120), AS.SETTINGS_STATUS_ICON_RADIUS)
  icon_size = size * 0.62
  draw_custom_icon(status.icon_key, well.x + (size - icon_size) / 2, well.y + (size - icon_size) / 2,
                   icon_size / CUSTOM_ICON_CANVAS_SIZE, AS.ICON_INK if status.is_on else style.subtitle_color)
  text_x = well.x + well.width + AS.SETTINGS_CONTROL_GAP
  draw_row_title_subtitle(rect, text_x, max(1.0, layout.text.x + layout.text.width - text_x), title, status.text,
                          SETTINGS_ROW_TITLE_FONT_SIZE, SETTINGS_ROW_SUBTITLE_FONT_SIZE, style.title_color, style.subtitle_color)
  center_y = rect.y + rect.height / 2
  draw_text_fit_common(value_font, value, rl.Vector2(layout.control.x, center_y - value_size * FONT_SCALE / 2),
                       value_width, value_size, align_right=True, color=style.title_color)
  draw_chevron_icon(rl.Rectangle(layout.control.x + layout.control.width - chevron_width, center_y - 18, chevron_width, 36),
                     style.subtitle_color)


def draw_settings_card_row(
  rect: rl.Rectangle, *, title: str, subtitle: str = "", value: str = "",
  toggle_value: bool | None = None, action_text: str = "", show_chevron: bool = True,
  enabled: bool = True, hovered: bool = False, pressed: bool = False, current: bool = False,
  title_size: int = SETTINGS_ROW_TITLE_FONT_SIZE, subtitle_size: int = SETTINGS_ROW_SUBTITLE_FONT_SIZE,
  value_size: int = SETTINGS_ROW_VALUE_FONT_SIZE, title_color: rl.Color | None = None,
  subtitle_color: rl.Color | None = None, value_color: rl.Color | None = None,
  style: PanelStyle = DEFAULT_PANEL_STYLE, action_fill: rl.Color | None = None,
  action_border: rl.Color | None = None, action_text_color: rl.Color | None = None,
  action_text_size: int = 26, action_height: float = AS.SWITCH_HEIGHT, alpha: int = 255,
) -> rl.Rectangle:
  """One card component; menu code supplies content and behavior, never insets."""
  max_control = max(0.0, (rect.width - AS.SETTINGS_CARD_INSET * 2) * 0.42)
  if toggle_value is not None:
    control_width = AS.SWITCH_WIDTH
  elif action_text:
    natural = measure_text_cached(gui_app.font(FontWeight.SEMI_BOLD), action_text, action_text_size).x + AS.SETTINGS_CARD_INSET
    control_width = min(max_control, max(AS.MIN_TOUCH, natural))
  elif value:
    control_width = value_pill_width(value, max_control, value_size) if show_chevron else max_control
  else:
    control_width = 28 if show_chevron else 0
  layout = build_settings_row_layout(rect, control_width)
  draw_settings_row_shell(layout.face, hovered=hovered and enabled, pressed=pressed and enabled,
                          current=current, emphasis=bool(toggle_value) or bool(value and show_chevron), alpha=alpha)
  draw_row_title_subtitle(
    layout.face, layout.text.x, layout.text.width, title, subtitle, title_size, subtitle_size,
    with_alpha(title_color or (style.title_color if enabled else style.muted_color), alpha),
    with_alpha(subtitle_color or (style.subtitle_color if enabled else style.muted_color), alpha),
  )
  center_y = layout.face.y + layout.face.height / 2
  right = layout.control.x + layout.control.width
  if toggle_value is not None:
    target = float(toggle_value)
    progress = _KNOB_ANIMATION_STATES.get(title, target)
    progress += (target - progress) * min(1.0, 12 * rl.get_frame_time())
    _KNOB_ANIMATION_STATES[title] = progress
    draw_toggle_switch(layout.face, toggle_value, knob_progress=progress, is_enabled=enabled,
                       track_color=style.accent, right_inset=AS.SETTINGS_CARD_INSET)
  elif action_text:
    height = min(action_height, layout.face.height - AS.SETTINGS_CARD_INSET)
    action = rl.Rectangle(layout.control.x, center_y - height / 2, control_width, height)
    draw_action_pill(action, action_text, with_alpha(action_fill or AS.ACCENT_TINT, alpha),
                     with_alpha(action_border or AS.ACCENT_EDGE, alpha),
                     with_alpha(action_text_color or AS.TEXT, alpha), font_size=action_text_size)
    return action
  elif value and show_chevron:
    return draw_value_pill(right, center_y, value, max_width=control_width, enabled=enabled,
                           pressed=pressed, font_size=value_size, max_height=layout.face.height - AS.SETTINGS_CARD_INSET)
  elif value:
    size = min(SETTINGS_ROW_VALUE_FONT_SIZE, value_size)
    draw_text_fit_common(gui_app.font(FontWeight.MEDIUM), value,
                         rl.Vector2(layout.control.x, center_y - size * FONT_SCALE / 2), control_width, size,
                         align_right=True, color=value_color or (style.title_color if enabled else style.muted_color))
  elif show_chevron:
    draw_chevron_icon(rl.Rectangle(layout.control.x, center_y - 14, 28, 28), style.muted_color)
  return layout.control


def wrap_subtitle(font: rl.Font, text: str, width: float, font_size: int, max_lines: int = ROW_SUBTITLE_MAX_LINES) -> list[str]:
  """Wrap a row subtitle to at most `max_lines`, ending the last line with an ellipsis when text is cut."""
  lines = wrap_text(font, text, width, font_size, max_lines=max_lines, spacing=0)
  if " ".join(lines).split() != text.split():
    last = lines[-1]
    while last and measure_text_cached(font, last + "...", font_size, spacing=0).x > width:
      last = last.rsplit(" ", 1)[0] if " " in last else last[:-1]
    lines[-1] = last.rstrip(" ,.;:") + "..."
  return lines


def draw_row_title_subtitle(rect: rl.Rectangle, x: float, width: float, title: str, subtitle: str,
                            title_size: int, subtitle_size: int, title_color: rl.Color, subtitle_color: rl.Color):
  """Title with a readable subtitle that wraps onto a second line instead of shrinking to fit."""
  title_size = min(SETTINGS_ROW_TITLE_FONT_SIZE, title_size)
  subtitle_size = min(SETTINGS_ROW_SUBTITLE_FONT_SIZE, subtitle_size)
  sub_font = gui_app.font(FontWeight.NORMAL)
  line_h = subtitle_size * FONT_SCALE + 2
  room = rect.height - AS.SETTINGS_ROW_GAP * 2 - title_size * FONT_SCALE - AS.SETTINGS_TEXT_GAP
  max_lines = max(1, min(ROW_SUBTITLE_MAX_LINES, int(room // line_h)))
  lines = wrap_subtitle(sub_font, subtitle, width, subtitle_size, max_lines) if subtitle else []
  total_h = title_size * FONT_SCALE + (AS.SETTINGS_TEXT_GAP + len(lines) * line_h if lines else 0)
  y = rect.y + (rect.height - total_h) / 2
  draw_text_fit_common(gui_app.font(FontWeight.SEMI_BOLD), title, rl.Vector2(x, y), width, title_size, color=title_color)
  y += title_size * FONT_SCALE + AS.SETTINGS_TEXT_GAP
  for line in lines:
    draw_text_fit_common(sub_font, line, rl.Vector2(x, y), width, subtitle_size, color=subtitle_color)
    y += line_h


VALUE_PILL_CHEVRON, VALUE_PILL_PAD_L, VALUE_PILL_PAD_R, VALUE_PILL_GAP = 36, 40, 26, 12


def value_pill_width(text: str, max_width: float, font_size: int = 34) -> float:
  font_size = min(font_size, 36)
  text_w = measure_text_cached(gui_app.font(FontWeight.SEMI_BOLD), text, font_size).x if text else 0.0
  natural = VALUE_PILL_PAD_L + text_w + VALUE_PILL_GAP + VALUE_PILL_CHEVRON + VALUE_PILL_PAD_R
  return max(float(AS.MIN_TOUCH * 1.4), min(max_width, natural))


def draw_value_pill(right: float, center_y: float, text: str, *, max_width: float, enabled: bool = True,
                    pressed: bool = False, font_size: int = 34, max_height: float = VALUE_PILL_HEIGHT) -> rl.Rectangle:
  """Accent-tinted pill holding a setting's current value and a chevron, right-aligned at `right`."""
  font = gui_app.font(FontWeight.SEMI_BOLD)
  font_size = min(font_size, 36)
  chevron_w, pad_l, pad_r, gap = VALUE_PILL_CHEVRON, VALUE_PILL_PAD_L, VALUE_PILL_PAD_R, VALUE_PILL_GAP
  width = value_pill_width(text, max_width, font_size)
  height = max(56.0, min(VALUE_PILL_HEIGHT, max_height))
  pill = snap_rect(rl.Rectangle(right - width, center_y - height / 2, width, height))
  fill = AS.ACCENT_TINT if enabled else with_alpha(AS.TRACK_OFF, 120)
  if pressed and enabled:
    fill = with_alpha(AS.ACCENT, 110)
  radius = pill.height / 2
  aether_fill(pill, fill, radius, segments=32)
  if enabled:
    _draw_card_outline(pill, AS.ACCENT_EDGE, radius, width=4)
  text_color = AS.TEXT if enabled else AS.TEXT_DISABLED
  text_max = max(1.0, pill.width - pad_l - gap - chevron_w - pad_r)
  draw_text_fit_common(font, text, rl.Vector2(pill.x + pad_l, pill.y + (pill.height - font_size * FONT_SCALE) / 2),
                       text_max, font_size, color=text_color)
  draw_chevron_icon(rl.Rectangle(pill.x + pill.width - pad_r - chevron_w, center_y - chevron_w / 2, chevron_w, chevron_w), text_color,
                    thickness=5.0)
  return pill


def draw_selectable_chip(rect: rl.Rectangle, text: str, *,
                          current: bool, pressed: bool,
                          color: rl.Color,
                          font: rl.Font | None = None,
                          font_size: int = 28,
                          radius_px: float = 16,
                          text_color_active: rl.Color = AetherListColors.HEADER,
                          text_color_normal: rl.Color = AetherListColors.SUBTEXT,
                          padding_x: int = 10):
  fill = rl.Color(255, 255, 255, 5)
  border = rl.Color(255, 255, 255, 14)
  text_color = text_color_normal
  if current:
    fill = mix_colors(rl.Color(18, 22, 28, 255), color, 0.22, alpha=255)
    border = with_alpha(color, 72)
    text_color = text_color_active
  elif pressed:
    fill = rl.Color(255, 255, 255, 10)
    border = rl.Color(255, 255, 255, 22)

  resolved_font = font or gui_app.font(FontWeight.MEDIUM)
  draw_rounded_fill(rect, fill, radius_px=radius_px)
  draw_rounded_stroke(rect, border, radius_px=radius_px)
  draw_text_fit_common(
    resolved_font,
    text,
    rl.Vector2(rect.x + padding_x, rect.y + (rect.height - font_size * FONT_SCALE) / 2),
    max(1.0, rect.width - padding_x * 2),
    font_size,
    align_center=True,
    color=text_color,
  )


def format_adjustor_value(value: float, *, step: float = 1.0, unit: str = "", labels: dict[float, str] | None = None) -> str:
  label_map = labels or {}
  tolerance = max(abs(step) * 0.5, 1e-4) if step != 0 else 1e-4
  for label_value, label in label_map.items():
    if abs(float(label_value) - float(value)) <= tolerance:
      return label

  if step > 0 and step < 1:
    decimals = max(1, min(3, len(f"{step:.6f}".rstrip("0").split(".")[-1])))
    return f"{value:.{decimals}f}{unit}"
  if abs(value - round(value)) <= tolerance:
    return f"{int(round(value))}{unit}"
  return f"{value:.2f}".rstrip("0").rstrip(".") + unit



class AetherInlineRangeControl(Widget):
  def __init__(
    self,
    min_val: float,
    max_val: float,
    step: float,
    current_val: float,
    on_change: Callable[[float], None],
    *,
    on_commit: Callable[[float], None] | None = None,
    unit: str = "",
    labels: dict[float, str] | None = None,
    color: rl.Color = AetherListColors.PRIMARY,
    major_tick_count: int = 5,
  ):
    super().__init__()
    self.min_val = min_val
    self.max_val = max_val
    self.step = step
    self.current_val = current_val
    self._on_change = on_change
    self._on_commit = on_commit
    self._unit = unit
    self._labels = labels or {}
    self._color = color
    self._major_tick_count = max(0, major_tick_count)
    self._font = gui_app.font(FontWeight.SEMI_BOLD)

    self._smooth_value = current_val
    self._thumb_focus = 0.0
    self._pending_drag = False
    self._is_dragging = False
    self._started_on_thumb = False
    self._press_start = rl.Vector2(0, 0)
    self._value_at_press = current_val

    self._pressed_button: int = 0
    self._button_press_started = 0.0
    self._next_repeat_at = 0.0
    self._repeat_count = 0
    self._button_press_changed = False

    self._minus_rect = rl.Rectangle(0, 0, 0, 0)
    self._plus_rect = rl.Rectangle(0, 0, 0, 0)
    self._track_rect = rl.Rectangle(0, 0, 0, 0)
    self._thumb_rect = rl.Rectangle(0, 0, 0, 0)

  @property
  def is_interacting(self) -> bool:
    return self._pending_drag or self._is_dragging or self._pressed_button != 0

  def set_value(self, value: float) -> None:
    self.current_val = self._clamp_and_snap(value)

  def reset_interaction(self) -> None:
    self._pending_drag = False
    self._is_dragging = False
    self._started_on_thumb = False
    self._pressed_button = 0
    self._repeat_count = 0
    self._button_press_changed = False

  def set_touch_valid_callback(self, touch_callback: Callable[[], bool]) -> None:
    super().set_touch_valid_callback(touch_callback)

  def _cancel_interaction(self, *, revert: bool = False) -> None:
    if revert and self.current_val != self._value_at_press:
      self.current_val = self._value_at_press
      self._on_change(self.current_val)
    self.reset_interaction()

  def _clamp_and_snap(self, value: float) -> float:
    return clamp_and_snap(value, self.min_val, self.max_val, self.step)

  def _step_value(self, direction: int) -> bool:
    new_val = self._clamp_and_snap(self.current_val + direction * self.step)
    if new_val == self.current_val:
      return False
    self.current_val = new_val
    self._on_change(self.current_val)
    self._button_press_changed = True
    return True

  def _value_fraction(self, value: float) -> float:
    return value_fraction(value, self.min_val, self.max_val)

  def _update_val_from_mouse(self, mouse_pos: MousePos) -> None:
    new_val = update_val_from_mouse(mouse_pos, self._track_rect, self.min_val, self.max_val, self.step)
    if new_val != self.current_val:
      self.current_val = new_val
      self._on_change(self.current_val)

  def _commit_if_needed(self) -> None:
    if self.current_val != self._value_at_press and self._on_commit is not None:
      self._on_commit(self.current_val)

  def _update_state(self):
    super()._update_state()
    if self._pressed_button == 0:
      return
    now = time.monotonic()
    if now < self._next_repeat_at:
      return

    if self._step_value(self._pressed_button):
      self._repeat_count += 1
    repeat_interval = 0.12 if self._repeat_count < 3 else 0.075
    self._next_repeat_at = now + repeat_interval

  def _handle_mouse_press(self, mouse_pos: MousePos):
    if not self._touch_valid() or not point_hits(mouse_pos, self._rect, self._parent_rect, pad_x=0, pad_y=0):
      return

    self._value_at_press = self.current_val
    self._button_press_changed = False
    now = time.monotonic()
    if rl.check_collision_point_rec(mouse_pos, self._minus_rect):
      self._pressed_button = -1
      self._button_press_started = now
      self._next_repeat_at = now + 0.34
      self._repeat_count = 0
      return
    if rl.check_collision_point_rec(mouse_pos, self._plus_rect):
      self._pressed_button = 1
      self._button_press_started = now
      self._next_repeat_at = now + 0.34
      self._repeat_count = 0
      return

    self._pending_drag = True
    self._started_on_thumb = rl.check_collision_point_rec(mouse_pos, _inflate_rect(self._thumb_rect, 12, 12))
    self._press_start = rl.Vector2(mouse_pos.x, mouse_pos.y)

  def _handle_mouse_release(self, mouse_pos: MousePos):
    if self._pressed_button != 0:
      direction = self._pressed_button
      button_rect = self._minus_rect if direction < 0 else self._plus_rect
      if rl.check_collision_point_rec(mouse_pos, button_rect) and self._repeat_count == 0:
        self._step_value(direction)
      self._pressed_button = 0
      self._repeat_count = 0
      self._commit_if_needed()
      return

    if self._is_dragging:
      self._is_dragging = False
      self._commit_if_needed()
      return

    if self._pending_drag:
      if not self._started_on_thumb and rl.check_collision_point_rec(mouse_pos, self._rect):
        self._update_val_from_mouse(mouse_pos)
        self._commit_if_needed()
      self._pending_drag = False
      self._started_on_thumb = False

  def _handle_mouse_event(self, mouse_event: MouseEvent):
    mouse_in_rect = rl.check_collision_point_rec(mouse_event.pos, self._rect)
    if mouse_event.left_released and self.is_interacting and not mouse_in_rect:
      if self._pressed_button != 0:
        self._pressed_button = 0
        self._repeat_count = 0
        self._commit_if_needed()
      elif self._is_dragging or self._pending_drag:
        self._cancel_interaction(revert=True)
      return

    if not self._touch_valid():
      self._cancel_interaction(revert=True)
      return

    if self._pressed_button != 0:
      button_rect = self._minus_rect if self._pressed_button < 0 else self._plus_rect
      if not rl.check_collision_point_rec(mouse_event.pos, _inflate_rect(button_rect, 4, 4)):
        self._pressed_button = 0
        self._repeat_count = 0
        if self._button_press_changed:
          self._commit_if_needed()
      return

    if self._pending_drag and not self._is_dragging:
      dx = mouse_event.pos.x - self._press_start.x
      dy = mouse_event.pos.y - self._press_start.y
      if abs(dy) > 12 and abs(dy) > abs(dx):
        self._pending_drag = False
        self._started_on_thumb = False
        return
      if abs(dx) > 12 and abs(dx) >= abs(dy):
        self._pending_drag = False
        self._is_dragging = True

    if self._is_dragging:
      dx = mouse_event.pos.x - self._press_start.x
      dy = mouse_event.pos.y - self._press_start.y
      if abs(dy) > 18 and abs(dy) > abs(dx) * 1.15:
        self._cancel_interaction(revert=True)
        return
      self._update_val_from_mouse(mouse_event.pos)

  def _draw_button(self, rect: rl.Rectangle, label: str, *, pressed: bool = False):
    fill = rl.Color(255, 255, 255, 8 if not pressed else 14)
    border = rl.Color(255, 255, 255, 18 if not pressed else 28)
    draw_rounded_fill(rect, fill, radius_px=14)
    draw_rounded_stroke(rect, border, radius_px=14)
    draw_stepper_symbol(rect, increment=label == "+", color=AetherListColors.HEADER)

  def _render(self, rect: rl.Rectangle):
    rect = snap_rect(rect)
    self.set_rect(rect)
    dt = rl.get_frame_time()
    self._smooth_value += (self.current_val - self._smooth_value) * (1 - math.exp(-dt / 0.075))
    thumb_target = 1.0 if self._is_dragging or self._pending_drag else 0.0
    self._thumb_focus += (thumb_target - self._thumb_focus) * (1 - math.exp(-dt / 0.070))

    button_size = min(rect.height, 64)
    button_y = rect.y + (rect.height - button_size) / 2
    self._minus_rect = snap_rect(rl.Rectangle(rect.x, button_y, button_size, button_size))
    self._plus_rect = snap_rect(rl.Rectangle(rect.x + rect.width - button_size, button_y, button_size, button_size))
    self._draw_button(self._minus_rect, "-", pressed=self._pressed_button < 0)
    self._draw_button(self._plus_rect, "+", pressed=self._pressed_button > 0)

    track_x = self._minus_rect.x + self._minus_rect.width + 20
    track_w = max(1.0, self._plus_rect.x - 20 - track_x)
    lane_h = rect.height
    track_h = 6.0
    track_y = rect.y + (lane_h - track_h) / 2
    self._track_rect = snap_rect(rl.Rectangle(track_x, track_y, track_w, track_h))

    rl.draw_rectangle_rounded(self._track_rect, 1.0, 12, rl.Color(255, 255, 255, 18))
    if self._major_tick_count > 1:
      for index in range(self._major_tick_count):
        frac = index / max(1, self._major_tick_count - 1)
        tick_x = self._track_rect.x + frac * self._track_rect.width
        rl.draw_rectangle_rec(rl.Rectangle(tick_x - 1, rect.y + rect.height / 2 - 8, 3, 23), rl.Color(255, 255, 255, 24))

    fill_frac = self._value_fraction(self._smooth_value)
    fill_w = fill_frac * self._track_rect.width
    if fill_w > 1:
      fill_rect = snap_rect(rl.Rectangle(self._track_rect.x, self._track_rect.y, fill_w, self._track_rect.height))
      rl.draw_rectangle_rounded(fill_rect, 1.0, 12, with_alpha(self._color, 220))

    thumb_w = 32 + self._thumb_focus * 4
    thumb_h = 41 + self._thumb_focus * 4
    thumb_center_x = self._track_rect.x + fill_frac * self._track_rect.width
    thumb_center_y = rect.y + rect.height / 2
    self._thumb_rect = snap_rect(rl.Rectangle(thumb_center_x - thumb_w / 2, thumb_center_y - thumb_h / 2, thumb_w, thumb_h))
    thumb_fill = mix_colors(rl.Color(224, 230, 238, 255), self._color, 0.12)
    draw_rounded_fill(self._thumb_rect, thumb_fill, radius_px=12)
    draw_rounded_stroke(self._thumb_rect, rl.Color(14, 17, 23, 52), radius_px=12)
    if self._thumb_focus > 0.02:
      draw_rounded_stroke(_inflate_rect(self._thumb_rect, 1, 1), with_alpha(self._color, int(70 * self._thumb_focus)), radius_px=13)

    if self._is_dragging or self._pressed_button != 0:
      bubble_text = format_adjustor_value(self.current_val, step=self.step, unit=self._unit, labels=self._labels)
      bubble_w = max(116.0, min(191.0, 44.0 + len(bubble_text) * 10.0))
      bubble_rect = snap_rect(rl.Rectangle(thumb_center_x - bubble_w / 2, rect.y - 58, bubble_w, 46))
      bubble_fill = mix_colors(rl.Color(18, 22, 28, 255), self._color, 0.18)
      bubble_border = with_alpha(self._color, 70)
      draw_rounded_fill(bubble_rect, bubble_fill, radius_px=14)
      draw_rounded_stroke(bubble_rect, bubble_border, radius_px=14)
      draw_text_fit_common(
        gui_app.font(FontWeight.MEDIUM),
        bubble_text,
        rl.Vector2(bubble_rect.x + 10, bubble_rect.y + 7),
        max(1.0, bubble_rect.width - 20),
        23,
        align_center=True,
        color=AetherListColors.HEADER,
      )





class AetherAdjustorRow(Widget):
  def __init__(
    self,
    title: str,
    subtitle: str,
    min_val: float,
    max_val: float,
    step: float,
    get_value: Callable[[], float],
    on_change: Callable[[float], None],
    *,
    on_commit: Callable[[float], None] | None = None,
    unit: str = "",
    labels: dict[float, str] | None = None,
    presets: list[float] | None = None,
    is_active: bool | Callable[[], bool] = False,
    set_active: Callable[[bool], None] | None = None,
    style: PanelStyle = DEFAULT_PANEL_STYLE,
    color: rl.Color | None = None,
    icon_key: str | None = None,
    status: RowStatus | Callable[[], RowStatus] | None = None,
  ):
    super().__init__()
    self._title = title
    self._subtitle = subtitle
    self._get_value = get_value
    self._is_active = is_active
    self._set_active = set_active
    self._style = style
    self._color = color or style.accent
    self._status = status
    valid_icons = {"sound", "steering", "navigate", "system", "display", "vehicle", "road", "aicar", "first_aid"}
    self._icon_key = icon_key if icon_key in valid_icons else None
    self._presets = presets or []
    self._preset_applied = False
    self._font_title = gui_app.font(FontWeight.MEDIUM)
    self._font_subtitle = gui_app.font(FontWeight.NORMAL)
    self._font_value = gui_app.font(FontWeight.MEDIUM)
    self._focus_progress = 0.0
    self._pressed_zone: str | None = None
    self._is_last = False
    self._header_rect = rl.Rectangle(0, 0, 0, 0)
    self._progress_bar_rect = rl.Rectangle(0, 0, 0, 0)
    self._preset_rects: list[tuple[float, rl.Rectangle]] = []
    self._scrubber_rect = rl.Rectangle(0, 0, 0, 0)
    self._scrubber = self._child(
      AetherInlineRangeControl(
        min_val,
        max_val,
        step,
        get_value(),
        on_change,
        on_commit=on_commit,
        unit=unit,
        labels=labels,
        color=self._color,
      )
    )
    self._unit = unit
    self._labels = labels or {}
    self._step = step
    self.custom_row_height = None

  @property
  def is_interacting(self) -> bool:
    return self._scrubber.is_interacting

  def _active(self) -> bool:
    return bool(self._is_active() if callable(self._is_active) else self._is_active)

  def reset_interaction(self) -> None:
    self._pressed_zone = None
    self._scrubber.reset_interaction()

  def set_touch_valid_callback(self, touch_callback: Callable[[], bool]) -> None:
    super().set_touch_valid_callback(touch_callback)
    self._scrubber.set_touch_valid_callback(touch_callback)

  def set_is_last(self, is_last: bool) -> None:
    self._is_last = is_last

  def _current_value(self) -> float:
    return self._scrubber.current_val if (self._active() or self._scrubber.is_interacting) else self._get_value()

  def formatted_value(self) -> str:
    return format_adjustor_value(self._current_value(), step=self._step, unit=self._unit, labels=self._labels)

  def measure_height(self, width: float) -> float:
    del width
    if getattr(self, "custom_row_height", None) is not None:
      return float(self.custom_row_height)
    base_height = AS.SETTINGS_ROW_CARD_HEIGHT if self._status is not None else AETHER_LIST_METRICS.adjustor_row_height
    if not self._active():
      return float(base_height)
    preset_height = AETHER_LIST_METRICS.adjustor_preset_height + AETHER_LIST_METRICS.adjustor_preset_gap if self._presets else 0
    return float(base_height + AETHER_LIST_METRICS.adjustor_row_active_height - AETHER_LIST_METRICS.adjustor_row_height + preset_height)

  def _set_active_state(self, active: bool) -> None:
    if self._set_active is not None:
      self._set_active(active)

  def _handle_mouse_press(self, mouse_pos: MousePos):
    if not self._touch_valid() or not rl.check_collision_point_rec(mouse_pos, self._rect):
      return
    self._pressed_zone = None

    if self._active():
      for preset_value, preset_rect in self._preset_rects:
        if rl.check_collision_point_rec(mouse_pos, _inflate_rect(preset_rect, 4, 4)):
          self._pressed_zone = f"preset:{preset_value}"
          return
      if rl.check_collision_point_rec(mouse_pos, self._scrubber_rect):
        self._pressed_zone = "scrubber"
        return

    if rl.check_collision_point_rec(mouse_pos, self._header_rect):
      self._pressed_zone = "header"

  def _handle_mouse_release(self, mouse_pos: MousePos):
    pressed_zone = self._pressed_zone
    self._pressed_zone = None

    if not self._touch_valid():
      return

    if pressed_zone == "scrubber":
      return

    if pressed_zone and pressed_zone.startswith("preset:"):
      self._scrubber._value_at_press = self._scrubber.current_val
      try:
        preset_value = float(pressed_zone.split(":", 1)[1])
      except ValueError:
        return
      for value, preset_rect in self._preset_rects:
        if value == preset_value and rl.check_collision_point_rec(mouse_pos, _inflate_rect(preset_rect, 4, 4)):
          self._scrubber.set_value(preset_value)
          self._scrubber._on_change(self._scrubber.current_val)
          self._scrubber._commit_if_needed()
          self._preset_applied = True
          return
      return

    if pressed_zone == "header":
      active = self._active()
      if rl.check_collision_point_rec(mouse_pos, _inflate_rect(self._header_rect, 6, 4)):
        self._set_active_state(not active)

  def _handle_mouse_event(self, mouse_event: MouseEvent):
    pass

  def _render_preset_chip(self, rect: rl.Rectangle, text: str, *, current: bool, pressed: bool):
    fill = rl.Color(255, 255, 255, 5)
    border = rl.Color(255, 255, 255, 14)
    text_color = self._style.subtitle_color
    if current:
      fill = mix_colors(rl.Color(18, 22, 28, 255), self._color, 0.22, alpha=255)
      border = with_alpha(self._color, 72)
      text_color = self._style.title_color
    elif pressed:
      fill = rl.Color(255, 255, 255, 10)
      border = rl.Color(255, 255, 255, 22)

    draw_rounded_fill(rect, fill, radius_px=13)
    draw_rounded_stroke(rect, border, radius_px=13)
    draw_text_fit_common(
      gui_app.font(FontWeight.MEDIUM),
      text,
      rl.Vector2(rect.x + 10, rect.y + 7),
      max(1.0, rect.width - 20),
      16,
      align_center=True,
      color=text_color,
    )

  def _render(self, rect: rl.Rectangle):
    rect = snap_rect(rect)
    self.set_rect(rect)
    active = self._active()
    if not self._scrubber.is_interacting:
      self._scrubber.set_value(self._get_value())

    dt = rl.get_frame_time()
    focus_target = 1.0 if active else 0.0
    self._focus_progress += (focus_target - self._focus_progress) * (1 - math.exp(-dt / 0.09))

    hovered = point_hits(gui_app.last_mouse_event.pos, rect, self._parent_rect, pad_x=6, pad_y=0)
    current_bg = with_alpha(mix_colors(rl.Color(18, 22, 28, 255), self._color, 0.16), int(18 + self._focus_progress * 14))
    current_border = with_alpha(self._color, int(34 + self._focus_progress * 34))
    draw_list_row_shell(
      rect,
      current=active or self._focus_progress > 0.02,
      hovered=hovered and not self.is_interacting,
      pressed=self._pressed_zone == "header",
      is_last=self._is_last,
      row_bg=rl.Color(255, 255, 255, 0),
      row_border=rl.Color(255, 255, 255, 0),
      row_separator=self._style.divider_color,
      current_bg=current_bg,
      current_border=current_border,
    )

    if self._status is not None:
      status = self._status() if callable(self._status) else self._status
      header = rl.Rectangle(rect.x, rect.y, rect.width, min(rect.height, AS.SETTINGS_ROW_CARD_HEIGHT))
      self._header_rect = self._progress_bar_rect = header
      draw_status_value_row(header, title=self._title, value=self.formatted_value(), status=status, style=self._style)
      if not active:
        return
      content_left = rect.x + AS.SETTINGS_CARD_INSET
      bar_width = max(120.0, rect.width - AS.SETTINGS_CARD_INSET * 2)
    else:
      self._render_level_header(rect)
      content_left = self._progress_bar_rect.x
      bar_width = self._progress_bar_rect.width

    if not active:
      return

    tray_top = self._progress_bar_rect.y + self._progress_bar_rect.height + 10
    current_y = tray_top
    self._preset_rects.clear()

    if self._presets:
      chip_gap = 12.0
      chip_h = float(AETHER_LIST_METRICS.adjustor_preset_height)
      chip_w = max(68.0, (bar_width - chip_gap * (len(self._presets) - 1)) / max(1, len(self._presets)))
      chip_x = content_left
      for preset_value in self._presets:
        chip_rect = snap_rect(rl.Rectangle(chip_x, current_y, chip_w, chip_h))
        self._preset_rects.append((preset_value, chip_rect))
        self._render_preset_chip(
          chip_rect,
          format_adjustor_value(preset_value, step=self._step, unit=self._unit, labels=self._labels),
          current=abs(self._current_value() - preset_value) <= max(abs(self._step) * 0.5, 1e-4),
          pressed=self._pressed_zone == f"preset:{preset_value}",
        )
        chip_x += chip_w + chip_gap
      current_y += chip_h + AETHER_LIST_METRICS.adjustor_preset_gap

    self._scrubber_rect = snap_rect(rl.Rectangle(content_left, current_y, bar_width, AETHER_LIST_METRICS.adjustor_scrubber_height))
    self._scrubber.set_parent_rect(self._parent_rect)
    self._scrubber.render(self._scrubber_rect)

  def _render_level_header(self, rect: rl.Rectangle) -> None:
    bar_h = max(74, min(94, int(rect.height * 0.87)))
    title_fs = max(38, int(bar_h * 0.53))
    value_fs = max(28, int(bar_h * 0.38))

    content_left = rect.x + AS.SETTINGS_CARD_INSET
    bar_width = max(120.0, rect.width - AS.SETTINGS_CARD_INSET * 2)
    bar_y = rect.y + (rect.height - bar_h) / 2
    bar_rect = snap_rect(rl.Rectangle(content_left, bar_y, bar_width, bar_h))
    self._progress_bar_rect = bar_rect
    self._header_rect = bar_rect

    # Aether Cards: a plain row in its group; the level is a thin line along the bottom (drag the row to change it).
    level_h = 5
    track = snap_rect(rl.Rectangle(bar_rect.x, rect.y + rect.height - level_h - 9, bar_rect.width, level_h))
    fill_frac = self._scrubber._value_fraction(self._current_value())
    if fill_frac > 0 or self._active():  # nothing at zero, so an "Off" row reads as a plain row
      aether_fill(track, rl.Color(255, 255, 255, 22), level_h / 2, segments=12)
    if fill_frac > 0:
      fill_rect = snap_rect(rl.Rectangle(track.x, track.y, max(level_h, track.width * fill_frac), level_h))
      fill_alpha = 255 if self._pressed_zone == "header" else (235 if self._active() else 200)
      aether_fill(fill_rect, with_alpha(self._color, fill_alpha), level_h / 2, segments=12)

    title_y = bar_rect.y + (bar_h - title_fs * FONT_SCALE) / 2
    rl.draw_text_ex(self._font_title, self._title,
                    rl.Vector2(bar_rect.x, title_y),
                    title_fs, 0, self._style.title_color)

    value_str = self.formatted_value()
    value_w = measure_text_cached(self._font_value, value_str, value_fs).x
    rl.draw_text_ex(self._font_value, value_str,
                    rl.Vector2(bar_rect.x + bar_rect.width - value_w,
                               bar_rect.y + (bar_h - value_fs * FONT_SCALE) / 2),
                    value_fs, 0, self._style.title_color)

    if self._subtitle:
      sub_fs = 26
      sub_y = bar_rect.y - sub_fs - 4
      gui_label(rl.Rectangle(content_left, sub_y, bar_width, sub_fs),
                self._subtitle, sub_fs, self._style.subtitle_color, FontWeight.NORMAL)


def draw_selection_list_row(
  rect: rl.Rectangle,
  *,
  title: str,
  subtitle: str = "",
  action_text: str = "",
  current: bool = False,
  hovered: bool = False,
  pressed: bool = False,
  is_last: bool = False,
  alpha: int = 255,
  action_width: int = AETHER_LIST_METRICS.action_width,
  action_chip: bool = False,
  action_pill: bool = False,
  title_size: int = 36,
  subtitle_size: int = 26,
  action_text_size: int = 26,
  action_pill_height: int = 64,
  action_pill_width: float | None = None,
  title_color: rl.Color = AetherListColors.HEADER,
  subtitle_color: rl.Color = AetherListColors.SUBTEXT,
  action_fill: rl.Color = AetherListColors.CURRENT_BG,
  action_border: rl.Color = AetherListColors.CURRENT_BORDER,
  action_text_color: rl.Color = AetherListColors.HEADER,
  row_bg: rl.Color = AetherListColors.ROW_BG,
  row_border: rl.Color = AetherListColors.ROW_BORDER,
  row_separator: rl.Color = AetherListColors.ROW_SEPARATOR,
  row_hover: rl.Color = AetherListColors.ROW_HOVER,
  current_bg: rl.Color = AetherListColors.CURRENT_BG,
  current_border: rl.Color = AetherListColors.CURRENT_BORDER,
  card: bool = False,
):
  if card:
    return draw_settings_card_row(
      row_card_rect(rect), title=title, subtitle=subtitle, action_text=action_text, current=current,
      hovered=hovered, pressed=pressed, title_size=title_size, subtitle_size=subtitle_size,
      title_color=title_color, subtitle_color=subtitle_color, action_fill=action_fill,
      action_border=action_border, action_text_color=action_text_color,
      action_text_size=action_text_size, action_height=action_pill_height, alpha=alpha, show_chevron=False,
    )
  draw_rect = snap_rect(rect)
  draw_list_row_shell(
    draw_rect,
    card=card,
    current=current,
    hovered=hovered,
    pressed=pressed,
    is_last=is_last,
    alpha=alpha,
    row_bg=row_bg,
    row_border=row_border,
    row_separator=row_separator,
    row_hover=row_hover,
    current_bg=current_bg,
    current_border=current_border,
  )
  action_rect = rl.Rectangle(draw_rect.x + draw_rect.width - action_width, draw_rect.y, action_width, draw_rect.height)
  if not action_pill:
    action_rect = draw_action_rail(draw_rect, action_width, current=current, alpha=alpha)

  info_gap = 36 if action_pill else 42
  info_rect = rl.Rectangle(draw_rect.x + 24, draw_rect.y + 16, max(0.0, draw_rect.width - action_width - info_gap), draw_rect.height - 32)
  title_font = gui_app.font(FontWeight.SEMI_BOLD)
  subtitle_font = gui_app.font(FontWeight.NORMAL)

  if subtitle:
    text_height = (title_size + subtitle_size) * FONT_SCALE + 8
    title_y = info_rect.y + (info_rect.height - text_height) / 2
    subtitle_y = title_y + title_size * FONT_SCALE + 8
  else:
    title_y = info_rect.y + (info_rect.height - title_size * FONT_SCALE) / 2
    subtitle_y = title_y

  draw_text_fit_common(
    title_font,
    title,
    rl.Vector2(info_rect.x, title_y),
    info_rect.width,
    title_size,
    color=with_alpha(title_color, alpha),
  )

  if subtitle:
    draw_text_fit_common(
      subtitle_font,
      subtitle,
      rl.Vector2(info_rect.x, subtitle_y),
      info_rect.width,
      subtitle_size,
      color=with_alpha(subtitle_color, alpha),
    )

  if action_text:
    if action_pill:
      available_w = max(96.0, action_rect.width - 28)
      pill_width = action_pill_width
      if pill_width is None:
        pill_width = max(96.0, math.ceil(measure_text_cached(title_font, action_text, action_text_size).x) + 24)
      chip_w = min(available_w, pill_width)
      chip_h = min(float(action_pill_height), max(36.0, action_rect.height - 28))
      chip_rect = rl.Rectangle(action_rect.x + action_rect.width - chip_w - 18, action_rect.y + (action_rect.height - chip_h) / 2, chip_w, chip_h)
      draw_action_pill(
        chip_rect,
        action_text,
        with_alpha(action_fill, alpha),
        with_alpha(action_border, alpha),
        with_alpha(action_text_color, alpha),
        font_size=action_text_size,
      )
      return chip_rect
    if action_chip:
      available_w = max(74.0, action_rect.width - 24)
      chip_w = min(available_w, max(74.0, 44 + len(action_text) * 9))
      chip_rect = rl.Rectangle(action_rect.x + (action_rect.width - chip_w) / 2, action_rect.y + (action_rect.height - 40) / 2, chip_w, 40)
      AetherChip(
        action_text,
        with_alpha(action_fill, alpha),
        with_alpha(action_border, alpha),
        with_alpha(action_text_color, alpha),
        pill=True,
      ).render(chip_rect)
    else:
      draw_text_fit_common(
        title_font,
        action_text,
        rl.Vector2(action_rect.x + 16, action_rect.y + (action_rect.height - 18) / 2),
        max(1.0, action_rect.width - 32),
        action_text_size,
        align_center=True,
        color=with_alpha(action_text_color, alpha),
      )

  return action_rect


def draw_status_led(center: rl.Vector2, enabled: bool):
  if enabled:
    led_color = rl.Color(110, 175, 245, 255)
    rl.draw_circle(int(center.x), int(center.y), 16, rl.Color(110, 175, 245, 24))
    rl.draw_circle(int(center.x), int(center.y), 9, led_color)
  else:
    rl.draw_circle(int(center.x), int(center.y), 10, rl.Color(14, 16, 22, 255))
    rl.draw_ring(center, 7, 9, 0, 360, 24, rl.Color(70, 78, 95, 140))


def draw_overflow_dots(center: rl.Vector2, color: rl.Color):
  dot_r = 6
  gap = 17
  for i in range(3):
    rl.draw_circle(int(center.x + (i - 1) * gap), int(center.y), dot_r, color)



def draw_heart_icon(center: rl.Vector2, color: rl.Color):
  rl.draw_circle(int(center.x - 5), int(center.y - 3), 10, color)
  rl.draw_circle(int(center.x + 5), int(center.y - 3), 10, color)
  rl.draw_triangle(
    rl.Vector2(center.x + 13, center.y + 1),
    rl.Vector2(center.x - 13, center.y + 1),
    rl.Vector2(center.x, center.y + 13),
    color,
  )


def draw_download_icon(center: rl.Vector2, color: rl.Color):
  shaft_top = rl.Vector2(center.x, center.y - 18)
  shaft_bottom = rl.Vector2(center.x, center.y + 8)
  left_head = rl.Vector2(center.x - 11, center.y - 2)
  right_head = rl.Vector2(center.x + 11, center.y - 2)
  tray_left = rl.Vector2(center.x - 14, center.y + 18)
  tray_right = rl.Vector2(center.x + 14, center.y + 18)
  rl.draw_line_ex(shaft_top, shaft_bottom, 6, color)
  rl.draw_line_ex(left_head, shaft_bottom, 6, color)
  rl.draw_line_ex(right_head, shaft_bottom, 6, color)
  rl.draw_line_ex(tray_left, tray_right, 6, color)


class AetherButton(Widget):
  """Shared pill action, with an optional confirmation before its callback runs."""

  def __init__(
    self,
    text: str | Callable[[], str],
    click_callback: Callable[[], None] | None = None,
    enabled: bool | Callable[[], bool] = True,
    emphasized: bool = False,
    font_size: int = 34,
    accent_color: rl.Color | None = None,
    confirmation: str | Callable[[], str] = "",
    confirm_label: str | Callable[[], str] | None = None,
    neutral: bool = False,
  ):
    super().__init__()
    self._text = text
    self._emphasized = emphasized
    self._font_size = font_size
    self._accent_color = accent_color
    self._action_callback = click_callback
    self._confirmation = confirmation
    self._confirm_label = confirm_label
    self._neutral = neutral
    self.set_click_callback(self._activate)
    self.set_enabled(enabled)

  def measure_width(self) -> float:
    text_width = measure_text_cached(gui_app.font(FontWeight.SEMI_BOLD), self.text, self._font_size).x
    return max(float(AS.MIN_TOUCH), text_width + AS.SETTINGS_CARD_INSET * 2)

  def measure_height(self) -> float:
    return float(AS.MIN_TOUCH)

  def _activate(self) -> None:
    if not self.enabled or self._action_callback is None:
      return
    confirmation = str(_resolve_value(self._confirmation, ""))
    if not confirmation:
      self._action_callback()
      return
    from openpilot.system.ui.widgets.confirm_dialog import ConfirmDialog

    def on_result(result: DialogResult):
      if result == DialogResult.CONFIRM and self.enabled:
        self._action_callback()

    confirm_label = str(_resolve_value(self._confirm_label, self.text))
    gui_app.push_widget(ConfirmDialog(confirmation, confirm_label, callback=on_result))

  @property
  def text(self) -> str:
    return str(_resolve_value(self._text, ""))

  def set_text(self, text: str | Callable[[], str]):
    self._text = text

  def set_emphasized(self, emphasized: bool):
    self._emphasized = emphasized

  def _render(self, rect: rl.Rectangle):
    enabled = self.enabled
    hovered = enabled and rl.check_collision_point_rec(gui_app.last_mouse_event.pos, rect)
    pressed = enabled and self.is_pressed

    if self._emphasized:
      accent = self._accent_color or AetherListColors.PRIMARY
      bg = accent if enabled else rl.Color(accent.r, accent.g, accent.b, 80)
      border = with_alpha(accent, 190 if enabled else 70)
      if hovered:
        bg = rl.Color(min(bg.r + 10, 255), min(bg.g + 10, 255), min(bg.b + 10, 255), bg.a)
      if pressed:
        bg = rl.Color(max(bg.r - 8, 0), max(bg.g - 8, 0), max(bg.b - 8, 0), bg.a)
    elif self._neutral:
      bg = with_alpha(AS.TRACK_OFF, 100 if pressed else 40 if hovered else 0)
      border = AS.SETTINGS_CARD_BORDER_PRESSED if pressed else AS.SETTINGS_TILE_BORDER
    else:
      bg = with_alpha(AS.ACCENT, 100 if pressed else 70 if hovered else 51) if enabled else with_alpha(AS.TRACK_OFF, 100)
      border = AS.SETTINGS_CARD_BORDER_PRESSED if pressed else AS.ACCENT_EDGE if enabled else AS.SETTINGS_CARD_BORDER_IDLE

    draw_action_pill(rect, self.text, bg, border, AetherListColors.HEADER if enabled else AetherListColors.MUTED,
                     font_size=self._font_size, padding_x=AS.SETTINGS_CARD_INSET / 2)


class AetherChip:
  def __init__(self, text: str | Callable[[], str], fill: rl.Color, border: rl.Color, text_color: rl.Color, pill: bool = False, font_size: int = 26):
    self._text = text
    self._fill = fill
    self._border = border
    self._text_color = text_color
    self._pill = pill
    self._font_size = font_size

  @property
  def text(self) -> str:
    return str(_resolve_value(self._text, ""))

  def render(self, rect: rl.Rectangle):
    roundness = 1.0 if self._pill else 0.4
    rl.draw_rectangle_rounded(rect, roundness, 18, self._fill)
    rl.draw_rectangle_rounded_lines_ex(rect, roundness, 18, 1, with_alpha(self._border, 110))
    draw_text_fit_common(
      gui_app.font(FontWeight.MEDIUM),
      self.text,
      rl.Vector2(rect.x + 12, rect.y + (rect.height - self._font_size * FONT_SCALE) / 2),
      max(1.0, rect.width - 24),
      self._font_size,
      align_center=True,
      color=self._text_color,
    )


class AetherScrollbar:
  def __init__(
    self,
    track_color: rl.Color = AetherListColors.SCROLL_TRACK,
    thumb_color: rl.Color = AetherListColors.SCROLL_THUMB,
    track_width: int = 4,
    track_inset_x: int = -AS.SETTINGS_SCROLLBAR_GAP,
    track_inset_y: int = 8,
    min_thumb_height: float = 67.0,
  ):
    self._track_color = track_color
    self._thumb_color = thumb_color
    self._track_width = track_width
    self._track_inset_x = track_inset_x
    self._track_inset_y = track_inset_y
    self._min_thumb_height = min_thumb_height

  def render(self, rect: rl.Rectangle, content_height: float, scroll_offset: float):
    if content_height <= 0 or content_height <= rect.height:
      return

    track_rect = rl.Rectangle(rect.x + rect.width - self._track_inset_x, rect.y + self._track_inset_y, self._track_width, rect.height - self._track_inset_y * 2)
    rl.draw_rectangle_rounded(track_rect, 1.0, 12, self._track_color)

    max_scroll = max(content_height - rect.height, 1.0)
    thumb_height = max(self._min_thumb_height, track_rect.height * (rect.height / content_height))
    thumb_range = max(track_rect.height - thumb_height, 0.0)
    thumb_y = track_rect.y + (-scroll_offset / max_scroll) * thumb_range
    thumb_rect = rl.Rectangle(track_rect.x, thumb_y, track_rect.width, thumb_height)
    rl.draw_rectangle_rounded(thumb_rect, 1.0, 12, self._thumb_color)


# ── SettingRow / SettingSection dataclasses ──

SECTION_GAP = AETHER_LIST_METRICS.section_gap
SECTION_HEADER_HEIGHT = AETHER_LIST_METRICS.section_header_height
SECTION_HEADER_GAP = AETHER_LIST_METRICS.section_header_gap
ROW_HEIGHT = AETHER_LIST_METRICS.row_height


@dataclass
class SettingRow:
  id: str
  type: str
  title: str
  subtitle: str = ""
  visible: Callable[[], bool] | None = None
  enabled: Callable[[], bool] | None = None
  disabled_label: str = ""
  get_state: Callable[[], bool] | None = None
  set_state: Callable[[bool], None] | None = None
  get_value: Callable[[], str] | None = None
  on_click: Callable[[], object] | None = None
  action_text: str = ""
  action_danger: bool = False
  navigate_to: str = ""


@dataclass
class SettingSection:
  title: str
  rows: list[SettingRow]
  visible: Callable[[], bool] | None = None
  tab_key: str = ""
  column_pair: str = ""
  row_height: int = ROW_HEIGHT


@dataclass
class ParentToggle:
  label: str
  get_state: Callable[[], bool]
  set_state: Callable[[bool], None]
  subtitle: str = ""


# ── AetherSettingsView — reusable list-panel ManagerView ──

class AetherSettingsView(PanelManagerView):
  """Reusable list-panel manager for toggle/value/action settings pages."""

  TAB_HEIGHT = 98
  TAB_GAP = 14
  TAB_BOTTOM_GAP = 26
  COLUMN_GAP = AS.SETTINGS_ROW_GAP
  TWO_COLUMN_BREAKPOINT = 1180
  AUTO_TWO_COLUMN_MIN_ROWS = 4   # a single long section flows into two columns of cards

  def __init__(self, controller, sections: list[SettingSection],
               *, header_title: str = "", header_subtitle: str = "",
               parent_toggle: ParentToggle | None = None,
               tab_defs: list[dict] | None = None,
               panel_style=None, fade_height: float = AETHER_LIST_METRICS.fade_height,
               metrics = COMPACT_PANEL_METRICS):
    super().__init__()
    self._panel_style = panel_style or DEFAULT_PANEL_STYLE
    self._fade_height = fade_height
    self._metrics = metrics
    self._controller = controller
    self._sections = sections
    self._header_title = header_title
    self._header_subtitle = header_subtitle
    self._parent_toggle = parent_toggle
    # Aether Cards: the page title is drawn by the settings header bar, so only a parent toggle needs space here.
    self._has_header = parent_toggle is not None
    self._tab_defs = tab_defs
    self._active_tab_key = tab_defs[0]["id"] if tab_defs else ""

  def use_page_header(self) -> ParentToggle | None:
    """Let the enclosing page header own the master switch, without a duplicate row."""
    self._has_header = False
    return self._parent_toggle

  def setting_details(self, key: str) -> tuple[str, str] | None:
    """Reuse a setting's user-facing copy in its picker."""
    for section in self._sections:
      for row in section.rows:
        if row.id == key:
          return row.title, row.subtitle
    return None

  def _find_row(self, target_id: str) -> SettingRow | None:
    for section in self._active_sections():
      for row in section.rows:
        if f"{row.type}:{row.id}" == target_id:
          return row
    return None

  def _target_at(self, mouse_pos: MousePos) -> str | None:
    if self._parent_toggle:
      mid = f"parent_toggle:{self._parent_toggle.label}"
      rect = self._interactive_rects.get(mid)
      if rect and point_hits(mouse_pos, rect, None, pad_x=0, pad_y=0):
        return mid
    return super()._target_at(mouse_pos)

  def _activate_target(self, target_id: str | None):
    if not target_id:
      return
    if target_id.startswith("parent_toggle:") and self._parent_toggle:
      self._parent_toggle.set_state(not self._parent_toggle.get_state())
      return
    if target_id.startswith("tab:") and self._tab_defs:
      self._active_tab_key = target_id[4:]
      self.reset_scroll()
      return
    row = self._find_row(target_id)
    if row is None:
      return
    if row.enabled is not None and not row.enabled():
      return
    if row.navigate_to:
      self._controller._navigate_to(row.navigate_to)
    elif row.on_click:
      row.on_click()
    elif row.type == "toggle" and row.set_state and row.get_state:
      row.set_state(not row.get_state())

  def _header_text(self) -> tuple[str, str]:
    title, subtitle = self._header_title, self._header_subtitle
    if self._parent_toggle:
      title = title or self._parent_toggle.label
      subtitle = subtitle or self._parent_toggle.subtitle
    return tr(title), tr(subtitle) if subtitle else ""

  def _header_text_width(self, width: float) -> float:
    right_inset = SPACING.xl
    if self._parent_toggle:
      right_inset = AETHER_LIST_METRICS.toggle_width + AETHER_LIST_METRICS.toggle_right_inset + SPACING.lg
    return max(100.0, width - SPACING.xl - right_inset)

  def _compute_header_height(self, content_width: float) -> float:
    if not self._has_header:
      return 0.0
    if self._parent_toggle:
      return float(ROW_HEIGHT)
    _, subtitle = self._header_text()
    _, _, _, height = _settings_panel_header_layout(
      self._header_text_width(content_width + AETHER_LIST_METRICS.content_right_gutter), subtitle,
      PANEL_HEADER_TITLE_FONT_SIZE, PANEL_HEADER_SUBTITLE_FONT_SIZE,
      min_title_height=AETHER_LIST_METRICS.toggle_height if self._parent_toggle else 0.0,
    )
    return height + SECTION_GAP

  def _render(self, rect: rl.Rectangle):
    self.set_rect(rect)
    self._interactive_rects.clear()
    self._interactive_viewports.clear()

    shell_w = min(rect.width - self._metrics.outer_margin_x * 2, self._metrics.max_content_width)
    content_width = shell_w - self._metrics.panel_padding_x * 2 - AETHER_LIST_METRICS.content_right_gutter

    header_h = self._compute_header_height(content_width)
    metrics = replace(self._metrics, header_height=header_h) if header_h > 0 else self._metrics
    frame, scroll_rect, content_width = init_list_panel(rect, self._panel_style, metrics=metrics)
    self._scroll_rect = scroll_rect

    if self._has_header:
      self._draw_header(frame.header)

    self._content_height = self._measure_content_height(content_width)
    if self._tab_defs and self._build_scroll_columns(content_width):
      end = self._draw_tabs(scroll_rect.y, scroll_rect.x, content_width)
      scroll_rect.height = max(0.0, scroll_rect.height - (end - scroll_rect.y))
      scroll_rect.y = end
    self._render_scroll_area(scroll_rect, content_width, fade_height=self._fade_height)

  def _draw_header(self, rect: rl.Rectangle):
    if self._parent_toggle:
      # The section's master switch, drawn as the first row card.
      toggle = self._parent_toggle
      toggle_id = f"parent_toggle:{toggle.label}"
      row_rect = rl.Rectangle(rect.x, rect.y, rect.width, ROW_HEIGHT)
      self._interactive_rects[toggle_id] = row_card_rect(row_rect)
      hovered, pressed = self._interactive_state(toggle_id, row_rect)
      draw_settings_list_row(row_rect, title=tr(toggle.label), subtitle=tr(toggle.subtitle) if toggle.subtitle else "",
                             toggle_value=toggle.get_state(), hovered=hovered, pressed=pressed, style=self._panel_style, card=True)
      return
    title, subtitle = self._header_text()
    text_rect = rl.Rectangle(rect.x + SPACING.xl, rect.y, self._header_text_width(rect.width), rect.height)
    draw_settings_panel_header(
      text_rect, title, subtitle, max_title_width=1.0, max_subtitle_width=1.0,
      min_title_height=AETHER_LIST_METRICS.toggle_height if self._parent_toggle else 0.0,
    )

    if self._parent_toggle:
      toggle = self._parent_toggle
      toggle_id = f"parent_toggle:{toggle.label}"
      th = AETHER_LIST_METRICS.toggle_height
      self._interactive_rects[toggle_id] = rl.Rectangle(rect.x, rect.y, rect.width, rect.height - SECTION_GAP)

      toggle_value = toggle.get_state()

      draw_toggle_switch(
        rl.Rectangle(rect.x, rect.y, rect.width, th),
        toggle_value,
        knob_progress=1.0 if toggle_value else 0.0,
        track_color=self._panel_style.accent,
        seed_id=toggle_id,
        radius_px=100,
        bg_color=rl.Color(12, 10, 18, 255),
      )

  def _active_sections(self) -> list[SettingSection]:
    if self._tab_defs and self._active_tab_key:
      return [s for s in self._sections if s.tab_key == self._active_tab_key]
    return self._sections

  def _visible_rows(self, section: SettingSection) -> list[SettingRow]:
    if section.visible is not None and not section.visible():
      return []
    return [row for row in section.rows if row.visible is None or row.visible()]

  def _measure_content_height(self, width: float) -> float:
    total = 0.0
    if self._tab_defs:
      total += self.TAB_HEIGHT + self.TAB_BOTTOM_GAP
    active = self._active_sections()
    i = 0
    while i < len(active):
      section = active[i]
      visible_rows = self._visible_rows(section)
      if not visible_rows:
        i += 1
        continue
      row_h = self._section_rows_height(section, visible_rows, width)
      if section.column_pair and i + 1 < len(active) and active[i + 1].column_pair == section.column_pair and self._uses_two_columns(width):
        right_rows = self._visible_rows(active[i + 1])
        row_h = max(row_h, len(right_rows) * active[i + 1].row_height)
        i += 2
        total += SECTION_HEADER_HEIGHT + SECTION_HEADER_GAP
        total += row_h
        total += SECTION_GAP
      else:
        i += 1
        total += SECTION_HEADER_HEIGHT + SECTION_HEADER_GAP if section.title else 0.0
        total += row_h
        total += SECTION_GAP
    return max(0.0, total - SECTION_GAP) if total > 0 else 0.0

  def _draw_tabs(self, y: float, x: float, width: float) -> float:
    return draw_tab_bar(
      rl.Rectangle(x, y, width, self.TAB_HEIGHT),
      self._tab_defs, self._active_tab_key, self._interactive_state,
      style=self._panel_style,
    )

  def _uses_two_columns(self, width: float) -> bool:
    return width >= self.TWO_COLUMN_BREAKPOINT

  def _build_scroll_columns(self, width: float) -> list[SettingsColumn]:
    active = [(section, self._visible_rows(section)) for section in self._active_sections()]
    active = [(section, rows) for section, rows in active if rows]
    if not self._uses_two_columns(width) or not any(section.column_pair or len(rows) >= self.AUTO_TWO_COLUMN_MIN_ROWS
                                                   for section, rows in active):
      return []
    blocks = [[], []]
    heights = [0.0, 0.0]

    def append(index, section, rows, reserve_heading=False):
      if blocks[index]:
        heights[index] += SECTION_GAP
      heading = SECTION_HEADER_HEIGHT + SECTION_HEADER_GAP if section.title or reserve_heading else 0
      heights[index] += heading + len(rows) * section.row_height
      blocks[index].append((section, rows, heading))

    i = 0
    while i < len(active):
      section, rows = active[i]
      if section.column_pair and i + 1 < len(active) and active[i + 1][0].column_pair == section.column_pair:
        append(0, section, rows)
        append(1, *active[i + 1])
        i += 2
      elif len(rows) >= self.AUTO_TWO_COLUMN_MIN_ROWS:
        append(0, section, rows[::2])
        append(1, replace(section, title=""), rows[1::2], reserve_heading=bool(section.title))
        i += 1
      else:
        append(0 if heights[0] <= heights[1] else 1, section, rows)
        i += 1

    def draw(index, rect):
      y = rect.y
      for section, rows, heading in blocks[index]:
        if section.title:
          draw_section_header(rl.Rectangle(rect.x + AS.SETTINGS_CARD_INSET, y, rect.width - AS.SETTINGS_CARD_INSET * 2,
                                            SECTION_HEADER_HEIGHT), tr(section.title), style=self._panel_style)
        y += heading
        for j, row in enumerate(rows):
          self._draw_row(rl.Rectangle(rect.x, y, rect.width, section.row_height), row, j == len(rows) - 1)
          y += section.row_height
        y += SECTION_GAP

    return [SettingsColumn("left", heights[0], lambda rect: draw(0, rect)),
            SettingsColumn("right", heights[1], lambda rect: draw(1, rect))]

  def _has_subsequent_visible(self, start_idx: int, sections: list[SettingSection]) -> bool:
    for j in range(start_idx, len(sections)):
      if self._visible_rows(sections[j]):
        return True
    return False

  def _draw_scroll_content(self, rect: rl.Rectangle, width: float):
    y = rect.y + self._scroll_offset
    
    if self._tab_defs:
      y = self._draw_tabs(y, rect.x, width)
    active = self._active_sections()
    has_visible = any(self._visible_rows(s) for s in active)
    if not has_visible:
      if self._parent_toggle and not self._parent_toggle.get_state():
        draw_empty_state_card(
          rl.Rectangle(rect.x, y, width, rect.height - (y - rect.y)),
          tr("Enable {} to configure settings.").format(tr(self._parent_toggle.label)),
          "",
          style=self._panel_style,
        )
      elif not self._parent_toggle:
        draw_empty_state_card(
          rl.Rectangle(rect.x, y, width, rect.height - (y - rect.y)),
          tr("No settings to display"),
          tr("All options in this panel are hidden or unavailable."),
          style=self._panel_style,
        )
      return
    i = 0
    while i < len(active):
      section = active[i]
      visible_rows = self._visible_rows(section)
      if not visible_rows:
        i += 1
        continue
      if section.column_pair and i + 1 < len(active) and active[i + 1].column_pair == section.column_pair and self._uses_two_columns(width):
        right_section = active[i + 1]
        right_rows = self._visible_rows(right_section)
        col_w = (width - self.COLUMN_GAP) / 2
        section_h = len(visible_rows) * section.row_height
        right_h = len(right_rows) * right_section.row_height

        draw_section_header(
          rl.Rectangle(rect.x + AS.SETTINGS_CARD_INSET, y, col_w - AS.SETTINGS_CARD_INSET * 2, SECTION_HEADER_HEIGHT),
          tr(section.title), style=self._panel_style,
        )
        draw_section_header(
          rl.Rectangle(rect.x + col_w + self.COLUMN_GAP + AS.SETTINGS_CARD_INSET, y, col_w - AS.SETTINGS_CARD_INSET * 2, SECTION_HEADER_HEIGHT),
          tr(right_section.title), style=self._panel_style,
        )
        y += SECTION_HEADER_HEIGHT + SECTION_HEADER_GAP

        for j, row in enumerate(visible_rows):
          row_rect = rl.Rectangle(rect.x, y + j * section.row_height, col_w, section.row_height)
          self._draw_row(row_rect, row, is_last=(j == len(visible_rows) - 1))
        for j, row in enumerate(right_rows):
          row_rect = rl.Rectangle(rect.x + col_w + self.COLUMN_GAP, y + j * right_section.row_height, col_w, right_section.row_height)
          self._draw_row(row_rect, row, is_last=(j == len(right_rows) - 1))
        y += max(section_h, right_h) + SECTION_GAP
        i += 2
      else:
        y = self._draw_section(y, rect.x, width, section, visible_rows)
        y += SECTION_GAP
        i += 1

  def _auto_two_columns(self, section: SettingSection, rows: list[SettingRow], width: float) -> bool:
    return not section.column_pair and len(rows) >= self.AUTO_TWO_COLUMN_MIN_ROWS and self._uses_two_columns(width)

  def _section_rows_height(self, section: SettingSection, rows: list[SettingRow], width: float) -> float:
    count = math.ceil(len(rows) / 2) if self._auto_two_columns(section, rows, width) else len(rows)
    return count * section.row_height

  def _draw_section(self, y: float, x: float, width: float,
                    section: SettingSection, rows: list[SettingRow]) -> float:
    if section.title:
      draw_section_header(
        rl.Rectangle(x + AS.SETTINGS_CARD_INSET, y, width - AS.SETTINGS_CARD_INSET * 2, SECTION_HEADER_HEIGHT),
        tr(section.title),
        style=self._panel_style,
      )
      y += SECTION_HEADER_HEIGHT + SECTION_HEADER_GAP

    if self._auto_two_columns(section, rows, width):
      col_w = (width - self.COLUMN_GAP) / 2
      for i, row in enumerate(rows):
        row_rect = rl.Rectangle(x + (i % 2) * (col_w + self.COLUMN_GAP), y + (i // 2) * section.row_height, col_w, section.row_height)
        self._draw_row(row_rect, row, is_last=i >= len(rows) - 2)
      return y + self._section_rows_height(section, rows, width)

    group_rect = rl.Rectangle(x, y, width, len(rows) * section.row_height)

    for i, row in enumerate(rows):
      row_rect = rl.Rectangle(x, y + i * section.row_height, width, section.row_height)
      self._draw_row(row_rect, row, is_last=(i == len(rows) - 1))

    return y + group_rect.height

  def _draw_row(self, rect: rl.Rectangle, row: SettingRow, is_last: bool):
    target_id = f"{row.type}:{row.id}"
    hovered, pressed = self._interactive_state(target_id, row_card_rect(rect))

    enabled = row.enabled() if row.enabled is not None else True
    subtitle = row.disabled_label if not enabled and row.disabled_label else row.subtitle

    if row.type == "toggle":
      toggle_value = row.get_state() if row.get_state else False
      draw_standard_toggle_row(
        rect, tr(row.title), tr(subtitle), toggle_value,
        enabled=enabled, hovered=hovered, pressed=pressed,
        is_last=is_last, style=self._panel_style, card=True,
      )
    elif row.type == "value":
      value_text = row.get_value() if row.get_value else ""
      draw_settings_list_row(
        rect,
        title=tr(row.title),
        subtitle=tr(subtitle),
        value=value_text,
        enabled=enabled,
        hovered=hovered,
        pressed=pressed,
        is_last=is_last,
        show_chevron=row.on_click is not None,
        style=self._panel_style,
        card=True,
      )
    elif row.type == "action":
      action_fill = self._panel_style.danger_fill if row.action_danger else self._panel_style.current_fill
      action_border = self._panel_style.danger_border if row.action_danger else self._panel_style.current_border
      action_text_color = self._panel_style.danger_text if row.action_danger else self._panel_style.title_color
      draw_selection_list_row(
        rect,
        title=tr(row.title),
        subtitle=tr(subtitle),
        action_text=tr(row.action_text),
        hovered=hovered,
        pressed=pressed,
        is_last=is_last,
        action_pill=True,
        title_size=SETTINGS_ROW_TITLE_FONT_SIZE, subtitle_size=SETTINGS_ROW_SUBTITLE_FONT_SIZE,
        action_pill_height=AETHER_LIST_METRICS.toggle_height, action_text_size=26,
        action_text_color=action_text_color,
        action_fill=action_fill,
        action_border=action_border,
        row_separator=self._panel_style.divider_color,
        card=True,
      )


# ═══════════════════════════════════════════════════════════════
# CardHubManagerView — shared HubTile card-grid landing page
# ═══════════════════════════════════════════════════════════════

class CardHubManagerView(AetherSettingsView):
    """AetherSettingsView that renders a TileGrid of HubTile navigation cards.

    Subclasses override ``_build_cards()`` to return a list of card dicts
    with keys ``title``, ``desc``, ``icon``, ``on_click``.
    """

    def __init__(self, controller, sections, *, columns=3, padding=SPACING.tile_gap, **kwargs):
        super().__init__(controller, sections, **kwargs)
        self._grid = HubGrid(columns=columns, padding=padding)
        self._grid.set_touch_valid_callback(lambda: self._scroll_panel.is_touch_valid())
        self._child(self._grid)
        self._init_cards()

    def _init_cards(self):
        self._grid.clear()
        for d in self._build_cards():
            self._grid.add_tile(HubTile(
                title=d["title"], desc=d["desc"], icon_key=d["icon"],
                on_click=d["on_click"],
            ))

    def _build_cards(self) -> list[dict]:
        raise NotImplementedError

    def _measure_content_height(self, width: float) -> float:
        return max(self._scroll_rect.height, self._grid.measure_height(width))

    def _build_scroll_columns(self, width: float) -> list[SettingsColumn]:
        if not self._uses_two_columns(width) or self._grid.get_effective_column_count(width) != 2 or not self._grid.tiles:
            return []
        rows = self._grid.get_row_count(available_width=width)
        tile_height = (self._grid.measure_height(width) - self._grid.gap * (rows - 1)) / rows

        def draw(index, rect):
            for row, tile in enumerate(self._grid.tiles[index::2]):
                self._bind_scroll_widget(tile)
                tile.render(rl.Rectangle(rect.x, rect.y + row * (tile_height + self._grid.gap), rect.width, tile_height))

        return [SettingsColumn(key, len(self._grid.tiles[index::2]) * tile_height
                               + max(0, len(self._grid.tiles[index::2]) - 1) * self._grid.gap,
                               lambda rect, index=index: draw(index, rect)) for index, key in enumerate(("left", "right"))]

    def _draw_scroll_content(self, rect: rl.Rectangle, width: float):
        y = rect.y + self._scroll_offset
        self._grid.set_parent_rect(self._scroll_rect)
        self._grid.render(rl.Rectangle(rect.x, y, width, self._content_height))


def draw_round_icon_button(rect: rl.Rectangle, icon: str = "back", *, pressed: bool = False,
                           icon_texture: rl.Texture2D | None = None) -> rl.Rectangle:
  """Aether Cards round button (close / back): faint fill, card outline, white glyph."""
  r = rect.width / 2
  center = rl.Vector2(rect.x + r, rect.y + r)
  rl.draw_circle_v(center, r, rl.Color(255, 255, 255, 40 if pressed else 15))
  rl.draw_ring(center, r - AS.SETTINGS_CARD_BORDER_WIDTH, r, 0, 360, 48,
               AS.SETTINGS_CARD_BORDER_PRESSED if pressed else AS.SETTINGS_CARD_BORDER_ON)
  if icon_texture is not None:
    w, h = icon_texture.width, icon_texture.height
    rl.draw_texture_pro(icon_texture, rl.Rectangle(0, 0, w, h), rl.Rectangle(center.x - w / 2, center.y - h / 2, w, h),
                        rl.Vector2(0, 0), 0, rl.WHITE)
  elif icon == "close":
    k = r * 0.32
    rl.draw_line_ex(rl.Vector2(center.x - k, center.y - k), rl.Vector2(center.x + k, center.y + k), 5.0, rl.WHITE)
    rl.draw_line_ex(rl.Vector2(center.x + k, center.y - k), rl.Vector2(center.x - k, center.y + k), 5.0, rl.WHITE)
  else:
    draw_chevron_icon(rl.Rectangle(center.x - r / 2, center.y - r / 2, r, r), rl.WHITE, thickness=5.0, direction="left")
  return rect


def draw_back_button(pill_rect: rl.Rectangle, center_y: float, pressed: bool, hovered: bool) -> rl.Rectangle:
  back_size = 48
  back_x = pill_rect.x + 12
  btn = rl.Rectangle(back_x, center_y - back_size / 2, back_size, back_size)
  if pressed or hovered:
    bg = rl.Color(255, 255, 255, 24) if pressed else rl.Color(255, 255, 255, 10)
    rl.draw_rectangle_rounded(btn, 0.4, 12, bg)
  chev_size = 20
  chev_r = rl.Rectangle(back_x + (back_size - chev_size) / 2, center_y - chev_size / 2, chev_size, chev_size)
  chev_c = rl.Color(200, 200, 210, 200) if pressed else rl.Color(160, 170, 185, 180)
  draw_chevron_icon(chev_r, chev_c, thickness=2.0, direction="left")
  return rl.Rectangle(pill_rect.x, center_y - 40, max(120.0, back_size + 24), 80)


BACK_BTN = "__back__"


# ── AetherCategoryDrawer — touch-optimized sliding drawer ──

class AetherCategoryDrawer(AetherSettingsView):
  """Reusable nested drawer view that maps SettingRows to a slide-out vertical settings list."""

  def __init__(self, controller, title: str, rows: list[SettingRow],
               *, color: rl.Color | str = "#8B5CF6", subtitle: str = "",
               panel_style=None):
    # Group the rows in a single SettingSection with an empty title
    sections = [SettingSection(title="", rows=rows)]
    super().__init__(controller, sections, header_title=title, header_subtitle=subtitle, panel_style=panel_style)
    self._color = hex_to_color(color) if isinstance(color, str) else color
    self._rows = rows
    self._slide_progress = 0.0
    self._back_btn_rect = None
    
    # Read driving side dynamically for ergonomic layout (LHD vs RHD)
    try:
      self._is_rhd = shared_ui_params().get_bool("IsRHD")
    except Exception:
      self._is_rhd = False

  def _visible_rows(self, section: SettingSection) -> list[SettingRow]:
    return [row for row in self._rows if row.visible is None or row.visible()]

  def _render(self, rect: rl.Rectangle):
    self.set_rect(rect)
    self._interactive_rects.clear()

    # Dim the screen area outside the drawer
    rl.draw_rectangle(int(rect.x), int(rect.y), int(rect.width), int(rect.height), rl.Color(0, 0, 0, 160))

    # Drawer slide-in animation (exponential smoothing)
    dt = rl.get_frame_time()
    self._slide_progress += (1.0 - self._slide_progress) * (1.0 - math.exp(-dt / 0.12))

    drawer_w = 850
    if self._is_rhd:
      # RHD: slide out from the right (driver side)
      drawer_x = rect.x + rect.width - drawer_w * self._slide_progress
      drawer_rect = rl.Rectangle(drawer_x, rect.y + 12, drawer_w - 12, rect.height - 24)
    else:
      # LHD: slide out from the left (driver side)
      drawer_x = rect.x - drawer_w + drawer_w * self._slide_progress
      drawer_rect = rl.Rectangle(drawer_x + 12, rect.y + 12, drawer_w - 12, rect.height - 24)

    # Draw drawer background and border
    draw_rounded_fill(drawer_rect, rl.Color(12, 10, 18, 250), radius_px=24)
    draw_rounded_stroke(drawer_rect, rl.Color(255, 255, 255, 18), radius_px=24)
    
    # Draw accent stripe on the side separating it from the dimmed area
    if self._is_rhd:
      rl.draw_rectangle_rec(rl.Rectangle(drawer_rect.x, drawer_rect.y, 4, drawer_rect.height), self._color)
    else:
      rl.draw_rectangle_rec(rl.Rectangle(drawer_rect.x + drawer_rect.width - 4, drawer_rect.y, 4, drawer_rect.height), self._color)

    # Draw header with navigation breadcrumbs
    header_rect = rl.Rectangle(drawer_rect.x + 36, drawer_rect.y + 24, drawer_rect.width - 72, 60)
    if self._has_header:
      self._draw_header(header_rect)

    # Set up scroll area (vertical scroll list)
    self._scroll_rect = rl.Rectangle(
      drawer_rect.x + 36,
      drawer_rect.y + 100,
      drawer_rect.width - 72,
      drawer_rect.height - 124
    )

    content_width = self._scroll_rect.width - AETHER_LIST_METRICS.content_right_gutter
    self._content_height = self._measure_content_height(content_width)
    self._scroll_panel.set_enabled(self.is_visible)

    self._scroll_offset = self._scroll_panel.update(
      self._scroll_rect, max(self._content_height, self._scroll_rect.height)
    )

    # Scissor and render settings rows
    aether_begin_scissor_mode(
      int(self._scroll_rect.x), int(self._scroll_rect.y),
      int(self._scroll_rect.width), int(self._scroll_rect.height)
    )
    self._draw_scroll_content(self._scroll_rect, content_width)
    aether_end_scissor_mode()

    if self._content_height > self._scroll_rect.height:
      self._scrollbar.render(self._scroll_rect, self._content_height, self._scroll_offset)

    draw_list_scroll_fades(
      self._scroll_rect, self._content_height, self._scroll_offset,
      rl.Color(12, 10, 18, 250), fade_height=self._fade_height
    )

  def _target_at(self, mouse_pos: MousePos) -> str | None:
    if self._back_btn_rect and point_hits(mouse_pos, self._back_btn_rect, None, pad_x=8, pad_y=8):
      return BACK_BTN

    # Tap outside the drawer to dismiss
    drawer_w = 850
    if self._is_rhd:
      drawer_x = self._rect.x + self._rect.width - drawer_w * self._slide_progress
      if mouse_pos.x < drawer_x:
        return "__dismiss__"
    else:
      drawer_x = self._rect.x - drawer_w + drawer_w * self._slide_progress
      if mouse_pos.x > drawer_x + drawer_w:
        return "__dismiss__"

    return super()._target_at(mouse_pos)

  def _activate_target(self, target_id: str | None):
    if target_id == BACK_BTN or target_id == "__dismiss__":
      gui_app.pop_widget()
    else:
      super()._activate_target(target_id)

  def _draw_header(self, rect: rl.Rectangle):
    pill_h = 48
    pill_rect = rl.Rectangle(rect.x, rect.y + (rect.height - pill_h) / 2, rect.width, pill_h)
    center_y = pill_rect.y + pill_h / 2

    draw_rounded_fill(pill_rect, rl.Color(18, 16, 24, 200), radius_px=14)
    draw_rounded_stroke(pill_rect, rl.Color(255, 255, 255, 22), radius_px=14)

    mouse_pos = gui_app.last_mouse_event.pos
    is_pressed = getattr(self, '_pressed_target', None) == BACK_BTN
    is_hovered = point_hits(mouse_pos, pill_rect, None, pad_x=0, pad_y=0) and \
                 self._back_btn_rect and point_hits(mouse_pos, self._back_btn_rect, None, pad_x=8, pad_y=8)
    self._back_btn_rect = draw_back_button(pill_rect, center_y, is_pressed, is_hovered)

    crumb_x = pill_rect.x + 58
    crumb_w = pill_rect.width - (crumb_x - pill_rect.x) - 20
    crumb_rect = rl.Rectangle(crumb_x, pill_rect.y, crumb_w, pill_rect.height)
    self._breadcrumbs.draw(crumb_rect)


# Compatibility Alias
AetherCategoryTileView = AetherCategoryDrawer



class AetherTile(Widget):
  def __init__(self, surface_color: rl.Color | str | None = None, on_click: Callable | None = None):
    super().__init__()
    if isinstance(surface_color, str):
      self.surface_color = hex_to_color(surface_color)
    elif surface_color:
      self.surface_color = surface_color
    else:
      self.surface_color = AetherListColors.PRIMARY
    self.on_click = on_click
    self._plate_offset: float = 0.0
    self._plate_target: float = 0.0
    self._is_pressed: bool = False
    self._squish: float = 1.0

  @property
  def _hit_rect(self) -> rl.Rectangle:
    hit_rect = rl.Rectangle(
      self._rect.x - GEOMETRY_OFFSET,
      self._rect.y - GEOMETRY_OFFSET,
      self._rect.width + 2 * GEOMETRY_OFFSET,
      self._rect.height + 2 * GEOMETRY_OFFSET,
    )
    parent_rect = getattr(self, "_parent_rect", None)
    if parent_rect is not None:
      return _intersect_rect(hit_rect, parent_rect)
    return hit_rect

  def _handle_mouse_press(self, mouse_pos: MousePos):
    if not self.enabled:
      return
    if rl.check_collision_point_rec(mouse_pos, self._hit_rect):
      self._is_pressed = True
      self._plate_target = 1.0
      self._squish = 0.95

  def _handle_mouse_release(self, mouse_pos: MousePos):
    if not self.enabled:
      self._is_pressed = False
      self._plate_target = 0.0
      return
    if self._is_pressed:
      if rl.check_collision_point_rec(mouse_pos, self._hit_rect):
        self._plate_target = 0.0
        if self.on_click:
          self.on_click()
      else:
        self._plate_target = 0.0
      self._is_pressed = False

  def _handle_mouse_event(self, mouse_event):
    if not rl.check_collision_point_rec(mouse_event.pos, self._hit_rect):
      self._plate_target = 0.0

  def _animate_plate(self, dt: float):
    if self._plate_offset == self._plate_target:
      return
    self._plate_offset += (self._plate_target - self._plate_offset) * (1 - math.exp(-dt / PLATE_TAU))

  def _update_squish(self):
    dt = rl.get_frame_time()
    if self._squish < 1.0:
      self._squish += (1.0 - self._squish) * 15.0 * dt

  def _update_state(self):
    self._update_squish()

  def _draw_custom_icon(self, key: str, x: float, y: float, s: float, color: rl.Color):
    draw_custom_icon(key, x, y, s, color)

  def _constellation_seed(self) -> str:
    title = getattr(self, 'title', None)
    resolved = str(_resolve_value(title, '')) if title is not None else ''
    pos = getattr(self, '_rect', None)
    if pos is not None:
      return f"{resolved}:{int(pos.x)}:{int(pos.y)}" if resolved else f"{self.__class__.__name__}:{int(pos.x)}:{int(pos.y)}"
    return resolved or self.__class__.__name__

  def _generate_and_cache_constellation(self):
    if hasattr(self, '_constellation_data'):
      return
    rng = random.Random(self._constellation_seed())
    num = _NODE_NUM_MIN + rng.randint(0, _NODE_NUM_MAX - _NODE_NUM_MIN)
    self._constellation_data = _build_constellation_nodes(
      rng, num, _CONST_REGIONS_TILE,
      r_min=0.05, r_max=0.11, min_sep=0.07, x_margin=0.04, y_margin=0.04,
    )

  def _draw_constellation(self, face: rl.Rectangle, accent: rl.Color, glow: float):
    if not SHOW_CONSTELLATIONS:
      return
    self._generate_and_cache_constellation()
    nodes, vecs = self._constellation_data
    draw_constellation_nodes(nodes, vecs, face, accent, glow, scale=1.0)

  def _draw_constellation_disconnected(self, face: rl.Rectangle, accent: rl.Color, glow: float):
    if not SHOW_CONSTELLATIONS:
      return
    self._generate_and_cache_constellation()
    nodes, _ = self._constellation_data
    draw_constellation_nodes(nodes, [], face, accent, glow, scale=1.0)

  def _render_hud_background(self, rect: rl.Rectangle, accent: rl.Color, glow: float = 1.0, *, bg_color: rl.Color | None = None, const_connected: bool = True) -> tuple[rl.Rectangle, rl.Color]:
    sq = self._squish
    snapped = snap_rect(rect)
    sw = snapped.width * sq
    sh = snapped.height * sq
    ox = snapped.x + (snapped.width - sw) / 2
    oy = snapped.y + (snapped.height - sh) / 2
    face, accent = draw_hud_background(rl.Rectangle(ox, oy, sw, sh), accent, glow, bg_color=bg_color)
    if const_connected:
      self._draw_constellation(face, accent, glow)
    else:
      self._draw_constellation_disconnected(face, accent, glow)
    return face, accent

  def _render(self, rect: rl.Rectangle):
    pass


class HubTile(AetherTile):
  def __init__(
    self,
    title: str | Callable[[], str],
    desc: str | Callable[[], str],
    icon_key: str | None = None,
    on_click: Callable | None = None,
    bg_color: rl.Color | str | None = None,
    get_status: Callable[[], str] | None = None,
  ):
    if bg_color:
      super().__init__(surface_color=bg_color, on_click=on_click)
    else:
      super().__init__(on_click=on_click)
    self.get_status = get_status
    self.title = title
    self.desc = desc
    self.custom_icon_key = icon_key if icon_key in ("sound", "steering", "navigate", "system", "display", "vehicle", "road", "aicar") else None
    self._icon = None
    self._font_title = gui_app.font(FontWeight.BOLD)
    self._font_desc = gui_app.font(FontWeight.NORMAL)

  def _render(self, rect: rl.Rectangle):
    self._animate_plate(rl.get_frame_time())

    status_text = self.get_status() if self.get_status else ""
    title_text = str(_resolve_value(self.title, ""))

    # Aether Cards: light outline (the accent lives in the icon well), brighter while pressed.
    face, accent = self._render_hud_background(rect, self.surface_color, 0.35 if self._is_pressed else 0.0)
    rx, ry, rw, rh = face.x, face.y, face.width, face.height
    pad = float(AS.SETTINGS_TILE_INSET) if rh >= 260 else float(AS.SETTINGS_CARD_INSET / 2)
    max_w = rw - pad * 2

    title_size = 42 if rw >= 420 else 36
    desc_text = status_text or str(_resolve_value(self.desc, ""))
    desc_size = 28

    well = 112.0 if rh >= 300 else 88.0
    text_x = rx + pad
    desc_lines = wrap_subtitle(self._font_desc, desc_text, max_w, desc_size) if desc_text else []
    line_h = desc_size * FONT_SCALE + 2
    text_h = title_size * FONT_SCALE + (SPACING.sm + len(desc_lines) * line_h if desc_lines else 0)
    stacked = not self.custom_icon_key or rh - 2 * pad >= well + 24 + text_h
    if self.custom_icon_key:
      if stacked:  # icon well top-left, text along the bottom
        well_rect = snap_rect(rl.Rectangle(rx + pad, ry + pad, well, well))
      else:        # short tile: icon well beside the text
        well = min(well, rh - 2 * pad)
        well_rect = snap_rect(rl.Rectangle(rx + pad, ry + (rh - well) / 2, well, well))
        text_x = well_rect.x + well + 28
        max_w = rx + rw - pad - text_x
        desc_lines = wrap_subtitle(self._font_desc, desc_text, max_w, desc_size) if desc_text else []
        text_h = title_size * FONT_SCALE + (SPACING.sm + len(desc_lines) * line_h if desc_lines else 0)
      aether_fill(well_rect, AS.ACCENT_TINT, well * 0.29)
      icon_size = well * 0.62
      s = icon_size / CUSTOM_ICON_CANVAS_SIZE
      self._draw_custom_icon(self.custom_icon_key, well_rect.x + (well - icon_size) / 2, well_rect.y + (well - icon_size) / 2, s,
                             AS.ICON_INK)
    y = ry + rh - pad - text_h if stacked else ry + (rh - text_h) / 2

    draw_text_fit_common(self._font_title, title_text, rl.Vector2(text_x, y), max_w, title_size, color=rl.WHITE)
    y += title_size * FONT_SCALE + SPACING.sm
    for line in desc_lines:
      draw_text_fit_common(self._font_desc, line, rl.Vector2(text_x, y), max_w, desc_size, color=AS.TEXT_SECONDARY)
      y += line_h

    if status_text:
      import re
      m = re.search(r'(\d+)%$', status_text)
      if m:
        ratio = min(1.0, max(0.0, float(m.group(1)) / 100.0))
        if ratio > 0.05:
          meter_h = 9
          meter_rect = rl.Rectangle(rx + pad, ry + rh - pad / 2 - meter_h, rw - pad * 2, meter_h)
          fill_rect = rl.Rectangle(meter_rect.x, meter_rect.y, meter_rect.width * ratio, meter_h)
          rl.draw_rectangle_rec(snap_rect(meter_rect), rl.Color(255, 255, 255, 14))
          rl.draw_rectangle_rec(snap_rect(fill_rect), with_alpha(accent, 170))



class ToggleTile(AetherTile):
  def __init__(
    self,
    title: str,
    get_state: Callable[[], bool],
    set_state: Callable[[bool], None],
    bg_color: rl.Color | str | None = None,
    desc: str = "",
    is_enabled: Callable[[], bool] | None = None,
    disabled_label: str = "",
  ):
    if bg_color:
      super().__init__(surface_color=bg_color)
    else:
      super().__init__(surface_color=AetherListColors.SUCCESS)
    self.title = title
    self.desc = desc
    self.get_state = get_state
    self.set_state = set_state
    self.set_enabled(is_enabled or True)
    self._disabled_label = disabled_label

  def _handle_mouse_release(self, mouse_pos: MousePos):
    if self._is_pressed:
      if rl.check_collision_point_rec(mouse_pos, self._hit_rect) and self.enabled:
        self.set_state(not self.get_state())
      self._plate_target = 0.0
      self._is_pressed = False

  def _render(self, rect: rl.Rectangle):
    subtitle = self.desc
    if not self.enabled:
      subtitle = tr(self._disabled_label) if self._disabled_label else tr("Unavailable")
    draw_settings_card_row(rect, title=self.title, subtitle=subtitle, toggle_value=self.get_state(),
                           enabled=self.enabled, pressed=self._is_pressed)


class RowToggleTile(ToggleTile):
  """Compatibility name; all toggle tiles use the shared settings card row."""


class ValueTile(AetherTile):
  def __init__(
    self,
    title: str,
    get_value: Callable[[], str],
    on_click: Callable,
    bg_color: rl.Color | str | None = None,
    is_enabled: Callable[[], bool] | None = None,
    desc: str = "",
  ):
    super().__init__(surface_color=bg_color, on_click=on_click)
    self.title = title
    self.desc = desc
    self.get_value = get_value
    self.set_enabled(is_enabled or (lambda: True))
    self._font = gui_app.font(FontWeight.BOLD)
    self._font_desc = gui_app.font(FontWeight.MEDIUM)
    self._active_color = self.surface_color
    self._disabled_color = rl.Color(120, 120, 120, 255)

  def _render(self, rect: rl.Rectangle):
    enabled = self.enabled
    self._animate_plate(rl.get_frame_time())

    if not enabled:
      self._plate_offset = 0.0
      self._plate_target = 0.0

    color = self._active_color if enabled else self._disabled_color
    glow = 1.0 if enabled else 0.0
    face, accent = self._render_hud_background(rect, color, glow)
    rx, ry, rw, rh = face.x, face.y, face.width, face.height

    content_pad = SPACING.tile_content
    max_w = rw - content_pad * 2
    text_scale = min(rw / 360.0, rh / 205.0)

    # Title
    title_size = max(26, int(round(32 * text_scale)))
    draw_text_fit_common(self._font, self.title,
                        rl.Vector2(rx + content_pad, ry + int(rh * 0.35)),
                        max_w, title_size, align_center=True, color=_HUD_TEXT_DIM)

    # Value
    val_text = self.get_value()
    val_size = max(26, int(round(35 * text_scale)))
    val_color = accent if enabled else _HUD_TEXT_DIM
    draw_text_fit_common(self._font, val_text,
                        rl.Vector2(rx + content_pad, ry + int(rh * 0.58)),
                        max_w, val_size, align_center=True, color=val_color)


class SliderTile(AetherTile):
    LONG_PRESS_THRESHOLD = 0.5
    DRAG_THRESHOLD = 10

    def __init__(
        self,
        title: str,
        get_value: Callable[[], float],
        set_value: Callable[[float], None],
        min_val: float,
        max_val: float,
        step: float,
        bg_color: rl.Color | str | None = None,
        is_enabled: Callable[[], bool] | None = None,
        desc: str = "",
        unit: str = "",
        labels: dict[float, str] | None = None,
        on_test: Callable[[], None] | None = None,
    ):
        super().__init__(surface_color=bg_color)
        self.title = title
        self.desc = desc
        self.get_value = get_value
        self.set_value = set_value
        self.min_val = min_val
        self.max_val = max_val
        self.step = step
        self.unit = unit
        self.labels = labels or {}
        self.on_test = on_test
        self.set_enabled(is_enabled or (lambda: True))
        self._font = gui_app.font(FontWeight.BOLD)
        self._font_desc = gui_app.font(FontWeight.MEDIUM)
        self._active_color = self.surface_color
        self._disabled_color = rl.Color(120, 120, 120, 255)

        self._is_dragging = False
        self._last_mouse_x = 0.0
        self._velocity = 0.0
        self._smooth_value = get_value()
        self._press_start_x = 0.0
        self._press_start_time: float | None = None
        self._long_press_triggered = False

    def _handle_mouse_press(self, mouse_pos: MousePos):
        if rl.check_collision_point_rec(mouse_pos, self._hit_rect) and self.enabled:
            self._is_pressed = True
            self._squish = 0.95
            self._last_mouse_x = mouse_pos.x
            self._velocity = 0.0
            self._press_start_x = mouse_pos.x
            self._press_start_time = time.monotonic()
            self._long_press_triggered = False

    def _handle_mouse_release(self, mouse_pos: MousePos):
        self._is_dragging = False
        self._is_pressed = False
        self._press_start_time = None

    def _handle_mouse_event(self, mouse_event):
        if not rl.check_collision_point_rec(mouse_event.pos, self._hit_rect):
            if not self._is_dragging and not self._press_start_time:
                self._plate_target = 0.0

        if self._press_start_time and not self._is_dragging and not self._long_press_triggered:
            dx = abs(mouse_event.pos.x - self._press_start_x)
            if dx > self.DRAG_THRESHOLD:
                self._is_dragging = True
                self._press_start_time = None
            else:
                elapsed = time.monotonic() - self._press_start_time
                if elapsed >= self.LONG_PRESS_THRESHOLD:
                    self._long_press_triggered = True
                    self._press_start_time = None
                    if self.on_test:
                        self.on_test()

        if self._is_dragging:
            dt = rl.get_frame_time()
            current_val = self.get_value()
            mouse_pos = mouse_event.pos
            dx = mouse_pos.x - self._last_mouse_x
            self._velocity = dx / max(dt, 0.001)
            self._last_mouse_x = mouse_pos.x

            rect_w = self._rect.width
            if rect_w > 0:
                val_range = self.max_val - self.min_val
                val_dx = (dx / rect_w) * val_range
                new_val = current_val + val_dx

                abs_vel = abs(self._velocity)
                snap_threshold = 800
                coarse_step = 10 if val_range >= 100 else self.step * 5
                dynamic_step = coarse_step if abs_vel > snap_threshold else self.step

                snapped = round(new_val / dynamic_step) * dynamic_step
                snapped = max(self.min_val, min(self.max_val, snapped))

                if abs(snapped - current_val) >= self.step:
                    self.set_value(float(snapped))

    def _render(self, rect: rl.Rectangle):
        enabled = self.enabled
        current_val = self.get_value()
        dt = rl.get_frame_time()

        self._smooth_value += (current_val - self._smooth_value) * (1 - math.exp(-dt / 0.1))
        self._animate_plate(dt)

        if not enabled:
            self._plate_offset = 0.0
            self._plate_target = 0.0

        color = self._active_color if enabled else self._disabled_color
        glow = 1.0 if enabled else 0.0
        face, accent = self._render_hud_background(rect, color, glow)
        rx, ry, rw, rh = face.x, face.y, face.width, face.height

        content_pad = SPACING.tile_content
        max_w = rw - content_pad * 2
        text_scale = min(rw / 360.0, rh / 205.0)

        # Title
        title_size = max(26, int(round(32 * text_scale)))
        draw_text_fit_common(self._font, self.title,
                            rl.Vector2(rx + content_pad, ry + int(rh * 0.30)),
                            max_w, title_size, align_center=True, color=_HUD_TEXT_DIM)

        # Value text
        val_str = self.labels.get(current_val, f"{int(current_val)}{self.unit}")
        val_size = max(26, int(round(35 * text_scale)))
        val_color = accent if enabled else _HUD_TEXT_DIM
        draw_text_fit_common(self._font, val_str,
                            rl.Vector2(rx + content_pad, ry + int(rh * 0.52)),
                            max_w, val_size, align_center=True, color=val_color)

        # Slider meter
        value_range = self.max_val - self.min_val
        frac = 0.0 if value_range == 0 else max(0.0, min(1.0, (self._smooth_value - self.min_val) / value_range))
        meter_h = 9
        meter_rect = rl.Rectangle(rx + content_pad, ry + rh - content_pad - meter_h, rw - content_pad * 2, meter_h)
        fill_w = meter_rect.width * frac
        rl.draw_rectangle_rec(snap_rect(meter_rect), rl.Color(255, 255, 255, 14))
        if fill_w > 1:
            fill_rect = rl.Rectangle(meter_rect.x, meter_rect.y, fill_w, meter_rect.height)
            fill_color = with_alpha(accent, 176) if enabled else rl.Color(120, 120, 120, 100)
            rl.draw_rectangle_rec(snap_rect(fill_rect), fill_color)


class AetherSlider(Widget):
  def __init__(
    self,
    min_val: float,
    max_val: float,
    step: float,
    current_val: float,
    on_change: Callable[[float], None],
    unit: str = "",
    labels: dict[float, str] | None = None,
    color: rl.Color = rl.Color(54, 77, 239, 255),
    on_commit: Callable[[float], None] | None = None,
    show_value_label: bool = True,
  ):
    super().__init__()
    self.min_val, self.max_val, self.step, self.current_val = min_val, max_val, step, current_val
    self.on_change, self.on_commit = on_change, on_commit
    self.unit, self.labels, self.color = unit, labels or {}, color
    self.show_value_label = show_value_label
    self._is_dragging = False
    self._font = gui_app.font(FontWeight.BOLD)
    self._thumb_offset: float = 0.0
    self._minus_offset: float = 0.0
    self._plus_offset: float = 0.0
    self._minus_pressed = False
    self._plus_pressed = False
    self._pending_drag = False
    self._press_start = rl.Vector2(0, 0)
    self._started_on_thumb = False
    self._value_at_press = current_val

  @property
  def is_interacting(self) -> bool:
    return self._is_dragging or self._pending_drag or self._minus_pressed or self._plus_pressed

  def set_value(self, value: float) -> None:
    self.current_val = self._clamp_and_snap(value)

  def reset_interaction(self) -> None:
    self._is_dragging = False
    self._pending_drag = False
    self._started_on_thumb = False
    self._thumb_offset = 0.0
    self._minus_pressed = False
    self._plus_pressed = False

  def _cancel_interaction(self, *, revert: bool = False) -> None:
    if revert and self.current_val != self._value_at_press:
      self.current_val = self._value_at_press
      self.on_change(self.current_val)
    self.reset_interaction()

  def _finalize_interaction(self, mouse_pos: MousePos, *, inside_release: bool) -> None:
    button_w = self._button_width(self._rect)
    changed = False

    if self._minus_pressed:
      self._minus_pressed = False
      if inside_release and rl.check_collision_point_rec(mouse_pos, rl.Rectangle(self._rect.x, self._rect.y, button_w, self._rect.height)):
        new_val = self._clamp_and_snap(self.current_val - self.step)
        if new_val != self.current_val:
          self.current_val = new_val
          self.on_change(self.current_val)
          changed = True

    if self._plus_pressed:
      self._plus_pressed = False
      if inside_release and rl.check_collision_point_rec(mouse_pos, rl.Rectangle(self._rect.x + self._rect.width - button_w, self._rect.y, button_w, self._rect.height)):
        new_val = self._clamp_and_snap(self.current_val + self.step)
        if new_val != self.current_val:
          self.current_val = new_val
          self.on_change(self.current_val)
          changed = True

    if self._is_dragging:
      changed = changed or self.current_val != self._value_at_press
      self._is_dragging = False
      self._thumb_offset = 0.0
    elif self._pending_drag:
      if inside_release and not self._started_on_thumb and rl.check_collision_point_rec(mouse_pos, self._rect):
        before_tap = self.current_val
        self._update_val_from_mouse(mouse_pos)
        changed = changed or before_tap != self.current_val
      self._pending_drag = False
      self._thumb_offset = 0.0
      changed = changed or self.current_val != self._value_at_press

    self._started_on_thumb = False
    if changed and self.on_commit is not None:
      self.on_commit(self.current_val)

  def _clamp_and_snap(self, val: float) -> float:
    return clamp_and_snap(val, self.min_val, self.max_val, self.step)

  def _button_width(self, rect: rl.Rectangle) -> int:
    return min(SLIDER_BUTTON_SIZE, max(64, int(rect.width * 0.14)))

  def _thumb_size(self, rect: rl.Rectangle, track_h: int | None = None) -> tuple[int, int]:
    effective_track_h = track_h if track_h is not None else max(17, int(rect.height * 0.22))
    return max(26, int(effective_track_h * 0.95)), max(49, int(rect.height * 0.50))

  def _get_thumb_x(self, rect: rl.Rectangle) -> float:
    button_w = self._button_width(rect)
    track_x = rect.x + button_w
    track_w = rect.width - 2 * button_w
    value_range = self.max_val - self.min_val
    frac = 0.0 if value_range == 0 else (self.current_val - self.min_val) / value_range
    return track_x + frac * track_w

  def _exponential_ease(self, current: float, target: float, dt: float) -> float:
    if current == target:
      return target
    return current + (target - current) * (1 - math.exp(-dt / PLATE_TAU))

  def _draw_slider_button(self, rect: rl.Rectangle, label: str):
    offset = self._minus_offset if label == "-" else self._plus_offset
    face_x = _snap(rect.x)
    face_y = _snap(rect.y + min(1.0, offset))
    face_rect = snap_rect(rl.Rectangle(face_x, face_y, rect.width, rect.height))
    btn_color = rl.Color(34, 38, 48, 255)
    border_color = rl.Color(255, 255, 255, 28)
    draw_rounded_fill(face_rect, btn_color, radius_px=23)
    draw_rounded_stroke(face_rect, border_color, radius_px=23)
    rl.draw_rectangle_rec(rl.Rectangle(face_rect.x, face_rect.y, face_rect.width, 1), rl.Color(255, 255, 255, 16))
    draw_stepper_symbol(face_rect, increment=label == "+")

  def _render(self, rect: rl.Rectangle):
    rect = snap_rect(rect)
    self.set_rect(rect)
    dt = rl.get_frame_time()
    if self._is_dragging:
      self._update_val_from_mouse(rl.get_mouse_position())
    self._minus_offset = self._exponential_ease(self._minus_offset, 1.0 if self._minus_pressed else 0.0, dt)
    self._plus_offset = self._exponential_ease(self._plus_offset, 1.0 if self._plus_pressed else 0.0, dt)
    button_w = self._button_width(rect)
    minus_rect = snap_rect(rl.Rectangle(rect.x, rect.y, button_w, rect.height))
    plus_rect = snap_rect(rl.Rectangle(rect.x + rect.width - button_w, rect.y, button_w, rect.height))
    self._draw_slider_button(minus_rect, "-")
    self._draw_slider_button(plus_rect, "+")
    track_x = rect.x + button_w
    track_w = rect.width - 2 * button_w
    track_h = max(17, int(rect.height * 0.22))
    track_rect = snap_rect(rl.Rectangle(track_x, rect.y + (rect.height - track_h) / 2, track_w, track_h))
    draw_rounded_fill(track_rect, rl.Color(34, 38, 48, 255), radius_px=track_h / 2)
    draw_rounded_stroke(track_rect, rl.Color(255, 255, 255, 20), radius_px=track_h / 2)
    value_range = self.max_val - self.min_val
    frac = 0.0 if value_range == 0 else (self.current_val - self.min_val) / value_range
    fill_w = frac * track_w
    if fill_w > 0:
      fill_rect = snap_rect(rl.Rectangle(track_x, track_rect.y, fill_w, track_h))
      rl.draw_rectangle_rec(fill_rect, with_alpha(self.color, 190))
    if self.step > 0:
      n_steps = int(round(value_range / self.step))
      if n_steps > 0:
        tick_count = min(n_steps, 24)
        for i in range(tick_count + 1):
          tick_x = track_x + (i / max(1, tick_count)) * track_w
          tick_h = int(track_h * 0.6)
          tick_y = track_rect.y + (track_h - tick_h) / 2
          rl.draw_rectangle_rec(rl.Rectangle(tick_x - 1, tick_y, 2, tick_h), rl.Color(255, 255, 255, 60))
    thumb_w, thumb_h = self._thumb_size(rect, track_h)
    thumb_x = self._get_thumb_x(rect) - thumb_w / 2
    thumb_y = rect.y + (rect.height - thumb_h) / 2
    thumb_offset = GEOMETRY_OFFSET * self._thumb_offset
    t_face_rect = snap_rect(rl.Rectangle(thumb_x, thumb_y + min(1.0, thumb_offset), thumb_w, thumb_h))
    draw_rounded_fill(t_face_rect, rl.Color(230, 235, 242, 255), radius_px=17)
    draw_rounded_stroke(t_face_rect, rl.Color(20, 22, 28, 46), radius_px=17)
    rl.draw_rectangle_rec(rl.Rectangle(t_face_rect.x, t_face_rect.y, t_face_rect.width, 1), rl.Color(255, 255, 255, 40))
    if self.show_value_label:
      val_str = self.labels.get(self.current_val, f"{self.current_val:.2f}".rstrip('0').rstrip('.') + self.unit)
      label_size = max(26, int(round(rect.height * 0.38)))
      ts = measure_text_cached(self._font, val_str, label_size)
      val_x = max(rect.x, min(thumb_x + (thumb_w - ts.x) / 2, rect.x + rect.width - ts.x))
      val_pos = rl.Vector2(val_x, thumb_y - label_size - 10)
      rl.draw_text_ex(self._font, val_str, rl.Vector2(round(val_pos.x), round(val_pos.y)), label_size, 0, rl.WHITE)

  def _handle_mouse_press(self, mouse_pos: MousePos):
    if not self._touch_valid() or not rl.check_collision_point_rec(mouse_pos, self._rect):
      return
    self._value_at_press = self.current_val
    button_w = self._button_width(self._rect)
    minus_rect = rl.Rectangle(self._rect.x, self._rect.y, button_w, self._rect.height)
    plus_rect = rl.Rectangle(self._rect.x + self._rect.width - button_w, self._rect.y, button_w, self._rect.height)
    if rl.check_collision_point_rec(mouse_pos, minus_rect):
      self._minus_pressed = True
      return
    if rl.check_collision_point_rec(mouse_pos, plus_rect):
      self._plus_pressed = True
      return
    thumb_w, thumb_h = self._thumb_size(self._rect)
    thumb_x = self._get_thumb_x(self._rect) - thumb_w / 2
    thumb_y = self._rect.y + (self._rect.height - thumb_h) / 2
    thumb_rect = rl.Rectangle(thumb_x - 8, thumb_y - 8, thumb_w + 16, thumb_h + 16)
    if rl.check_collision_point_rec(mouse_pos, thumb_rect):
      self._pending_drag = True
      self._started_on_thumb = True
      self._press_start = rl.Vector2(mouse_pos.x, mouse_pos.y)
      self._thumb_offset = 1.0
    else:
      self._pending_drag = True
      self._started_on_thumb = False
      self._press_start = rl.Vector2(mouse_pos.x, mouse_pos.y)

  def _handle_mouse_release(self, mouse_pos: MousePos):
    self._finalize_interaction(mouse_pos, inside_release=True)

  def _handle_mouse_event(self, mouse_event: MouseEvent):
    mouse_in_rect = rl.check_collision_point_rec(mouse_event.pos, self._rect)
    if mouse_event.left_released and self.is_interacting and not mouse_in_rect:
      self._finalize_interaction(mouse_event.pos, inside_release=False)
      return

    if not self._touch_valid():
      self._cancel_interaction(revert=True)
      return

    if self._pending_drag and not self._is_dragging:
      dx = mouse_event.pos.x - self._press_start.x
      dy = mouse_event.pos.y - self._press_start.y
      if abs(dy) > 12 and abs(dy) > abs(dx):
        self._pending_drag = False
        self._started_on_thumb = False
        self._thumb_offset = 0.0
        return
      if abs(dx) > 12 and abs(dx) >= abs(dy):
        self._pending_drag = False
        self._is_dragging = True
        self._thumb_offset = 1.0

    if self._is_dragging:
      dx = mouse_event.pos.x - self._press_start.x
      dy = mouse_event.pos.y - self._press_start.y
      if abs(dy) > 18 and abs(dy) > abs(dx) * 1.15:
        self._cancel_interaction(revert=True)
        return
      self._update_val_from_mouse(mouse_event.pos)

  def _update_val_from_mouse(self, mouse_pos: MousePos):
    button_w = self._button_width(self._rect)
    track_x = self._rect.x + button_w
    track_w = self._rect.width - 2 * button_w
    track_rect = rl.Rectangle(track_x, self._rect.y, track_w, self._rect.height)
    snapped = update_val_from_mouse(mouse_pos, track_rect, self.min_val, self.max_val, self.step)
    if snapped != self.current_val:
      self.current_val = snapped
      self.on_change(self.current_val)


class AetherSelectionDialog(Widget):
  """One shell and fixed header for grid, list, multi-select and numeric pickers."""

  def __init__(self, title: str, subtitle: str = "", callback: Callable[[DialogResult], None] | None = None):
    super().__init__()
    self.title = title
    self._subtitle = subtitle or tr("Choose an option, then tap Apply.")
    self._callback = callback
    self._closed = False
    self._content_rect = rl.Rectangle()
    self._cancel_rect = rl.Rectangle()
    self._ok_rect = rl.Rectangle()
    self._cancel = self._child(AetherButton(tr("Cancel"), lambda: self._finish(DialogResult.CANCEL), neutral=True))
    self._apply = self._child(AetherButton(tr("Apply"), lambda: self._finish(DialogResult.CONFIRM),
                                          emphasized=True, accent_color=AS.ACCENT_SOLID, enabled=self._can_apply))

  def _can_apply(self) -> bool:
    return True

  def _before_close(self):
    pass

  def _on_result(self, result: DialogResult):
    if self._callback is not None:
      self._callback(result)

  def _finish(self, result: DialogResult):
    if self._closed or (result == DialogResult.CONFIRM and not self._can_apply()):
      return
    self._closed = True
    self._before_close()
    gui_app.pop_widget()
    self._on_result(result)

  def _render(self, rect: rl.Rectangle):
    if self._closed:
      return
    rl.draw_rectangle_rec(rect, AS.SETTINGS_BG)
    margin_x = min(AS.SETTINGS_DIALOG_MARGIN_X, rect.width * 0.05)
    margin_y = min(AS.SETTINGS_DIALOG_MARGIN_Y, rect.height * 0.05)
    shell = snap_rect(rl.Rectangle(rect.x + margin_x, rect.y + margin_y, rect.width - margin_x * 2, rect.height - margin_y * 2))
    draw_settings_card(shell, fill=AS.SETTINGS_DIALOG_FILL, border=AS.SETTINGS_TILE_BORDER, radius_px=AS.SETTINGS_DIALOG_RADIUS)
    inset = min(AS.SETTINGS_DIALOG_INSET, shell.width * 0.05)
    x, y, width = shell.x + inset, shell.y + inset, shell.width - inset * 2
    apply_width = max(AS.SETTINGS_DIALOG_ACTION_WIDTH, self._apply.measure_width())
    cancel_width = max(AS.SETTINGS_DIALOG_ACTION_WIDTH, self._cancel.measure_width())
    self._ok_rect = rl.Rectangle(x + width - apply_width, y, apply_width, self._apply.measure_height())
    self._cancel_rect = rl.Rectangle(self._ok_rect.x - AS.SETTINGS_TILE_GAP - cancel_width, y, cancel_width, self._cancel.measure_height())
    text_width = max(1.0, self._cancel_rect.x - AS.SETTINGS_CARD_INSET - x)
    # Stack the actions below the text when the panel is too narrow for both.
    stacked = text_width < 440
    if stacked:
      text_width = width
    title_size, description_size = AS.SETTINGS_DIALOG_TITLE_SIZE, AS.SETTINGS_DIALOG_DESCRIPTION_SIZE
    titles = wrap_text(gui_app.font(FontWeight.BOLD), self.title, text_width, title_size, max_lines=2, spacing=0)
    descriptions = wrap_text(gui_app.font(FontWeight.NORMAL), self._subtitle, text_width, description_size, max_lines=3, spacing=0)
    title_height = max(70.0, title_size * FONT_SCALE)
    description_height = max(36.0, description_size * FONT_SCALE)
    text_y = y
    for line in titles:
      gui_label(rl.Rectangle(x, text_y, text_width, title_height), line, title_size, AS.TEXT, FontWeight.BOLD)
      text_y += title_height
    text_y += 4
    for line in descriptions:
      gui_label(rl.Rectangle(x, text_y, text_width, description_height), line, description_size, AS.TEXT_SECONDARY)
      text_y += description_height
    header_height = max(self._apply.measure_height(), text_y - y)
    if stacked:
      self._cancel_rect.y = self._ok_rect.y = text_y + AS.SETTINGS_TEXT_GAP
      action_width = min(max(apply_width, cancel_width), (width - AS.SETTINGS_TILE_GAP) / 2)
      self._ok_rect.x, self._ok_rect.width = x + width - action_width, action_width
      self._cancel_rect.x, self._cancel_rect.width = self._ok_rect.x - AS.SETTINGS_TILE_GAP - action_width, action_width
      header_height = self._ok_rect.y + self._ok_rect.height - y
    content_y = y + header_height + AS.SETTINGS_TILE_GAP
    self._content_rect = rl.Rectangle(x, content_y, width, max(0.0, shell.y + shell.height - inset - content_y))
    self._cancel.render(self._cancel_rect)
    self._apply.render(self._ok_rect)
    if self._closed:
      return
    if rl.is_key_pressed(rl.KeyboardKey.KEY_ESCAPE):
      self._finish(DialogResult.CANCEL)
      return
    self._render_content(self._content_rect)

  def _render_content(self, rect: rl.Rectangle):
    raise NotImplementedError


class AetherSliderDialog(AetherSelectionDialog):
  def __init__(
    self,
    title: str,
    min_val: float,
    max_val: float,
    step: float,
    current_val: float,
    on_close: Callable,
    presets: list[float] | None = None,
    unit: str = "",
    labels: dict[float, str] | None = None,
    color: rl.Color | str = "#8B5CF6",
    on_change: Callable[[float], None] | None = None,
    subtitle: str = "",
  ):
    super().__init__(title, subtitle or tr("Adjust the value, then tap Apply."))
    self._user_callback = on_close
    self._on_change = on_change
    self._color = hex_to_color(color) if isinstance(color, str) else color
    self._current_val = current_val
    self.min_val, self.max_val, self.step = min_val, max_val, step
    self._presets = presets or []
    self._unit, self._labels = unit, labels or {}
    self._preset_rects: list[tuple[float, rl.Rectangle]] = []
    self._pressed_zone: str | None = None
    self._is_dragging = False
    self._val_on_press = current_val
    self._minus_rect = rl.Rectangle()
    self._plus_rect = rl.Rectangle()
    self._track_rect = rl.Rectangle()
    self._thumb_rect = rl.Rectangle()

  def _on_result(self, result: DialogResult):
    self._user_callback(result, self._current_val)

  def _value_fraction(self, value: float) -> float:
    return value_fraction(value, self.min_val, self.max_val)

  def _clamp_and_snap(self, val: float) -> float:
    return clamp_and_snap(val, self.min_val, self.max_val, self.step)

  def _update_val_from_mouse(self, mouse_pos: MousePos) -> None:
    self._current_val = update_val_from_mouse(mouse_pos, self._track_rect, self.min_val, self.max_val, self.step)

  def formatted_value(self) -> str:
    return format_adjustor_value(self._current_val, step=self.step, unit=self._unit, labels=self._labels)

  def _handle_mouse_press(self, mouse_pos: MousePos):
    if self._closed:
      return
    self._val_on_press = self._current_val
    for value, preset_rect in self._preset_rects:
      if rl.check_collision_point_rec(mouse_pos, preset_rect):
        self._pressed_zone = f"preset:{value}"
        return
    if rl.check_collision_point_rec(mouse_pos, self._minus_rect):
      self._pressed_zone = "minus"
    elif rl.check_collision_point_rec(mouse_pos, self._plus_rect):
      self._pressed_zone = "plus"
    elif rl.check_collision_point_rec(mouse_pos, _inflate_rect(self._track_rect, 0, 52)):
      self._is_dragging = True
      self._update_val_from_mouse(mouse_pos)

  def _handle_mouse_release(self, mouse_pos: MousePos):
    if self._closed:
      return
    zone, self._pressed_zone = self._pressed_zone, None
    if zone is not None:
      if zone.startswith("preset:"):
        for value, preset_rect in self._preset_rects:
          if zone == f"preset:{value}" and rl.check_collision_point_rec(mouse_pos, preset_rect):
            self._current_val = value
            break
      elif zone == "minus" and rl.check_collision_point_rec(mouse_pos, self._minus_rect):
        self._current_val = self._clamp_and_snap(self._current_val - self.step)
      elif zone == "plus" and rl.check_collision_point_rec(mouse_pos, self._plus_rect):
        self._current_val = self._clamp_and_snap(self._current_val + self.step)
    self._is_dragging = False
    if self._current_val != self._val_on_press and self._on_change:
      self._on_change(self._current_val)

  def _handle_mouse_event(self, mouse_event):
    if self._is_dragging and not self._closed:
      self._update_val_from_mouse(mouse_event.pos)

  def _render_preset_chip(self, rect: rl.Rectangle, text: str, *, current: bool, pressed: bool):
    draw_selectable_chip(rect, text, current=current, pressed=pressed, color=self._color,
                         font_size=40, radius_px=AS.SETTINGS_CARD_RADIUS, padding_x=24)

  def _render_content(self, rect: rl.Rectangle):
    gap, inset = AS.SETTINGS_TILE_GAP, AS.SETTINGS_CARD_INSET
    value_height, chip_height, button_size = 184, AS.MIN_TOUCH, 160
    columns = max(1, min(len(self._presets), int((rect.width + gap) / (240 + gap))))
    rows = math.ceil(len(self._presets) / columns)
    content_height = value_height + gap + (rows * (chip_height + gap) if rows else 0) + button_size
    top = rect.y + max(0, (rect.height - content_height) / 2)
    value_rect = rl.Rectangle(rect.x, top, rect.width, value_height)
    draw_settings_card(value_rect, fill=AS.SETTINGS_CHOICE_FILL, border=AS.SETTINGS_TILE_BORDER)
    draw_centered_text(rl.Rectangle(value_rect.x + inset, value_rect.y, value_rect.width - inset * 2, value_rect.height),
                       self.formatted_value(), 112, self._color)

    self._preset_rects.clear()
    chip_width = (rect.width - (columns - 1) * gap) / columns
    for index, value in enumerate(self._presets):
      row, column = divmod(index, columns)
      chip_rect = snap_rect(rl.Rectangle(rect.x + column * (chip_width + gap), top + value_height + gap + row * (chip_height + gap),
                                        chip_width, chip_height))
      self._preset_rects.append((value, chip_rect))
      self._render_preset_chip(chip_rect, format_adjustor_value(value, step=self.step, unit=self._unit, labels=self._labels),
                               current=abs(self._current_val - value) <= 0.5 * self.step, pressed=self._pressed_zone == f"preset:{value}")

    slider_y = top + content_height - button_size / 2
    self._minus_rect = snap_rect(rl.Rectangle(rect.x, slider_y - button_size / 2, button_size, button_size))
    self._plus_rect = snap_rect(rl.Rectangle(rect.x + rect.width - button_size, slider_y - button_size / 2, button_size, button_size))
    for bounds, zone in ((self._minus_rect, "minus"), (self._plus_rect, "plus")):
      draw_settings_card(bounds, fill=AS.ACCENT_TINT if self._pressed_zone == zone else AS.SETTINGS_CHOICE_FILL,
                          border=AS.ACCENT_EDGE if self._pressed_zone == zone else AS.SETTINGS_TILE_BORDER, radius_px=button_size / 2)
      draw_stepper_symbol(bounds, increment=zone == "plus")
    track_x = self._minus_rect.x + button_size + gap
    track_width = max(1.0, self._plus_rect.x - gap - track_x)
    track_height = 23
    self._track_rect = snap_rect(rl.Rectangle(track_x, slider_y - track_height / 2, track_width, track_height))
    draw_rounded_fill(self._track_rect, AS.TRACK_OFF, radius_px=12)
    for value in self._presets or [self.min_val, (self.min_val + self.max_val) / 2, self.max_val]:
      tick_x = track_x + self._value_fraction(value) * track_width
      rl.draw_rectangle_rec(rl.Rectangle(tick_x - 2, self._track_rect.y - 7, 4, 37), AS.SETTINGS_TILE_BORDER)
    fraction = self._value_fraction(self._current_val)
    if fraction > 0:
      draw_rounded_fill(rl.Rectangle(track_x, self._track_rect.y, fraction * track_width, track_height), self._color, radius_px=12)
    self._thumb_rect = snap_rect(rl.Rectangle(track_x + fraction * track_width - 23, slider_y - 46, 46, 92))
    draw_rounded_fill(self._thumb_rect, AS.TEXT, radius_px=23)


class RadioTileGroup(Widget):
  def __init__(self, title: str, options: list[str], current_index: int, on_change: Callable):
    super().__init__()
    self.title, self.options, self.current_index, self.on_change = title, options, current_index, on_change
    self._font, self._font_title = gui_app.font(FontWeight.BOLD), gui_app.font(FontWeight.NORMAL)
    self._active_color, self._inactive_color = AetherListColors.PRIMARY, rl.Color(80, 80, 80, 255)
    self._pressed_index = -1
    self._option_rects: list[rl.Rectangle] = []
    self._option_offsets: list[float] = []
    self._option_targets: list[float] = []

  def set_index(self, index: int):
    self.current_index = index

  def _handle_mouse_press(self, mouse_pos: MousePos):
    for i, r in enumerate(self._option_rects):
      hit = rl.Rectangle(r.x - GEOMETRY_OFFSET, r.y - GEOMETRY_OFFSET, r.width + 2 * GEOMETRY_OFFSET, r.height + 2 * GEOMETRY_OFFSET)
      if rl.check_collision_point_rec(mouse_pos, hit):
        self._pressed_index = i
        if i < len(self._option_offsets):
          self._option_targets[i] = 1.0
        return

  def _handle_mouse_release(self, mouse_pos: MousePos):
    if self._pressed_index != -1:
      r = self._option_rects[self._pressed_index]
      hit = rl.Rectangle(r.x - GEOMETRY_OFFSET, r.y - GEOMETRY_OFFSET, r.width + 2 * GEOMETRY_OFFSET, r.height + 2 * GEOMETRY_OFFSET)
      if rl.check_collision_point_rec(mouse_pos, hit):
        if self.current_index != self._pressed_index:
          self.current_index = self._pressed_index
          self.on_change(self.current_index)
      if self._pressed_index < len(self._option_targets):
        self._option_targets[self._pressed_index] = 0.0
      self._pressed_index = -1

  def _render(self, rect: rl.Rectangle):
    rect = snap_rect(rect)
    self.set_rect(rect)
    self._option_rects.clear()
    dt = rl.get_frame_time()
    while len(self._option_offsets) < len(self.options):
      self._option_offsets.append(0.0)
      self._option_targets.append(0.0)
    for i in range(len(self._option_offsets)):
      self._option_offsets[i] += (self._option_targets[i] - self._option_offsets[i]) * (1 - math.exp(-dt / PLATE_TAU))
    gap = SPACING.lg
    option_w = (rect.width - max(0, len(self.options) - 1) * gap) / max(1, len(self.options))
    total_width = len(self.options) * option_w + max(0, len(self.options) - 1) * gap
    if self.title:
      title_size = measure_text_cached(self._font_title, self.title, 58)
      rl.draw_text_ex(self._font_title, self.title, rl.Vector2(round(rect.x), round(rect.y + (rect.height - title_size.y) / 2)), 58, 0, rl.WHITE)
      start_x = rect.x + rect.width - total_width
    else:
      start_x = rect.x + (rect.width - total_width) / 2
    for i, opt in enumerate(self.options):
      r = snap_rect(rl.Rectangle(start_x + i * (option_w + gap), rect.y, option_w, rect.height))
      self._option_rects.append(r)
      is_active = i == self.current_index
      fill = mix_colors(rl.Color(28, 32, 40, 255), self._active_color, 0.18 if is_active else 0.05)
      border = with_alpha(self._active_color if is_active else rl.Color(255, 255, 255, 36), 96 if is_active else 28)
      offset = self._option_offsets[i] if i < len(self._option_offsets) else 0.0
      face_x = r.x
      face_y = r.y + min(1.0, offset)
      face_rect = snap_rect(rl.Rectangle(face_x, face_y, r.width, r.height))
      draw_rounded_fill(face_rect, fill, radius_px=23)
      draw_rounded_stroke(face_rect, border, radius_px=23)
      rl.draw_rectangle_rec(rl.Rectangle(face_rect.x, face_rect.y, face_rect.width, 1), rl.Color(255, 255, 255, 16))
      font_size = max(26, min(44, int(r.height * 0.34)))
      spacing = round(font_size * 0.05)
      max_width = r.width - (SPACING.lg + SPACING.xs)
      ts = measure_text_cached(self._font, opt, font_size, spacing=spacing)
      while font_size > 16 and ts.x > max_width:
        font_size -= 1
        spacing = round(font_size * 0.05)
        ts = measure_text_cached(self._font, opt, font_size, spacing=spacing)
      text_pos = rl.Vector2(face_x + (r.width - ts.x) / 2, face_y + (r.height - ts.y) / 2)
      rl.draw_text_ex(self._font, opt, rl.Vector2(round(text_pos.x), round(text_pos.y)), font_size, spacing, AetherListColors.HEADER if is_active else AetherListColors.SUBTEXT)


class AetherMultiSelectTile(AetherTile):
  def __init__(
    self,
    title: str,
    options: dict[str, str],
    get_values: Callable[[], list[str]],
    set_values: Callable[[list[str]], None],
    bg_color: rl.Color | str | None = None,
    is_enabled: Callable[[], bool] | None = None,
    desc: str = "",
  ):
    super().__init__(surface_color=bg_color)
    self.title = title
    self.desc = desc
    self._options = options
    self.get_values = get_values
    self.set_values = set_values
    self.set_enabled(is_enabled or (lambda: True))
    self._font = gui_app.font(FontWeight.BOLD)
    self._font_desc = gui_app.font(FontWeight.MEDIUM)
    self._active_color = self.surface_color
    self._disabled_color = rl.Color(120, 120, 120, 255)

  def _handle_mouse_release(self, mouse_pos: MousePos):
    if self._is_pressed:
      if rl.check_collision_point_rec(mouse_pos, self._hit_rect) and self.enabled:
        def on_close(res, new_values):
          if res == DialogResult.CONFIRM:
            self.set_values(new_values)
        from openpilot.selfdrive.ui.layouts.settings.starpilot.choice_dialog import AetherMultiSelectDialog
        dialog = AetherMultiSelectDialog(
          title=self.title,
          options=self._options,
          current_values=self.get_values(),
          on_close=on_close,
          subtitle=tr(self.desc),
        )
        gui_app.push_widget(dialog)
      self._plate_target = 0.0
      self._is_pressed = False

  def _render(self, rect: rl.Rectangle):
    enabled = self.enabled
    self._animate_plate(rl.get_frame_time())

    if not enabled:
      self._plate_offset = 0.0
      self._plate_target = 0.0

    color = self._active_color if enabled else self._disabled_color
    glow = 0.0
    face, accent = self._render_hud_background(rect, color, glow)
    rx, ry, rw, rh = face.x, face.y, face.width, face.height

    content_pad = SPACING.tile_content
    max_w = rw - content_pad * 2
    text_scale = min(rw / 360.0, rh / 205.0)

    title_size = max(18, int(round(22 * text_scale)))
    draw_text_fit_common(self._font, self.title,
                        rl.Vector2(rx + content_pad, ry + int(rh * 0.15)),
                        max_w, title_size, align_center=True, color=_HUD_TEXT_DIM)

    current_values = self.get_values()
    val_size = max(14, int(round(18 * text_scale)))
    val_color = rl.WHITE if enabled else _HUD_TEXT_DIM

    list_start_y = ry + int(rh * 0.40)
    line_spacing = max(18, int(round(26 * text_scale)))

    for i, val_slug in enumerate(current_values):
      if i >= 4:
        break
      y = list_start_y + i * line_spacing
      name = self._options.get(val_slug, val_slug)
      
      led_cx = rx + content_pad + 10
      led_cy = y + val_size // 2 + 1
      if enabled:
        rl.draw_circle(int(led_cx), int(led_cy), 8, rl.Color(accent.r, accent.g, accent.b, 24))
        rl.draw_circle(int(led_cx), int(led_cy), 4, accent)
      else:
        rl.draw_circle(int(led_cx), int(led_cy), 5, rl.Color(14, 16, 22, 255))
        rl.draw_ring(rl.Vector2(led_cx, led_cy), 3, 4, 0, 360, 24, rl.Color(70, 78, 95, 140))
      
      draw_text_fit_common(self._font_desc, name,
                          rl.Vector2(rx + content_pad + 26, y),
                          max_w - 26, val_size, align_center=False, color=val_color)

class AetherSegmentedControl(Widget):
  """Full-content-width mode selector with one size and type scale at every depth."""

  HEIGHT = AS.SETTINGS_SEGMENTED_HEIGHT
  GAP = AS.SETTINGS_ROW_GAP

  def __init__(
    self,
    options: list[str | Callable[[], str]],
    current_index: int | Callable[[], int],
    on_change: Callable[[int], None],
    statuses: list[str | Callable[[], str] | None] | None = None,
    style: PanelStyle | None = None,
  ):
    super().__init__()
    self._options = options
    self._current_index = current_index
    self._on_change = on_change
    self._statuses = statuses or [""] * len(options)
    if len(self._statuses) < len(self._options):
      self._statuses += [""] * (len(self._options) - len(self._statuses))
    self._style = style
    self._pressed_index = -1
    self._option_rects: list[rl.Rectangle] = []
    self._option_offsets: list[float] = []
    self._option_targets: list[float] = []

  def measure_height(self, width: float | None = None) -> float:
    return float(self.HEIGHT)

  @property
  def _hit_rect(self) -> rl.Rectangle:
    hit_rect = rl.Rectangle(
      self._rect.x - GEOMETRY_OFFSET,
      self._rect.y - GEOMETRY_OFFSET,
      self._rect.width + 2 * GEOMETRY_OFFSET,
      self._rect.height + 2 * GEOMETRY_OFFSET,
    )
    parent_rect = getattr(self, "_parent_rect", None)
    if parent_rect is not None:
      return _intersect_rect(hit_rect, parent_rect)
    return hit_rect

  def _current(self) -> int:
    if callable(self._current_index):
      return max(0, min(len(self._options) - 1, int(self._current_index())))
    return max(0, min(len(self._options) - 1, int(self._current_index)))

  def _handle_mouse_press(self, mouse_pos: MousePos):
    if not self._touch_valid():
      return
    for i, r in enumerate(self._option_rects):
      hit = rl.Rectangle(r.x - GEOMETRY_OFFSET, r.y - GEOMETRY_OFFSET, r.width + 2 * GEOMETRY_OFFSET, r.height + 2 * GEOMETRY_OFFSET)
      if rl.check_collision_point_rec(mouse_pos, hit):
        self._pressed_index = i
        while len(self._option_targets) < len(self._options):
          self._option_offsets.append(0.0)
          self._option_targets.append(0.0)
        self._option_targets[i] = 1.0
        return

  def _handle_mouse_release(self, mouse_pos: MousePos):
    if self._pressed_index == -1:
      return
    pressed_index = self._pressed_index
    self._pressed_index = -1
    if pressed_index < len(self._option_targets):
      self._option_targets[pressed_index] = 0.0
    if not self._touch_valid():
      return
    r = self._option_rects[pressed_index]
    hit = rl.Rectangle(r.x - GEOMETRY_OFFSET, r.y - GEOMETRY_OFFSET, r.width + 2 * GEOMETRY_OFFSET, r.height + 2 * GEOMETRY_OFFSET)
    if rl.check_collision_point_rec(mouse_pos, hit) and self._current() != pressed_index:
      self._on_change(pressed_index)

  def _handle_mouse_event(self, mouse_event: MouseEvent):
    if self._pressed_index == -1:
      return
    if not self._touch_valid():
      if self._pressed_index < len(self._option_targets):
        self._option_targets[self._pressed_index] = 0.0
      self._pressed_index = -1
      return
    if self._pressed_index < len(self._option_rects):
      r = self._option_rects[self._pressed_index]
      hit = rl.Rectangle(r.x - GEOMETRY_OFFSET, r.y - GEOMETRY_OFFSET, r.width + 2 * GEOMETRY_OFFSET, r.height + 2 * GEOMETRY_OFFSET)
      if not rl.check_collision_point_rec(mouse_event.pos, hit):
        if self._pressed_index < len(self._option_targets):
          self._option_targets[self._pressed_index] = 0.0
        self._pressed_index = -1

  def _render(self, rect: rl.Rectangle):
    rect = snap_rect(rl.Rectangle(rect.x, rect.y, rect.width, self.measure_height(rect.width)))
    self.set_rect(rect)
    self._option_rects.clear()

    if not self._touch_valid() and self._pressed_index != -1:
      if self._pressed_index < len(self._option_targets):
        self._option_targets[self._pressed_index] = 0.0
      self._pressed_index = -1

    dt = rl.get_frame_time()
    while len(self._option_offsets) < len(self._options):
      self._option_offsets.append(0.0)
      self._option_targets.append(0.0)
    for i in range(len(self._option_offsets)):
      self._option_offsets[i] += (self._option_targets[i] - self._option_offsets[i]) * (1 - math.exp(-dt / PLATE_TAU))

    radius_px = min(AS.SETTINGS_CARD_RADIUS, rect.width / 2, rect.height / 2)
    draw_settings_card(rect, border=AS.SETTINGS_TILE_BORDER, radius_px=radius_px)

    # Concentric corners keep the segment inside the shared card's outline,
    # including the one-pixel movement when pressed.
    inner_pad = AS.SETTINGS_SEGMENTED_INSET
    inner_radius = max(0.0, radius_px - inner_pad)
    gap = AS.SETTINGS_SEGMENTED_GAP
    inner_rect = _inset_rect(rect, inner_pad)
    option_w = (inner_rect.width - max(0, len(self._options) - 1) * gap) / max(1, len(self._options))
    has_status = any(str(_resolve_value(status, "")) for status in self._statuses)
    current_index = self._current()

    for i, option in enumerate(self._options):
      base_rect = snap_rect(rl.Rectangle(inner_rect.x + i * (option_w + gap), inner_rect.y, option_w, inner_rect.height))
      self._option_rects.append(base_rect)
      offset = self._option_offsets[i] if i < len(self._option_offsets) else 0.0
      face_rect = snap_rect(rl.Rectangle(base_rect.x, base_rect.y + min(1.0, offset), base_rect.width, base_rect.height))
      is_active = i == current_index

      if self._style is not None:
        accent = self._style.accent
        fill = mix_colors(rl.Color(18, 22, 28, 255), accent, 0.16, alpha=255) if is_active else rl.Color(255, 255, 255, 3)
        border = with_alpha(accent, 72) if is_active else rl.Color(255, 255, 255, 8)
        title_color = accent if is_active else AetherListColors.SUBTEXT
        status_color = mix_colors(accent, AetherListColors.HEADER, 0.4) if is_active else AetherListColors.MUTED
      else:
        fill = rl.Color(255, 255, 255, 12) if is_active else rl.Color(255, 255, 255, 3)
        border = rl.Color(255, 255, 255, 30) if is_active else rl.Color(255, 255, 255, 8)
        title_color = AetherListColors.HEADER if is_active else AetherListColors.SUBTEXT
        status_color = AetherListColors.MUTED

      aether_fill(face_rect, fill, inner_radius)
      _draw_card_outline(face_rect, border, inner_radius, width=1)

      label = str(_resolve_value(option, ""))
      status = str(_resolve_value(self._statuses[i], ""))
      title_size = AS.SETTINGS_SEGMENTED_FONT_SIZE
      status_size = AS.SETTINGS_SEGMENTED_STATUS_FONT_SIZE
      title_height = title_size * FONT_SCALE
      status_height = status_size * FONT_SCALE
      text_height = title_height + (AS.SETTINGS_TEXT_GAP + status_height if has_status else 0)
      title_y = face_rect.y + (face_rect.height - text_height) / 2
      text_x = face_rect.x + AS.SETTINGS_SEGMENTED_TEXT_INSET
      text_width = max(1.0, face_rect.width - AS.SETTINGS_SEGMENTED_TEXT_INSET * 2)
      # Elide unusually long labels instead of changing typography for one option.
      gui_label(rl.Rectangle(text_x, title_y, text_width, title_height), label, title_size, title_color,
                FontWeight.MEDIUM, alignment=rl.GuiTextAlignment.TEXT_ALIGN_CENTER)
      if has_status:
        status_y = title_y + title_height + AS.SETTINGS_TEXT_GAP
        gui_label(rl.Rectangle(text_x, status_y, text_width, status_height), status, status_size, status_color,
                  FontWeight.NORMAL, alignment=rl.GuiTextAlignment.TEXT_ALIGN_CENTER)


class TileGrid(Widget):
  def __init__(self, columns: int | None = None, padding: int | None = None, uniform_width: bool = False,
               min_tile_width: int | None = None, tile_height: float | None = None, force_square: bool = False,
               carousel_rows: int | None = None, carousel_tile_width: float | None = None,
               min_tile_height: float | None = None, max_tile_height: float | None = None, align_top: bool = False):
    super().__init__()
    self._columns = columns
    self._gap = padding if padding is not None else SPACING.tile_gap
    self.tiles = []
    self._uniform_width = uniform_width
    self._min_tile_width = min_tile_width if min_tile_width is not None else MIN_TILE_WIDTH
    self._tile_height = tile_height
    self.force_square = force_square
    self.carousel_rows = carousel_rows
    self.carousel_tile_width = carousel_tile_width
    self.min_tile_height = min_tile_height
    self.max_tile_height = max_tile_height
    self.align_top = align_top


  @property
  def gap(self) -> int:
    return self._gap

  def add_tile(self, tile: Widget):
    self.tiles.append(tile)
    touch_valid_callback = getattr(self, "_touch_valid_callback", None)
    if touch_valid_callback is not None and hasattr(tile, "set_touch_valid_callback"):
      tile.set_touch_valid_callback(touch_valid_callback)

  def set_touch_valid_callback(self, touch_callback: Callable[[], bool]) -> None:
    super().set_touch_valid_callback(touch_callback)
    for tile in self.tiles:
      if hasattr(tile, "set_touch_valid_callback"):
        tile.set_touch_valid_callback(touch_callback)

  def clear(self):
    self.tiles.clear()

  def get_column_count(self, tile_count: int | None = None) -> int:
    count = len(self.tiles) if tile_count is None else tile_count
    if count <= 0:
      return self._columns or 1
    if self._columns is not None:
      return self._columns
    if count == 1:
      return 1
    if count == 2:
      return 2
    if count == 3:
      return 3
    if count == 4:
      return 2
    if count <= 6:
      return 3
    return 4

  def get_effective_column_count(self, available_width: float | None = None, tile_count: int | None = None) -> int:
    count = len(self.tiles) if tile_count is None else tile_count
    preferred = self.get_column_count(count)
    if available_width is None or available_width <= 0:
      return preferred
    min_tile_width = max(1, self._min_tile_width)
    max_cols_by_width = max(1, int((available_width + self._gap) / (min_tile_width + self._gap)))
    limit_by_count = count if self._columns is None else preferred
    return max(1, min(preferred, limit_by_count, max_cols_by_width))

  def get_row_count(self, tile_count: int | None = None, available_width: float | None = None) -> int:
    count = len(self.tiles) if tile_count is None else tile_count
    if count <= 0:
      return 0
    cols = self.get_effective_column_count(available_width, count)
    return (count + cols - 1) // cols

  def get_internal_gap_height(self, tile_count: int | None = None, available_width: float | None = None) -> float:
    rows = self.get_row_count(tile_count, available_width=available_width)
    return self._gap * max(0, rows - 1)

  def measure_height(self, width: float) -> float:
    if not self.tiles:
      return 0.0
    count = len(self.tiles)
    if self.carousel_rows and self.carousel_tile_width:
      rows = self.carousel_rows
      h = self._tile_height if self._tile_height is not None else 130.0
      return rows * h + self._gap * max(0, rows - 1)
      
    rows = self.get_row_count(count, available_width=width)
    if self.force_square:
      cols = self.get_effective_column_count(width, count)
      col_w = (width - (self._gap * (cols - 1))) / cols
      h = col_w
      if self.min_tile_height is not None:
        h = max(self.min_tile_height, h)
      if self.max_tile_height is not None:
        h = min(self.max_tile_height, h)
    else:
      if self._tile_height is not None:
        h = self._tile_height
      else:
        h = 140.0 if rows == 1 else (160.0 if rows == 2 else 180.0)
        if self.min_tile_height is not None:
          h = max(h, self.min_tile_height)
        if self.max_tile_height is not None:
          h = min(h, self.max_tile_height)
    return rows * h + self.get_internal_gap_height(count, available_width=width)

  def measure_width(self) -> float:
    if not self.tiles:
      return 0.0
    if not self.carousel_rows or not self.carousel_tile_width:
      return 0.0
    count = len(self.tiles)
    cols = (count + self.carousel_rows - 1) // self.carousel_rows
    return cols * self.carousel_tile_width + max(0, cols - 1) * self._gap

  def _render(self, rect: rl.Rectangle):
    rect = snap_rect(rect)
    self.set_rect(rect)
    if not self.tiles:
      return
    tiles_to_render = list(self.tiles)
    count = len(tiles_to_render)
    
    if self.carousel_rows and self.carousel_tile_width:
      rows = self.carousel_rows
      cols = (count + rows - 1) // rows
      tile_w = self.carousel_tile_width
      tile_h = self._tile_height if self._tile_height is not None else (rect.height - self._gap * (rows - 1)) / rows
      
      for i, tile in enumerate(tiles_to_render):
        c = i // rows
        r = i % rows
        row_x = rect.x + c * (tile_w + self._gap)
        row_y = rect.y + r * (tile_h + self._gap)
        
        parent_rect = getattr(self, "_parent_rect", None)
        if parent_rect is not None and hasattr(tile, "set_parent_rect"):
          tile.set_parent_rect(parent_rect)
        tile.render(snap_rect(rl.Rectangle(row_x, row_y, tile_w, tile_h)))
      return

    cols = self.get_effective_column_count(rect.width, count)
    rows = self.get_row_count(count, available_width=rect.width)

    if self.force_square:
      uniform_tile_w = (rect.width - (self._gap * (cols - 1))) / cols
      tile_h = uniform_tile_w
      if self.min_tile_height is not None:
        tile_h = max(self.min_tile_height, tile_h)
      if self.max_tile_height is not None:
        tile_h = min(self.max_tile_height, tile_h)
      uniform_tile_w = tile_h
    else:
      if self._tile_height is not None:
        tile_h = self._tile_height
      else:
        tile_h = (rect.height - (self._gap * (rows - 1))) / rows
        if self.min_tile_height is not None:
          tile_h = max(self.min_tile_height, tile_h)
        if self.max_tile_height is not None:
          tile_h = min(self.max_tile_height, tile_h)
      uniform_tile_w = (rect.width - (self._gap * (cols - 1))) / cols if self._uniform_width else 0
    content_height = rows * tile_h + max(0, rows - 1) * self._gap
    y_offset = (rect.height - content_height) / 2 if content_height < rect.height and not self.align_top else 0
    tile_idx = 0
    for r in range(rows):
      remaining = count - tile_idx
      if remaining <= 0:
        break
      items_in_row = min(cols, remaining)
      if self.force_square or self._uniform_width:
        row_tile_w = uniform_tile_w
        row_width = row_tile_w * items_in_row + self._gap * (items_in_row - 1)
        row_x = rect.x + (rect.width - row_width) / 2
      else:
        row_tile_w = (rect.width - (self._gap * (items_in_row - 1))) / items_in_row
        row_x = rect.x
      for c in range(items_in_row):
        tile = tiles_to_render[tile_idx]
        parent_rect = getattr(self, "_parent_rect", None)
        if parent_rect is not None and hasattr(tile, "set_parent_rect"):
          tile.set_parent_rect(parent_rect)
        tile.render(snap_rect(rl.Rectangle(row_x + c * (row_tile_w + self._gap), rect.y + y_offset + r * (tile_h + self._gap), row_tile_w, tile_h)))
        tile_idx += 1


class HubGrid(TileGrid):
  """Category cards keep their height and top alignment even in small folders."""

  def __init__(self, *, columns: int | None = None, padding: int = SPACING.tile_gap):
    super().__init__(columns=columns, padding=padding, min_tile_height=320, max_tile_height=AS.SETTINGS_HUB_TILE_HEIGHT, align_top=True)
