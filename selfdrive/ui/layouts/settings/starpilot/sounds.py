from __future__ import annotations
from dataclasses import replace
import subprocess
from pathlib import Path

import pyray as rl

from openpilot.common.basedir import BASEDIR
from openpilot.starpilot.common.starpilot_variables import ACTIVE_THEME_PATH
from openpilot.system.ui.lib.application import gui_app
from openpilot.system.ui.lib.multilang import tr, tr_noop
from openpilot.system.ui.widgets import DialogResult
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.selfdrive.ui.lib.starpilot_state import starpilot_state
from openpilot.selfdrive.ui.layouts.settings.starpilot.panel import _SettingsPage
from openpilot.selfdrive.ui.layouts.settings.starpilot.aethergrid import (
  COMPACT_PANEL_METRICS,
  AdjustorTogglesPanelView,
  AetherAdjustorRow,
  AetherButton,
  RowStatus,
  SettingsColumn,
  SPACING,
  TileGrid,
  TOGGLE_MIN_HEIGHT,
  DEFAULT_PANEL_STYLE,
  draw_settings_group,
  AetherSliderDialog,
  SECTION_GAP,
  GROUP_OVERHEAD,
)

PANEL_STYLE = DEFAULT_PANEL_STYLE
SOUNDS_PANEL_METRICS = replace(
  COMPACT_PANEL_METRICS,
  header_height=0,
)



