from __future__ import annotations

import shutil
import threading
from dataclasses import dataclass, replace

from cereal import log, messaging
import pyray as rl

from openpilot.common.params import Params
from openpilot.selfdrive.ui.ui_state import device, ui_state
from openpilot.system.ui.lib.application import FONT_SCALE, FontWeight, gui_app
from openpilot.system.ui.lib.multilang import tr, tr_noop, trn
from openpilot.system.ui.widgets import DialogResult
from openpilot.system.ui.widgets.confirm_dialog import ConfirmDialog, alert_dialog
from openpilot.system.ui.widgets.option_dialog import MultiOptionDialog

from openpilot.selfdrive.ui.lib import aether_style as AS
from openpilot.selfdrive.ui.layouts.settings.starpilot.aethergrid import (
  AETHER_LIST_METRICS,
  GROUP_OVERHEAD,
  SECTION_GAP,
  SETTINGS_ROW_SUBTITLE_FONT_SIZE,
  SETTINGS_ROW_TITLE_FONT_SIZE,
  SETTINGS_ROW_VALUE_FONT_SIZE,
  AetherButton,
  AetherListColors,
  AetherSegmentedControl,
  DEFAULT_PANEL_STYLE,
  PanelManagerView,
  build_settings_group_frame,
  draw_busy_ring,
  draw_empty_state_card,
  draw_list_group_shell,
  draw_metric_strip,
  draw_text_fit_common,
  draw_section_header,
  draw_settings_card_row,
  draw_settings_group,
  with_alpha,
  wrap_subtitle,
)
from openpilot.selfdrive.ui.layouts.settings.starpilot.panel import _SettingsPage
from openpilot.starpilot.common.maps_catalog import (
  MAPS_CATALOG,
  MAP_TOKEN_LABELS,
  MAP_SCHEDULE_LABELS,
  sanitize_selected_locations_csv,
  schedule_label,
)
from openpilot.starpilot.common.maps_download_progress import MAPS_STORAGE_CACHE_PARAM, load_maps_storage_cache
from openpilot.starpilot.common.maps_selection import COUNTRY_PREFIX
from openpilot.starpilot.common.starpilot_variables import MAPS_PATH as OFFLINE_MAPS_PATH


NetworkType = log.DeviceState.NetworkType

CANCEL_REQUEST_TIMEOUT = 3.0
PANEL_STYLE = DEFAULT_PANEL_STYLE
MAPS_METRICS = replace(AETHER_LIST_METRICS, header_height=0)

COUNTRIES_SECTION = next(section for section in MAPS_CATALOG if section["key"] == "countries")
STATES_SECTION = next(section for section in MAPS_CATALOG if section["key"] == "states")
US_COUNTRY_TOKEN = f"{COUNTRY_PREFIX}US"

ALL_US_STATE_TOKENS = frozenset({
  region["token"] for group in STATES_SECTION["groups"] for region in group["regions"]
})

REGIONAL_PACKAGES = {
  "pkg:midwest": {
    "title": tr_noop("U.S. Midwest Region (12 States)"),
    "subtitle": tr_noop("IL, IN, IA, KS, MI, MN, MO, NE, ND, OH, SD, WI"),
    "tokens": frozenset({r["token"] for g in STATES_SECTION["groups"] if g["key"] == "midwest" for r in g["regions"]}),
  },
  "pkg:northeast": {
    "title": tr_noop("U.S. Northeast Region (9 States)"),
    "subtitle": tr_noop("CT, ME, MA, NH, NJ, NY, PA, RI, VT"),
    "tokens": frozenset({r["token"] for g in STATES_SECTION["groups"] if g["key"] == "northeast" for r in g["regions"]}),
  },
  "pkg:south": {
    "title": tr_noop("U.S. South Region (17 States)"),
    "subtitle": tr_noop("AL, AR, DE, DC, FL, GA, KY, LA, MD, MS, NC, OK, SC, TN, TX, VA, WV"),
    "tokens": frozenset({r["token"] for g in STATES_SECTION["groups"] if g["key"] == "south" for r in g["regions"]}),
  },
  "pkg:west": {
    "title": tr_noop("U.S. West Region (13 States)"),
    "subtitle": tr_noop("AK, AZ, CA, CO, HI, ID, MT, NV, NM, OR, UT, WA, WY"),
    "tokens": frozenset({r["token"] for g in STATES_SECTION["groups"] if g["key"] == "west" for r in g["regions"]}),
  },
  "pkg:territories": {
    "title": tr_noop("U.S. Territories (5 Territories)"),
    "subtitle": tr_noop("AS, GU, MP, PR, VI"),
    "tokens": frozenset({r["token"] for g in STATES_SECTION["groups"] if g["key"] == "territories" for r in g["regions"]}),
  },
}

