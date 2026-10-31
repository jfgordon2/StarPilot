"""Drawing primitives shared by every Essentials component."""
from __future__ import annotations

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
# Glyphs the components need are drawn as strokes so they don't depend on exported assets.

def _stroke_width(box: rl.Rectangle) -> float:
  return max(3.0, box.width * 0.11)


def chevron(rect: rl.Rectangle, color: rl.Color, size: float, direction: str = "right") -> None:
  box = place(rect, size, size)
  w = _stroke_width(box)
  cx, cy, r = box.x + box.width / 2, box.y + box.height / 2, box.width * 0.3
  tip, tail = {"right": ((r * 0.6, 0), (-r * 0.6, r)), "left": ((-r * 0.6, 0), (r * 0.6, r)),
               "down": ((0, r * 0.6), (r, -r * 0.6)), "up": ((0, -r * 0.6), (r, r * 0.6))}[direction]
  a = rl.Vector2(cx + tip[0], cy + tip[1])
  if direction in ("right", "left"):
    ends = (rl.Vector2(cx + tail[0], cy - tail[1]), rl.Vector2(cx + tail[0], cy + tail[1]))
  else:
    ends = (rl.Vector2(cx - tail[0], cy + tail[1]), rl.Vector2(cx + tail[0], cy + tail[1]))
  for end in ends:
    rl.draw_line_ex(end, a, w, color)
    rl.draw_circle_v(end, w / 2, color)
  rl.draw_circle_v(a, w / 2, color)


def cross(rect: rl.Rectangle, color: rl.Color, size: float) -> None:
  box = place(rect, size * 0.5, size * 0.5)
  w = _stroke_width(rl.Rectangle(0, 0, size, size))
  rl.draw_line_ex(rl.Vector2(box.x, box.y), rl.Vector2(box.x + box.width, box.y + box.height), w, color)
  rl.draw_line_ex(rl.Vector2(box.x + box.width, box.y), rl.Vector2(box.x, box.y + box.height), w, color)


def plus(rect: rl.Rectangle, color: rl.Color, size: float, vertical: bool = True) -> None:
  box = place(rect, size * 0.5, size * 0.5)
  w = _stroke_width(rl.Rectangle(0, 0, size, size))
  cx, cy = box.x + box.width / 2, box.y + box.height / 2
  rl.draw_line_ex(rl.Vector2(box.x, cy), rl.Vector2(box.x + box.width, cy), w, color)
  if vertical:
    rl.draw_line_ex(rl.Vector2(cx, box.y), rl.Vector2(cx, box.y + box.height), w, color)


def minus(rect: rl.Rectangle, color: rl.Color, size: float) -> None:
  plus(rect, color, size, vertical=False)


def check(rect: rl.Rectangle, color: rl.Color, size: float) -> None:
  box = place(rect, size, size)
  w = _stroke_width(box)
  p1 = rl.Vector2(box.x + box.width * 0.2, box.y + box.height * 0.52)
  p2 = rl.Vector2(box.x + box.width * 0.42, box.y + box.height * 0.72)
  p3 = rl.Vector2(box.x + box.width * 0.8, box.y + box.height * 0.3)
  rl.draw_line_ex(p1, p2, w, color)
  rl.draw_line_ex(p2, p3, w, color)
  for p in (p1, p2, p3):
    rl.draw_circle_v(p, w / 2, color)


def icon(rect: rl.Rectangle, name: str, color: rl.Color, size: float) -> None:
  """A white PNG from selfdrive/assets/icons, tinted and centered in rect."""
  texture = gui_app.texture(f"icons/{name}.png", int(size), int(size))
  box = place(rect, texture.width, texture.height)
  rl.draw_texture(texture, int(box.x), int(box.y), color)