class SoundsManagerView(AdjustorTogglesPanelView):
  METRICS = SOUNDS_PANEL_METRICS

  def __init__(self, controller: StarPilotSoundsLayout):
    super().__init__()
    self._controller = controller
    self._reset_button = self._child(AetherButton(
      tr("Reset All"), self._controller._restore_defaults,
      confirmation=tr("Reset all sound volumes, cooldown, and custom alerts to their defaults?"),
      confirm_label=tr("Reset All"),
    ))

    self._tile_grid_h = 0.0

    self._init_adjustors()
    self._init_toggles()

  def _init_toggles(self):
    if self.PANEL_STYLE.toggle_row_mode:
      self._toggle_grid = TileGrid(columns=1, padding=SPACING.xl, min_tile_height=TOGGLE_MIN_HEIGHT)
    else:
      self._toggle_grid = TileGrid(columns=2, padding=12, min_tile_height=130.0)
    self.register_scroll_grid(self._toggle_grid)

    toggle_defs = []
    for key in self._controller.CUSTOM_ALERTS_KEYS:
      info = self._controller.ALERT_INFO[key]
      toggle_defs.append({
        "title": tr(info["title"]),
        "subtitle": tr(info.get("subtitle", "")),
        "get_state": lambda k=key: self._controller._params.get_bool(k),
        "set_state": lambda state, k=key: self._controller._params.put_bool(k, state),
        "is_enabled": info.get("is_enabled"),
        "disabled_label": tr(info.get("disabled_label", "")) if info.get("disabled_label") else "",
      })

    self.set_toggle_items(toggle_defs)

  def _init_adjustors(self):
    for key in self._controller.VOLUME_KEYS:
      info = self._controller.VOLUME_INFO[key]

      adjustor = AetherAdjustorRow(
        tr(info["title"]),
        tr(info["subtitle"]),
        float(info["min"]), 101.0, 1.0,
        get_value=lambda k=key: float(self._controller._params.get_int(k, return_default=True, default=101)),
        on_change=lambda _v: None,
        on_commit=None,
        unit="%",
        labels={0.0: tr("Muted"), 101.0: tr("Auto")},
        presets=[p for p in [0, 25, 50, 75, 101] if p >= info["min"]],
        is_active=lambda: False,
        set_active=lambda active, k=key: self._show_volume_slider(k) if active else None,
        style=PANEL_STYLE,
        color=PANEL_STYLE.accent,
        status=lambda k=key: self._volume_status(k),
      )
      self._adjustor_rows[key] = adjustor

    cd_key = self._controller.COOLDOWN_KEY
    cd_info = self._controller.COOLDOWN_INFO
    def on_cd_close(res, val):
      if res == DialogResult.CONFIRM:
        self._controller._params.put_int(cd_key, int(val))

    cd_adjustor = AetherAdjustorRow(
      tr(cd_info["title"]),
      tr(cd_info["subtitle"]),
      0.0, float(cd_info["max"]), 1.0,
      get_value=lambda: float(self._controller._params.get_int(cd_key, return_default=True, default=0)),
      on_change=lambda _v: None,
      on_commit=None,
      unit=" " + tr("min"),
      labels={0.0: tr("Off"), 1.0: tr("1 min")},
      presets=[0, 1, 5, 10, 20, 30],
      is_active=lambda: False,
      set_active=lambda active: gui_app.push_widget(
        AetherSliderDialog(
          title=tr(cd_info["title"]),
          min_val=0.0,
          max_val=float(cd_info["max"]),
          step=1.0,
          current_val=float(self._controller._params.get_int(cd_key, return_default=True, default=0)),
          on_close=on_cd_close,
          presets=[0.0, 1.0, 5.0, 10.0, 20.0, 30.0],
          subtitle=tr(cd_info["subtitle"]),
          unit=" " + tr("min"),
          labels={0.0: tr("Off"), 1.0: tr("1 min")},
          color=PANEL_STYLE.accent,
        )
      ) if active else None,
      style=PANEL_STYLE,
      color=PANEL_STYLE.accent,
      status=lambda: RowStatus("timer", tr("Cooldown enabled") if self._controller._params.get_int(cd_key) > 0 else tr("Cooldown off"),
                               self._controller._params.get_int(cd_key) > 0),
    )
    self._adjustor_rows[cd_key] = cd_adjustor

  def _volume_status(self, key: str) -> RowStatus:
    volume = self._controller._params.get_int(key, return_default=True, default=101)
    return RowStatus("sound" if volume > 0 else "sound_muted", tr("Sound enabled") if volume > 0 else tr("Sound muted"), volume > 0)

  def _show_volume_slider(self, key: str):
    info = self._controller.VOLUME_INFO[key]
    min_v = info["min"]
    original_val = self._controller._params.get_int(key, return_default=True, default=101)

    def on_close(res, val):
      if res == DialogResult.CONFIRM:
        new_v = int(val)
        if new_v != 101 and new_v < min_v:
          new_v = min_v
        self._controller._params.put_int(key, new_v)
      else:
        self._controller._params.put_int(key, original_val)

    def on_change(val):
      new_v = int(val)
      if new_v != 101 and new_v < min_v:
        new_v = min_v
      self._controller._params.put_int(key, new_v)
      self._controller._test_sound(key)

    current_val = float(original_val)
    dialog_title = tr(info["title"])
    gui_app.push_widget(
      AetherSliderDialog(
        title=dialog_title,
        subtitle=" ".join(filter(None, (tr(info["subtitle"]), tr("Preview the selected volume. Cancel restores the previous volume.")))),
        min_val=float(min_v),
        max_val=101.0,
        step=1.0,
        current_val=current_val,
        on_close=on_close,
        presets=[float(p) for p in [0, 25, 50, 75, 101] if p >= min_v],
        unit="%",
        labels={0.0: tr("Muted"), 101.0: tr("Auto")},
        color=PANEL_STYLE.accent,
        on_change=on_change,
      )
    )

  def use_page_header(self) -> AetherButton:
    return self._reset_button

  def _measure_content_height(self, content_width: float) -> float:
    col_width = self._column_width(content_width)

    for key in self._controller.VOLUME_KEYS:
      self._adjustor_rows[key].custom_row_height = None
    self._adjustor_rows[self._controller.COOLDOWN_KEY].custom_row_height = None

    vol_overhead = GROUP_OVERHEAD

    left_content_h = sum(row.measure_height(col_width) for row in self._adjustor_rows.values()) + vol_overhead
    tiles_needed_h = self.measure_scroll_grid_height(self._toggle_grid, col_width) + GROUP_OVERHEAD
    max_content_h = max(left_content_h, tiles_needed_h)

    self._left_container_h = left_content_h
    self._tiles_container_h = tiles_needed_h

    return self._compute_two_column_height(max_content_h) if self._uses_two_columns(content_width) else left_content_h + SECTION_GAP + tiles_needed_h

  def _build_scroll_columns(self, width: float) -> list[SettingsColumn]:
    if not self._uses_two_columns(width):
      return []
    return [SettingsColumn("left", self._left_container_h, lambda rect: self._draw_volume_column(rect.y, rect.x, rect.width)),
            SettingsColumn("right", self._tiles_container_h, lambda rect: self._draw_utility_column(rect.y, rect.x, rect.width))]

  def _draw_header(self, rect: rl.Rectangle):
    pass

  def _draw_scroll_content(self, rect: rl.Rectangle, content_width: float):
    y = rect.y + self._scroll_offset
    col_width = self._column_width(content_width)

    self._draw_volume_column(y, rect.x, col_width)
    if self._uses_two_columns(content_width):
      self._draw_utility_column(y, rect.x + col_width + SECTION_GAP, col_width)
    else:
      self._draw_utility_column(y + self._left_container_h + SECTION_GAP, rect.x, col_width)

  def _draw_volume_column(self, y: float, x: float, width: float):
    all_keys = self._controller.VOLUME_KEYS + [self._controller.COOLDOWN_KEY]

    body = draw_settings_group(rl.Rectangle(x, y, width, self._left_container_h), tr("Volumes"), style=PANEL_STYLE)
    current_y = body.y
    for index, key in enumerate(all_keys):
      adjustor = self._adjustor_rows[key]
      row_h = adjustor.measure_height(width)
      row_rect = rl.Rectangle(x, current_y, width, row_h)
      adjustor.set_is_last(index == len(all_keys) - 1)
      self._bind_scroll_widget(adjustor)
      adjustor.render(row_rect)
      current_y += row_h

  def _draw_utility_column(self, y: float, x: float, width: float):
    body = draw_settings_group(rl.Rectangle(x, y, width, self._tiles_container_h), tr("Alerts"), style=PANEL_STYLE, kind="tiles")
    self._render_scroll_grid(self._toggle_grid, body)


