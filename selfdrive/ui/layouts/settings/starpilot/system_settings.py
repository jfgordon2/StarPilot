from __future__ import annotations
import os
import re
import shutil
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

import pyray as rl

from openpilot.system.hardware import HARDWARE
from openpilot.system.ui.lib.application import gui_app
from openpilot.system.ui.lib.multilang import tr, tr_noop
from openpilot.system.ui.widgets import DialogResult
from openpilot.system.ui.widgets.confirm_dialog import ConfirmDialog, alert_dialog
from openpilot.system.ui.widgets.keyboard import Keyboard
from openpilot.system.ui.widgets.option_dialog import MultiOptionDialog

from openpilot.selfdrive.ui.ui_state import device, ui_state
from openpilot.selfdrive.ui.layouts.settings.starpilot.panel import _SettingsPage
from openpilot.selfdrive.ui.layouts.settings.starpilot.choice_dialog import AetherChoiceDialog, PreviewChoice
from openpilot.selfdrive.ui.layouts.settings.starpilot.aethergrid import (
  AETHER_LIST_METRICS,
  AetherAdjustorRow,
  AetherButton,
  AetherSegmentedControl,
  RowStatus,
  DEFAULT_PANEL_STYLE,
  PanelManagerView,
  SettingsColumn,
  TileGrid,
  GROUP_OVERHEAD,
  draw_settings_group,
  AetherSliderDialog,
  SECTION_GAP,
  SPACING,
  TOGGLE_MIN_HEIGHT,
)
from openpilot.starpilot.common import param_profiles
from openpilot.starpilot.common.connect_server import prepare_konik_server_switch
from openpilot.starpilot.common.starpilot_variables import EXCLUDED_KEYS as STARPILOT_EXCLUDED_KEYS, TOGGLE_BACKUPS, update_starpilot_toggles

LEGACY_STARPILOT_PARAM_RENAMES = {
  "FrogPilotApiToken": "StarPilotApiToken",
  "FrogPilotCarParams": "StarPilotCarParams",
  "FrogPilotCarParamsPersistent": "StarPilotCarParamsPersistent",
  "FrogPilotDongleId": "StarPilotDongleId",
  "FrogPilotStats": "StarPilotStats",
}

EXCLUDED_KEYS = {
  "AvailableModels",
  "AvailableModelNames",
  "AvailableModelArtifactFormats",
  "StarPilotStats",
  "GithubSshKeys",
  "GithubUsername",
  "MapBoxRequests",
  "ModelDrivesAndScores",
  "ModelManifestVersion",
  "OverpassRequests",
  "SpeedLimits",
  "SpeedLimitsFiltered",
  "UpdaterAvailableBranches",
}

REPORT_CATEGORIES = [
  tr_noop("Acceleration feels harsh or jerky"),
  tr_noop("An alert was unclear and I'm not sure what it meant"),
  tr_noop("Braking is too sudden or uncomfortable"),
  tr_noop("I'm not sure if this is normal or a bug:"),
  tr_noop("My steering wheel buttons aren't working"),
  tr_noop("openpilot disengages when I don't expect it"),
  tr_noop("openpilot feels sluggish or slow to respond"),
  tr_noop("Something else (please describe)"),
]



PANEL_STYLE = DEFAULT_PANEL_STYLE

SYSTEM_PANEL_METRICS = AETHER_LIST_METRICS


