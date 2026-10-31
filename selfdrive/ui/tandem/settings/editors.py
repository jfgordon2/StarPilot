"""The number editor sheet: big value with − and +, a slider with the default marked, quick picks, and reset."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pyray as rl

from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.base import Component
from openpilot.selfdrive.ui.tandem.controls import Button, ButtonStyle, Chip, Slider, Stepper, Tone
from openpilot.selfdrive.ui.tandem.layout import FILL, column, row
from openpilot.selfdrive.ui.tandem.overlays import Sheet


@dataclass(frozen=True)
class NumberSpec:
  minimum: float
  maximum: float
  step: float
  default: float
  fmt: Callable[[float], str] = lambda v: f"{v:g}"
  picks: tuple[float, ...] = ()


class NumberEditor(Component):
  grow_touch_target = False

  def __init__(self, spec: NumberSpec, value: Callable[[], float], on_change: Callable[[float], None]):
    super().__init__()
    self._spec = spec
    self._value = value
    s = spec
    self._stepper = self._child(Stepper(value, on_change, s.minimum, s.maximum, s.step, fmt=s.fmt, value_width=T.px(220),
                                        height=T.px(84), button_size=T.px(76), font_size=T.font_px(40)))
    self._slider = self._child(Slider(value, on_change, s.minimum, s.maximum, s.step, default=s.default,
                                      marks=[(s.minimum, s.fmt(s.minimum)), (s.maximum, s.fmt(s.maximum))]))
    self._picks = [self._child(Chip(s.fmt(p), Tone.NEUTRAL, height=T.px(40), font_size=T.font_px(16))) for p in s.picks]
    for chip, pick in zip(self._picks, s.picks, strict=True):
      chip.set_click_callback(lambda p=pick: on_change(p))
    self._reset = self._child(Button("Reset to default", lambda: on_change(s.default), ButtonStyle.GHOST))

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    return max_width, T.px(84) + self._slider.preferred_height(max_width) + T.px(120)

  def _render(self, rect: rl.Rectangle):
    top, slider, bottom = column(rect, [T.px(84), self._slider.preferred_height(rect.width), FILL], T.px(18))
    w, h = self._stepper.preferred_size(rect.width)
    self._stepper.render(rl.Rectangle(top.x + (top.width - w) / 2, top.y, w, h))
    self._slider.render(slider)
    picks, reset = row(column(bottom, [T.BUTTON_HEIGHT, FILL])[0], [FILL, self._reset.preferred_size(rect.width)[0]])
    x = picks.x
    if self._picks:
      label_w = draw.text(picks, "Quick picks", T.SIZE_SUBTITLE, T.TEXT_MUTED)
      x += label_w + T.px(14)
    for chip in self._picks:
      cw, ch = chip.preferred_size(picks.width)
      chip.render(rl.Rectangle(x, picks.y + (picks.height - ch) / 2, cw, ch))
      x += cw + T.px(8)
    self._reset.render(reset)


def number_sheet(window, title: str, subtitle: str, spec: NumberSpec, value: Callable[[], float],
                 on_change: Callable[[float], None]) -> Sheet:
  return Sheet(title, NumberEditor(spec, value, on_change), subtitle=subtitle,
               actions=[Button("Done", window.dismiss, ButtonStyle.PRIMARY)], on_dismiss=window.dismiss)
