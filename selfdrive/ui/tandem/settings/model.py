"""Driving Model: the active model, Use recommended, and a catalog to download and switch models.

The catalog, downloads and switching are StarPilot's: UpstreamModels drives its model screen's controller,
which keeps its checks (no downloads while driving, one at a time, eGPU-only models) and its download thread.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import pyray as rl

from openpilot.system.ui.widgets import Widget
from openpilot.selfdrive.ui.tandem import tokens as T
from openpilot.selfdrive.ui.tandem.base import Component
from openpilot.selfdrive.ui.tandem.blocks import SPACER, Card, Columns, Inline, Label, Surface
from openpilot.selfdrive.ui.tandem.controls import Badge, Button, ButtonStyle, Segmented, Switch, Tone
from openpilot.selfdrive.ui.tandem.layout import FILL, row
from openpilot.selfdrive.ui.tandem.rows import ListPanel, SectionHeader, SettingRow, Text
from openpilot.selfdrive.ui.tandem.settings.pages import TitledPage
from openpilot.selfdrive.ui.tandem.settings.store import SettingsStore


@dataclass(frozen=True)
class ModelInfo:
  key: str
  name: str
  installed: bool
  community_pick: bool = False
  needs_egpu: bool = False
  removable: bool = True


class ModelSource(Protocol):
  def refresh(self) -> None: ...
  def tick(self) -> None: ...
  def models(self) -> list[ModelInfo]: ...
  def current_key(self) -> str: ...
  def recommended_key(self) -> str: ...
  def downloading_key(self) -> str | None: ...
  def progress(self) -> str: ...
  def egpu_available(self) -> bool: ...
  def free_space(self) -> str: ...
  def use(self, key: str) -> None: ...
  def download(self, key: str) -> None: ...
  def cancel(self) -> None: ...
  def remove(self, key: str) -> None: ...


class Models:
  def __init__(self, store: SettingsStore, source: ModelSource):
    self._store = store
    self.source = source

  def find(self, key: str) -> ModelInfo | None:
    return next((m for m in self.source.models() if m.key == key), None)

  def current_name(self) -> str:
    model = self.find(self.source.current_key())
    return model.name if model else "Default model"

  @property
  def use_recommended(self) -> bool:
    return self._store.get_bool("AutomaticallyDownloadModels") and self.source.current_key() == self.source.recommended_key()

  def set_use_recommended(self, on: bool) -> None:
    self._store.write({"AutomaticallyDownloadModels": on})
    if on:
      self.source.use(self.source.recommended_key())

  def status(self, model: ModelInfo) -> str:
    """One state per model: active, downloading, on device, not available, or downloadable."""
    if model.key == self.source.current_key():
      return "active"
    if model.key == self.source.downloading_key():
      return "downloading"
    if model.installed:
      return "on_device"
    if model.needs_egpu and not self.source.egpu_available():
      return "unavailable"
    return "download"

  def tab(self, index: int) -> list[ModelInfo]:
    models = self.source.models()
    if index == 1:
      return [m for m in models if m.community_pick]
    if index == 2:
      return [m for m in models if m.installed]
    return models

  def unused(self) -> list[ModelInfo]:
    return [m for m in self.source.models() if m.installed and m.removable and m.key not in (self.source.current_key(),
                                                                                          self.source.recommended_key())]

  def remove_unused(self) -> None:
    for model in self.unused():
      self.source.remove(model.key)

  def summary(self) -> str:
    return "Recommended" if self.use_recommended else self.current_name()

  def update_summary(self) -> str:
    if self.source.downloading_key():
      return "Downloading"
    return "Updates automatically" if self.use_recommended else "Chosen by you"


def model_row(models: Models, model: ModelInfo) -> SettingRow:
  def subtitle() -> str:
    status = models.status(model)
    return {
      "active": "Recommended · On device" if model.key == models.source.recommended_key() else "On device",
      "downloading": f"Downloading · {models.source.progress() or 'starting'}",
      "on_device": "On device",
      "unavailable": "Needs an eGPU",
      "download": "Community pick" if model.community_pick else "Available to download",
    }[status]

  def action() -> None:
    status = models.status(model)
    if status == "downloading":
      models.source.cancel()
    elif status == "on_device":
      models.source.use(model.key)
    elif status == "download":
      models.source.download(model.key)

  label = {"downloading": "Cancel", "on_device": "Use", "download": "Download", "unavailable": "Not available"}
  button = Button(lambda: label.get(models.status(model), ""), action)
  button.set_visible(lambda: models.status(model) != "active")
  button.set_enabled(lambda: models.status(model) != "unavailable" and (models.status(model) != "on_device" or not models.use_recommended))
  badge = Badge("ACTIVE", Tone.SUCCESS)
  badge.set_visible(lambda: models.status(model) == "active")
  return SettingRow(model.name, subtitle, Pair(badge, button), height=T.px(66))


class Pair(Component):
  """Whichever of two controls is visible (e.g. the ACTIVE badge or an action button)."""
  grow_touch_target = False

  def __init__(self, first: Component, second: Component):
    super().__init__()
    self._items = [self._child(first), self._child(second)]

  def _visible(self) -> Component:
    return next((w for w in self._items if w.is_visible), self._items[-1])

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    return self._visible().preferred_size(max_width)

  def set_parent_rect(self, parent_rect: rl.Rectangle) -> None:
    super().set_parent_rect(parent_rect)
    for w in self._items:
      w.set_parent_rect(parent_rect)

  def _render(self, rect: rl.Rectangle):
    self._visible().render(rect)


class Rebuilding(Component):
  """Rebuilds its content when key() changes, e.g. a list of models after a download finishes."""
  grow_touch_target = False

  def __init__(self, key: Callable[[], object], build: Callable[[], Widget], tick: Callable[[], None] | None = None,
               on_show: Callable[[], None] | None = None):
    super().__init__()
    self._on_show = on_show
    self._key_fn = key
    self._build = build
    self._tick = tick
    self._key: object = None
    self._content: Widget | None = None
    self._shown = False

  def show_event(self):
    super().show_event()
    self._shown = True
    if self._on_show is not None:
      self._on_show()
    if self._content is not None:
      self._content.show_event()

  def hide_event(self):
    super().hide_event()
    self._shown = False
    if self._content is not None:
      self._content.hide_event()

  def _update_state(self):
    if self._tick is not None:
      self._tick()
    key = self._key_fn()
    if self._content is None or key != self._key:
      if self._content is not None and self._shown:
        self._content.hide_event()
      self._key, self._content = key, self._build()
      if self._shown:
        self._content.show_event()

  def _render(self, rect: rl.Rectangle):
    if self._content is not None:
      self._content.render(rect)


def model_page(models: Models, open_catalog: Callable[[], None]) -> Widget:
  """The active model on an accent card at the left; other models on the device at the right."""
  def build() -> Widget:
    current = models.source.current_key()
    # Models on the device first, then community picks to download.
    others = sorted((m for m in models.source.models() if m.key != current and (m.installed or m.community_pick)),
                    key=lambda m: not m.installed)[:3]
    active = Card([
      Inline(Badge("ACTIVE", solid=True)),
      Label(models.current_name, T.font_px(26), weight=T.FONT_EXTRABOLD),
      Text(lambda: "Chosen for your car. Swaps to newer recommended models automatically." if models.use_recommended
           else "Picked by you", T.font_px(16), T.TEXT_TERTIARY, padding=(0, 0)),
      SPACER,
      Surface(SettingRow("Use recommended", "Turn off to pick your own", Switch(lambda: models.use_recommended,
                                                                              models.set_use_recommended), height=T.px(66)),
              T.ACCENT_INSET, T.px(16)),
    ], padding=(T.px(22), T.px(22)), tone="accent")
    browse = Button("Browse all", open_catalog, ButtonStyle.GHOST, height=T.px(32))
    other = ListPanel([
      SectionHeader("OTHER MODELS", trailing=browse),
      *[model_row(models, m) for m in others],
      Text("Available when Use recommended is off. Model randomizer and blacklist are in Tuner Mode.", T.SIZE_SUBTITLE),
    ])
    return Columns([active, other], [1, 1.2])

  return TitledPage("Driving Model", "The neural network that steers and judges speed",
                    Rebuilding(lambda: (models.source.current_key(), tuple((m.key, m.installed) for m in models.source.models())), build,
                               models.source.tick, on_show=models.source.refresh))


class CatalogPage(Component):
  """Tabs of models on the left; storage and notes on the right."""
  grow_touch_target = False
  TABS = ["All models", "Community picks", "On device"]

  def __init__(self, models: Models):
    super().__init__()
    self._models = models
    self._tab = 0
    tabs = Segmented(self.TABS, lambda: self._tab, self._select)
    self._list = self._child(Rebuilding(
      lambda: (self._tab, tuple((m.key, m.installed) for m in models.tab(self._tab))),
      lambda: ListPanel([model_row(models, m) for m in models.tab(self._tab)] or [Text("No models here yet.")],
                        title="Driving models", header_control=tabs),
      models.source.tick))
    self._side = self._child(ListPanel([
      SectionHeader("STORAGE"),
      SettingRow(models.source.free_space, None),
      SettingRow("Remove unused models", lambda: f"{len(models.unused())} can be removed",
                 Button("Remove", models.remove_unused, ButtonStyle.DANGER_OUTLINE)),
      SectionHeader("GOOD TO KNOW"),
      Text("One download at a time. Downloads pause while driving and resume when parked."),
      Text("A new model takes effect the next time you start the car."),
    ]))

  def _select(self, index: int) -> None:
    self._tab = index

  def _render(self, rect: rl.Rectangle):
    from openpilot.selfdrive.ui.tandem.settings.pages import body_rect
    left, right = row(body_rect(rect), [FILL, T.px(380)], T.PANEL_GAP)
    self._list.render(left)
    self._side.render(right)


class UpstreamModels:
  """ModelSource backed by StarPilot's driving model screen controller."""

  def __init__(self):
    from openpilot.selfdrive.ui.layouts.settings.starpilot import driving_model as dm
    self._dm = dm
    self._layout = dm.StarPilotDrivingModelLayout()

  def refresh(self) -> None:
    self._layout.show_event()   # fetches the manifest in the background

  def tick(self) -> None:
    self._layout._update_state()   # starts and tracks the download thread

  def models(self) -> list[ModelInfo]:
    entries = {e.key: e for e in self._layout.installed_entries() + self._layout.available_entries()}
    return [ModelInfo(e.key, self._dm._clean_model_name(e.name), e.installed, e.community_favorite, e.requires_external_gpu,
                      self._layout.is_model_removable(e.key)) for e in entries.values()]

  def current_key(self) -> str:
    entry = self._layout.current_entry()
    return entry.key if entry else ""

  def recommended_key(self) -> str:
    return self._dm.canonical_model_key(self._layout._default_model_key())

  def downloading_key(self) -> str | None:
    if not self._layout._is_download_active():
      return None
    active = self._layout._params_memory.get(self._dm.MODEL_DOWNLOAD_PARAM, encoding="utf-8") or ""
    return self._dm.canonical_model_key(active) or None

  def progress(self) -> str:
    return self._layout.download_progress_text()

  def egpu_available(self) -> bool:
    return bool(self._dm.external_gpu_available())

  def free_space(self) -> str:
    import shutil
    try:
      return f"{shutil.disk_usage(self._layout._model_dir).free / 1e9:.1f} GB free"
    except OSError:
      return "Free space unknown"

  def use(self, key: str) -> None:
    self._layout.select_model(key)

  def download(self, key: str) -> None:
    self._layout.start_download(key)

  def cancel(self) -> None:
    self._layout.cancel_active_download()

  def remove(self, key: str) -> None:
    self._layout.delete_model(key)