# Map Data uses the shared settings components: one status card with the standard card inset and
# 112 px action buttons, the shared segmented control, and grouped region rows with row-sized buttons.
# Everything scrolls together, like the other settings pages.
STATUS_BUTTON_GAP = AS.SETTINGS_ROW_GAP
STATUS_ACTIONS_MAX_WIDTH = 620.0
STATUS_CARD_HEIGHT = AS.SETTINGS_CARD_INSET * 2 + AS.MIN_TOUCH * 2 + STATUS_BUTTON_GAP
STATUS_METRICS_HEIGHT = 84.0
STATUS_METRICS_VALUE_OFFSET = 40.0   # label line, then the value below it
REGION_ROW_HEIGHT = 160.0
REGION_ACTION_HEIGHT = AS.VALUE_PILL_HEIGHT
BROWSER_EMPTY_STATE_HEIGHT = 208.0


def _format_mb(size_bytes: int) -> str:
  mb = size_bytes / (1024 * 1024)
  if mb >= 1024:
    return f"{mb / 1024:.2f} GB"
  return f"{mb:.2f} MB"


def _format_elapsed_ms(elapsed_ms: int) -> str:
  if elapsed_ms <= 0:
    return tr("Calculating...")
  total_seconds = elapsed_ms // 1000
  hours = total_seconds // 3600
  minutes = (total_seconds % 3600) // 60
  seconds = total_seconds % 60
  if hours > 0:
    return f"{hours:d}:{minutes:02d}:{seconds:02d}"
  return f"{minutes:d}:{seconds:02d}"


def _format_eta_ms(elapsed_ms: int, downloaded_files: int, total_files: int) -> str:
  if elapsed_ms <= 0 or downloaded_files <= 0 or total_files <= 0 or downloaded_files >= total_files:
    return tr("Calculating...")
  remaining_files = total_files - downloaded_files
  if remaining_files <= 0:
    return tr("Almost done")
  files_per_ms = downloaded_files / max(elapsed_ms, 1)
  if files_per_ms <= 0:
    return tr("Calculating...")
  remaining_ms = int(remaining_files / files_per_ms)
  return _format_elapsed_ms(remaining_ms)


def _localized_schedule_label(value) -> str:
  return tr(schedule_label(value))


def _selected_token_set(selected_raw: str | bytes | None) -> set[str]:
  normalized = sanitize_selected_locations_csv(selected_raw or "")
  return {token for token in normalized.split(",") if token}


@dataclass(slots=True)
class MapsDownloadState:
  active: bool = False
  cancelled: bool = False
  total_files: int = 0
  downloaded_files: int = 0
  primary_location: str = ""
  percent: int = 0
  progress_text: str = ""