class StarPilotSoundsLayout(_SettingsPage):
  COOLDOWN_KEY = "SwitchbackModeCooldown"
  VOLUME_KEYS = [
    "WarningImmediateVolume",
    "WarningSoftVolume",
    "RefuseVolume",
    "PromptDistractedVolume",
    "EngageVolume",
    "DisengageVolume",
    "PromptVolume",
    "BelowSteerSpeedVolume",
  ]
  CUSTOM_ALERTS_KEYS = [
    "GreenLightAlert",
    "LeadDepartingAlert",
    "LoudBlindspotAlert",
    "LoudBlindspotAlertWhenDisengaged",
    "SpeedLimitChangedAlert",
  ]

  COOLDOWN_INFO = {
    "title": tr_noop("Switchback Cooldown"),
    "subtitle": "",
    "min": 0,
    "max": 30,
  }
  VOLUME_INFO = {
    "WarningImmediateVolume": {"title": tr_noop("Immediate Warning"), "subtitle": "", "min": 25},
    "WarningSoftVolume": {"title": tr_noop("Soft Warning"), "subtitle": "", "min": 25},
    "RefuseVolume": {"title": tr_noop("Engagement Refused"), "subtitle": "", "min": 0},
    "PromptDistractedVolume": {"title": tr_noop("Distracted Driver"), "subtitle": "", "min": 0},
    "EngageVolume": {"title": tr_noop("Engagement Chime"), "subtitle": "", "min": 0},
    "DisengageVolume": {"title": tr_noop("Disengagement Alert"), "subtitle": "", "min": 0},
    "PromptVolume": {"title": tr_noop("General Prompt"), "subtitle": "", "min": 0},
    "BelowSteerSpeedVolume": {"title": tr_noop("Low Speed Alert"), "subtitle": "", "min": 0},
  }

  _sound_player_process = None

  def __init__(self):
    super().__init__()
    self._init_sound_player()

    self.ALERT_INFO = {
      "GreenLightAlert": {
        "title": tr_noop("Green Light"),
        "subtitle": "",
      },
      "LeadDepartingAlert": {
        "title": tr_noop("Lead Departure"),
        "subtitle": "",
      },
      "LoudBlindspotAlert": {
        "title": tr_noop("Loud Blindspot"),
        "subtitle": "",
        "is_enabled": lambda: starpilot_state.car_state.hasBSM,
        "disabled_label": tr_noop("Needs BSM")
      },
      "LoudBlindspotAlertWhenDisengaged": {
        "title": tr_noop("Loud While Paused"),
        "subtitle": "",
        "is_enabled": lambda: starpilot_state.car_state.hasBSM,
        "disabled_label": tr_noop("Needs BSM")
      },
      "SpeedLimitChangedAlert": {
        "title": tr_noop("Speed Limit"),
        "subtitle": "",
        "is_enabled": lambda: self._params.get_bool("ShowSpeedLimits") or (
          starpilot_state.car_state.hasOpenpilotLongitudinal and self._params.get_bool("SpeedLimitController")
        ),
        "disabled_label": tr_noop("Needs Speed Limits")
      },
    }

    self._manager_view = SoundsManagerView(self)

  def _restore_defaults(self):
    for key in self.VOLUME_KEYS:
      self._params.put_int(key, 101)
    self._params.put_int(self.COOLDOWN_KEY, 0)
    for key in self.CUSTOM_ALERTS_KEYS:
      self._params.put_bool(key, False)

  @classmethod
  def _init_sound_player(cls):
    if cls._sound_player_process is not None and cls._sound_player_process.poll() is None: return
    program = """
import numpy as np
import sounddevice as sd
import sys
import wave
while True:
  try:
    line = sys.stdin.readline()
    if not line: break
    path, volume = line.strip().split('|')
    with wave.open(path, 'rb') as sound_file:
      audio = np.frombuffer(sound_file.readframes(sound_file.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
      sd.play(audio * float(volume), sound_file.getframerate())
    sd.wait()
  except Exception:
    sd._terminate()
    sd._initialize()
"""
    cls._sound_player_process = subprocess.Popen(["python3", "-u", "-c", program], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

  def _test_sound(self, key: str):
    base_name = key.replace("Volume", "")
    if ui_state.started:
      alert_name = "belowSteerSpeed" if base_name == "BelowSteerSpeed" else base_name[0].lower() + base_name[1:]
      self._params_memory.put("TestAlert", alert_name)
    else:
      self._play_sound_offroad(key)

  def _play_sound_offroad(self, key: str):
    base_name = key.replace("Volume", "")
    preview_base_name = "Prompt" if base_name == "BelowSteerSpeed" else base_name
    snake_case = "".join(["_" + c.lower() if c.isupper() else c for c in preview_base_name]).lstrip("_")
    stock_path = Path(BASEDIR) / "selfdrive" / "assets" / "sounds" / f"{snake_case}.wav"
    theme_path = ACTIVE_THEME_PATH / "sounds" / f"{snake_case}.wav"
    sound_path = theme_path if theme_path.exists() else stock_path
    if not sound_path.exists(): return
    volume = self._params.get_int(key, return_default=True, default=100) / 100.0
    if self._sound_player_process.poll() is not None:
      self._sound_player_process = None
      self._init_sound_player()
    try:
      self._sound_player_process.stdin.write(f"{sound_path}|{volume}\n".encode())
      self._sound_player_process.stdin.flush()
    except (BrokenPipeError, OSError): pass
