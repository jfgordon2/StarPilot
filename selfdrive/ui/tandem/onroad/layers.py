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
  """What the car is doing on its own, bottom left just above the bar."""
  grow_touch_target = False
  INK = {ChipTone.INFO: T.ACCENT_TEXT, ChipTone.PAUSED: T.WARNING, ChipTone.WAITING: T.SUCCESS_TEXT}
  HEIGHT, GAP = T.px(44), T.px(12)

  def __init__(self, chip: Callable[[], Chip | None]):
    super().__init__()
    self._chip = chip

  def size(self, chip: Chip) -> tuple[float, float]:
    return draw.text_width(chip.label, T.font_px(17), T.FONT_SEMIBOLD) + T.px(70), self.HEIGHT

  def _render(self, rect: rl.Rectangle):
    chip = self._chip()
    if chip is None:
      return
    w, h = self.size(chip)
    bar_top = rect.y + rect.height - BAR_MARGIN - BAR_HEIGHT
    box = rl.Rectangle(rect.x + BAR_MARGIN, bar_top - self.GAP - h, w, h)
    draw.fill(box, draw.alpha(T.BG, 0.8), T.px(12))
    body = inset(box, x=T.px(16))
    ink = self.INK[chip.tone]
    draw.icon(rl.Rectangle(body.x, body.y, T.px(22), body.height), chip.icon, ink, T.px(22))
    draw.text(inset(body, left=T.px(32)), chip.label, T.font_px(17), T.TEXT if chip.tone == ChipTone.INFO else ink, T.FONT_SEMIBOLD)


# ── Steering headroom ──

COMFORTABLE, WORKING, AT_LIMIT = "comfortable", "working", "at_limit"
WORKING_FROM, LIMIT_FROM, LIMIT_HOLD = 0.60, 0.85, 0.5
LIMIT_RELEASE = 0.80
LIMIT_LANE_COLOR = rl.Color(255, 138, 77, 255)
LIMIT_BORDER_COLOR = rl.Color(224, 162, 58, 255)


class Headroom:
  """Debounce limit entry and release below 80%, so bumps and threshold noise don't repeat warnings."""

  def __init__(self):
    self._over_since: float | None = None
    self._at_limit = False

  def stage(self, usage: float, now: float, active: bool = True) -> str:
    if not active:
      self._over_since = None
      self._at_limit = False
      return COMFORTABLE
    usage = abs(usage)
    if self._at_limit and usage >= LIMIT_RELEASE:
      return AT_LIMIT
    self._at_limit = False
    if usage >= LIMIT_FROM:
      self._over_since = now if self._over_since is None else self._over_since
      if now - self._over_since >= LIMIT_HOLD:
        self._at_limit = True
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
  """The at-limit banner; the view requests its one-shot warning through soundd."""
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
  total: float = 30.0   # how long the offer lasts, for the countdown bar
  vienna: bool = False  # the round sign used outside the US


VIENNA_RED = rl.Color(0xD9, 0x43, 0x4F, 255)