class MapsManagerView(PanelManagerView):
  METRICS = MAPS_METRICS
  PANEL_STYLE = PANEL_STYLE

  def __init__(self, controller: StarPilotMapsLayout):
    super().__init__()
    self._controller = controller

    self._source_segmented_control = self._child(
      AetherSegmentedControl(
        [tr("U.S. States & Regions"), tr("Other Countries")],
        self._controller._get_source_segment_index,
        self._controller._on_source_segment_change,
        style=PANEL_STYLE,
      )
    )

  def _draw_header(self, rect: rl.Rectangle):
    pass

  def _region_groups(self) -> list[tuple[str, str, list[dict], bool]]:
    """(heading, trailing text, regions, downloaded) for each group of region rows."""
    downloaded, downloadable = self._controller._browse_regions_for_active_view()
    groups = []
    if downloaded:
      groups.append((tr("On This Device"), trn("{} region", "{} regions", len(downloaded)).format(len(downloaded)), downloaded, True))
    if downloadable:
      heading = tr("Available for Download") if downloaded else tr("Map Packages & Regions")
      groups.append((heading, self._controller._active_view_count_text(), downloadable, False))
    return groups

  def _measure_content_height(self, content_width: float) -> float:
    height = STATUS_CARD_HEIGHT + AetherSegmentedControl.GAP
    height += self._source_segmented_control.measure_height(content_width) + AetherSegmentedControl.GAP
    groups = self._region_groups()
    if not groups:
      return height + BROWSER_EMPTY_STATE_HEIGHT
    height += sum(GROUP_OVERHEAD + len(regions) * REGION_ROW_HEIGHT for _, _, regions, _ in groups)
    return height + SECTION_GAP * (len(groups) - 1)

  def _draw_scroll_content(self, scroll_rect: rl.Rectangle, content_width: float):
    y = scroll_rect.y + self._scroll_offset
    x = scroll_rect.x

    self._draw_status_card(rl.Rectangle(x, y, content_width, STATUS_CARD_HEIGHT))
    y += STATUS_CARD_HEIGHT + AetherSegmentedControl.GAP

    seg_height = self._source_segmented_control.measure_height(content_width)
    self._bind_scroll_widget(self._source_segmented_control)
    self._source_segmented_control.render(rl.Rectangle(x, y, content_width, seg_height))
    y += seg_height + AetherSegmentedControl.GAP

    groups = self._region_groups()
    if not groups:
      title, body = self._controller._browse_empty_state()
      draw_empty_state_card(rl.Rectangle(x, y, content_width, BROWSER_EMPTY_STATE_HEIGHT), title, body, style=PANEL_STYLE)
      return

    for heading, trailing, regions, downloaded in groups:
      group_rect = rl.Rectangle(x, y, content_width, GROUP_OVERHEAD + len(regions) * REGION_ROW_HEIGHT)
      body = draw_settings_group(group_rect, heading, style=PANEL_STYLE)
      draw_section_header(build_settings_group_frame(group_rect).heading, "", trailing_text=trailing,
                          trailing_size=AS.SETTINGS_GROUP_HEADING_SIZE - 4, style=PANEL_STYLE)
      row_y = body.y
      visible_top, visible_bottom = scroll_rect.y - REGION_ROW_HEIGHT, scroll_rect.y + scroll_rect.height
      for index, region in enumerate(regions):
        if visible_top <= row_y <= visible_bottom:
          self._draw_region_row(rl.Rectangle(x, row_y, content_width, REGION_ROW_HEIGHT), region, downloaded,
                                is_last=index == len(regions) - 1)
        row_y += REGION_ROW_HEIGHT
      y = group_rect.y + group_rect.height + SECTION_GAP

  def _draw_region_row(self, rect: rl.Rectangle, region: dict, downloaded: bool, *, is_last: bool):
    token = region["token"]
    hovered, pressed = self._interactive_state(f"region:{token}", rect)
    if downloaded:
      subtitle, action, highlighted = tr("Downloaded on device"), tr("Downloaded"), True
    else:
      highlighted = self._controller._get_map_state(token)
      subtitle, action = self._controller._region_primary_text(token), self._controller._region_action_text(token)
    draw_settings_card_row(
      rect, title=tr(region["label"]), subtitle=subtitle, action_text=action,
      hovered=hovered, pressed=pressed, current=highlighted, grouped=True, is_last=is_last,
      action_text_size=SETTINGS_ROW_VALUE_FONT_SIZE, action_height=REGION_ACTION_HEIGHT,
      action_fill=with_alpha(AetherListColors.SUCCESS_SOFT, 60) if highlighted else None,
      action_border=AetherListColors.SUCCESS if highlighted else None,
      style=PANEL_STYLE,
    )

  def _draw_status_card(self, rect: rl.Rectangle):
    draw_list_group_shell(rect, style=PANEL_STYLE)
    inset = AS.SETTINGS_CARD_INSET
    gap = STATUS_BUTTON_GAP
    actions_w = min(STATUS_ACTIONS_MAX_WIDTH, rect.width * 0.42)
    actions_x = rect.x + rect.width - inset - actions_w
    content_x = rect.x + inset
    summary_w = max(240.0, actions_x - AS.SETTINGS_CONTROL_GAP - content_x)

    # Left: status title and description (row typography), then the storage strip along the bottom.
    # Pinned to the card's top inset, level with the Download button, rather than centered in the
    # space above the storage strip (which left a gap above a short description).
    y = rect.y + inset
    draw_text_fit_common(gui_app.font(FontWeight.SEMI_BOLD), self._controller._progress_title(),
                         rl.Vector2(content_x, y), summary_w, SETTINGS_ROW_TITLE_FONT_SIZE, color=AetherListColors.HEADER)
    y += SETTINGS_ROW_TITLE_FONT_SIZE * FONT_SCALE + AS.SETTINGS_TEXT_GAP
    body_font = gui_app.font(FontWeight.NORMAL)
    for line in wrap_subtitle(body_font, self._controller._progress_body().replace("\n", " "), summary_w,
                              SETTINGS_ROW_SUBTITLE_FONT_SIZE):
      draw_text_fit_common(body_font, line, rl.Vector2(content_x, y), summary_w, SETTINGS_ROW_SUBTITLE_FONT_SIZE,
                           color=AetherListColors.SUBTEXT)
      y += SETTINGS_ROW_SUBTITLE_FONT_SIZE * FONT_SCALE + 2
    metrics = [
      (tr("Selected"), self._controller._selected_summary_text()),
      (tr("Storage"), self._controller._storage_text),
      (tr("Last Updated"), self._controller._last_updated_text()),
    ]
    # Centered on the Auto/Remove button row beside it, so labels and values read as one line with it.
    metrics_block_h = STATUS_METRICS_VALUE_OFFSET + SETTINGS_ROW_VALUE_FONT_SIZE * FONT_SCALE
    button_row_center = rect.y + inset + AS.MIN_TOUCH + gap + AS.MIN_TOUCH / 2
    draw_metric_strip(
      rl.Rectangle(content_x, button_row_center - metrics_block_h / 2, summary_w, STATUS_METRICS_HEIGHT),
      metrics, gap=36, min_col_width=140.0, label_size=SETTINGS_ROW_SUBTITLE_FONT_SIZE,
      value_size=SETTINGS_ROW_VALUE_FONT_SIZE, style=PANEL_STYLE, value_top_offset=STATUS_METRICS_VALUE_OFFSET,
      divider_bottom_offset=42,
    )

    # Right: the same 112 px AetherButtons used in page headers (Reset All, Maintenance).
    button_h = AS.MIN_TOUCH
    primary_rect = rl.Rectangle(actions_x, rect.y + inset, actions_w, button_h)
    half_w = (actions_w - gap) / 2
    second_y = primary_rect.y + button_h + gap
    for button, button_rect in (
      (self._controller._download_button, primary_rect),
      (self._controller._schedule_button, rl.Rectangle(actions_x, second_y, half_w, button_h)),
      (self._controller._remove_button, rl.Rectangle(actions_x + half_w + gap, second_y, half_w, button_h)),
    ):
      self._bind_scroll_widget(button)
      button.render(button_rect)

    if self._controller._download_state.active:
      center = rl.Vector2(primary_rect.x + primary_rect.width - inset, primary_rect.y + primary_rect.height / 2)
      draw_busy_ring(center, rl.get_time() * 160, PANEL_STYLE.accent, inner_radius=10, outer_radius=14, sweep=210, thickness=20)

  def _activate_target(self, target_id: str | None):
    if target_id and target_id.startswith("region:"):
      self._controller._toggle_region(target_id.split(":", 1)[1])


