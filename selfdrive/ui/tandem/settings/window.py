"""The settings window: five tabs along the bottom, each with its own stack of pages.

The button left of the tabs closes settings on a tab's first page and steps back everywhere deeper.
"""
from __future__ import annotations

from collections.abc import Callable
from enum import IntEnum

import pyray as rl

from openpilot.system.ui.widgets import Widget
from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.chrome import BottomNav, HubTile
from openpilot.selfdrive.ui.tandem.controls import Glyph
from openpilot.selfdrive.ui.tandem.layout import FILL, column
from openpilot.selfdrive.ui.tandem.settings import upstream
from openpilot.selfdrive.ui.tandem.settings.pages import HubPage, Section, SectionPage, can_go_back, go_back
from openpilot.selfdrive.ui.tandem.settings.speed_steering import SpeedSteering, everyday_panel
from openpilot.selfdrive.ui.tandem.settings.store import SettingsStore


class Tab(IntEnum):
  DRIVING = 0
  DEVICE = 1
  NETWORK = 2
  BLUETOOTH = 3
  SOFTWARE = 4


TABS = ["Driving", "Device", "Network", "Bluetooth", "Software"]
DEVELOPER_SECTION = 2

# Upstream PanelType names -> where they live here. Home and the sidebar open TOGGLES; it is part of Driving.
PANEL_TABS = {
  "STARPILOT": Tab.DRIVING,
  "TOGGLES": Tab.DRIVING,
  "DEVICE": Tab.DEVICE,
  "DEVELOPER": Tab.DEVICE,
  "NETWORK": Tab.NETWORK,
  "BLUETOOTH": Tab.BLUETOOTH,
  "SOFTWARE": Tab.SOFTWARE,
}


def scribble(key: str) -> Glyph:
  """StarPilot's vector icons (drawn on a 60 px canvas), as a glyph."""
  def glyph(rect: rl.Rectangle, color: rl.Color, size: float) -> None:
    from openpilot.selfdrive.ui.layouts.settings.starpilot.scribble import draw_custom_icon
    draw_custom_icon(key, rect.x + (rect.width - size) / 2, rect.y + (rect.height - size) / 2, size / 60, color)
  return glyph


class SettingsWindow(Widget):
  def __init__(self, store: SettingsStore | None = None):
    super().__init__()
    self._store = store
    self._tab = Tab.DRIVING
    self._roots: list[Callable[[], Widget]] = [self._driving, self._device, upstream.network, upstream.bluetooth, upstream.software]
    self._stacks: list[list[Widget]] = [[] for _ in TABS]
    self._shown = False
    self._close_callback: Callable[[], None] | None = None
    self._nav = BottomNav(TABS, lambda: self._tab, self.select_tab, on_leading=self.back,
                          leading=lambda: "back" if self.can_go_back() else "close")

  # Upstream SettingsLayout interface, used by MainLayout

  def set_callbacks(self, on_close: Callable[[], None]):
    self._close_callback = on_close

  def set_current_panel(self, panel_type) -> None:
    """Open settings at an upstream PanelType, starting that tab from its first page."""
    name = getattr(panel_type, "name", str(panel_type))
    tab = PANEL_TABS.get(name, Tab.DRIVING)
    self._unwind(tab)
    if name == "DEVELOPER":
      self._stack(tab)[0].select(DEVELOPER_SECTION)
    self.select_tab(tab)

  def show_event(self):
    super().show_event()
    self._shown = True
    self.top.show_event()

  def hide_event(self):
    super().hide_event()
    self._shown = False
    self.top.hide_event()

  # Navigation

  @property
  def tab(self) -> Tab:
    return self._tab

  @property
  def store(self) -> SettingsStore:
    if self._store is None:
      self._store = SettingsStore()
    return self._store

  def _stack(self, tab: int) -> list[Widget]:
    stack = self._stacks[tab]
    if not stack:
      stack.append(self._roots[tab]())
    return stack

  @property
  def top(self) -> Widget:
    return self._stack(self._tab)[-1]

  @property
  def depth(self) -> int:
    return len(self._stack(self._tab))

  def can_go_back(self) -> bool:
    return self.depth > 1 or can_go_back(self.top)

  def select_tab(self, tab: int) -> None:
    if tab == self._tab:
      return
    if self._shown:
      self.top.hide_event()
    self._tab = Tab(tab)
    if self._shown:
      self.top.show_event()

  def push(self, page: Widget) -> None:
    if self._shown:
      self.top.hide_event()
    self._stack(self._tab).append(page)
    if self._shown:
      page.show_event()

  def pop(self) -> None:
    stack = self._stack(self._tab)
    if len(stack) < 2:
      return
    page = stack.pop()
    if self._shown:
      page.hide_event()
      self.top.show_event()

  def back(self) -> None:
    if can_go_back(self.top):
      go_back(self.top)
    elif self.depth > 1:
      self.pop()
    elif self._close_callback is not None:
      self._close_callback()

  def _unwind(self, tab: int) -> None:
    stack = self._stack(tab)
    while len(stack) > 1:
      page = stack.pop()
      if self._shown and tab == self._tab:
        page.hide_event()
        if len(stack) == 1:
          stack[0].show_event()

  def _render(self, rect: rl.Rectangle):
    body, nav = column(rect, [FILL, T.NAV_HEIGHT])
    draw.fill(body, T.BG)
    self.top.render(body)
    self._nav.render(nav)

  # Tabs

  def _driving(self) -> Widget:
    model = SpeedSteering(self.store)

    def starpilot(panel: str) -> Callable[[], Widget]:
      return lambda: upstream.StarPilotPage(panel, on_exit=self.pop)

    def open_page(make: Callable[[], Widget]) -> Callable[[], None]:
      return lambda: self.push(make())

    def speed_steering() -> Widget:
      return SectionPage("SPEED & STEERING", [
        Section("Everyday", lambda: everyday_panel(model)),
        Section("Navigation", lambda: upstream.StarPilotPage("NAVIGATION")),
        Section("Gas & Brake", lambda: upstream.StarPilotPage("LONGITUDINAL")),
        Section("Steering", lambda: upstream.StarPilotPage("LATERAL")),
      ])

    def display() -> Widget:
      return SectionPage("DISPLAY", [
        Section("Driving Screen", lambda: upstream.StarPilotPage("VISUALS")),
        Section("Map Data", lambda: upstream.StarPilotPage("MAPS")),
      ])

    return HubPage("Driving", "Good defaults are on. Change only what matters to you.", [
      HubTile("Speed & Steering", [model.summary, model.speed_limit_summary], open_page(speed_steering), scribble("steering")),
      HubTile("Display", ["Driving screen and theme", "Offline map data"], open_page(display), scribble("display")),
      HubTile("Alerts", ["Volumes and chimes"], open_page(starpilot("SOUNDS")), scribble("sound")),
      HubTile("Driving Model", ["Choose and download models"], open_page(starpilot("DRIVING_MODEL")), scribble("aicar")),
      HubTile("Vehicle", ["Features for your car"], open_page(starpilot("VEHICLE")), scribble("vehicle")),
      HubTile("Driver Assistance", ["Experimental mode, driver camera", "and other core options"], open_page(upstream.toggles),
              scribble("road")),
    ])

  def _device(self) -> Widget:
    return SectionPage("DEVICE", [
      Section("This Device", upstream.device),
      Section("General", lambda: upstream.StarPilotPage("SYSTEM")),
      Section("Developer", upstream.developer),
    ])
