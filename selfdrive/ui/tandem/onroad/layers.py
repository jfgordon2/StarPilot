"""Essentials onroad layers: the bottom bar, the status chip, the steering headroom arc and the new-limit card.

Each layer reads a small state object through a getter and calls plain callbacks, so it draws the same with real
messages on the device and with made-up state in tests and renders.
"""
from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

import pyray as rl

from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.base import Component
from openpilot.selfdrive.ui.tandem.controls import Button, ButtonStyle
from openpilot.selfdrive.ui.tandem.layout import FILL, Align, column, inset, place, row
from openpilot.selfdrive.ui.tandem.onroad.status import Chip, ChipTone

BAR_HEIGHT = T.px(74)
BAR_MARGIN = T.px(16)
BAR_ZONE = BAR_HEIGHT + BAR_MARGIN * 2          # space the bar takes at the bottom of the road view
CONTROL_FILL = draw.alpha(T.CONTROL_NAV, 0.8)    # 80% so controls stay readable over bright scenes
ENGAGED = T.SUCCESS


@dataclass
class BarState:
  engaged: bool = False
  can_engage: bool = False
  set_speed: float = 0.0          # display units; 0 when cruise isn't set
  unit: str = "mph"
  street: str = ""
  navigating: bool = False
  arrive: str = ""                # e.g. "4:52 PM"
  left: str = ""                  # e.g. "12 min · 8.4 mi"


def _glyph_button(name: str, on_click: Callable[[], None]) -> Button:
  return Button(on_click=on_click, style=ButtonStyle.NAV, height=BAR_HEIGHT, width=BAR_HEIGHT, radius=T.RADIUS_CARD,
                glyph=lambda r, c, s: draw.icon(r, name, c, T.px(28)))


class OnroadBar(Component):
  """Menu, MAX − / +, the street name (with arrival, time left and End route while navigating), and engage."""
  grow_touch_target = False

  def __init__(self, state: Callable[[], BarState], on_menu: Callable[[], None], on_speed: Callable[[int], None],
               on_engage: Callable[[], None], on_end_route: Callable[[], None]):
    super().__init__()
    self._state = state
    self._menu = self._child(_glyph_button("menu", on_menu))
    self._minus = self._child(Button("−", lambda: on_speed(-1), ButtonStyle.GHOST, height=BAR_HEIGHT, width=T.px(56),
                                     font_size=T.font_px(30)))
    self._plus = self._child(Button("+", lambda: on_speed(1), ButtonStyle.GHOST, height=BAR_HEIGHT, width=T.px(56),
                                    font_size=T.font_px(30)))
    # Ghost style, so the fill drawn below (green while engaged) shows through.
    self._engage = self._child(Button(on_click=on_engage, style=ButtonStyle.GHOST, height=BAR_HEIGHT, width=BAR_HEIGHT,
                                      radius=T.RADIUS_CARD, glyph=lambda r, c, s: draw.icon(r, "wheel", T.TEXT, T.px(32))))
    self._end = self._child(Button("End route", on_end_route, ButtonStyle.DANGER_SOFT, height=T.px(52), font_size=T.font_px(17)))
    for b in (self._minus, self._plus):
      b.set_enabled(lambda: self._state().engaged and self._state().set_speed > 0)

  def rects(self, rect: rl.Rectangle) -> dict[str, rl.Rectangle]:
    body = rl.Rectangle(rect.x + BAR_MARGIN, rect.y + rect.height - BAR_MARGIN - BAR_HEIGHT, rect.width - BAR_MARGIN * 2, BAR_HEIGHT)
    menu, speed, center, engage = row(body, [BAR_HEIGHT, T.px(194), FILL, BAR_HEIGHT], T.px(12))
    return {"menu": menu, "speed": speed, "center": center, "engage": engage}

  def hit_rects(self, rect: rl.Rectangle) -> list[rl.Rectangle]:
    return list(self.rects(rect).values())

  def _render(self, rect: rl.Rectangle):
    state = self._state()
    zone = rl.Rectangle(rect.x, rect.y + rect.height - BAR_ZONE * 1.6, rect.width, BAR_ZONE * 1.6)
    draw.gradient_v(zone, draw.alpha(T.BG, 0.0), draw.alpha(T.BG, 0.55))   # a scrim, not a panel: the road stays visible
    r = self.rects(rect)
    self._menu.render(r["menu"])

    draw.fill(r["speed"], CONTROL_FILL, T.RADIUS_CARD)
    minus, value, plus = row(r["speed"], [T.px(56), FILL, T.px(56)])
    self._minus.render(minus)
    self._plus.render(plus)
    label, number = column(place(value, value.width, T.px(56)), [T.px(18), FILL])
    draw.text(label, "MAX", T.font_px(13), T.ACCENT_TEXT, T.FONT_BOLD, Align.CENTER)
    draw.text(number, f"{state.set_speed:.0f}" if state.set_speed else "–", T.font_px(26), T.TEXT, T.FONT_EXTRABOLD, Align.CENTER)

    center = r["center"]
    draw.fill(center, CONTROL_FILL, T.RADIUS_CARD)
    if state.navigating:
      # Arrival and time left at the left, then the street name in what's left, then End route.
      body = inset(center, x=T.px(22))
      w, _ = self._end.preferred_size(body.width)
      self._end.render(place(body, w, T.px(52), Align.END))
      body = inset(body, right=w + T.px(20))
      x = body.x
      for caption, text in (("ARRIVE", state.arrive or "–"), ("LEFT", state.left or "–")):
        cell_w = max(draw.text_width(caption, T.SIZE_CAPTION, T.FONT_BOLD, tracking=T.CAPTION_TRACKING), draw.text_width(text, T.font_px(22), T.FONT_BOLD))
        top, bottom = column(place(rl.Rectangle(x, body.y, cell_w, body.height), cell_w, T.px(56)), [T.px(18), FILL], T.px(3))
        draw.caption(top, caption)
        draw.text(bottom, text, T.font_px(22), T.TEXT, T.FONT_BOLD)
        x += cell_w + T.px(24)
      if state.street and x + T.px(80) < body.x + body.width:
        rl.draw_rectangle_rec(rl.Rectangle(x, body.y + body.height * 0.25, T.DIVIDER, body.height * 0.5), T.CONTROL)
        self._street(rl.Rectangle(x + T.px(22), body.y, body.x + body.width - x - T.px(22), body.height), state.street, Align.START)
    elif state.street:
      self._street(inset(center, x=T.px(16)), state.street, Align.CENTER)

    engage = r["engage"]
    draw.fill(engage, ENGAGED if state.engaged else CONTROL_FILL, T.RADIUS_CARD)
    self._engage.set_enabled(state.engaged or state.can_engage)
    self._engage.render(engage)


  @staticmethod
  def _street(rect: rl.Rectangle, street: str, h: Align) -> None:
    """The road icon and street name, centered (or at the start) in rect, the name elided to fit."""
    text_w = min(rect.width - T.px(40), draw.text_width(street, T.font_px(22), T.FONT_BOLD))
    block = place(rect, text_w + T.px(40), rect.height, h)
    draw.icon(rl.Rectangle(block.x, block.y, T.px(28), block.height), "road", T.ACCENT_TEXT, T.px(22))
    draw.text(inset(block, left=T.px(40)), street, T.font_px(22), T.TEXT, T.FONT_BOLD)