class StarPilotMapsLayout(_SettingsPage):
  VIEW_STATES = 0
  VIEW_COUNTRIES = 1

  def __init__(self):
    super().__init__()
    self._params_memory = Params(memory=True)
    self._worker_params = Params()
    self._map_sm = messaging.SubMaster(["mapdExtendedOut", "starpilotCarState"])

    self._storage_text = tr("Calculating...")
    self._storage_known = False
    self._has_downloaded_data = False
    self._storage_updated_at = 0.0
    self._download_started_at: float | None = None
    self._cancel_requested_at: float | None = None
    self._cancel_visual_until = 0.0
    self._download_state = MapsDownloadState()
    self._view_index = self.VIEW_STATES
    self._cached_selected_tokens: set[str] = set()

    self._download_button = self._child(
      AetherButton(
        self._primary_action_label,
        self._on_primary_action,
        enabled=self._primary_action_enabled,
        emphasized=True,
      )
    )
    self._schedule_button = self._child(
      AetherButton(
        self._schedule_action_label,
        self._on_schedule,
        emphasized=False,
      )
    )
    # Enabled whenever maps exist and no download is running; _on_remove explains when the car must be parked
    # and asks for confirmation before deleting.
    self._remove_button = self._child(
      AetherButton(
        tr("Remove"),
        self._on_remove,
        enabled=lambda: self._has_downloaded_data and not self._download_in_flight() and not self._is_visually_cancelling(),
        neutral=True,
      )
    )

    self._manager_view = MapsManagerView(self)

    self._refresh_storage_state(force=True)
    self._sync_download_state(force=True)

  def show_event(self):
    super().show_event()
    self._refresh_storage_state(force=True)
    raw_selected = self._params.get("MapsSelected", encoding="utf-8") or ""
    self._cached_selected_tokens = _selected_token_set(raw_selected)

    if self._cancel_requested() and self._cancel_requested_at is None:
      self._cancel_requested_at = rl.get_time()
    if self._cancel_requested() and self._cancel_visual_until <= rl.get_time():
      self._cancel_visual_until = rl.get_time() + 2.5
    self._sync_download_state(force=True)

  def hide_event(self):
    super().hide_event()
    device.set_override_interactive_timeout(None)

  def _update_state(self):
    super()._update_state()
    self._cached_selected_tokens = _selected_token_set(
      self._params.get("MapsSelected", encoding="utf-8") or ""
    )
    self._sync_download_state()
    self._refresh_storage_state()

    if self._download_state.active:
      device.set_override_interactive_timeout(300)
    else:
      device.set_override_interactive_timeout(None)

    if self._cancel_requested_at is not None and not self._download_state.active:
      if (rl.get_time() - self._cancel_requested_at) >= CANCEL_REQUEST_TIMEOUT:
        self._params_memory.remove("CancelDownloadMaps")
        self._cancel_requested_at = None

    if self._cancel_visual_until and rl.get_time() >= self._cancel_visual_until and not self._download_state.active:
      self._cancel_visual_until = 0.0

  def _sync_download_state(self, force: bool = False):
    del force
    self._map_sm.update(0)
    progress = self._map_sm["mapdExtendedOut"].downloadProgress if self._map_sm.valid.get("mapdExtendedOut", False) else None
    active = bool(progress.active) if progress is not None else False

    if active and self._download_started_at is None:
      self._download_started_at = rl.get_time()
    if active:
      self._cancel_requested_at = None
      self._cancel_visual_until = 0.0
    if not self._download_in_flight() and self._download_started_at is not None:
      self._download_started_at = None

    total_files = int(progress.totalFiles) if progress is not None else 0
    downloaded_files = int(progress.downloadedFiles) if progress is not None else 0
    percent = int((downloaded_files * 100) / max(total_files, 1)) if total_files > 0 else 0
    primary_location = ""
    if progress is not None and len(progress.locationDetails) > 0:
      primary_location = str(progress.locationDetails[0].location)
    elif progress is not None and len(progress.locations) > 0:
      primary_location = str(progress.locations[0])

    progress_text = ""
    if active:
      progress_text = tr("{} / {} ({}%)").format(downloaded_files, total_files, percent)
      if primary_location:
        progress_text = f"{progress_text}  {primary_location}"

    self._download_state = MapsDownloadState(
      active=active,
      cancelled=bool(progress.cancelled) if progress is not None else False,
      total_files=total_files,
      downloaded_files=downloaded_files,
      primary_location=primary_location,
      percent=percent,
      progress_text=progress_text,
    )

  def _refresh_storage_state(self, force: bool = False):
    now = rl.get_time()
    if not force and (now - self._storage_updated_at) < 4.0:
      return

    cache = load_maps_storage_cache(self._worker_params.get(MAPS_STORAGE_CACHE_PARAM, encoding="utf-8") or "")
    total_size = cache.storage_bytes
    self._storage_known = cache.storage_known
    self._has_downloaded_data = bool(cache.maps_present)
    self._storage_text = _format_mb(total_size) if total_size is not None else tr("Calculating...")
    self._storage_updated_at = now

  def _selected_tokens(self) -> set[str]:
    return self._cached_selected_tokens

  def _selected_count(self) -> int:
    tokens = self._selected_tokens()
    if US_COUNTRY_TOKEN in tokens:
      return len(ALL_US_STATE_TOKENS)
    return len(tokens)

  def _selected_summary_text(self) -> str:
    count = self._selected_count()
    if count == 0:
      return tr("No regions selected")
    if US_COUNTRY_TOKEN in self._selected_tokens():
      return tr("Whole U.S. (56 states)")
    return trn("{} region selected", "{} regions selected", count).format(count)

  def _selected_primary_token(self) -> str | None:
    selected = sorted(self._selected_tokens())
    if not selected:
      return None
    return selected[0]

  def _selected_primary_label(self) -> str:
    token = self._selected_primary_token()
    if not token:
      return ""
    if token == US_COUNTRY_TOKEN:
      return tr("Whole U.S.")
    return tr(MAP_TOKEN_LABELS.get(token, token))

  def _selection_preview_text(self) -> str:
    count = self._selected_count()
    if count <= 0:
      return tr("No regions selected yet")
    if US_COUNTRY_TOKEN in self._selected_tokens():
      return tr("Whole U.S. package")
    primary_label = self._selected_primary_label()
    if count == 1:
      return primary_label
    return tr("{} + {} more").format(primary_label, count - 1)

  def _has_full_us_selected(self) -> bool:
    tokens = self._selected_tokens()
    return (US_COUNTRY_TOKEN in tokens) or ALL_US_STATE_TOKENS.issubset(tokens)

  def _is_states_view(self) -> bool:
    return self._view_index == self.VIEW_STATES

  def _get_source_segment_index(self) -> int:
    return 0 if self._is_states_view() else 1

  def _on_source_segment_change(self, idx: int):
    self._view_index = self.VIEW_STATES if idx == 0 else self.VIEW_COUNTRIES

  def _all_country_regions(self) -> list[dict]:
    regions = [region for group in COUNTRIES_SECTION["groups"] for region in group["regions"]]
    return sorted(regions, key=lambda r: tr(r["label"]))

  def _all_us_states_regions(self) -> list[dict]:
    regions = [region for group in STATES_SECTION["groups"] for region in group["regions"]]
    return sorted(regions, key=lambda r: tr(r["label"]))

  def _bulk_package_regions(self) -> list[dict]:
    return [
      {"token": US_COUNTRY_TOKEN, "label": tr("Whole U.S. (All 50 States & Territories)")},
      *[
        {"token": key, "label": tr(spec["title"])}
        for key, spec in REGIONAL_PACKAGES.items()
      ]
    ]

  def _active_view_count_text(self) -> str:
    if not self._is_states_view():
      total = len(self._all_country_regions())
      selected_count = sum(1 for region in self._all_country_regions() if self._get_map_state(region["token"]))
    else:
      total = len(self._all_us_states_regions())
      selected_count = self._selected_count()
      if self._has_full_us_selected():
        return tr("Whole U.S. Selected")

    if selected_count <= 0:
      return tr("{} available - Tap to select").format(total)
    return tr("{} selected | {} available").format(selected_count, max(0, total - selected_count))

  def _toggle_region(self, token: str):
    self._set_map_state(token, not self._get_map_state(token))

  def _is_region_downloaded(self, token: str) -> bool:
    """Returns True ONLY if map data is actually downloaded on disk AND token is part of installed set."""
    if not self._has_downloaded_data:
      return False
    return self._get_map_state(token)

  def _region_primary_text(self, token: str) -> str:
    if token == US_COUNTRY_TOKEN:
      return tr("Master Package - Full country map data")
    if token in REGIONAL_PACKAGES:
      return tr(REGIONAL_PACKAGES[token]["subtitle"])
    if self._get_map_state(token):
      return tr("Selected for download")
    return tr("Tap to select state")

  def _region_action_text(self, token: str) -> str:
    if self._get_map_state(token):
      return tr("Selected")
    return tr("Add")

  def _browse_empty_state(self) -> tuple[str, str]:
    return tr("No regions available"), tr("Switch sources to keep browsing maps.")

  def _browse_regions_for_active_view(self) -> tuple[list[dict], list[dict]]:
    """Partition active view regions into (downloaded_on_device, available_for_download)."""
    if not self._is_states_view():
      all_regions = self._all_country_regions()
    else:
      all_regions = [*self._bulk_package_regions(), *self._all_us_states_regions()]

    # If NO map data exists on disk, ZERO regions are downloaded on device!
    if not self._has_downloaded_data:
      return [], all_regions

    downloaded = []
    downloadable = []
    for region in all_regions:
      token = region["token"]
      if self._is_region_downloaded(token):
        downloaded.append(region)
      else:
        downloadable.append(region)

    return downloaded, downloadable

  def _get_map_state(self, token: str) -> bool:
    tokens = self._selected_tokens()
    if not tokens:
      return False
    if US_COUNTRY_TOKEN in tokens:
      return True
    if token == US_COUNTRY_TOKEN:
      return ALL_US_STATE_TOKENS.issubset(tokens)
    if token in REGIONAL_PACKAGES:
      return REGIONAL_PACKAGES[token]["tokens"].issubset(tokens)
    return token in tokens

  def _set_map_state(self, token: str, state: bool):
    selected = set(self._cached_selected_tokens)

    # Expand Whole U.S. to individual states first if modifying a subset
    if US_COUNTRY_TOKEN in selected:
      selected.remove(US_COUNTRY_TOKEN)
      selected.update(ALL_US_STATE_TOKENS)

    if state:
      if token == US_COUNTRY_TOKEN:
        selected = {US_COUNTRY_TOKEN}
      elif token in REGIONAL_PACKAGES:
        selected.update(REGIONAL_PACKAGES[token]["tokens"])
      else:
        selected.add(token)
    else:
      if token == US_COUNTRY_TOKEN:
        selected.difference_update(ALL_US_STATE_TOKENS)
        selected.discard(US_COUNTRY_TOKEN)
      elif token in REGIONAL_PACKAGES:
        selected.difference_update(REGIONAL_PACKAGES[token]["tokens"])
      else:
        selected.discard(token)

    # Auto-consolidate to c:US if all 56 states are selected
    if ALL_US_STATE_TOKENS.issubset(selected):
      selected = {US_COUNTRY_TOKEN}

    self._params.put("MapsSelected", sanitize_selected_locations_csv(sorted(selected)))
    self._cached_selected_tokens = selected

  def _is_online(self) -> bool:
    network_type = ui_state.sm["deviceState"].networkType if ui_state.sm.valid.get("deviceState", False) else NetworkType.none
    return network_type != NetworkType.none

  def _is_parked(self) -> bool:
    if ui_state.is_offroad():
      return True
    if self._map_sm.valid.get("starpilotCarState", False):
      return bool(self._map_sm["starpilotCarState"].isParked)
    return False

  def _download_requested(self) -> bool:
    return self._params_memory.get_bool("DownloadMaps")

  def _cancel_requested(self) -> bool:
    return self._params_memory.get_bool("CancelDownloadMaps")

  def _is_visually_cancelling(self) -> bool:
    return self._cancel_requested() or (self._cancel_visual_until > rl.get_time())

  def _download_in_flight(self) -> bool:
    return self._download_state.active or self._download_requested()

  def _remove_enabled(self) -> bool:
    return self._has_downloaded_data and self._is_parked() and not self._download_in_flight() and not self._is_visually_cancelling()

  def _download_gate_reason(self) -> str:
    reasons = []
    if self._download_in_flight():
      reasons.append(tr("Download in progress"))
    if not self._is_online():
      reasons.append(tr("Connect to the internet"))
    if not self._is_parked():
      reasons.append(tr("Park the vehicle to download"))
    return "\n".join(reasons) if reasons else ""

  def _primary_action_enabled(self) -> bool:
    if self._is_visually_cancelling():
      return False
    if self._download_in_flight():
      return True
    return self._download_gate_reason() == ""

  def _primary_action_label(self) -> str:
    if self._is_visually_cancelling():
      return tr("Cancelling...")
    if self._download_in_flight():
      return tr("Cancel Download")
    if self._selected_count() == 0:
      return tr("Select Regions Below")
    return tr("Download Offline Maps")

  def _on_primary_action(self):
    if self._download_in_flight():
      self._on_cancel()
    elif self._selected_count() == 0:
      gui_app.push_widget(alert_dialog(tr("Please select 'Whole U.S.' or pick individual states from the list below.")))
    else:
      self._on_download()

  def _schedule_action_label(self) -> str:
    return {
      "Manually": tr("Auto: Off"),
      "Weekly": tr("Auto: Weekly"),
      "Monthly": tr("Auto: Monthly"),
    }[schedule_label(self._params.get("PreferredSchedule"))]

  def _on_schedule(self):
    localized_options = [(value, tr(label)) for value, label in MAP_SCHEDULE_LABELS.items()]
    options = [label for _, label in localized_options]
    current = _localized_schedule_label(self._params.get("PreferredSchedule"))
    value_by_label = {label: value for value, label in localized_options}

    def on_select(res):
      if res == DialogResult.CONFIRM and dialog.selection:
        selected_value = value_by_label.get(dialog.selection)
        if selected_value is not None:
          self._params.put_int("PreferredSchedule", selected_value)

    dialog = MultiOptionDialog(tr("Auto Update Schedule"), options, current, callback=on_select,
                               subtitle=tr("Choose how often to update downloaded offline maps."))
    gui_app.push_widget(dialog)

  def _on_download(self):
    gate_reason = self._download_gate_reason()
    if gate_reason:
      gui_app.push_widget(alert_dialog(gate_reason))
      return

    current_selected = self._params.get("MapsSelected", encoding="utf-8") or ""
    selected_raw = sanitize_selected_locations_csv(current_selected)
    if selected_raw != current_selected:
      self._params.put("MapsSelected", selected_raw)
    if not selected_raw:
      gui_app.push_widget(alert_dialog(tr("Please select 'Whole U.S.' or pick individual states from the list below.")))
      return

    def on_confirm(res):
      if res == DialogResult.CONFIRM:
        gate_reason = self._download_gate_reason()
        if gate_reason:
          gui_app.push_widget(alert_dialog(gate_reason))
          return
        self._params_memory.put_bool("DownloadMaps", True)
        self._params_memory.remove("CancelDownloadMaps")
        self._download_started_at = rl.get_time()

    gui_app.push_widget(ConfirmDialog(tr("Start downloading offline maps for the selected regions?"), tr("Download"), callback=on_confirm))

  def _on_cancel(self):
    def on_confirm(res):
      if res == DialogResult.CONFIRM:
        if not self._download_in_flight():
          self._cancel_requested_at = None
          self._cancel_visual_until = 0.0
          return
        self._params_memory.put_bool("CancelDownloadMaps", True)
        self._params_memory.remove("DownloadMaps")
        self._cancel_requested_at = rl.get_time()
        self._cancel_visual_until = rl.get_time() + 2.5

    gui_app.push_widget(ConfirmDialog(tr("Cancel the current map download?"), tr("Cancel Download"), callback=on_confirm))

  def _on_remove(self):
    if not self._remove_enabled():
      if not self._is_parked():
        gui_app.push_widget(alert_dialog(tr("Park to remove downloaded maps.")))
      return

    def on_confirm(res):
      if res == DialogResult.CONFIRM:
        if not self._remove_enabled():
          if not self._is_parked():
            gui_app.push_widget(alert_dialog(tr("Park to remove downloaded maps.")))
          return

        def remove_worker():
          if OFFLINE_MAPS_PATH.exists():
            shutil.rmtree(OFFLINE_MAPS_PATH, ignore_errors=True)
            OFFLINE_MAPS_PATH.mkdir(parents=True, exist_ok=True)
          cache = load_maps_storage_cache(self._worker_params.get(MAPS_STORAGE_CACHE_PARAM, encoding="utf-8") or "")
          cache.clear()
          self._worker_params.put(MAPS_STORAGE_CACHE_PARAM, cache.to_json())
          self._storage_updated_at = 0.0

        threading.Thread(target=remove_worker, daemon=True).start()
        gui_app.push_widget(alert_dialog(tr("Removing offline maps...")))

    gui_app.push_widget(ConfirmDialog(tr("Delete all downloaded offline map data?"), tr("Remove Maps"), callback=on_confirm))

  def _last_updated_text(self) -> str:
    last_update = self._worker_params.get("LastMapsUpdate", encoding="utf-8")
    return last_update or tr("Never")

  def _progress_title(self) -> str:
    if self._is_visually_cancelling():
      return tr("Cancelling Download")
    if self._download_state.active:
      return tr("Downloading Maps")
    if self._download_requested():
      return tr("Starting Download")
    if self._has_downloaded_data:
      return tr("Offline Maps")
    if not self._storage_known:
      return tr("Checking Offline Maps")
    if self._selected_count() == 0:
      return tr("Select Map Data")
    return tr("Download Readiness")

  def _progress_body(self) -> str:
    if self._download_state.active:
      elapsed_ms = int((rl.get_time() - (self._download_started_at or rl.get_time())) * 1000)
      elapsed_text = _format_elapsed_ms(elapsed_ms)
      eta_text = _format_eta_ms(elapsed_ms, self._download_state.downloaded_files, self._download_state.total_files)
      if self._download_state.primary_location:
        return tr("{}\nElapsed {} | ETA {}").format(self._download_state.progress_text, elapsed_text, eta_text)
      return tr("{} / {} ({}%)\nElapsed {} | ETA {}").format(
        self._download_state.downloaded_files,
        self._download_state.total_files,
        self._download_state.percent,
        elapsed_text,
        eta_text,
      )

    if self._is_visually_cancelling():
      return tr("Stop request sent. The current transfer will wind down safely.")

    if self._download_requested():
      return tr("Preparing the selected regions for download.")

    if self._selected_count() == 0:
      return tr("No regions selected yet. Tap 'Whole U.S.' or pick specific states below to get started.")

    gate_reason = self._download_gate_reason()
    if gate_reason:
      return gate_reason

    return tr("Ready to download {}.").format(self._selection_preview_text())
