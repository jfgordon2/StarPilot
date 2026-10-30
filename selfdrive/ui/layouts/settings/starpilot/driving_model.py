from __future__ import annotations

from dataclasses import dataclass, replace
from collections.abc import Callable
import json
import math
import shutil
import threading
import time

import pyray as rl

from openpilot.common.file_chunker import get_chunk_name, get_manifest_path
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.starpilot.assets.model_manager import (
  CANCEL_DOWNLOAD_PARAM,
  DOWNLOAD_PROGRESS_PARAM,
  MODEL_DOWNLOAD_ALL_PARAM,
  MODEL_DOWNLOAD_PARAM,
  ModelManager,
  canonical_model_key,
  external_gpu_available,
  is_builtin_model_key,
  model_uses_external_gpu,
  model_key_aliases,
  set_model_profile,
)
from openpilot.starpilot.common.starpilot_variables import MODELS_PATH, update_starpilot_toggles
from openpilot.system.ui.lib.application import FontWeight, MousePos, gui_app
from openpilot.system.ui.lib.multilang import tr
from openpilot.system.ui.lib.scroll_panel2 import GuiScrollPanel2
from openpilot.system.ui.widgets import DialogResult, Widget
from openpilot.system.ui.widgets.confirm_dialog import ConfirmDialog, alert_dialog
from openpilot.system.ui.widgets.option_dialog import MultiOptionDialog
from openpilot.selfdrive.ui.layouts.settings.starpilot.panel import _SettingsPage
from openpilot.system.ui.lib.text_measure import measure_text_cached
from openpilot.selfdrive.ui.lib import aether_style as AS
from openpilot.selfdrive.ui.layouts.settings.starpilot.aethergrid import (
  AETHER_LIST_METRICS,
  AetherButton,
  AetherInteractiveMixin,
  AetherListColors,
  AetherScrollbar,
  AetherSegmentedControl,
  DEFAULT_PANEL_STYLE,
  GROUP_OVERHEAD,
  aether_begin_scissor_mode,
  aether_end_scissor_mode,
  build_settings_group_frame,
  point_hits,
  draw_action_pill,
  draw_list_scroll_fades,
  draw_section_header,
  draw_settings_card_row,
  draw_settings_empty_state,
  draw_settings_group,
  draw_settings_group_heading,
  init_list_panel,
  settings_empty_state_height,
  with_alpha,
  SECTION_GAP,
  SETTINGS_ROW_VALUE_FONT_SIZE,
)
FADE_HEIGHT = AETHER_LIST_METRICS.fade_height
DRIVING_MODEL_METRICS = replace(AETHER_LIST_METRICS, header_height=0)
CONFIRM_TIMEOUT_SECONDS = 3.0
TRANSITION_SECONDS = 0.24
PANEL_STYLE = DEFAULT_PANEL_STYLE
MODEL_ROW_HEIGHT = 160.0  # same grouped row as Map Data's regions
DOWNLOAD_ALL_WIDTH = 520.0
_SORT_MODES = ("alphabetical", "date", "date_oldest", "favorites", "community_picks")
_SORT_LABELS = {
  "alphabetical":     "Alphabetical",
  "date":             "Date",
  "date_oldest":      "Date (Oldest)",
  "favorites":        "Favorites",
  "community_picks":  "Community",
}
_SORT_PILLS = ("alphabetical", "date", "favorites", "community_picks")


@dataclass
class ModelCatalogEntry:
  key: str
  name: str
  series: str
  version: str
  released: str
  builtin: bool
  installed: bool
  partial: bool
  community_favorite: bool
  user_favorite: bool
  requires_external_gpu: bool = False


def _clean_model_name(name: str) -> str:
  return str(name or "").replace("_default", "").replace("(Default)", "").strip()


def _ease(current: float, target: float, tau: float = 0.085) -> float:
  dt = max(rl.get_frame_time(), 1 / max(gui_app.target_fps, 1))
  return current + (target - current) * (1 - math.exp(-dt / tau))


