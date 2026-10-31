"""Page shapes the settings window is built from: a hub of tiles, and a sidebar of sections."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pyray as rl

from openpilot.system.ui.widgets import Widget
from openpilot.selfdrive.ui.tandem import tokens as T
from openpilot.selfdrive.ui.tandem.base import Bindable, Component
from openpilot.selfdrive.ui.tandem.chrome import HubGrid, HubTile, PageHeader, Sidebar, SidebarItem
from openpilot.selfdrive.ui.tandem.layout import FILL, column, inset, row


def can_go_back(page: Widget) -> bool:
  """True when the page has its own level to step back from (e.g. a sub-page inside a hosted panel)."""
  check = getattr(page, "can_go_back", None)
  return bool(check and check())


def go_back(page: Widget) -> None:
  page.go_back()  # type: ignore[attr-defined]


def body_rect(rect: rl.Rectangle) -> rl.Rectangle:
  return inset(rect, left=T.PAGE_INSET, right=T.PAGE_INSET, top=T.px(18), bottom=T.px(14))


class HubPage(Component):
  """Title and subtitle, then a grid of tiles."""
  grow_touch_target = False

  def __init__(self, title: str, subtitle: str, tiles: list[HubTile], columns: int = 3):
    super().__init__()
    self._header = self._child(PageHeader(title, subtitle))
    self._grid = self._child(HubGrid(tiles, columns))

  def _render(self, rect: rl.Rectangle):
    body = body_rect(rect)
    header, grid, _ = column(body, [self._header.preferred_height(body.width), self._grid.preferred_height(body.width), FILL], T.px(14))
    self._header.render(header)
    self._grid.render(grid)


@dataclass
class Section:
  label: str
  page: Callable[[], Widget]
  value: Bindable[str] | None = None


class SectionPage(Component):
  """A sidebar of sections; the chosen section fills the rest. Sections are built when first chosen."""
  grow_touch_target = False

  def __init__(self, caption: str, sections: list[Section], selected: int = 0):
    super().__init__()
    self._sections = sections
    self._pages: dict[int, Widget] = {}
    self._selected = selected
    self._shown = False
    items = [SidebarItem(s.label, on_select=lambda i=i: self.select(i), value=s.value) for i, s in enumerate(sections)]
    self._sidebar = self._child(Sidebar(caption, items, selected=lambda: self._selected))

  @property
  def selected(self) -> int:
    return self._selected

  @property
  def current(self) -> Widget:
    if self._selected not in self._pages:
      self._pages[self._selected] = self._sections[self._selected].page()
    return self._pages[self._selected]

  def select(self, index: int) -> None:
    if index == self._selected:
      return
    if self._shown:
      self.current.hide_event()
    self._selected = index
    if self._shown:
      self.current.show_event()

  def can_go_back(self) -> bool:
    return can_go_back(self.current)

  def go_back(self) -> None:
    go_back(self.current)

  def show_event(self):
    super().show_event()
    self._shown = True
    self.current.show_event()

  def hide_event(self):
    super().hide_event()
    self._shown = False
    self.current.hide_event()

  def _render(self, rect: rl.Rectangle):
    side, content = row(body_rect(rect), [T.SIDEBAR_WIDTH, FILL], T.PANEL_GAP)
    self._sidebar.render(inset(side, top=T.px(8)))
    self.current.render(content)
