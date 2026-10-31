"""Line icons for the onroad bar and status chips, drawn with raylib so they scale with no textures."""
from __future__ import annotations

import math

import pyray as rl

from openpilot.selfdrive.ui.tandem import draw
from openpilot.selfdrive.ui.tandem.layout import place


def _box(rect: rl.Rectangle, size: float) -> tuple[float, float, float, float]:
  b = place(rect, size, size)
  return b.x, b.y, b.width, max(1.5, size * 0.09)


def _line(points: list[tuple[float, float]], x: float, y: float, s: float, width: float, color: rl.Color) -> None:
  for (x0, y0), (x1, y1) in zip(points, points[1:], strict=False):
    rl.draw_line_ex(rl.Vector2(x + x0 * s, y + y0 * s), rl.Vector2(x + x1 * s, y + y1 * s), width, color)


def _wheel(x: float, y: float, s: float, w: float, color: rl.Color) -> None:
  c = rl.Vector2(x + s / 2, y + s / 2)
  rl.draw_ring(c, s * 0.42 - w, s * 0.42, 0, 360, 36, color)
  rl.draw_ring(c, s * 0.1, s * 0.1 + w, 0, 360, 24, color)
  _line([(0.08, 0.45), (0.4, 0.45)], x, y, s, w, color)
  _line([(0.6, 0.45), (0.92, 0.45)], x, y, s, w, color)
  _line([(0.5, 0.6), (0.5, 0.92)], x, y, s, w, color)


def _car(x: float, y: float, s: float, w: float, color: rl.Color) -> None:
  _line([(0.18, 0.62), (0.28, 0.32), (0.72, 0.32), (0.82, 0.62)], x, y, s, w, color)
  draw.stroke(rl.Rectangle(x + s * 0.12, y + s * 0.6, s * 0.76, s * 0.2), color, s * 0.06, w)


def icon(name: str, rect: rl.Rectangle, color: rl.Color, size: float) -> None:
  x, y, s, w = _box(rect, size)
  if name == "menu":
    for fy in (0.28, 0.5, 0.72):
      _line([(0.18, fy), (0.82, fy)], x, y, s, w, color)
  elif name in ("wheel", "wheel_pause"):
    _wheel(x, y, s * (0.8 if name == "wheel_pause" else 1), w, color)
    if name == "wheel_pause":
      _line([(0.86, 0.6), (0.86, 0.95)], x, y, s, w, color)
      _line([(0.98, 0.6), (0.98, 0.95)], x, y, s, w, color)
  elif name == "road":
    _line([(0.3, 0.9), (0.45, 0.1)], x, y, s, w, color)
    _line([(0.7, 0.9), (0.55, 0.1)], x, y, s, w, color)
    for fy in (0.3, 0.55, 0.8):
      _line([(0.5, fy - 0.08), (0.5, fy)], x, y, s, w, color)
  elif name == "curve":
    _line([(0.15, 0.85), (0.4, 0.7), (0.6, 0.45), (0.85, 0.15)], x, y, s, w, color)
  elif name in ("light_red", "light_green"):
    draw.stroke(rl.Rectangle(x + s * 0.3, y + s * 0.05, s * 0.4, s * 0.9), color, s * 0.12, w)
    lit = 0.25 if name == "light_red" else 0.75
    for fy in (0.25, 0.5, 0.75):
      c = rl.Vector2(x + s * 0.5, y + s * fy)
      if fy == lit:
        rl.draw_circle_v(c, s * 0.1, color)
      else:
        rl.draw_ring(c, s * 0.1 - w * 0.6, s * 0.1, 0, 360, 20, color)
  elif name == "stop_sign":
    pts = [(0.5 + 0.42 * math.cos(math.radians(22.5 + 45 * i)), 0.5 + 0.42 * math.sin(math.radians(22.5 + 45 * i))) for i in range(9)]
    _line(pts, x, y, s, w, color)
  elif name in ("car", "car_up"):
    _car(x, y + (s * 0.08 if name == "car_up" else 0), s, w, color)
    if name == "car_up":
      _line([(0.38, 0.2), (0.5, 0.05), (0.62, 0.2)], x, y, s, w, color)
  elif name == "turn":
    _line([(0.3, 0.9), (0.3, 0.45), (0.7, 0.45)], x, y, s, w, color)
    _line([(0.58, 0.32), (0.72, 0.45), (0.58, 0.58)], x, y, s, w, color)
  elif name == "gauge":
    rl.draw_ring(rl.Vector2(x + s / 2, y + s * 0.62), s * 0.4 - w, s * 0.4, 180, 360, 30, color)
    _line([(0.5, 0.62), (0.7, 0.36)], x, y, s, w, color)
  elif name == "rain":
    _line([(0.2, 0.5), (0.25, 0.3), (0.45, 0.2), (0.62, 0.28), (0.8, 0.3), (0.85, 0.5), (0.2, 0.5)], x, y, s, w, color)
    for fx in (0.3, 0.5, 0.7):
      _line([(fx, 0.62), (fx - 0.06, 0.82)], x, y, s, w, color)
  elif name == "signal":
    _line([(0.45, 0.25), (0.2, 0.5), (0.45, 0.75)], x, y, s, w, color)
    _line([(0.75, 0.25), (0.5, 0.5), (0.75, 0.75)], x, y, s, w, color)
  elif name in ("lane_left", "lane_right"):
    flip = name == "lane_left"
    pts = [(0.3, 0.9), (0.3, 0.55), (0.7, 0.25), (0.7, 0.1)]
    _line([(1 - px, py) if flip else (px, py) for px, py in pts], x, y, s, w, color)
    head = [(0.56, 0.22), (0.7, 0.08), (0.84, 0.22)]
    _line([(1 - px, py) if flip else (px, py) for px, py in head], x, y, s, w, color)
  elif name == "lane_blocked":
    _line([(0.25, 0.1), (0.25, 0.9)], x, y, s, w, color)
    _line([(0.55, 0.3), (0.85, 0.6)], x, y, s, w, color)
    _line([(0.85, 0.3), (0.55, 0.6)], x, y, s, w, color)
  elif name == "navigate":
    _line([(0.15, 0.48), (0.85, 0.15), (0.52, 0.85), (0.45, 0.55), (0.15, 0.48)], x, y, s, w, color)
  elif name == "download":
    _line([(0.5, 0.12), (0.5, 0.66)], x, y, s, w, color)
    _line([(0.3, 0.46), (0.5, 0.66), (0.7, 0.46)], x, y, s, w, color)
    _line([(0.2, 0.86), (0.8, 0.86)], x, y, s, w, color)
  elif name == "play":
    pts = [(0.32, 0.2), (0.78, 0.5), (0.32, 0.8), (0.32, 0.2)]
    _line(pts, x, y, s, w, color)