class LimitCard(Component):
  """Asks before speeding up to a higher limit; lower limits never ask. It sits over StarPilot's speed limit sign, top left,
  with the new limit's sign in it, and a bar that drains until the offer is ignored."""
  grow_touch_target = False
  WIDTH, PAD = T.px(360), T.px(12)   # the pad puts the card's sign exactly where the plain sign sits

  def __init__(self, offer: Callable[[], LimitOffer | None], on_match: Callable[[], None], on_ignore: Callable[[], None],
               top: Callable[[], float] = lambda: T.px(16)):
    """top: how far down the card sits, below the turn card while navigating."""
    super().__init__()
    self._offer = offer
    self._top = top
    self._match = self._child(Button("Match", on_match, ButtonStyle.PRIMARY, height=T.px(60), font_size=T.font_px(18),
                                     radius=T.px(16), weight=T.FONT_EXTRABOLD))
    self._ignore = self._child(Button("Ignore", on_ignore, ButtonStyle.SECONDARY, height=T.px(60), font_size=T.font_px(18),
                                      radius=T.px(16), weight=T.FONT_BOLD))

  def box(self, rect: rl.Rectangle) -> rl.Rectangle:
    height = self.PAD * 2 + SIGN_SIZE[1] + T.px(14) + T.px(60) + T.px(14) + T.px(4)
    return rl.Rectangle(rect.x + T.px(16), rect.y + self._top(), self.WIDTH, height)

  def _render(self, rect: rl.Rectangle):
    offer = self._offer()
    if offer is None:
      return
    box = self.box(rect)
    draw.fill(box, draw.alpha(T.SURFACE_2, 0.96), T.px(22))
    draw.stroke(box, T.ACCENT, T.px(22), T.px(2))
    body = inset(box, self.PAD)
    top, buttons, bar = column(body, [SIGN_SIZE[1], T.px(60), T.px(4)], T.px(14))
    sign, text = row(top, [SIGN_SIZE[0], FILL], T.px(16))
    draw_sign(sign, f"{offer.limit:.0f}", offer.vienna)
    lines = [draw.line_height(T.font_px(22)), draw.line_height(T.font_px(16)), draw.line_height(T.font_px(13))]
    title, question, source = column(place(text, text.width, sum(lines) + T.px(8)), lines, T.px(4))
    draw.text(title, f"New limit {offer.limit:.0f}", T.font_px(22), T.TEXT, T.FONT_EXTRABOLD)
    draw.text(question, f"Speed up to {offer.target:.0f} {offer.unit}?", T.font_px(16), T.TEXT_SECONDARY)
    draw.text(source, f"From {offer.source.lower() or 'map'} · ignored in {max(0, math.ceil(offer.seconds_left))} s", T.font_px(13),
              T.TEXT_MUTED)
    ignore, match = row(buttons, [FILL, FILL], T.px(10))
    self._ignore.render(ignore)
    self._match.render(match)
    draw.fill(bar, T.TRACK, T.px(2))
    left = max(0.0, min(1.0, offer.seconds_left / offer.total)) if offer.total > 0 else 0.0
    if left > 0:
      draw.fill(rl.Rectangle(bar.x, bar.y, max(bar.height, bar.width * left), bar.height), T.ACCENT, T.px(2))


# ── Speed, speed limit sign and turn card, as in the onroad mocks ──

HUD_PILL = rl.Color(0x0B, 0x0D, 0x10, 230)
SPEED_UNIT = rl.Color(0xC9, 0xD0, 0xDA, 255)
TURN_LINE = rl.Color(0xC9, 0xD8, 0xEA, 255)
SIGN_TILE = (T.px(82), T.px(98))
SIGN_SIZE = (T.px(62), T.px(78))   # the US sign inside the tile; the new-limit card draws it at the same size and spot
SIGN_MARGIN = T.px(18)


SIGNAL_BRIGHT, SIGNAL_DIM = T.SUCCESS_BRIGHT, rl.Color(0x2A, 0x8F, 0x5E, 255)
SIGNAL_SIZE = (T.px(46), T.px(30))   # both chevrons, as in the onroad mock
SIGNAL_GAP = T.px(22)
SIGNAL_STEP = 0.4                    # seconds each chevron leads, so the light steps outward