class DrivingModelManagerView(AetherInteractiveMixin, Widget):
  """Driving Model page on the shared components.

  Page header: Refresh Catalog. Pinned: the sort segmented control (or Blacklist / Ratings while the
  randomizer is on). Scrolling: an "Active Model" group (current model, randomizer, download all), then
  the model groups as grouped rows with the shared 112 px action pills, like Map Data's regions.
  """

  def __init__(self, controller: StarPilotDrivingModelLayout):
    super().__init__()
    self._controller = controller
    self._scroll_panel = GuiScrollPanel2(horizontal=False)
    self._scrollbar = AetherScrollbar()
    self._content_height = 0.0
    self._scroll_offset = 0.0
    self._confirm_key: str | None = None
    self._confirm_until = 0.0
    self._transition_starts: dict[str, tuple[float, float]] = {}
    self._known_install_state: dict[str, bool] = {}
    self._active_download_key: str | None = None
    self._shell_rect = rl.Rectangle(0, 0, 0, 0)
    self._scroll_rect = rl.Rectangle(0, 0, 0, 0)
    self._refresh_button = self._child(AetherButton(
      lambda: self._controller.secondary_header_button_state()[0],
      self._controller.refresh_manifest,
      enabled=lambda: self._controller.secondary_header_button_state()[1],
    ))
    self._download_all_button = self._child(AetherButton(
      lambda: self._controller.primary_header_button_state()[0],
      lambda: self._controller.cancel_active_download() if self._controller._is_download_active() else self._controller.download_all_missing(),
      enabled=lambda: self._controller.primary_header_button_state()[1],
      emphasized=True,
      accent_color=AS.ACCENT_SOLID,
    ))
    self._sort_control = self._child(AetherSegmentedControl(
      [tr(_SORT_LABELS[mode]) for mode in _SORT_PILLS],
      self._sort_index,
      lambda index: self._controller._params.put("ModelSortMode", _SORT_PILLS[index]),
      statuses=[tr("A to Z"), self._date_status, tr("Then downloaded"), tr("Most popular")],
      style=PANEL_STYLE,
      on_reselect=self._on_sort_reselect,
    ))
    self._blacklist_button = self._child(AetherButton(self._blacklist_label, self._controller._on_blacklist_clicked, neutral=True))
    self._ratings_button = self._child(AetherButton(tr("Ratings"), self._controller._on_scores_clicked, neutral=True))
    self._download_all_button.set_touch_valid_callback(lambda: self._scroll_panel.is_touch_valid())

  def use_page_header(self) -> AetherButton:
    return self._refresh_button

  def _sort_index(self) -> int:
    mode = self._controller._get_sort_mode()
    return _SORT_PILLS.index("date" if mode == "date_oldest" else mode) if mode in (*_SORT_PILLS, "date_oldest") else 0

  def _date_status(self) -> str:
    return tr("Oldest first") if self._controller._get_sort_mode() == "date_oldest" else tr("Newest first")

  def _on_sort_reselect(self, index: int):
    if _SORT_PILLS[index] == "date":
      current = self._controller._get_sort_mode()
      self._controller._params.put("ModelSortMode", "date" if current == "date_oldest" else "date_oldest")

  def _blacklist_label(self) -> str:
    blacklisted = [m.strip() for m in (self._controller._params.get("BlacklistedModels", encoding="utf-8") or "").split(",") if m.strip()]
    return tr("Blacklist: {} blocked").format(len(blacklisted)) if blacklisted else tr("Blacklist")

  def _clear_ephemeral_state(self):
    self._pressed_target = None
    self._can_click = True
    self._confirm_key = None
    self._confirm_until = 0.0

  def show_event(self):
    super().show_event()
    self._clear_ephemeral_state()

  def hide_event(self):
    super().hide_event()
    self._clear_ephemeral_state()

  def _update_state(self):
    super()._update_state()

    if self._confirm_key is not None and time.monotonic() >= self._confirm_until:
      self._confirm_key = None

    progress = self._controller.download_progress_text()
    active_key = canonical_model_key(self._controller._params_memory.get(MODEL_DOWNLOAD_PARAM, encoding="utf-8") or "")
    if active_key:
      self._active_download_key = active_key
    elif self._controller._params_memory.get_bool(MODEL_DOWNLOAD_ALL_PARAM):
      parsed_key = self._controller._model_key_for_progress(progress)
      if parsed_key:
        self._active_download_key = parsed_key
    elif not self._controller._is_download_active():
      self._active_download_key = None

    latest_state = {key: entry.installed for key, entry in self._controller._catalog_entries.items()}
    for key, installed in latest_state.items():
      previous = self._known_install_state.get(key)
      if previous is None:
        self._known_install_state[key] = installed
        continue
      if previous != installed:
        self._transition_starts[key] = (time.monotonic(), 1.0 if installed else -1.0)
        self._known_install_state[key] = installed

    for key in list(self._transition_starts.keys()):
      started_at, _direction = self._transition_starts[key]
      if time.monotonic() - started_at >= TRANSITION_SECONDS:
        self._transition_starts.pop(key, None)

  def _target_at(self, mouse_pos: MousePos) -> str | None:
    # Menu pills sit over their row, so they win over the row underneath.
    for prefix in ("menu:", "action:", "row:", "active:"):
      for target_id, rect in self._interactive_rects.items():
        if target_id.startswith(prefix) and point_hits(mouse_pos, rect, self._scroll_rect, pad_x=0, pad_y=0):
          return target_id
    return None

  def _activate_target(self, target: str | None):
    if not target:
      return

    if target == "active:randomizer":
      self._controller.toggle_model_randomizer()
      return

    if target.startswith("row:"):
      self._confirm_key = None
      self._controller.select_model(target.split(":", 1)[1])
      return

    if target.startswith("action:"):
      model_key = target.split(":", 1)[1]
      entry = self._controller._catalog_entries.get(model_key)
      if entry is None:
        return
      if not entry.installed:
        self._confirm_key = None
        self._controller.start_download(model_key)
        return
      if not self._controller.is_model_removable(model_key):
        return
      # Toggle the Delete / Favorite pills open or closed.
      if self._confirm_key == model_key:
        self._confirm_key = None
      else:
        self._confirm_key = model_key
        self._confirm_until = time.monotonic() + CONFIRM_TIMEOUT_SECONDS
      return

    if target.startswith("menu:"):
      parts = target.split(":", 2)
      model_key = parts[1] if len(parts) > 1 else ""
      action = parts[2] if len(parts) > 2 else ""
      self._confirm_key = None
      if action == "delete":
        self._controller.delete_model(model_key)
      elif action == "favorite":
        self._controller.toggle_favorite(model_key)

  # ── layout ─────────────────────────────────────────────────

  def _render(self, rect: rl.Rectangle):
    self.set_rect(rect)
    self._interactive_rects.clear()

    frame, scroll_rect, content_width = init_list_panel(rect, PANEL_STYLE, metrics=DRIVING_MODEL_METRICS)
    self._shell_rect = frame.shell

    pinned_h = self._draw_pinned_controls(rl.Rectangle(scroll_rect.x, scroll_rect.y, content_width, 0))
    scroll_rect = rl.Rectangle(scroll_rect.x, scroll_rect.y + pinned_h, scroll_rect.width, max(0.0, scroll_rect.height - pinned_h))
    self._scroll_rect = scroll_rect

    self._content_height = self._measure_content_height(content_width)
    self._scroll_panel.set_enabled(lambda: not self._controller._is_download_active())
    self._scroll_offset = self._scroll_panel.update(scroll_rect, max(self._content_height, scroll_rect.height))

    aether_begin_scissor_mode(int(scroll_rect.x), int(scroll_rect.y), int(scroll_rect.width), int(scroll_rect.height))
    self._draw_scroll_content(scroll_rect, content_width)
    aether_end_scissor_mode()

    if self._content_height > scroll_rect.height:
      self._scrollbar.render(scroll_rect, self._content_height, self._scroll_offset)
    draw_list_scroll_fades(scroll_rect, self._content_height, self._scroll_offset, AetherListColors.PANEL_BG, fade_height=FADE_HEIGHT)

  def _draw_pinned_controls(self, rect: rl.Rectangle) -> float:
    """Sort control, or the randomizer's Blacklist / Ratings buttons, pinned like System's mode control."""
    if self._controller._params.get_bool("ModelRandomizer"):
      height = AS.MIN_TOUCH
      half = (rect.width - AS.SETTINGS_TILE_GAP) / 2
      self._blacklist_button.render(rl.Rectangle(rect.x, rect.y, half, height))
      self._ratings_button.render(rl.Rectangle(rect.x + half + AS.SETTINGS_TILE_GAP, rect.y, half, height))
    else:
      height = self._sort_control.measure_height(rect.width)
      self._sort_control.render(rl.Rectangle(rect.x, rect.y, rect.width, height))
    return height + AetherSegmentedControl.GAP

  def _get_sections(self) -> list[tuple[str, list[ModelCatalogEntry]]]:
    sort_mode = self._controller._get_sort_mode()
    is_current = self._controller.is_current_model

    if sort_mode == "favorites":
      fav_entries = [e for e in self._controller.favorites_entries() if not is_current(e.key)]
      fav_keys = {e.key for e in self._controller.favorites_entries()}
      other_installed = [e for e in self._controller.installed_entries() if e.key not in fav_keys and not is_current(e.key)]
      sections = []
      if fav_entries:
        sections.append((tr("Favorites"), fav_entries))
      if other_installed:
        sections.append((tr("Downloaded"), other_installed))
      return sections

    if sort_mode == "community_picks":
      entries = [e for e in self._controller.community_picks_entries() if not is_current(e.key)]
      return [(tr("Community Picks"), entries)] if entries else []

    installed = [e for e in self._controller.installed_entries() if not is_current(e.key)]
    available = [] if self._controller._params.get_bool("ModelRandomizer") else self._controller.available_entries()
    sections = []
    if installed:
      sections.append((tr("On Device"), installed))
    if available:
      sections.append((tr("Available to Download"), available))
    return sections

  def _active_rows(self) -> list[str]:
    rows = ["current"] if self._controller.current_entry() is not None else []
    return rows + ["randomizer", "download_all"]

  def _measure_content_height(self, width: float) -> float:
    total = GROUP_OVERHEAD + len(self._active_rows()) * MODEL_ROW_HEIGHT
    sections = self._get_sections()
    if not sections:
      return total + SECTION_GAP + GROUP_OVERHEAD + settings_empty_state_height()
    for _title, entries in sections:
      total += SECTION_GAP + GROUP_OVERHEAD + len(entries) * MODEL_ROW_HEIGHT
    return float(total)

  def _draw_scroll_content(self, rect: rl.Rectangle, width: float):
    y = self._draw_active_group(rl.Rectangle(rect.x, rect.y + self._scroll_offset, width, 0))
    sections = self._get_sections()
    if not sections:
      group = rl.Rectangle(rect.x, y + SECTION_GAP, width, GROUP_OVERHEAD + settings_empty_state_height())
      body = draw_settings_group_heading(group, tr("Models"), style=PANEL_STYLE)
      draw_settings_empty_state(body, self._controller.empty_state_title(), self._controller.empty_state_body(), style=PANEL_STYLE)
      return
    for title, entries in sections:
      y = self._draw_model_section(rect.x, y + SECTION_GAP, width, title, entries)

  def _draw_active_group(self, rect: rl.Rectangle) -> float:
    rows = self._active_rows()
    group = rl.Rectangle(rect.x, rect.y, rect.width, GROUP_OVERHEAD + len(rows) * MODEL_ROW_HEIGHT)
    body = draw_settings_group(group, tr("Active Model"), style=PANEL_STYLE)
    y = body.y
    randomizer_on = self._controller._params.get_bool("ModelRandomizer")
    for index, row in enumerate(rows):
      row_rect = rl.Rectangle(body.x, y, body.width, MODEL_ROW_HEIGHT)
      is_last = index == len(rows) - 1
      if row == "current":
        entry = self._controller.current_entry()
        assert entry is not None
        self._draw_model_row(row_rect, entry, is_last=is_last)
      elif row == "randomizer":
        hovered, pressed = self._interactive_state("active:randomizer", row_rect)
        draw_settings_card_row(row_rect, title=tr("Model Randomizer"), subtitle=tr("Drive a random downloaded model each time"),
                               toggle_value=randomizer_on, hovered=hovered, pressed=pressed, grouped=True, is_last=is_last,
                               style=PANEL_STYLE)
      else:
        draw_settings_card_row(row_rect, title=tr("Download Models"), subtitle=self._controller.header_description_text(),
                               show_chevron=False, grouped=True, is_last=is_last, style=PANEL_STYLE)
        button_w = min(DOWNLOAD_ALL_WIDTH, row_rect.width * 0.42)
        button_rect = rl.Rectangle(row_rect.x + row_rect.width - AS.SETTINGS_CARD_INSET - button_w,
                                   row_rect.y + (row_rect.height - AS.MIN_TOUCH) / 2, button_w, AS.MIN_TOUCH)
        self._download_all_button.set_parent_rect(self._scroll_rect)
        self._download_all_button.render(button_rect)
      y += MODEL_ROW_HEIGHT
    return group.y + group.height

  def _draw_model_section(self, x: float, y: float, width: float, title: str, entries: list[ModelCatalogEntry]) -> float:
    group = rl.Rectangle(x, y, width, GROUP_OVERHEAD + len(entries) * MODEL_ROW_HEIGHT)
    body = draw_settings_group(group, title, style=PANEL_STYLE)
    draw_section_header(build_settings_group_frame(group).heading, "", trailing_text=str(len(entries)),
                        trailing_size=AS.SETTINGS_GROUP_HEADING_SIZE - 4, style=PANEL_STYLE)
    visible_top, visible_bottom = self._scroll_rect.y - MODEL_ROW_HEIGHT, self._scroll_rect.y + self._scroll_rect.height
    for index, entry in enumerate(entries):
      row_y = body.y + index * MODEL_ROW_HEIGHT
      if visible_top <= row_y <= visible_bottom:
        self._draw_model_row(rl.Rectangle(body.x, row_y, body.width, MODEL_ROW_HEIGHT), entry, is_last=index == len(entries) - 1)
    return group.y + group.height

  # ── model rows ─────────────────────────────────────────────

  def _model_subtitle(self, entry: ModelCatalogEntry, current: bool) -> tuple[str, bool]:
    parts: list[str] = [part for part in (entry.series, entry.released) if part]
    if self._controller._params.get_bool("ModelRandomizer"):
      parts.append(tr("In Pool"))
    elif current:
      parts.append(tr("Active"))
    elif entry.builtin:
      parts.append(tr("Built-in"))
    if entry.user_favorite:
      parts.append(tr("Favorite"))
    if entry.partial:
      parts.append(tr("Incomplete"))
    if entry.requires_external_gpu:
      parts.append(tr("GPU required"))
    if not entry.user_favorite and entry.community_favorite:
      parts.append(tr("Popular"))
    return " • ".join(parts), entry.partial or entry.requires_external_gpu

  def _model_action(self, entry: ModelCatalogEntry, current: bool) -> tuple[str, str]:
    """(label, kind) for the row's pill; kind is current, protected, options, downloading or download."""
    if entry.installed:
      if current and not self._controller._params.get_bool("ModelRandomizer"):
        return tr("Current"), "current"
      if not self._controller.is_model_removable(entry.key):
        return tr("Protected"), "protected"
      return tr("Options"), "options"
    if self._controller.is_entry_actively_downloading(entry.key, self._active_download_key):
      return self._controller.download_progress_text() or tr("Downloading..."), "downloading"
    return tr("Download"), "download"

  def _draw_model_row(self, rect: rl.Rectangle, entry: ModelCatalogEntry, is_last: bool):
    current = self._controller.is_current_model(entry.key)
    row_touchable = entry.installed and not self._controller._params.get_bool("ModelRandomizer")
    hovered, pressed = self._interactive_state(f"row:{entry.key}", rect) if row_touchable else (False, False)
    subtitle, warning = self._model_subtitle(entry, current)
    alpha = self._row_alpha(entry.key)
    label, kind = self._model_action(entry, current)

    if self._confirm_key == entry.key:
      draw_settings_card_row(rect, title=entry.name, subtitle=subtitle, show_chevron=False, hovered=hovered, pressed=pressed,
                             current=current, grouped=True, is_last=is_last, alpha=alpha, style=PANEL_STYLE,
                             subtitle_color=AetherListColors.WARNING if warning else None)
      self._draw_options_menu(rect, entry)
      return

    action_kwargs = {}
    if kind == "current":
      action_kwargs = {"action_fill": with_alpha(AetherListColors.SUCCESS_SOFT, 60), "action_border": AetherListColors.SUCCESS}
    elif kind == "protected":
      action_kwargs = {"action_fill": with_alpha(AS.TRACK_OFF, 120), "action_border": AS.SETTINGS_TILE_BORDER,
                       "action_text_color": AS.TEXT_SECONDARY}
    elif kind in ("options", "downloading"):
      action_kwargs = {"action_fill": with_alpha(AS.TRACK_OFF, 160), "action_border": AS.SETTINGS_TILE_BORDER}
    action = draw_settings_card_row(
      rect, title=entry.name, subtitle=subtitle, action_text=label, hovered=hovered, pressed=pressed, current=current,
      grouped=True, is_last=is_last, alpha=alpha, style=PANEL_STYLE, action_text_size=SETTINGS_ROW_VALUE_FONT_SIZE,
      action_height=AS.VALUE_PILL_HEIGHT, subtitle_color=AetherListColors.WARNING if warning else None, **action_kwargs,
    )
    if kind in ("options", "download", "downloading"):
      self._interactive_rects[f"action:{entry.key}"] = action
    if row_touchable:
      # The row selects the model; the pill on its right does its own action.
      self._interactive_rects[f"row:{entry.key}"] = rl.Rectangle(rect.x, rect.y, max(0.0, action.x - rect.x), rect.height)

  def _draw_options_menu(self, rect: rl.Rectangle, entry: ModelCatalogEntry):
    font = gui_app.font(FontWeight.SEMI_BOLD)
    labels = [(tr("Delete"), "delete"), (tr("Unfavorite") if entry.user_favorite else tr("Favorite"), "favorite")]
    right = rect.x + rect.width - AS.SETTINGS_CARD_INSET
    y = rect.y + (rect.height - AS.VALUE_PILL_HEIGHT) / 2
    for label, action in reversed(labels):
      width = max(AS.MIN_TOUCH * 1.4, measure_text_cached(font, label, SETTINGS_ROW_VALUE_FONT_SIZE).x + AS.SETTINGS_CARD_INSET * 2)
      pill = rl.Rectangle(right - width, y, width, AS.VALUE_PILL_HEIGHT)
      if action == "delete":
        fill, border = AetherListColors.DANGER_SOFT, with_alpha(AetherListColors.DANGER, 140)
      else:
        fill, border = AS.ACCENT_TINT, AS.ACCENT_EDGE
      draw_action_pill(pill, label, fill, border, AS.TEXT, font_size=SETTINGS_ROW_VALUE_FONT_SIZE)
      self._interactive_rects[f"menu:{entry.key}:{action}"] = pill
      right = pill.x - AS.SETTINGS_CONTROL_GAP

  def _row_alpha(self, key: str) -> int:
    if key not in self._transition_starts:
      return 255
    started_at, _direction = self._transition_starts[key]
    elapsed = min(max((time.monotonic() - started_at) / TRANSITION_SECONDS, 0.0), 1.0)
    return int(150 + 105 * (1.0 - (1.0 - elapsed) * (1.0 - elapsed)))