class SystemSettingsManagerView(PanelManagerView):
  HEADER_SUBTITLE_HEIGHT = 24
  HEADER_SUMMARY_GAP = 6
  HEADER_CARD_HEIGHT = 140
  ACTION_PILL_WIDTH = 132
  DANGER_PILL_WIDTH = 112
  METRICS = SYSTEM_PANEL_METRICS

  def __init__(self, controller: StarPilotSystemLayout):
    super().__init__()
    self._controller = controller
    self._adjustor_rows: dict[str, AetherAdjustorRow] = {}
    self._display_slider_keys = ["ScreenBrightness", "ScreenBrightnessOnroad", "ScreenTimeout", "ScreenTimeoutOnroad"]
    self._power_slider_keys = ["DeviceShutdown", "LowVoltageShutdown"]

    shutdown_labels = {
      hours: f"{hours} " + (tr("hour") if hours == 1 else tr("hours"))
      for hours in range(1, 31)
    }
    brightness_labels = {101: tr("Auto"), 0: tr("Off")}

    self._slider_specs: dict[str, dict[str, Any]] = {
      "ScreenBrightness": {
        "title": tr("Offroad Brightness"),
        "description": tr("Screen brightness while parked. Auto follows ambient light. Cancel restores the previous brightness."),
        "subtitle": "",
        "unit": "%",
        "labels": brightness_labels,
        "min": 0,
        "max": 101,
        "step": 1,
        "live": True,
        "presets": [0, 25, 50, 75, 101],
        "get": lambda: float(self._controller._params.get_int("ScreenBrightness")),
        "set": lambda v: self._controller._set_brightness("ScreenBrightness", v),
      },
      "ScreenBrightnessOnroad": {
        "title": tr("Onroad Brightness"),
        "description": tr("Screen brightness while driving. Auto follows ambient light. Cancel restores the previous brightness."),
        "subtitle": "",
        "unit": "%",
        "labels": brightness_labels,
        "min": 0,
        "max": 101,
        "step": 1,
        "live": True,
        "presets": [0, 35, 60, 80, 101],
        "get": lambda: float(self._controller._params.get_int("ScreenBrightnessOnroad")),
        "set": lambda v: self._controller._set_brightness("ScreenBrightnessOnroad", int(v)),
      },
      "ScreenTimeout": {
        "title": tr("Offroad Screen Timeout"),
        "description": tr("How long the screen stays on without interaction while parked."),
        "subtitle": "",
        "unit": "s",
        "labels": {},
        "min": 5,
        "max": 60,
        "step": 5,
        "live": False,
        "presets": [5, 15, 30, 60],
        "get": lambda: float(self._controller._params.get_int("ScreenTimeout", return_default=True)),
        "set": lambda v: self._set_timeout("ScreenTimeout", v),
      },
      "ScreenTimeoutOnroad": {
        "title": tr("Onroad Screen Timeout"),
        "description": tr("How long the screen stays on without interaction while driving."),
        "subtitle": "",
        "unit": "s",
        "labels": {},
        "min": 5,
        "max": 60,
        "step": 5,
        "live": False,
        "presets": [5, 15, 30, 60],
        "get": lambda: float(self._controller._params.get_int("ScreenTimeoutOnroad", return_default=True)),
        "set": lambda v: self._set_timeout("ScreenTimeoutOnroad", v),
      },
      "DeviceShutdown": {
        "title": tr("Shutdown Delay"),
        "description": tr("How long the device waits before shutting down after a drive."),
        "subtitle": "",
        "unit": "",
        "labels": shutdown_labels,
        "min": 1,
        "max": 30,
        "step": 1,
        "live": False,
        "presets": [1, 3, 6, 12],
        "get": lambda: float(self._controller._params.get_int("DeviceShutdown")),
        "set": lambda v: self._controller._params.put_int("DeviceShutdown", int(v)),
      },
      "LowVoltageShutdown": {
        "title": tr("Low Voltage Shutdown"),
        "description": tr("Shut down the device when the vehicle battery falls below this voltage."),
        "subtitle": "",
        "unit": "V",
        "labels": {},
        "min": 11.8,
        "max": 12.5,
        "step": 0.1,
        "live": False,
        "presets": [11.8, 12.0, 12.2, 12.5],
        "get": lambda: float(self._controller._params.get_float("LowVoltageShutdown")),
        "set": lambda v: self._controller._params.put_float("LowVoltageShutdown", float(v)),
      },
    }

    def make_set_active(k: str):
      return lambda active: self._show_system_slider(k) if active else None

    def brightness_status(key: str) -> RowStatus:
      value = self._controller._params.get_int(key)
      if value >= 101:
        return RowStatus("display", tr("Follows ambient light"), True)
      return RowStatus("display", tr("Screen off") if value <= 0 else tr("Fixed brightness"), value > 0)

    # Same status rows as Sounds: icon well, one-line status, value and chevron.
    row_status = {
      "ScreenBrightness": lambda: brightness_status("ScreenBrightness"),
      "ScreenBrightnessOnroad": lambda: brightness_status("ScreenBrightnessOnroad"),
      "ScreenTimeout": lambda: RowStatus("timer", tr("Screen sleeps when idle"), True),
      "ScreenTimeoutOnroad": lambda: RowStatus("timer", tr("Screen sleeps when idle"), True),
      "DeviceShutdown": lambda: RowStatus("system", tr("Shuts down after each drive"), True),
      "LowVoltageShutdown": lambda: RowStatus("vehicle", tr("Protects the car battery"), True),
    }

    for key, spec in self._slider_specs.items():
      adjustor = self._child(
        AetherAdjustorRow(
          spec["title"],
          spec["subtitle"],
          spec["min"],
          spec["max"],
          spec["step"],
          spec["get"],
          on_change=lambda _v: None,
          on_commit=None,
          unit=spec["unit"],
          labels=spec["labels"],
          presets=spec.get("presets", []),
          is_active=lambda: False,
          set_active=make_set_active(key),
          style=PANEL_STYLE,
          color=PANEL_STYLE.accent,
          status=row_status[key],
        )
      )
      self._adjustor_rows[key] = adjustor

    self._toggle_defs = [
      {
        "title": tr("Standby Mode"),
        "subtitle": "",
        "get_state": lambda: self._controller._params.get_bool("StandbyMode"),
        "set_state": lambda v: self._controller._params.put_bool("StandbyMode", v),
      },
      {
        "title": tr("Use Konik Server"),
        "subtitle": "",
        "get_state": self._controller._get_konik_state,
        "set_state": self._controller._on_konik_toggle,
      },
      {
        "title": tr("Debug Mode"),
        "subtitle": "",
        "get_state": lambda: self._controller._params.get_bool("DebugMode"),
        "set_state": lambda v: self._controller._params.put_bool("DebugMode", v),
      },
      {
        "title": tr("Show FPS"),
        "subtitle": "",
        "get_state": lambda: self._controller._params.get_bool("FPSCounter"),
        "set_state": lambda v: self._controller._params.put_bool("FPSCounter", v),
      },
      {
        "title": tr("Disable Uploads"),
        "subtitle": "",
        "get_state": lambda: self._controller._params.get_bool("NoUploads"),
        "set_state": self._controller._on_no_uploads_toggle,
      },
      {
        "title": tr("Disable Onroad Uploads"),
        "subtitle": "",
        "get_state": lambda: self._controller._params.get_bool("DisableOnroadUploads"),
        "set_state": lambda v: self._controller._params.put_bool("DisableOnroadUploads", v),
        "is_enabled": lambda: not self._controller._params.get_bool("NoUploads"),
        "disabled_label": tr("Turn off Disable Uploads first"),
      },
      {
        "title": tr("Disable Logging"),
        "subtitle": "",
        "get_state": lambda: self._controller._params.get_bool("NoLogging"),
        "set_state": self._controller._on_no_logging_toggle,
      },
      {
        "title": tr("High Bitrate Recording"),
        "subtitle": "",
        "get_state": lambda: self._controller._params.get_bool("HigherBitrate"),
        "set_state": self._controller._on_higher_bitrate_toggle,
        "is_enabled": lambda: not self._controller._params.get_bool("DisableOnroadUploads") and not self._controller._params.get_bool("NoUploads"),
        "disabled_label": tr("Uploads must stay enabled"),
      },
    ]

    self._basics_tile_grid_h = 0.0

    if self.PANEL_STYLE.toggle_row_mode:
      self._connectivity_tile_grid = TileGrid(columns=1, padding=SPACING.xl, min_tile_height=TOGGLE_MIN_HEIGHT)
    else:
      self._connectivity_tile_grid = TileGrid(columns=2, padding=12, min_tile_height=130.0)
    for toggle_def in self._toggle_defs:
      tile = self._make_toggle_tile(toggle_def)
      self._connectivity_tile_grid.add_tile(tile)
    self.register_scroll_grid(self._connectivity_tile_grid)
    self.set_toggle_items(self._toggle_defs)

    # Maintenance (backups, snapshots, resets, Flash Panda) lives in the shared page header, like Sounds' Reset All.
    self._maintenance_button = self._child(AetherButton(
      tr("Maintenance"), lambda: gui_app.push_widget(AetherBackupsCareDialog(self._controller))))

    self._drive_mode_control = self._child(
      AetherSegmentedControl(
        [tr("Auto"), tr("Onroad"), tr("Offroad")],
        self._get_drive_mode_index,
        self._on_drive_mode_change,
        style=PANEL_STYLE,
      )
    )

  def _tab_subtitle(self, tab_id: str) -> str:
    if tab_id == "basics":
      return tr("{} controls + {} toggles").format(
        len(self._display_slider_keys) + len(self._power_slider_keys),
        len(self._toggle_defs))
    return self._controller.backup_status_text()

  def _format_slider_value(self, key: str) -> str:
    adjustor = self._adjustor_rows.get(key)
    if adjustor is not None:
      return adjustor.formatted_value()
    spec = self._slider_specs[key]
    current_val = spec["get"]()
    if current_val in spec["labels"]:
      return str(spec["labels"][current_val])
    if spec["step"] < 1:
      return f"{current_val:.1f}{spec['unit']}"
    return f"{int(current_val)}{spec['unit']}"

  def _show_system_slider(self, key: str):
    spec = self._slider_specs[key]
    original_val = spec["get"]()

    def on_close(res, val):
      if res == DialogResult.CONFIRM:
        spec["set"](val)
      else:
        if spec.get("live"):
          spec["set"](original_val)

    def on_change(val):
      if spec.get("live"):
        spec["set"](val)

    gui_app.push_widget(
      AetherSliderDialog(
        title=spec["title"],
        subtitle=spec["description"],
        min_val=float(spec["min"]),
        max_val=float(spec["max"]),
        step=float(spec["step"]),
        current_val=float(original_val),
        on_close=on_close,
        presets=[float(p) for p in spec.get("presets", [])],
        unit=spec["unit"],
        labels=spec["labels"],
        color=PANEL_STYLE.accent,
        on_change=on_change if spec.get("live") else None,
      )
    )

  def _set_timeout(self, key: str, value: float):
    self._controller._params.put_int(key, int(value))
    device.reset_interactive_timeout()

  def _get_drive_mode_index(self):
    state = self._controller._get_force_drive_state()
    if state == tr("Default"):
      return 0
    if state == tr("Onroad"):
      return 1
    if state == tr("Offroad"):
      return 2
    return 0

  def _on_drive_mode_change(self, idx):
    if idx == 0:
        self._controller.handle_action("DriveDefault")
    elif idx == 1:
        self._controller.handle_action("DriveOnroad")
    elif idx == 2:
        self._controller.handle_action("DriveOffroad")

  def _clear_ephemeral_state(self):
    self._pressed_target = None
    self._can_click = True
    for adjustor in self._adjustor_rows.values():
      adjustor.reset_interaction()

  def show_event(self):
    super().show_event()
    self._clear_ephemeral_state()
    self.reset_scroll()

  def hide_event(self):
    super().hide_event()
    self._clear_ephemeral_state()

  def use_page_header(self) -> AetherButton:
    return self._maintenance_button

  def _on_frame_created(self, frame) -> None:
    pass

  @property
  def bottombar_height(self) -> float:
    return 0.0

  def _draw_static_elements(self, scroll_rect: rl.Rectangle, content_width: float) -> None:
    pass

  def _draw_header(self, rect: rl.Rectangle):
    content_width = self._scroll_rect.width - AETHER_LIST_METRICS.content_right_gutter
    bar_height = self._drive_mode_control.measure_height(content_width)
    bar_rect = rl.Rectangle(rect.x, rect.y, content_width, bar_height)
    self._drive_mode_control.render(bar_rect)
    total_offset = bar_height + AetherSegmentedControl.GAP
    self._scroll_rect.y += total_offset
    self._scroll_rect.height = max(0.0, self._scroll_rect.height - total_offset)

  def _measure_content_height(self, width: float) -> float:
    for key in self._display_slider_keys + self._power_slider_keys:
      self._adjustor_rows[key].custom_row_height = None
    column_w = self._column_width(width)
    display_h = self._slider_section_height(self._display_slider_keys, column_w) + GROUP_OVERHEAD
    power_h = self._slider_section_height(self._power_slider_keys, column_w) + GROUP_OVERHEAD
    self._system_adjustor_h = display_h + SECTION_GAP + power_h
    self._system_toggle_h = self.measure_scroll_grid_height(self._connectivity_tile_grid, column_w) + GROUP_OVERHEAD
    if self._uses_two_columns(width):
      return self._compute_two_column_height(max(display_h + SECTION_GAP + power_h, self._system_toggle_h))
    return self._stacked_section_height([display_h, power_h, self._system_toggle_h])

  def _build_scroll_columns(self, width: float) -> list[SettingsColumn]:
    if not self._uses_two_columns(width):
      return []
    return [SettingsColumn("left", self._system_adjustor_h, self._draw_slider_column),
            SettingsColumn("right", self._system_toggle_h,
                           lambda rect: self._draw_connectivity_tiles_section(rect.y, rect.x, rect.width))]

  def _draw_slider_column(self, rect: rl.Rectangle):
    y = self._draw_slider_section(rect.y, rect.x, rect.width, tr("Display"), self._display_slider_keys)
    self._draw_slider_section(y + SECTION_GAP, rect.x, rect.width, tr("Power"), self._power_slider_keys)

  def _slider_section_height(self, keys: list[str], width: float) -> float:
    total = 0.0
    for key in keys:
      adjustor = self._adjustor_rows[key]
      total += adjustor.measure_height(width)
    return total

  def _draw_scroll_content(self, rect: rl.Rectangle, width: float):
    y = rect.y + self._scroll_offset
    self._draw_basics_tab(y, rect.x, width)

  def _draw_basics_tab(self, y: float, x: float, width: float):
    if self._uses_two_columns(width):
      column_w = self._column_width(width)
      current_y = self._draw_slider_section(y, x, column_w, tr("Display"), self._display_slider_keys)
      self._draw_slider_section(current_y + SECTION_GAP, x, column_w, tr("Power"), self._power_slider_keys)
      tg_cols = 1 if self.PANEL_STYLE.toggle_row_mode else 2
      self._draw_two_column_tile_grid(
        self._connectivity_tile_grid, x + column_w + self.COLUMN_GAP, y, column_w,
        self._system_toggle_h, title=tr("Options"), columns=tg_cols)
      return

    y = self._draw_slider_section(y, x, width, tr("Display"), self._display_slider_keys)
    y += SECTION_GAP
    y = self._draw_slider_section(y, x, width, tr("Power"), self._power_slider_keys)
    y += SECTION_GAP
    self._draw_connectivity_tiles_section(y, x, width)

  def _draw_connectivity_tiles_section(self, y: float, x: float, width: float):
    group_h = self.measure_scroll_grid_height(self._connectivity_tile_grid, width) + GROUP_OVERHEAD
    body = draw_settings_group(rl.Rectangle(x, y, width, group_h), tr("Options"), style=PANEL_STYLE, kind="tiles")
    self._render_scroll_grid(self._connectivity_tile_grid, body)

  def _draw_slider_section(self, y: float, x: float, width: float, title: str, keys: list[str]) -> float:
    group_h = self._slider_section_height(keys, width) + GROUP_OVERHEAD
    body = draw_settings_group(rl.Rectangle(x, y, width, group_h), title, style=PANEL_STYLE)
    current_y = body.y
    for index, key in enumerate(keys):
      current_y = self._draw_slider_row(rl.Rectangle(body.x, current_y, body.width, 0), key, is_last=index == len(keys) - 1)
    return y + group_h

  def _draw_slider_row(self, rect: rl.Rectangle, key: str, is_last: bool) -> float:
    adjustor = self._adjustor_rows[key]
    adjustor.set_is_last(is_last)
    row_h = adjustor.measure_height(rect.width)
    row_rect = rl.Rectangle(rect.x, rect.y, rect.width, row_h)
    self._bind_scroll_widget(adjustor)
    adjustor.render(row_rect)
    return rect.y + row_h