def draw_signal(rect: rl.Rectangle, side: str, now: float) -> None:
  """Two chevrons pointing the way of the turn. The bright one steps outward, from beside the speed to the edge."""
  w, h = SIGNAL_SIZE
  box = place(rect, w, h)
  stroke = T.px(5)
  outer_bright = int(now / SIGNAL_STEP) % 2 == 1
  for i, x0 in enumerate((T.px(18), T.px(36))):   # the mock's chevron tips: at 8 and 26 of 46, arms out to 18 and 36
    outer = i == 0
    color = SIGNAL_BRIGHT if outer == outer_bright else SIGNAL_DIM
    tip_x, arm_x = x0 - T.px(10), x0
    if side == "right":
      tip_x, arm_x = w - tip_x, w - arm_x
    tip = rl.Vector2(box.x + tip_x, box.y + h / 2)
    for arm in (rl.Vector2(box.x + arm_x, box.y + h / 2 - T.px(10)), rl.Vector2(box.x + arm_x, box.y + h / 2 + T.px(10))):
      rl.draw_line_ex(arm, tip, stroke, color)
      rl.draw_circle_v(arm, stroke / 2, color)
    rl.draw_circle_v(tip, stroke / 2, color)


def draw_speed(rect: rl.Rectangle, speed: float, unit: str, offset_y: float = 0.0, left: bool = False, right: bool = False,
               now: float = 0.0) -> None:
  """The current speed, top center on a dark pill. A blinker adds our turn signal on its side; the number stays centered."""
  number, size = f"{round(speed)}", T.font_px(62)
  lines = [draw.line_height(size), draw.line_height(T.font_px(17))]
  w = max(draw.text_width(number, size, T.FONT_EXTRABOLD), draw.text_width(unit, T.font_px(17))) + T.px(80)
  h = sum(lines) + T.px(20) - T.px(6)
  center = rl.Rectangle(rect.x + (rect.width - w) / 2, rect.y + T.px(16) + offset_y, w, h)
  extra = SIGNAL_SIZE[0] + SIGNAL_GAP - T.px(10)   # the mock's pill is 10 px tighter on the signal side
  pill = rl.Rectangle(center.x - (extra if left else 0), center.y, w + (extra if left else 0) + (extra if right else 0), h)
  draw.fill(pill, HUD_PILL, T.px(22))
  value, label = column(inset(center, y=T.px(10)), [lines[0] - T.px(6), lines[1]])
  draw.text(value, number, size, T.TEXT, T.FONT_EXTRABOLD, Align.CENTER)
  draw.text(label, unit, T.font_px(17), SPEED_UNIT, h=Align.CENTER)
  for side, on in (("left", left), ("right", right)):
    if on:
      x = pill.x + T.px(30) if side == "left" else pill.x + pill.width - T.px(30) - SIGNAL_SIZE[0]
      draw_signal(rl.Rectangle(x, pill.y, SIGNAL_SIZE[0], pill.height), side, now)


def sign_tile(rect: rl.Rectangle) -> rl.Rectangle:
  """Where the speed limit sign sits: top left."""
  return rl.Rectangle(rect.x + SIGN_MARGIN, rect.y + SIGN_MARGIN, *SIGN_TILE)


def draw_speed_limit(tile: rl.Rectangle, limit: str, vienna: bool) -> None:
  """The posted limit on a dark tile."""
  draw.fill(tile, rl.Color(0x0B, 0x0D, 0x10, 255), T.px(14))
  draw_sign(place(tile, *SIGN_SIZE), limit, vienna)


def draw_sign(area: rl.Rectangle, limit: str, vienna: bool) -> None:
  """A US sign filling area, or Vienna's red ring centered on it (a little wider than the US sign, as in the mock)."""
  if vienna:
    sign = place(area, T.px(72), T.px(72))
    draw.fill(sign, VIENNA_RED, sign.width / 2)
    draw.fill(inset(sign, T.px(8)), rl.WHITE, sign.width / 2)
    draw.text(sign, limit, T.font_px(28), T.BG, T.FONT_EXTRABOLD, Align.CENTER)
    return
  sign = area
  draw.fill(sign, rl.WHITE, T.px(8))
  draw.stroke(inset(sign, T.px(2)), T.BG, T.px(7), T.px(3))
  body = inset(sign, x=T.px(5), y=T.px(9))
  top, middle, number = column(body, [T.px(12), T.px(12), FILL])
  draw.text(top, "SPEED", T.font_px(10), T.BG, T.FONT_EXTRABOLD, Align.CENTER)
  draw.text(middle, "LIMIT", T.font_px(10), T.BG, T.FONT_EXTRABOLD, Align.CENTER)
  draw.text(number, limit, T.font_px(32), T.BG, T.FONT_EXTRABOLD, Align.CENTER)


