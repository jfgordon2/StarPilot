"""Drawing primitives shared by every Essentials component."""
from __future__ import annotations

from pathlib import Path

import pyray as rl

from openpilot.system.ui.lib.application import FONT_SCALE, gui_app
from openpilot.system.ui.lib.text_measure import measure_text_cached
from openpilot.system.ui.lib.wrap_text import wrap_text
from openpilot.selfdrive.ui.tandem import tokens as T
from openpilot.selfdrive.ui.tandem.fonts import Face, font
from openpilot.selfdrive.ui.tandem.layout import Align, place

SEGMENTS = 16
ELLIPSIS = "…"


def alpha(color: rl.Color, factor: float) -> rl.Color:
  return rl.Color(color.r, color.g, color.b, int(color.a * factor))


def _roundness(rect: rl.Rectangle, radius: float) -> float:
  short = min(rect.width, rect.height)
  return 0.0 if short <= 0 or radius <= 0 else min(1.0, 2 * radius / short)


def fill(rect: rl.Rectangle, color: rl.Color, radius: float = 0) -> None:
  if radius <= 0:
    rl.draw_rectangle_rec(rect, color)
  else:
    rl.draw_rectangle_rounded(rect, _roundness(rect, radius), SEGMENTS, color)


def stroke(rect: rl.Rectangle, color: rl.Color, radius: float = 0, width: float = T.DIVIDER) -> None:
  rl.draw_rectangle_rounded_lines_ex(rect, _roundness(rect, radius), SEGMENTS, width, color)


def gradient_v(rect: rl.Rectangle, top: rl.Color, bottom: rl.Color) -> None:
  rl.draw_rectangle_gradient_v(int(rect.x), int(rect.y), int(rect.width), int(rect.height), top, bottom)


def hline(x: float, y: float, width: float, color: rl.Color = T.CONTROL) -> None:
  rl.draw_rectangle_rec(rl.Rectangle(x, y, width, T.DIVIDER), color)


def pressed(rect: rl.Rectangle, radius: float = 0) -> None:
  fill(rect, T.PRESSED_OVERLAY, radius)


# ── Text ──

def text_width(text: str, size: int, weight: Face = T.FONT, tracking: float = 0) -> float:
  return measure_text_cached(font(weight), text, size, tracking).x


def line_height(size: int) -> float:
  return size * FONT_SCALE


def fit(text: str, size: int, weight: Face, max_width: float, tracking: float = 0) -> str:
  max_width += 0.5  # layout math leaves float error; text measured for a rect must still fit in it
  if text_width(text, size, weight, tracking) <= max_width:
    return text
  while text and text_width(text + ELLIPSIS, size, weight, tracking) > max_width:
    text = text[:-1]
  return text.rstrip() + ELLIPSIS if text else ""


def text(rect: rl.Rectangle, value: str, size: int, color: rl.Color, weight: Face = T.FONT,
         h: Align = Align.START, v: Align = Align.CENTER, tracking: float = 0, elide: bool = True) -> float:
  """Draw one line inside rect. Returns the drawn width."""
  if elide:
    value = fit(value, size, weight, rect.width, tracking)
  width = text_width(value, size, weight, tracking)
  box = place(rect, width, line_height(size), h, v)
  rl.draw_text_ex(font(weight), value, rl.Vector2(round(box.x), round(box.y)), size, tracking, color)
  return width


def caption(rect: rl.Rectangle, value: str, color: rl.Color = T.TEXT_MUTED, h: Align = Align.START, v: Align = Align.CENTER) -> float:
  """Section labels: small bold capitals with tracking."""
  return text(rect, value.upper(), T.SIZE_CAPTION, color, T.FONT_BOLD, h, v, tracking=T.CAPTION_TRACKING)


def paragraph_lines(value: str, size: int, weight: Face, width: float) -> list[str]:
  return wrap_text(font(weight), value, size, int(width))


def paragraph_height(value: str, size: int, weight: Face, width: float, spacing: float = 1.3) -> float:
  return len(paragraph_lines(value, size, weight, width)) * line_height(size) * spacing


def paragraph(rect: rl.Rectangle, value: str, size: int, color: rl.Color, weight: Face = T.FONT, spacing: float = 1.3) -> float:
  """Wrapped text from the top of rect. Returns the height used."""
  y = rect.y
  step = line_height(size) * spacing
  for line in paragraph_lines(value, size, weight, rect.width):
    rl.draw_text_ex(font(weight), line, rl.Vector2(round(rect.x), round(y)), size, 0, color)
    y += step
  return y - rect.y


# ── Icons ──
# Line icons from the design mocks, rasterized to white PNGs in icons/ (tools/build_icons.js) and tinted here.
# size is the icon's box, as the mocks size their SVGs; the strokes keep the mock's weight at any size.

ICON_DIR = Path(__file__).resolve().parent / "icons"
MIRRORED = {"lane_left": "lane_right"}   # drawn from another icon, flipped


def icon(rect: rl.Rectangle, name: str, color: rl.Color, size: float) -> None:
  """A mock icon by name (icons/svg/<name>.svg), tinted and centered in rect."""
  flip = name in MIRRORED
  texture = gui_app.texture((ICON_DIR / f"{MIRRORED.get(name, name)}.png").as_posix(), int(size), int(size), flip_x=flip)
  box = place(rect, texture.width, texture.height)
  rl.draw_texture_pro(texture, rl.Rectangle(0, 0, texture.width, texture.height), rl.Rectangle(round(box.x), round(box.y), texture.width,
                      texture.height), rl.Vector2(0, 0), 0, color)


def chevron(rect: rl.Rectangle, color: rl.Color, size: float, direction: str = "right") -> None:
  icon(rect, "chevron" if direction == "right" else "back", color, size)


def cross(rect: rl.Rectangle, color: rl.Color, size: float) -> None:
  icon(rect, "close", color, size)


def plus(rect: rl.Rectangle, color: rl.Color, size: float) -> None:
  icon(rect, "plus", color, size)


def minus(rect: rl.Rectangle, color: rl.Color, size: float) -> None:
  box = place(rect, size * 0.58, size)   # the plus icon's bar, which has no icon of its own
  w = max(2.0, size / 12)
  ends = rl.Vector2(box.x, box.y + size / 2), rl.Vector2(box.x + box.width, box.y + size / 2)
  rl.draw_line_ex(*ends, w, color)
  for end in ends:
    rl.draw_circle_v(end, w / 2, color)


def check(rect: rl.Rectangle, color: rl.Color, size: float) -> None:
  icon(rect, "check", color, size)