class StatusChip(Component):
  """Top-right explanation of what the car is doing on its own."""
  grow_touch_target = False
  INK = {ChipTone.INFO: T.ACCENT_TEXT, ChipTone.PAUSED: T.WARNING, ChipTone.WAITING: T.SUCCESS_TEXT}

  def __init__(self, chip: Callable[[], Chip | None]):
    super().__init__()
    self._chip = chip

  def size(self, chip: Chip) -> tuple[float, float]:
    return draw.text_width(chip.label, T.font_px(17), T.FONT_SEMIBOLD) + T.px(70), T.px(44)

  def _render(self, rect: rl.Rectangle):
    chip = self._chip()
    if chip is None:
      return
    w, h = self.size(chip)
    box = rl.Rectangle(rect.x + rect.width - w - T.px(22), rect.y + T.px(22), w, h)
    draw.fill(box, draw.alpha(T.BG, 0.8), T.px(12))
    body = inset(box, x=T.px(16))
    ink = self.INK[chip.tone]
    draw.icon(rl.Rectangle(body.x, body.y, T.px(22), body.height), chip.icon, ink, T.px(22))
    draw.text(inset(body, left=T.px(32)), chip.label, T.font_px(17), T.TEXT if chip.tone == ChipTone.INFO else ink, T.FONT_SEMIBOLD)


# ── Steering headroom ──

COMFORTABLE, WORKING, AT_LIMIT = "comfortable", "working", "at_limit"
WORKING_FROM, LIMIT_FROM, LIMIT_HOLD = 0.60, 0.85, 0.5


class Headroom:
  """Three stages instead of a fade. At limit only after LIMIT_HOLD seconds over LIMIT_FROM, so a bump doesn't trigger it."""

  def __init__(self):
    self._over_since: float | None = None

  def stage(self, usage: float, now: float) -> str:
    usage = abs(usage)
    if usage >= LIMIT_FROM:
      self._over_since = now if self._over_since is None else self._over_since
      if now - self._over_since >= LIMIT_HOLD:
        return AT_LIMIT
    else:
      self._over_since = None
    return WORKING if usage >= WORKING_FROM else COMFORTABLE


@dataclass
class ArcState:
  usage: float = 0.0       # -1..1, signed toward the turn
  preview: float = 0.0     # what the planned path needs 2–3 s ahead, same scale
  active: bool = False     # openpilot is steering
  stage: str = COMFORTABLE


