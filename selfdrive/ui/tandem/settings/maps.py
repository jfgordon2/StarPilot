"""Offline Maps: what's downloaded, keeping it up to date, choosing regions, and download progress.

The region catalog, selection rules and download requests are StarPilot's (its maps screen controller and the
DownloadMaps / CancelDownloadMaps signals), so mapd sees exactly what it would from StarPilot's own screen.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import pyray as rl

from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.base import Component
from openpilot.selfdrive.ui.tandem.controls import Button, ButtonStyle, ProgressBar, Segmented, Switch
from openpilot.selfdrive.ui.tandem.layout import FILL, column, inset, row
from openpilot.selfdrive.ui.tandem.rows import ListPanel, SectionHeader, SettingRow, Text
from openpilot.selfdrive.ui.tandem.settings.model import Rebuilding
from openpilot.selfdrive.ui.tandem.settings.pages import body_rect
from openpilot.selfdrive.ui.tandem.settings.store import SettingsStore

SCHEDULES = ["Off", "Weekly", "Monthly"]   # PreferredSchedule 0, 1, 2


@dataclass(frozen=True)
class Region:
  token: str
  name: str
  detail: str = ""


@dataclass(frozen=True)
class Progress:
  active: bool
  done: int
  total: int
  location: str

  @property
  def fraction(self) -> float:
    return self.done / self.total if self.total else 0.0


class MapsSource(Protocol):
  def tick(self) -> None: ...
  def refresh(self) -> None: ...
  def regions(self, tab: int) -> list[Region]: ...     # 0 U.S. regions, 1 U.S. states, 2 other countries
  def selected(self, token: str) -> bool: ...
  def set_selected(self, token: str, on: bool) -> None: ...
  def selection_summary(self) -> str: ...
  def has_selection(self) -> bool: ...
  def downloaded(self) -> bool: ...
  def storage(self) -> str: ...
  def progress(self) -> Progress: ...
  def cancelling(self) -> bool: ...
  def checks(self) -> list[tuple[str, bool]]: ...      # e.g. ("Parked", True)
  def download(self) -> None: ...
  def cancel(self) -> None: ...
  def remove(self) -> None: ...


class Maps:
  def __init__(self, store: SettingsStore, source: MapsSource):
    self._store = store
    self.source = source

  @property
  def schedule(self) -> int:
    return max(0, min(2, self._store.get_int("PreferredSchedule")))

  def set_schedule(self, index: int) -> None:
    self._store.write({"PreferredSchedule": index})

  def ready(self) -> bool:
    return self.source.has_selection() and all(ok for _, ok in self.source.checks()) and not self.source.progress().active

  def blocked_reason(self) -> str:
    if not self.source.has_selection():
      return "Choose at least one region"
    return next((f"Waiting: {name.lower()}" for name, ok in self.source.checks() if not ok), "")

  def status(self) -> str:
    progress = self.source.progress()
    if self.source.cancelling():
      return "Cancelling…"
    if progress.active:
      return f"Downloading {progress.location or 'maps'} · {round(progress.fraction * 100)}%"
    return "Downloaded" if self.source.downloaded() else "Not downloaded yet"

  def summary(self) -> str:
    return f"{self.source.selection_summary()} · {self.status().lower()}"


class ProgressCard(Component):
  """Percent and files while a download runs; hidden otherwise."""
  grow_touch_target = False

  def __init__(self, maps: Maps):
    super().__init__()
    self._maps = maps
    self._bar = self._child(ProgressBar(lambda: maps.source.progress().fraction))
    self._cancel = self._child(Button("Cancel download", maps.source.cancel, ButtonStyle.DANGER_OUTLINE))
    self.set_visible(lambda: maps.source.progress().active)

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    return max_width, T.px(120)

  def set_parent_rect(self, parent_rect: rl.Rectangle) -> None:
    super().set_parent_rect(parent_rect)
    self._cancel.set_parent_rect(parent_rect)

  def _render(self, rect: rl.Rectangle):
    progress = self._maps.source.progress()
    body = inset(rect, x=T.PANEL_HEADER_INSET, y=T.px(14))
    top, bar, note = column(body, [T.BUTTON_HEIGHT, T.px(10), FILL], T.px(12))
    text, cancel = row(top, [FILL, self._cancel.preferred_size(top.width)[0]], T.px(12))
    draw.text(text, f"{round(progress.fraction * 100)}%", T.font_px(30), T.TEXT, T.FONT_EXTRABOLD)
    self._cancel.render(cancel)
    self._bar.render(bar)
    draw.text(note, f"{progress.done} of {progress.total} files · {progress.location}. Pauses if you drive or lose the connection.",
              T.SIZE_SUBTITLE, T.TEXT_TERTIARY)


def maps_panel(maps: Maps, open_regions: Callable[[], None]) -> ListPanel:
  def label() -> str:
    if not maps.ready():
      return maps.blocked_reason() or "Download"
    return "Update" if maps.source.downloaded() else "Download"

  download = Button(label, maps.source.download,
                    ButtonStyle.PRIMARY)
  download.set_enabled(maps.ready)
  download.set_visible(lambda: not maps.source.progress().active)
  remove = Button("Remove maps", maps.source.remove, ButtonStyle.DANGER_OUTLINE)   # the source confirms first
  remove.set_enabled(lambda: maps.source.downloaded() and not maps.source.progress().active)
  return ListPanel([
    SectionHeader("YOUR REGIONS"),
    SettingRow(maps.source.selection_summary, maps.status, download,
               subtitle_color=lambda: T.SUCCESS_TEXT if maps.status() == "Downloaded" else T.TEXT_TERTIARY, height=T.px(96)),
    ProgressCard(maps),
    SettingRow("Choose regions", "Add or remove states, regions and countries", on_click=open_regions),
    SettingRow("Keep up to date", "Updates download only while parked and online",
               Segmented(SCHEDULES, lambda: maps.schedule, maps.set_schedule)),
    SettingRow("Storage", lambda: f"Maps use {maps.source.storage()}", remove),
  ], title="Offline Maps", subtitle="Speed limits and curves work without a connection")


class RegionsPage(Component):
  """Tabs of regions on the left, each with a switch; the selection and readiness checks on the right."""
  grow_touch_target = False
  TABS = ["U.S. regions", "U.S. states", "Other countries"]

  def __init__(self, maps: Maps, on_download: Callable[[], None]):
    super().__init__()
    self._maps = maps
    self._tab = 0
    tabs = Segmented(self.TABS, lambda: self._tab, self._select)

    def build() -> ListPanel:
      rows = [SettingRow(r.name, r.detail or None, Switch(lambda t=r.token: maps.source.selected(t),
                                                          lambda on, t=r.token: maps.source.set_selected(t, on)))
              for r in maps.source.regions(self._tab)]
      return ListPanel(rows or [Text("No regions available.")], title="Add map regions", header_control=tabs)

    self._list = self._child(Rebuilding(lambda: self._tab, build, maps.source.tick))
    download = Button("Download", on_download, ButtonStyle.PRIMARY)
    download.set_enabled(maps.ready)
    self._side = self._child(ListPanel([
      SectionHeader("SELECTED"),
      SettingRow(maps.source.selection_summary, None),
      SectionHeader("READY TO DOWNLOAD"),
      *[SettingRow(name, lambda name=name: "Yes" if dict(maps.source.checks()).get(name) else "Not yet",
                   subtitle_color=lambda name=name: T.SUCCESS_TEXT if dict(maps.source.checks()).get(name) else T.WARNING)
        for name, _ in maps.source.checks()],
    ], footer=download))

  def _select(self, index: int) -> None:
    self._tab = index

  def _render(self, rect: rl.Rectangle):
    left, right = row(body_rect(rect), [FILL, T.px(380)], T.PANEL_GAP)
    self._list.render(left)
    self._side.render(right)


class UpstreamMaps:
  """MapsSource backed by StarPilot's maps screen controller."""

  def __init__(self):
    from openpilot.selfdrive.ui.layouts.settings.starpilot import maps as m
    self._m = m
    self._layout = m.StarPilotMapsLayout()

  def tick(self) -> None:
    self._layout._update_state()

  def refresh(self) -> None:
    self._layout.show_event()

  def regions(self, tab: int) -> list[Region]:
    m = self._m
    if tab == 0:
      packages = [Region(token, m.tr(spec["title"]), m.tr(spec["subtitle"])) for token, spec in m.REGIONAL_PACKAGES.items()]
      return [Region(m.US_COUNTRY_TOKEN, "Whole U.S.", "Every state and territory"), *packages]
    regions = self._layout._all_us_states_regions() if tab == 1 else self._layout._all_country_regions()
    return [Region(r["token"], m.tr(r["label"])) for r in regions]

  def selected(self, token: str) -> bool:
    return self._layout._get_map_state(token)

  def set_selected(self, token: str, on: bool) -> None:
    self._layout._set_map_state(token, on)

  def selection_summary(self) -> str:
    return self._layout._selected_summary_text()

  def has_selection(self) -> bool:
    return self._layout._selected_count() > 0

  def downloaded(self) -> bool:
    return self._layout._has_downloaded_data

  def storage(self) -> str:
    return self._layout._storage_text

  def progress(self) -> Progress:
    state = self._layout._download_state
    return Progress(state.active or self._layout._download_requested(), state.downloaded_files, state.total_files, state.primary_location)

  def cancelling(self) -> bool:
    return self._layout._is_visually_cancelling()

  def checks(self) -> list[tuple[str, bool]]:
    return [("Parked", self._layout._is_parked()), ("Online", self._layout._is_online())]

  def download(self) -> None:
    self._layout._params_memory.remove("CancelDownloadMaps")
    self._layout._params_memory.put_bool("DownloadMaps", True)

  def cancel(self) -> None:
    self._layout._params_memory.put_bool("CancelDownloadMaps", True)
    self._layout._params_memory.remove("DownloadMaps")

  def remove(self) -> None:
    self._layout._on_remove()   # upstream checks parked, confirms, and deletes


class MapsPage(Component):
  """The Offline Maps panel; tracks the download while open."""
  grow_touch_target = False

  def __init__(self, maps: Maps, open_regions: Callable[[], None]):
    super().__init__()
    self._maps = maps
    self._panel = self._child(maps_panel(maps, open_regions))

  def show_event(self):
    self._maps.source.refresh()
    super().show_event()

  def _update_state(self):
    self._maps.source.tick()

  def _render(self, rect: rl.Rectangle):
    self._panel.render(body_rect(rect))