class AetherBackupsCareDialog(AetherChoiceDialog):
  def __init__(self, controller: StarPilotSystemLayout):
    choices = [
      PreviewChoice("system_backups", tr("System Backups"), description=tr("Create, restore or delete a system backup.")),
      PreviewChoice("toggle_snapshots", tr("Profiles & Snapshots"), description=tr("Save and restore settings profiles or named snapshots.")),
      PreviewChoice("report_issue", tr("Report Issue"), description=tr("Choose a category and describe a problem.")),
      PreviewChoice("flash_panda", tr("Flash Panda"), description=tr("Reinstall the Panda firmware.")),
      PreviewChoice("clear_data", tr("Clear Driving Data"), description=tr("Delete driving data and footage after confirmation.")),
      PreviewChoice("clear_logs", tr("Clear Error Logs"), description=tr("Delete saved error logs after confirmation.")),
      PreviewChoice("reset_toggles", tr("Reset Toggles"), description=tr("Restore default settings after confirmation.")),
      PreviewChoice("reset_stock", tr("Reset To Stock"), description=tr("Restore stock openpilot settings after confirmation.")),
    ]
    description = tr("Storage: {} • Backups: {} • Snapshots: {}").format(
      controller.storage_summary(), controller.backup_count_text(), controller.toggle_backup_count_text())
    super().__init__(tr("Maintenance"), choices, subtitle=description, layout="list")
    self._controller = controller

  def _on_result(self, result: DialogResult):
    if result == DialogResult.CONFIRM:
      self._trigger_action(self.selection)

  def _trigger_action(self, btn_id: str):
    if btn_id == "system_backups":
      self._controller.open_backup_manager("system")
    elif btn_id == "toggle_snapshots":
      self._controller.open_backup_manager("toggle")
    elif btn_id == "report_issue":
      self._controller.handle_action("ReportIssue")
    elif btn_id == "flash_panda":
      self._controller.handle_action("FlashPanda")
    elif btn_id == "clear_data":
      self._controller.handle_action("Storage")
    elif btn_id == "clear_logs":
      self._controller.handle_action("ErrorLogs")
    elif btn_id == "reset_toggles":
      self._controller.handle_action("ResetDefaults")
    elif btn_id == "reset_stock":
      self._controller.handle_action("ResetStock")