ARC_SPAN = 42.0       # degrees of the full arc; at this radius it spans about 40% of the road view, as in the mock
STAGE_STYLE = {COMFORTABLE: (T.TEXT, T.px(8)), WORKING: (T.WARNING, T.px(13)), AT_LIMIT: (rl.Color(255, 112, 67, 255), T.px(18))}


class HeadroomArc(Component):
  """The arc above the bar. A faint track, the current use toward the turn, and a lighter preview of the curve ahead."""
  grow_touch_target = False

  def __init__(self, state: Callable[[], ArcState]):
    super().__init__()
    self._state = state

  def _render(self, rect: rl.Rectangle):
    s = self._state()
    radius = rect.width * 0.55
    sag = radius * (1 - math.cos(math.radians(ARC_SPAN / 2)))   # how far the ends sit below the top; keep them above the bar
    center = rl.Vector2(rect.x + rect.width / 2, rect.y + rect.height - T.px(18) - sag + radius)
    color, thickness = STAGE_STYLE[s.stage]
    top = 270.0
    half = ARC_SPAN / 2
    alpha = 1.0 if s.active else 0.35

    def arc(a0: float, a1: float, width: float, ink: rl.Color) -> None:
      if abs(a1 - a0) < 0.05:
        return
      rl.draw_ring(center, radius - width / 2, radius + width / 2, min(a0, a1), max(a0, a1), 64, ink)
      for a in (a0, a1):   # round caps
        rad = math.radians(a)
        rl.draw_circle_v(rl.Vector2(center.x + math.cos(rad) * radius, center.y + math.sin(rad) * radius), width / 2, ink)

    arc(top - half, top + half, T.px(8), draw.alpha(T.TEXT, 0.18 * alpha))
    if s.active and abs(s.preview) > abs(s.usage) + 0.05:
      arc(top, top + half * max(-1.0, min(1.0, s.preview)), thickness, draw.alpha(color, 0.3))
    arc(top, top + half * max(-1.0, min(1.0, s.usage)), thickness, draw.alpha(color, 0.95 * alpha))
    if abs(s.usage) < 0.03:
      rl.draw_circle_v(rl.Vector2(center.x, center.y - radius), T.px(5), draw.alpha(T.TEXT, 0.8 * alpha))


class HelpSteer(Component):
  """The at-limit banner. Drawn by the UI, so it has no chime of its own."""
  grow_touch_target = False

  def _render(self, rect: rl.Rectangle):
    box = place(rl.Rectangle(rect.x, rect.y + T.px(130), rect.width, T.px(84)), T.px(340), T.px(84))
    draw.fill(box, draw.alpha(T.WARNING_SURFACE, 0.92), T.px(16))
    title, line = column(place(inset(box, x=T.px(22)), box.width - T.px(44), T.px(58)), [T.px(32), FILL])
    draw.text(title, "Help steer", T.font_px(22), T.WARNING_TITLE, T.FONT_EXTRABOLD)
    draw.text(line, "Steering is at its limit for this curve", T.font_px(15), T.TEXT_SECONDARY)


# ── New speed limit ──

@dataclass
class LimitOffer:
  limit: float          # display units
  target: float         # what cruise would go to, with the offset
  unit: str
  source: str
  seconds_left: float


class LimitCard(Component):
  """Asks before speeding up to a higher limit. Lower limits never ask."""
  grow_touch_target = False

  def __init__(self, offer: Callable[[], LimitOffer | None], on_match: Callable[[], None], on_ignore: Callable[[], None]):
    super().__init__()
    self._offer = offer
    self._match = self._child(Button("Match", on_match, ButtonStyle.PRIMARY, height=T.px(52)))
    self._ignore = self._child(Button("Ignore", on_ignore, ButtonStyle.SECONDARY, height=T.px(52)))

  def box(self, rect: rl.Rectangle) -> rl.Rectangle:
    return rl.Rectangle(rect.x + T.px(22), rect.y + T.px(130), T.px(360), T.px(196))

  def _render(self, rect: rl.Rectangle):
    offer = self._offer()
    if offer is None:
      return
    box = self.box(rect)
    draw.fill(box, draw.alpha(T.SURFACE_2, 0.95), T.px(18))
    draw.stroke(box, T.ACCENT, T.px(18), T.px(2))
    body = inset(box, T.px(18))
    title, question, source, _, buttons = column(body, [T.px(30), T.px(24), T.px(20), FILL, T.px(52)], T.px(4))
    draw.text(title, f"New limit {offer.limit:.0f}", T.font_px(22), T.TEXT, T.FONT_EXTRABOLD)
    draw.text(question, f"Speed up to {offer.target:.0f} {offer.unit}?", T.font_px(17), T.TEXT_SECONDARY)
    draw.text(source, f"From {offer.source.lower() or 'map'} · ignored in {max(0, math.ceil(offer.seconds_left))} s", T.font_px(14),
              T.TEXT_MUTED)
    ignore, match = row(buttons, [FILL, FILL], T.px(10))
    self._ignore.render(ignore)
    self._match.render(match)