class StarPilotDrivingModelLayout(_SettingsPage):
  def __init__(self):
    super().__init__()

    self._model_dir = MODELS_PATH
    self._model_dir.mkdir(parents=True, exist_ok=True)

    self._catalog_entries: dict[str, ModelCatalogEntry] = {}
    self._model_file_to_name: dict[str, str] = {}
    self._model_file_to_name_processed: dict[str, str] = {}
    self._model_series_map: dict[str, str] = {}
    self._model_released_dates: dict[str, str] = {}
    self._model_version_map: dict[str, str] = {}
    self._community_favorites: set[str] = set()
    self._user_favorites: set[str] = set()
    self._current_model_key = self._default_model_key()
    self._current_model_name = self._default_model_name()

    self._model_manager = ModelManager(self._params, self._params_memory)
    self._download_thread: threading.Thread | None = None
    self._manifest_fetch_thread: threading.Thread | None = None
    self._manifest_fetched = False
    self._transient_status_text = ""
    self._transient_status_until = 0.0
    self._manager_view = DrivingModelManagerView(self)

    self._fetch_manifest_async()
    self._update_model_metadata()

  def _render(self, rect: rl.Rectangle):
    self._update_state()
    super()._render(rect)

  def show_event(self):
    super().show_event()
    self._fetch_manifest_async()
    self._update_model_metadata()

  def _fetch_manifest_async(self):
    if self._manifest_fetch_thread is not None and self._manifest_fetch_thread.is_alive():
      return

    def _task():
      try:
        self._model_manager.update_models()
      finally:
        self._manifest_fetched = True

    self._manifest_fetch_thread = threading.Thread(target=_task, daemon=True)
    self._manifest_fetch_thread.start()

  def _default_model_key(self) -> str:
    default_key = self._params.get_default_value("Model") or self._params.get_default_value("DrivingModel")
    if isinstance(default_key, bytes):
      default_key = default_key.decode("utf-8", errors="ignore")
    return canonical_model_key(str(default_key or "").strip()) or "rdf43"

  def _default_model_name(self) -> str:
    default_name = self._params.get_default_value("DrivingModelName")
    if isinstance(default_name, bytes):
      default_name = default_name.decode("utf-8", errors="ignore")
    return _clean_model_name(default_name or "") or "Regret Driven Framework V4"

  def _default_model_version(self) -> str:
    default_version = self._params.get_default_value("ModelVersion") or self._params.get_default_value("DrivingModelVersion")
    if isinstance(default_version, bytes):
      default_version = default_version.decode("utf-8", errors="ignore")
    return str(default_version or "").strip() or "v15"

  def _current_selected_key(self) -> str:
    current_key = self._params.get("Model", encoding="utf-8") or self._params.get("DrivingModel", encoding="utf-8") or ""
    return canonical_model_key(str(current_key).strip()) or self._default_model_key()

  def _load_on_disk_files(self) -> set[str]:
    try:
      return {entry.name for entry in self._model_dir.iterdir()}
    except Exception:
      return set()

  def _artifact_installed(self, filename: str, on_disk_files: set[str]) -> bool:
    if filename in on_disk_files:
      return True

    manifest = get_manifest_path(filename)
    if manifest not in on_disk_files:
      return False

    try:
      num_chunks = int((self._model_dir / manifest).read_text().strip())
    except Exception:
      return False

    return all(get_chunk_name(filename, idx, num_chunks) in on_disk_files for idx in range(num_chunks))

  def _is_model_installed(self, key: str, version: str = "", on_disk_files: set[str] | None = None) -> bool:
    model_key = canonical_model_key(str(key or "").strip())
    if not model_key:
      return False

    if is_builtin_model_key(model_key):
      return True

    files = on_disk_files if on_disk_files is not None else self._load_on_disk_files()
    return self._artifact_installed(f"{model_key}_driving_tinygrad.pkl", files)

  def _required_files_for_version(self, key: str, version: str) -> list[str]:
    del version
    return [f"{key}_driving_tinygrad.pkl"]

  def _ensure_default_model_visible(self):
    default_key = self._default_model_key()
    default_name = self._default_model_name()
    default_series = tr("Custom Series")
    default_released = ""

    for alias in model_key_aliases(default_key):
      alias = canonical_model_key(alias)
      if alias not in self._model_file_to_name:
        continue

      default_name = self._model_file_to_name.get(alias, default_name)
      default_series = self._model_series_map.get(alias, default_series)
      default_released = self._model_released_dates.get(alias, default_released)

      if alias != default_key:
        self._model_file_to_name.pop(alias, None)
        self._model_file_to_name_processed.pop(alias, None)
        self._model_series_map.pop(alias, None)
        self._model_released_dates.pop(alias, None)
        self._model_version_map.pop(alias, None)
        self._catalog_entries.pop(alias, None)

    version = self._model_version_map.get(default_key, self._default_model_version())
    self._model_file_to_name[default_key] = default_name
    self._model_file_to_name_processed[default_key] = _clean_model_name(default_name)
    self._model_series_map[default_key] = default_series
    if default_released:
      self._model_released_dates[default_key] = default_released
    self._model_version_map.setdefault(default_key, version)

  def _build_catalog_entries(self, on_disk_files: set[str]):
    self._catalog_entries.clear()
    self._model_file_to_name.clear()
    self._model_file_to_name_processed.clear()
    self._model_series_map.clear()
    self._model_released_dates.clear()
    self._model_version_map.clear()

    available_models = [entry.strip() for entry in (self._params.get("AvailableModels", encoding="utf-8") or "").split(",")]
    available_names = [entry.strip() for entry in (self._params.get("AvailableModelNames", encoding="utf-8") or "").split(",")]
    available_series = [entry.strip() for entry in (self._params.get("AvailableModelSeries", encoding="utf-8") or "").split(",")]
    available_versions = [entry.strip() for entry in (self._params.get("ModelVersions", encoding="utf-8") or "").split(",")]
    released_dates = [entry.strip() for entry in (self._params.get("ModelReleasedDates", encoding="utf-8") or "").split(",")]

    self._community_favorites = {
      canonical_model_key(entry.strip()) for entry in (self._params.get("CommunityFavorites", encoding="utf-8") or "").split(",") if entry.strip()
    }
    self._user_favorites = {
      canonical_model_key(entry.strip()) for entry in (self._params.get("UserFavorites", encoding="utf-8") or "").split(",") if entry.strip()
    }

    size = min(len(available_models), len(available_names))
    for i in range(size):
      canonical_key = canonical_model_key(available_models[i])
      name = available_names[i].strip()
      if not canonical_key or not name:
        continue

      series = available_series[i].strip() if i < len(available_series) and available_series[i].strip() else tr("Custom Series")
      version = available_versions[i].strip() if i < len(available_versions) else ""
      released = released_dates[i].strip() if i < len(released_dates) else ""

      self._model_file_to_name.setdefault(canonical_key, name)
      self._model_file_to_name_processed.setdefault(canonical_key, _clean_model_name(name))
      self._model_series_map.setdefault(canonical_key, series)
      if released:
        self._model_released_dates.setdefault(canonical_key, released)
      if version:
        self._model_version_map.setdefault(canonical_key, version)

    self._ensure_default_model_visible()

    for key, name in self._model_file_to_name.items():
      version = self._model_version_map.get(key, self._default_model_version() if is_builtin_model_key(key) else "")
      installed = self._is_model_installed(key, version, on_disk_files)
      partial = (not is_builtin_model_key(key)) and (not installed) and any(file.startswith(f"{key}.") or file.startswith(f"{key}_") for file in on_disk_files)
      self._catalog_entries[key] = ModelCatalogEntry(
        key=key,
        name=name,
        series=self._model_series_map.get(key, tr("Custom Series")),
        version=version,
        released=self._model_released_dates.get(key, ""),
        builtin=is_builtin_model_key(key),
        installed=installed,
        partial=partial,
        community_favorite=(key in self._community_favorites),
        user_favorite=(key in self._user_favorites),
        requires_external_gpu=model_uses_external_gpu(key),
      )

  def _update_model_metadata(self):
    on_disk_files = self._load_on_disk_files()
    self._build_catalog_entries(on_disk_files)

    self._current_model_key = self._current_selected_key()
    current_entry = self._catalog_entries.get(self._current_model_key)
    if current_entry is None or not current_entry.installed:
      self._current_model_key = self._default_model_key()
      current_entry = self._catalog_entries.get(self._current_model_key)

    if current_entry is not None:
      self._current_model_name = current_entry.name
    else:
      self._current_model_name = self._default_model_name()

  def _show_selection_dialog(self, title: str, options: dict[str, str] | list[str], current_val: str, on_confirm: Callable, current_key: str = ""):
    if not options:
      gui_app.push_widget(alert_dialog(tr("No options available.")))
      return

    option_labels = list(options.values()) if isinstance(options, dict) else list(options)

    def _on_close(result):
      if result == DialogResult.CONFIRM and dialog.selection:
        if isinstance(options, dict):
          reverse_map = {value: key for key, value in options.items()}
          on_confirm(reverse_map.get(dialog.selection, dialog.selection))
        else:
          on_confirm(dialog.selection)

    dialog = MultiOptionDialog(title, option_labels, current_val, callback=_on_close,
                               subtitle=tr("Choose a driving model to continue."))
    gui_app.push_widget(dialog)

  def _is_download_active(self) -> bool:
    return bool(self._params_memory.get(MODEL_DOWNLOAD_PARAM, encoding="utf-8") or self._params_memory.get_bool(MODEL_DOWNLOAD_ALL_PARAM))

  def _selected_model_version(self, model_key: str) -> str:
    version = self._model_version_map.get(model_key, "")
    if version:
      return version

    try:
      versions_file = self._model_dir / ".model_versions.json"
      if versions_file.is_file():
        payload = json.loads(versions_file.read_text())
        if isinstance(payload, dict):
          for alias in model_key_aliases(model_key):
            resolved = str(payload.get(alias, "")).strip()
            if resolved:
              return resolved
    except Exception:
      pass

    if is_builtin_model_key(model_key):
      return self._default_model_version()
    return ""

  def installed_entries(self) -> list[ModelCatalogEntry]:
    entries = [entry for entry in self._catalog_entries.values() if entry.installed]
    sort_mode = self._get_sort_mode()
    if sort_mode == "date":
      return sorted(entries, key=lambda e: (e.released or "0000-00-00", self._model_file_to_name_processed.get(e.key, e.name).lower(), e.key), reverse=True)
    if sort_mode == "date_oldest":
      return sorted(entries, key=lambda e: (e.released or "0000-00-00", self._model_file_to_name_processed.get(e.key, e.name).lower(), e.key))
    return sorted(entries, key=lambda e: (0 if e.builtin else 1, self._model_file_to_name_processed.get(e.key, e.name).lower(), e.key))

  def available_entries(self) -> list[ModelCatalogEntry]:
    entries = [entry for entry in self._catalog_entries.values() if not entry.installed]
    sort_mode = self._get_sort_mode()
    if sort_mode == "date":
      return sorted(entries, key=lambda e: (e.released or "0000-00-00", self._model_file_to_name_processed.get(e.key, e.name).lower(), e.key), reverse=True)
    if sort_mode == "date_oldest":
      return sorted(entries, key=lambda e: (e.released or "0000-00-00", self._model_file_to_name_processed.get(e.key, e.name).lower(), e.key))
    return sorted(entries, key=lambda e: (self._model_file_to_name_processed.get(e.key, e.name).lower(), e.key))

  def community_picks_entries(self) -> list[ModelCatalogEntry]:
    entries = [entry for entry in self._catalog_entries.values() if entry.community_favorite]
    if self._params.get_bool("ModelRandomizer"):
      entries = [e for e in entries if e.installed]
    return sorted(entries, key=lambda e: (
      self._model_file_to_name_processed.get(e.key, e.name).lower(),
      e.key
    ))

  def favorites_entries(self) -> list[ModelCatalogEntry]:
    entries = [entry for entry in self._catalog_entries.values() if entry.user_favorite]
    if self._params.get_bool("ModelRandomizer"):
      entries = [e for e in entries if e.installed]
    return sorted(entries, key=lambda e: (
      self._model_file_to_name_processed.get(e.key, e.name).lower(),
      e.key
    ))

  def is_current_model(self, model_key: str) -> bool:
    return canonical_model_key(model_key) == self._current_model_key

  def current_entry(self) -> ModelCatalogEntry | None:
    return self._catalog_entries.get(self._current_model_key)

  def _get_sort_mode(self) -> str:
    mode = (self._params.get("ModelSortMode", encoding="utf-8") or "").strip()
    return mode if mode in _SORT_MODES else _SORT_MODES[0]

  def is_model_removable(self, model_key: str) -> bool:
    key = canonical_model_key(model_key)
    if not key:
      return False
    if is_builtin_model_key(key):
      return False
    if key == self._default_model_key() or key == self._current_model_key:
      return False
    return self._catalog_entries.get(key, ModelCatalogEntry(key, "", "", "", "", False, False, False, False, False)).installed

  def is_entry_actively_downloading(self, model_key: str, active_key: str | None) -> bool:
    if not self._is_download_active():
      return False
    return canonical_model_key(model_key) == canonical_model_key(active_key or "")

  def download_progress_text(self) -> str:
    progress = self._params_memory.get(DOWNLOAD_PROGRESS_PARAM, encoding="utf-8") or ""
    if progress:
      return progress
    if self._transient_status_text and time.monotonic() < self._transient_status_until:
      return self._transient_status_text
    return ""

  def _model_key_for_progress(self, progress_text: str) -> str | None:
    if not progress_text:
      return None

    lower_progress = progress_text.lower()
    for key, entry in self._catalog_entries.items():
      if f'"{entry.name}"'.lower() in lower_progress:
        return key
      clean_name = _clean_model_name(entry.name).lower()
      if clean_name and clean_name in lower_progress:
        return key
    return None

  def primary_header_button_state(self) -> tuple[str, bool]:
    if self._is_download_active():
      return tr("Cancel Download"), True
    missing_count = len(self.available_entries())
    if missing_count == 0:
      return tr("All Models On Device"), False
    if ui_state.started:
      return tr("Downloads Pause Onroad"), False
    return tr(f"Download All Missing ({missing_count})"), True

  def secondary_header_button_state(self) -> tuple[str, bool]:
    if self._manifest_fetch_thread is not None and self._manifest_fetch_thread.is_alive():
      return tr("Refreshing..."), False
    if ui_state.started or self._is_download_active():
      return tr("Refresh Catalog"), False
    return tr("Refresh Catalog"), True

  def header_description_text(self) -> str:
    if self._is_download_active():
      return self.download_progress_text() or tr("Downloading model files...")
    if self._manifest_fetch_thread is not None and self._manifest_fetch_thread.is_alive():
      return tr("Refreshing the driving model catalog in the background.")
    if ui_state.started:
      return tr("Downloads and removals pause while driving.")
    return tr("Tap a downloaded model to set it as active.")

  def empty_state_title(self) -> str:
    if self._params.get_bool("ModelRandomizer"):
      return tr("Model Randomizer Active")
    if self._manifest_fetch_thread is not None and self._manifest_fetch_thread.is_alive():
      return tr("Refreshing model catalog")
    return tr("No models available")

  def empty_state_body(self) -> str:
    if self._params.get_bool("ModelRandomizer"):
      return tr("Models are selected automatically each drive. Disable Randomizer to choose manually.")
    if self._manifest_fetch_thread is not None and self._manifest_fetch_thread.is_alive():
      return tr("StarPilot is pulling the latest driving model list. This panel will populate automatically when the refresh completes.")
    return tr("Try refreshing the catalog once the device is offroad and connected.")


  def select_model(self, model_key: str):
    selected_model = canonical_model_key(model_key)
    entry = self._catalog_entries.get(selected_model)
    if entry is None or not entry.installed:
      gui_app.push_widget(alert_dialog(tr("Model is not available on this device.")))
      return False
    if entry.requires_external_gpu and not external_gpu_available():
      gui_app.push_widget(alert_dialog(tr("This model requires a detected external GPU.")))
      return False
    if self._params.get_bool("ModelRandomizer"):
      gui_app.push_widget(alert_dialog(tr("Turn off Model Randomizer to choose a model manually.")))
      return False
    if selected_model == self._current_model_key:
      return True

    self._params.put("Model", selected_model)
    self._params.put("DrivingModel", selected_model)
    self._params.put("DrivingModelName", entry.name)
    resolved_version = self._selected_model_version(selected_model)
    resolved_version = resolved_version or entry.version or self._default_model_version()
    self._params.put("ModelVersion", resolved_version)
    self._params.put("DrivingModelVersion", resolved_version)
    set_model_profile(
      self._params,
      "big" if entry.requires_external_gpu else "small",
      selected_model,
      entry.name,
      resolved_version,
    )
    update_starpilot_toggles()
    self._update_model_metadata()
    if ui_state.started:
      self._params.put_bool("OnroadCycleRequested", True)
      gui_app.push_widget(alert_dialog(tr("Drive-cycle requested for immediate apply.")))
    return True

  def start_download(self, model_key: str):
    self._update_model_metadata()
    if ui_state.started:
      gui_app.push_widget(alert_dialog(tr("Cannot download models while driving.")))
      return False
    if self._is_download_active():
      gui_app.push_widget(alert_dialog(tr("A model download is already in progress.")))
      return False

    entry = self._catalog_entries.get(canonical_model_key(model_key))
    if entry is None:
      gui_app.push_widget(alert_dialog(tr("Unknown model.")))
      return False
    if entry.requires_external_gpu and not external_gpu_available():
      gui_app.push_widget(alert_dialog(tr("This model requires a detected external GPU.")))
      return False
    if entry.installed:
      gui_app.push_widget(alert_dialog(tr("Model is already on this device.")))
      return False

    self._params_memory.remove(CANCEL_DOWNLOAD_PARAM)
    self._params_memory.remove(MODEL_DOWNLOAD_ALL_PARAM)
    self._params_memory.put(MODEL_DOWNLOAD_PARAM, entry.key)
    self._params_memory.put(DOWNLOAD_PROGRESS_PARAM, f'Downloading "{entry.name}"...')
    return True

  def download_all_missing(self):
    self._update_model_metadata()
    if ui_state.started:
      gui_app.push_widget(alert_dialog(tr("Cannot download models while driving.")))
      return False
    if self._is_download_active():
      gui_app.push_widget(alert_dialog(tr("A model download is already in progress.")))
      return False
    if not self.available_entries():
      return False

    self._params_memory.remove(CANCEL_DOWNLOAD_PARAM)
    self._params_memory.remove(MODEL_DOWNLOAD_PARAM)
    self._params_memory.put_bool(MODEL_DOWNLOAD_ALL_PARAM, True)
    self._params_memory.put(DOWNLOAD_PROGRESS_PARAM, "Downloading...")
    return True

  def cancel_active_download(self):
    if self._is_download_active():
      self._params_memory.put_bool(CANCEL_DOWNLOAD_PARAM, True)

  def refresh_manifest(self):
    if ui_state.started:
      gui_app.push_widget(alert_dialog(tr("Cannot refresh the model catalog while driving.")))
      return False
    if self._is_download_active():
      gui_app.push_widget(alert_dialog(tr("Cannot refresh the model catalog during an active download.")))
      return False
    self._fetch_manifest_async()
    return True

  def delete_model(self, model_key: str):
    self._update_model_metadata()
    key = canonical_model_key(model_key)
    entry = self._catalog_entries.get(key)
    if entry is None:
      gui_app.push_widget(alert_dialog(tr("Unknown model.")))
      return False
    if ui_state.started:
      gui_app.push_widget(alert_dialog(tr("Cannot delete model files while driving.")))
      return False
    if self._is_download_active():
      gui_app.push_widget(alert_dialog(tr("Cannot delete model files while a download is in progress.")))
      return False
    if not self.is_model_removable(key):
      gui_app.push_widget(alert_dialog(tr("This model is protected and cannot be removed.")))
      return False

    for file in self._model_dir.iterdir():
      if not (file.name == f"{key}.thneed" or file.name == f"{key}.pkl" or file.name.startswith(f"{key}_")):
        continue
      if file.is_dir():
        shutil.rmtree(file, ignore_errors=True)
      elif file.is_file():
        file.unlink(missing_ok=True)

    self._update_model_metadata()
    return True

  def toggle_favorite(self, model_key: str):
    key = canonical_model_key(model_key)
    current_favorites = {
      canonical_model_key(m.strip())
      for m in (self._params.get("UserFavorites", encoding="utf-8") or "").split(",")
      if m.strip()
    }
    if key in current_favorites:
      current_favorites.discard(key)
    else:
      current_favorites.add(key)
    self._params.put("UserFavorites", ",".join(sorted(current_favorites)))
    self._update_model_metadata()


  def _on_blacklist_clicked(self):
    blacklisted = [m.strip() for m in (self._params.get("BlacklistedModels", encoding="utf-8") or "").split(",") if m.strip()]

    def _on_close(result):
      if result != DialogResult.CONFIRM or not dialog.selection:
        return
      if dialog.selection == tr("Add"):
        blacklistable = {k: v for k, v in self._model_file_to_name.items() if k not in blacklisted}
        self._show_selection_dialog(tr("Add to Blacklist"), blacklistable, "", lambda k: self._params.put("BlacklistedModels", ",".join(blacklisted + [k])))
      elif dialog.selection == tr("Remove"):
        options = {k: self._model_file_to_name.get(k, k) for k in blacklisted}

        def _remove(k):
          blacklisted.remove(k)
          self._params.put("BlacklistedModels", ",".join(blacklisted))

        self._show_selection_dialog(tr("Remove from Blacklist"), options, "", _remove)
      elif dialog.selection == tr("Reset All"):
        self._params.remove("BlacklistedModels")

    dialog = MultiOptionDialog(tr("Manage Blacklist"), [tr("Add"), tr("Remove"), tr("Reset All")], callback=_on_close,
                               subtitle=tr("Manage models excluded from random selection."))
    gui_app.push_widget(dialog)

  def _on_scores_clicked(self):
    scores_raw = self._params.get("ModelDrivesAndScores", encoding="utf-8") or ""
    if not scores_raw:
      gui_app.push_widget(alert_dialog(tr("No model ratings found.")))
      return
    try:
      scores = json.loads(scores_raw)
      lines = [f"{key}: {value.get('Score', 0)}% ({value.get('Drives', 0)} drives)" for key, value in scores.items()]
      gui_app.push_widget(ConfirmDialog("\n".join(lines), tr("Close"), rich=True))
    except Exception:
      gui_app.push_widget(alert_dialog(tr("Unable to read model ratings.")))

  def _on_model_randomizer_toggled(self, state: bool):
    self._params.put_bool("ModelRandomizer", state)
    update_starpilot_toggles()
    self._update_model_metadata()

  def toggle_model_randomizer(self):
    currently = self._params.get_bool("ModelRandomizer")
    if not currently:
      def on_confirm(result):
        if result == DialogResult.CONFIRM:
          self._on_model_randomizer_toggled(True)
      gui_app.push_widget(ConfirmDialog(
        tr("Model Randomizer will change your driving model each drive."),
        tr("Enable"),
        tr("Cancel"),
        callback=on_confirm,
      ))
    else:
      self._on_model_randomizer_toggled(False)

  def random_model_button_label(self) -> str:
    return tr("Model Randomizer")

  def _update_state(self):
    if self._transient_status_text and time.monotonic() >= self._transient_status_until:
      self._transient_status_text = ""

    if self._manifest_fetched:
      self._manifest_fetched = False
      self._update_model_metadata()

    model_to_download = self._params_memory.get(MODEL_DOWNLOAD_PARAM, encoding="utf-8") or ""
    download_all = self._params_memory.get_bool(MODEL_DOWNLOAD_ALL_PARAM)
    is_downloading = bool(model_to_download or download_all)

    if is_downloading and (self._download_thread is None or not self._download_thread.is_alive()):

      def _download_task():
        try:
          if download_all:
            self._model_manager.download_all_models()
          else:
            self._model_manager.download_model(model_to_download)
        except Exception:
          pass
        finally:
          final_status = self._params_memory.get(DOWNLOAD_PROGRESS_PARAM, encoding="utf-8") or ""
          self._params_memory.remove(CANCEL_DOWNLOAD_PARAM)
          self._params_memory.remove(MODEL_DOWNLOAD_PARAM)
          self._params_memory.put_bool(MODEL_DOWNLOAD_ALL_PARAM, False)
          self._params_memory.remove(DOWNLOAD_PROGRESS_PARAM)
          if final_status:
            self._transient_status_text = final_status
            self._transient_status_until = time.monotonic() + 2.5
          self._download_thread = None
          self._update_model_metadata()

      self._download_thread = threading.Thread(target=_download_task, daemon=True)
      self._download_thread.start()
