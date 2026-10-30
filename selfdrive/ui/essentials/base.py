from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

import pyray as rl

from openpilot.system.ui.widgets import Widget
from openpilot.selfdrive.ui.essentials import tokens as T
from openpilot.selfdrive.ui.essentials.layout import grow

V = TypeVar("V")
Bindable = V | Callable[[], V]


def resolve(value: Bindable[V]) -> V:
  """Components take either a value or a getter, so rows can read Params every frame."""
  # raylib structs (colors, rectangles) report callable() but are values
  return value() if callable(value) and not isinstance(value, rl.ffi.CData) else value


def size_of(widget: Widget, max_width: float) -> tuple[float, float]:
  """Preferred size for Essentials components, current size for any other Widget."""
  return widget.preferred_size(max_width) if isinstance(widget, Component) else (widget.rect.width, widget.rect.height)


class Component(Widget):
  """Widget plus a preferred size, so containers can lay children out without hard-coded heights."""

  # Controls smaller than MIN_TOUCH still accept touches across MIN_TOUCH; containers turn this off.
  grow_touch_target = True

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    return self._rect.width, self._rect.height

  def preferred_height(self, width: float) -> float:
    return self.preferred_size(width)[1]

  @property
  def _hit_rect(self) -> rl.Rectangle:
    rect = grow(self._rect, T.MIN_TOUCH, T.MIN_TOUCH) if self.grow_touch_target else self._rect
    return rect if self._parent_rect is None else rl.get_collision_rec(rect, self._parent_rect)