class StarPilotSystemLayout(_SettingsPage):
  _BACKUP_NAME_SANITIZE_RE = re.compile(r"[^A-Za-z0-9._-]+")

  def __init__(self):
    super().__init__()
    self._keyboard = Keyboard(min_text_size=0)
    self._storage_text = "0 MB"
    self._storage_updated_at = 0.0
    self._storage_refresh_pending = False
    self._storage_refresh_generation = 0
    self._pending_storage_text: tuple[int, str] | None = None
    self._manager_view = SystemSettingsManagerView(self)
    self._refresh_storage_cache(force=True)

  def show_event(self):
    self._refresh_storage_cache(force=True)
    super().show_event()

  def _render(self, rect: rl.Rectangle):
    if self._pending_storage_text is not None:
      generation, storage_text = self._pending_storage_text
      self._pending_storage_text = None
      if generation == self._storage_refresh_generation:
        self._storage_text = storage_text
        self._storage_updated_at = rl.get_time()
      self._storage_refresh_pending = False
    self._refresh_storage_cache()
    super()._render(rect)

  def _refresh_storage_cache(self, force: bool = False):
    now = rl.get_time()
    if self._storage_refresh_pending:
      return
    if not force and (now - self._storage_updated_at) < 5.0:
      return

    generation = self._storage_refresh_generation + 1
    self._storage_refresh_generation = generation

    def refresh_worker():
      result: str | None = None
      try:
        result = self._get_storage()
      finally:
        if result is None:
          self._storage_refresh_pending = False
        else:
          self._pending_storage_text = (generation, result)

    self._storage_refresh_pending = True
    self._storage_updated_at = now
    threading.Thread(target=refresh_worker, daemon=True).start()

  def storage_summary(self) -> str:
    return str(self._storage_text)

  def backup_count_text(self) -> str:
    count = len(self._get_backups("backups"))
    return tr("None") if count == 0 else tr("{} saved").format(count)

  def backup_count(self) -> int:
    return len(self._get_backups("backups"))

  def toggle_backup_count_text(self) -> str:
    count = len(self._get_backups("toggle_backups"))
    return tr("None") if count == 0 else tr("{} saved").format(count)

  def toggle_backup_count(self) -> int:
    return len(self._get_backups("toggle_backups"))

  def latest_backup_summary(self) -> str:
    backups = self._get_backups("backups")
    if not backups:
      return tr("No full-system backups saved yet.")
    return backups[-1]

  def latest_toggle_backup_summary(self) -> str:
    backups = self._get_backups("toggle_backups")
    if not backups:
      return tr("No toggle snapshots saved yet.")
    return backups[-1]

  def backup_status_text(self) -> str:
    system_count = len(self._get_backups("backups"))
    toggle_count = len(self._get_backups("toggle_backups"))
    return tr("{} full | {} toggle").format(system_count, toggle_count)

  def open_backup_manager(self, backup_kind: str):
    if backup_kind == "system":
      options = [tr("Create Backup"), tr("Restore Backup"), tr("Delete Backup")]
      title = tr("System Backups")
    else:
      options = [
        tr("Profile Slot A"),
        tr("Profile Slot B"),
        tr("Save Named Snapshot"),
        tr("Restore Named Snapshot"),
        tr("Delete Named Snapshot"),
      ]
      title = tr("Settings Profiles & Snapshots")

    def on_select(res):
      if res != DialogResult.CONFIRM or not dialog.selection:
        return
      selection = dialog.selection
      if backup_kind == "system":
        if selection == options[0]:
          self._on_create_backup()
        elif selection == options[1]:
          self._on_restore_backup()
        elif selection == options[2]:
          self._on_delete_backup()
      else:
        if selection == options[0]:
          self._open_param_profile("a")
        elif selection == options[1]:
          self._open_param_profile("b")
        elif selection == options[2]:
          self._on_create_toggle_backup()
        elif selection == options[3]:
          self._on_restore_toggle_backup()
        elif selection == options[4]:
          self._on_delete_toggle_backup()

    dialog = MultiOptionDialog(title, options, callback=on_select,
                               subtitle=tr("Choose a backup or profile action to continue."))
    gui_app.push_widget(dialog)

  def handle_action(self, action_id: str):
    if action_id == "ScreenManagement":
      self._params.put_bool("ScreenManagement", not self._params.get_bool("ScreenManagement"))
    elif action_id == "DeviceManagement":
      self._params.put_bool("DeviceManagement", not self._params.get_bool("DeviceManagement"))
    elif action_id == "Storage":
      self._on_delete_driving_data()
    elif action_id == "ErrorLogs":
      self._on_delete_error_logs()
    elif action_id == "CreateBackup":
      self._on_create_backup()
    elif action_id == "RestoreBackup":
      self._on_restore_backup()
    elif action_id == "DeleteBackup":
      self._on_delete_backup()
    elif action_id == "CreateToggleBackup":
      self._on_create_toggle_backup()
    elif action_id == "RestoreToggleBackup":
      self._on_restore_toggle_backup()
    elif action_id == "DeleteToggleBackup":
      self._on_delete_toggle_backup()
    elif action_id == "DriveDefault":
      self._params.put_bool("ForceOffroad", False)
      self._params.put_bool("ForceOnroad", False)
    elif action_id == "DriveOnroad":
      self._params.put_bool("ForceOnroad", True)
      self._params.put_bool("ForceOffroad", False)
    elif action_id == "DriveOffroad":
      self._params.put_bool("ForceOffroad", True)
      self._params.put_bool("ForceOnroad", False)
    elif action_id == "FlashPanda":
      self._on_flash_panda()
    elif action_id == "ReportIssue":
      self._on_report_issue()
    elif action_id == "ResetDefaults":
      self._on_reset_defaults()
    elif action_id == "ResetStock":
      self._on_reset_stock()

  def _set_brightness(self, key, val):
    self._params.put_int(key, int(val))
    if not ui_state.started and key == "ScreenBrightness":
      if hasattr(HARDWARE, 'set_screen_brightness'):
        HARDWARE.set_screen_brightness(int(val))
    elif ui_state.started and key == "ScreenBrightnessOnroad":
      if hasattr(HARDWARE, 'set_screen_brightness'):
        HARDWARE.set_screen_brightness(int(val))

  def _get_konik_state(self):
    if Path("/data/not_vetted").exists():
      return True
    return self._params.get_bool("UseKonikServer")

  def _on_konik_toggle(self, state):
    target = tr("Konik") if state else tr("Comma")

    def on_confirm(res):
      if res != DialogResult.CONFIRM:
        self._params.put_bool("UseKonikServer", not state)
        return
      prepare_konik_server_switch(state, self._params)
      try:
        cache_path = Path("/cache/use_konik")
        if state:
          cache_path.parent.mkdir(parents=True, exist_ok=True)
          cache_path.touch()
        else:
          if cache_path.exists():
            cache_path.unlink()
      except OSError:
        pass
      if ui_state.started:
        gui_app.push_widget(
          ConfirmDialog(
            tr("Reboot required. Reboot now?"), tr("Reboot"), tr("Cancel"),
            callback=lambda res: HARDWARE.reboot() if res == DialogResult.CONFIRM else None
          )
        )

    gui_app.push_widget(
      ConfirmDialog(
        tr("Switch Connect endpoint to {}?").format(target),
        tr("Switch"),
        tr("Cancel"),
        callback=on_confirm
      )
    )

  def _on_no_uploads_toggle(self, state):
    if state:
      gui_app.push_widget(ConfirmDialog(
        tr("This will prevent your drives from being uploaded to comma connect which may impact receiving support. Are you sure?"),
        tr("Disable"),
        callback=lambda res: self._params.put_bool("NoUploads", True) if res == DialogResult.CONFIRM else None,
      ))
    else:
      self._params.put_bool("NoUploads", False)

  def _on_no_logging_toggle(self, state):
    if state:
      gui_app.push_widget(ConfirmDialog(
        tr("This will prevent your drives from being logged. Are you sure?"),
        tr("Disable"),
        callback=lambda res: self._params.put_bool("NoLogging", True) if res == DialogResult.CONFIRM else None,
      ))
    else:
      self._params.put_bool("NoLogging", False)

  def _on_higher_bitrate_toggle(self, state):
    self._params.put_bool("HigherBitrate", state)
    try:
      cache_path = Path("/cache/use_HD")
      if state:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.touch()
      else:
        if cache_path.exists():
          cache_path.unlink()
    except OSError:
      pass
    if ui_state.started:
      gui_app.push_widget(
        ConfirmDialog(
          tr("Reboot required. Reboot now?"), tr("Reboot"), tr("Cancel"), callback=lambda res: HARDWARE.reboot() if res == DialogResult.CONFIRM else None
        )
      )

  def _get_storage(self):
    paths = ["/data/media/0/osm/offline", "/data/media/0/realdata", "/data/backups"]
    total = 0
    for p in paths:
      pp = Path(p)
      if pp.exists():
        total += sum(f.stat().st_size for f in pp.rglob('*') if f.is_file())
    mb = total / (1024 * 1024)
    if mb > 1024:
      return f"{(mb / 1024):.2f} GB"
    return f"{mb:.2f} MB"

  def _on_delete_driving_data(self):
    def _do_delete(res):
      if res == DialogResult.CONFIRM:
        def _task():
          drive_paths = ["/data/media/0/realdata/", "/data/media/0/realdata_HD/", "/data/media/0/realdata_konik/"]
          for path in drive_paths:
            p = Path(path)
            if p.exists():
              for entry in p.iterdir():
                if entry.is_dir():
                  shutil.rmtree(entry, ignore_errors=True)
        threading.Thread(target=_task, daemon=True).start()
        gui_app.push_widget(alert_dialog(tr("Driving data deletion started.")))
    gui_app.push_widget(ConfirmDialog(tr("Delete all driving data and footage?"), tr("Delete"), callback=_do_delete))

  def _on_delete_error_logs(self):
    def _do_delete(res):
      if res == DialogResult.CONFIRM:
        shutil.rmtree("/data/error_logs", ignore_errors=True)
        os.makedirs("/data/error_logs", exist_ok=True)
        gui_app.push_widget(alert_dialog(tr("Error logs deleted.")))
    gui_app.push_widget(ConfirmDialog(tr("Delete all error logs?"), tr("Delete"), callback=_do_delete))

  def _get_backups(self, folder: str = "backups") -> list[str]:
    b_dir = Path(f"/data/{folder}")
    if not b_dir.exists():
      return []
    if folder == "backups":
      entries = [f for f in b_dir.glob("*.tar.zst") if "in_progress" not in f.name]
    else:
      entries = [d for d in b_dir.iterdir() if d.is_dir() and "in_progress" not in d.name]
    entries.sort(key=lambda item: item.stat().st_mtime if item.exists() else 0.0, reverse=True)
    return [entry.name for entry in entries]

  def _sanitize_backup_name(self, raw_name: str, prefix: str) -> str:
    sanitized = self._BACKUP_NAME_SANITIZE_RE.sub("_", raw_name.strip())
    sanitized = sanitized.strip("._-")
    if not sanitized:
      sanitized = f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    return sanitized

  def _on_create_backup(self):
    def on_name(res, name):
      if res == DialogResult.CONFIRM:
        safe_name = self._sanitize_backup_name(name or "", "backup")
        backup_path = f"/data/backups/{safe_name}.tar.zst"
        if Path(backup_path).exists():
          gui_app.push_widget(alert_dialog(tr("A backup with this name already exists.")))
          return
        gui_app.push_widget(alert_dialog(tr("Backup creation started.")))
        def _task():
          os.makedirs("/data/backups", exist_ok=True)
          subprocess.run(["tar", "--use-compress-program=zstd", "-cf", backup_path, "/data/openpilot"])
        threading.Thread(target=_task, daemon=True).start()
    self._keyboard.reset(min_text_size=0)
    self._keyboard.set_title(tr("Name your backup"), "")
    self._keyboard.set_text("")
    self._keyboard.set_callback(lambda result: on_name(result, self._keyboard.text))
    gui_app.push_widget(self._keyboard)

  def _on_restore_backup(self):
    backups = self._get_backups("backups")
    if not backups:
      gui_app.push_widget(alert_dialog(tr("No backups found.")))
      return

    def _on_select(res):
      if res == DialogResult.CONFIRM and dialog.selection:
        gui_app.push_widget(alert_dialog(tr("Restoring... device will reboot.")))
        def _task():
          shutil.rmtree("/data/openpilot", ignore_errors=True)
          os.makedirs("/data/openpilot", exist_ok=True)
          subprocess.run(["tar", "--use-compress-program=zstd", "-xf", f"/data/backups/{dialog.selection}", "-C", "/"])
          os.system("reboot")
        threading.Thread(target=_task, daemon=True).start()

    dialog = MultiOptionDialog(tr("Select Backup"), backups, callback=_on_select,
                               subtitle=tr("Choose the system backup to restore."))
    gui_app.push_widget(dialog)

  def _on_delete_backup(self):
    backups = self._get_backups("backups")
    if not backups:
      gui_app.push_widget(alert_dialog(tr("No backups found.")))
      return

    def _on_select(res):
      if res == DialogResult.CONFIRM and dialog.selection:
        backup_name = dialog.selection

        def _on_confirm(confirm_res):
          if confirm_res == DialogResult.CONFIRM:
            os.remove(f"/data/backups/{backup_name}")
            gui_app.push_widget(alert_dialog(tr("Backup deleted.")))

        gui_app.push_widget(ConfirmDialog(tr("Delete backup '{}'?").format(backup_name), tr("Delete"), callback=_on_confirm))

    dialog = MultiOptionDialog(tr("Delete Backup"), backups, callback=_on_select,
                               subtitle=tr("Choose a backup to delete. You will be asked to confirm."))
    gui_app.push_widget(dialog)

  def _on_create_toggle_backup(self):
    def on_name(res, name):
      if res == DialogResult.CONFIRM:
        safe_name = self._sanitize_backup_name(name or "", "toggle_backup")
        backup_path = Path(f"/data/toggle_backups/{safe_name}")
        if backup_path.exists():
          gui_app.push_widget(alert_dialog(tr("A toggle backup with this name already exists.")))
          return
        os.makedirs(backup_path, exist_ok=True)
        shutil.copytree("/data/params/d", str(backup_path), dirs_exist_ok=True)
        gui_app.push_widget(alert_dialog(tr("Toggle backup created.")))
    self._keyboard.reset(min_text_size=0)
    self._keyboard.set_title(tr("Name your toggle backup"), "")
    self._keyboard.set_text("")
    self._keyboard.set_callback(lambda result: on_name(result, self._keyboard.text))
    gui_app.push_widget(self._keyboard)

  def _open_param_profile(self, slot: str):
    status = param_profiles.profile_status(slot, profile_root=TOGGLE_BACKUPS)
    options = [tr("Save Current Settings")]
    if status["saved"] and not status.get("invalid"):
      options.append(tr("Load Saved Settings"))

    def _on_select(res):
      if res != DialogResult.CONFIRM or not dialog.selection:
        return
      if dialog.selection == options[0]:
        if ui_state.started:
          gui_app.push_widget(alert_dialog(tr("Settings profiles can only be saved while parked.")))
          return
        if status["saved"]:
          gui_app.push_widget(ConfirmDialog(
            tr("Overwrite {} with your current settings?").format(status["label"]),
            tr("Overwrite"),
            callback=lambda confirm_res: self._save_param_profile(slot) if confirm_res == DialogResult.CONFIRM else None,
          ))
        else:
          self._save_param_profile(slot)
      elif len(options) > 1 and dialog.selection == options[1]:
        if ui_state.started:
          gui_app.push_widget(alert_dialog(tr("Settings profiles can only be loaded while parked.")))
          return
        gui_app.push_widget(ConfirmDialog(
          tr("Load {} and overwrite your current settings?").format(status["label"]),
          tr("Load"),
          callback=lambda confirm_res: self._load_param_profile(slot) if confirm_res == DialogResult.CONFIRM else None,
        ))

    dialog = MultiOptionDialog(status["label"], options, callback=_on_select,
                               subtitle=tr("Choose whether to save current settings or load this profile."))
    gui_app.push_widget(dialog)

  def _save_param_profile(self, slot: str):
    try:
      status = param_profiles.save_profile(
        self._params,
        slot,
        allowed_keys=param_profiles.eligible_profile_keys(self._params, excluded_keys=STARPILOT_EXCLUDED_KEYS),
        profile_root=TOGGLE_BACKUPS,
      )
    except param_profiles.ParamProfileError as error:
      gui_app.push_widget(alert_dialog(str(error)))
      return
    gui_app.push_widget(alert_dialog(tr("Saved current settings to {}.").format(status["label"])))

  def _load_param_profile(self, slot: str):
    try:
      result = param_profiles.load_profile(
        self._params,
        slot,
        allowed_keys=param_profiles.eligible_profile_keys(self._params, excluded_keys=STARPILOT_EXCLUDED_KEYS),
        profile_root=TOGGLE_BACKUPS,
        legacy_renames=LEGACY_STARPILOT_PARAM_RENAMES,
      )
    except param_profiles.ParamProfileError as error:
      gui_app.push_widget(alert_dialog(str(error)))
      return
    update_starpilot_toggles()
    gui_app.push_widget(alert_dialog(
      tr("Loaded {} settings from {}.").format(result["restoredCount"], result["label"])
    ))

  def _on_restore_toggle_backup(self):
    backups = self._get_backups("toggle_backups")
    if not backups:
      gui_app.push_widget(alert_dialog(tr("No toggle backups found.")))
      return

    def _on_select(res):
      if res == DialogResult.CONFIRM and dialog.selection:
        def on_confirm(r2):
          if r2 == DialogResult.CONFIRM:
            src = Path(f"/data/toggle_backups/{dialog.selection}")
            params_dir = Path("/data/params/d")
            for old_key, new_key in LEGACY_STARPILOT_PARAM_RENAMES.items():
              if (src / old_key).exists():
                (params_dir / new_key).unlink(missing_ok=True)
            shutil.copytree(str(src), "/data/params/d", dirs_exist_ok=True)
            for old_key, new_key in LEGACY_STARPILOT_PARAM_RENAMES.items():
              old_path = params_dir / old_key
              new_path = params_dir / new_key
              if old_path.exists():
                old_path.replace(new_path)
            gui_app.push_widget(alert_dialog(tr("Toggles restored.")))
        gui_app.push_widget(ConfirmDialog(tr("This will overwrite your current toggles."), tr("Restore"), callback=on_confirm))

    dialog = MultiOptionDialog(tr("Select Toggle Backup"), backups, callback=_on_select,
                               subtitle=tr("Choose the settings snapshot to restore."))
    gui_app.push_widget(dialog)

  def _on_delete_toggle_backup(self):
    backups = self._get_backups("toggle_backups")
    if not backups:
      gui_app.push_widget(alert_dialog(tr("No toggle backups found.")))
      return

    def _on_select(res):
      if res == DialogResult.CONFIRM and dialog.selection:
        backup_name = dialog.selection

        def _on_confirm(confirm_res):
          if confirm_res == DialogResult.CONFIRM:
            shutil.rmtree(f"/data/toggle_backups/{backup_name}", ignore_errors=True)
            gui_app.push_widget(alert_dialog(tr("Toggle backup deleted.")))

        gui_app.push_widget(ConfirmDialog(tr("Delete toggle backup '{}'?").format(backup_name), tr("Delete"), callback=_on_confirm))

    dialog = MultiOptionDialog(tr("Delete Toggle Backup"), backups, callback=_on_select,
                               subtitle=tr("Choose a settings snapshot to delete. You will be asked to confirm."))
    gui_app.push_widget(dialog)

  def _get_force_drive_state(self):
    if self._params.get_bool("ForceOnroad"):
      return tr("Onroad")
    if self._params.get_bool("ForceOffroad"):
      return tr("Offroad")
    return tr("Default")

  def _on_flash_panda(self):
    def _do_flash(res):
      if res == DialogResult.CONFIRM:
        self._params_memory.put_bool("FlashPanda", True)
        gui_app.push_widget(alert_dialog(tr("Panda flashing started. Device will reboot when finished.")))
    gui_app.push_widget(ConfirmDialog(tr("Flash Panda firmware?"), tr("Flash"), callback=_do_flash))

  def _on_report_issue(self):
    def on_category(res):
      if res != DialogResult.CONFIRM or not dialog.selection:
        return
      discord_user = self._params.get("DiscordUsername", encoding='utf-8') or ""
      def on_discord(res2, username):
        if res2 == DialogResult.CONFIRM and username:
          self._params.put("DiscordUsername", username)
          report = {"DiscordUser": username, "Issue": dialog.selection}
          self._params_memory.put("IssueReported", report)
          gui_app.push_widget(alert_dialog(tr("Issue reported. Thank you!")))
      self._keyboard.reset(min_text_size=1)
      self._keyboard.set_title(tr("Discord Username"), "")
      self._keyboard.set_text(discord_user or "")
      self._keyboard.set_callback(lambda result: on_discord(result, self._keyboard.text))
      gui_app.push_widget(self._keyboard)
    dialog = MultiOptionDialog(tr("Select Issue"), REPORT_CATEGORIES, callback=on_category,
                               subtitle=tr("Choose the category that best describes the problem."))
    gui_app.push_widget(dialog)

  def _on_reset_defaults(self):
    def _do_reset(res):
      if res == DialogResult.CONFIRM:
        all_keys = self._params.all_keys()
        for k in all_keys:
          if k in EXCLUDED_KEYS:
            continue
          default = self._params.get_default_value(k)
          if default is not None:
            self._params.put(k, default)
        gui_app.push_widget(alert_dialog(tr("Toggles reset to defaults.")))
    gui_app.push_widget(ConfirmDialog(tr("Reset all toggles to defaults?"), tr("Reset"), callback=_do_reset))

  def _on_reset_stock(self):
    def _do_reset(res):
      if res == DialogResult.CONFIRM:
        all_keys = self._params.all_keys()
        for k in all_keys:
          if k in EXCLUDED_KEYS:
            continue
          stock = self._params.get_stock_value(k)
          if stock is not None:
            self._params.put(k, stock)
        gui_app.push_widget(alert_dialog(tr("Toggles reset to stock openpilot.")))
    gui_app.push_widget(ConfirmDialog(tr("Reset all toggles to stock openpilot?"), tr("Reset"), callback=_do_reset))