DM_TILE = T.px(64)
DM_RING = (T.px(50), T.px(3))     # diameter and width


def dm_tile(rect: rl.Rectangle) -> rl.Rectangle:
  """The driver monitor's place: the top right corner, inset like the sign is on the left."""
  return rl.Rectangle(rect.x + rect.width - SIGN_MARGIN - DM_TILE, rect.y + SIGN_MARGIN, DM_TILE, DM_TILE)


def draw_driver_monitor(tile: rl.Rectangle, opacity: float, attentive: float, watching: bool) -> None:
  """The driver on a dark tile, ringed green while attentive and amber as attention drops. Without a camera policy
  (watching False) the ring is a quiet track and the whole tile is dimmed by the caller's opacity."""
  if opacity <= 0.01:
    return
  draw.fill(tile, draw.alpha(rl.Color(0x0B, 0x0D, 0x10, 255), opacity), T.px(14))
  ring = place(tile, DM_RING[0], DM_RING[0])
  if watching:
    color = mix(T.WARNING, T.SUCCESS_BRIGHT, attentive)
  else:
    color = draw.alpha(T.TEXT, 0.25)
  draw.stroke(ring, draw.alpha(color, opacity), ring.width / 2, DM_RING[1])
  draw.icon(tile, "driver", draw.alpha(T.TEXT, opacity), T.px(26))


def mix(a: rl.Color, b: rl.Color, t: float) -> rl.Color:
  """a at t=0, b at t=1."""
  t = min(1.0, max(0.0, t))
  return rl.Color(*(round(x + (y - x) * t) for x, y in zip((a.r, a.g, a.b, a.a), (b.r, b.g, b.b, b.a), strict=True)))


def turn_icon(maneuver: str, modifier: str) -> str:
  """A mock icon for a maneuver: turn arrows by side, an up arrow for straight on, a pin on arrival."""
  if maneuver in ("arrive", "depart"):
    return "pin"
  if maneuver in ("roundabout", "rotary", "roundabout turn") or "uturn" in modifier.lower():
    return "restart"
  modifier = modifier.lower()
  if "left" in modifier:
    return "turn_left"
  if "right" in modifier:
    return "turn_right"
  return "shift"   # straight


TURN_CARD_WIDTH = T.px(330)
TURN_CARD_TOP = T.px(16)
TURN_BELOW_SIGN = SIGN_MARGIN + SIGN_TILE[1] + T.px(12)   # the card's top while the sign holds the corner


def draw_turn_card(rect: rl.Rectangle, distance: str, text: str, maneuver: str, modifier: str,
                   top: float = TURN_CARD_TOP) -> rl.Rectangle:
  """The next turn, top left (below the sign when there is one): its arrow, the distance and the instruction. Returns the card's box."""
  lines = [draw.line_height(T.font_px(30)), draw.line_height(T.font_px(17))]
  box = rl.Rectangle(rect.x + SIGN_MARGIN, rect.y + top, TURN_CARD_WIDTH, max(T.px(54), sum(lines)) + T.px(28))
  draw.fill(box, T.ACCENT_SURFACE, T.px(20))
  body = inset(box, x=T.px(18), y=T.px(14))
  icon, words = row(body, [T.px(54), FILL], T.px(16))
  draw.icon(icon, turn_icon(maneuver, modifier), T.TEXT, T.px(54))
  dist, line = column(place(words, words.width, sum(lines) + T.px(2)), lines, T.px(2))
  draw.text(dist, distance, T.font_px(30), T.TEXT, T.FONT_EXTRABOLD)
  draw.text(line, text, T.font_px(17), TURN_LINE)
  return box

