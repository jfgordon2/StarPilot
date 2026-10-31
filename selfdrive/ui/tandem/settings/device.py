"""This Device: pairing, cameras, the training guide, and power.

The actions are upstream's: UpstreamDevice calls DeviceLayout's own handlers, so calibration reset and power off
keep upstream's checks and dialogs. Pairing opens our page (design/pairing.html) around upstream's QR code, which
carries the same comma connect pairing token.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

import pyray as rl

from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.base import Component
from openpilot.selfdrive.ui.tandem.blocks import Card, Columns, Label
from openpilot.selfdrive.ui.tandem.controls import Button, ButtonRow, ButtonStyle
from openpilot.selfdrive.ui.tandem.layout import Align, place
from openpilot.selfdrive.ui.tandem.rows import ListPanel, SectionHeader, SettingRow


class Calibration:
  CALIBRATED = "Calibrated"
  CALIBRATING = "Calibrating"
  UNKNOWN = "Not calibrated yet"


class Device(Protocol):
  """What the screen needs to know and do. UpstreamDevice is the real one."""

  def is_paired(self) -> bool: ...
  def is_offroad(self) -> bool: ...
  def calibration(self) -> str: ...
  def remote_access_label(self) -> str: ...
  def ids(self) -> str: ...
  def show_regulatory(self) -> bool: ...
  def refresh(self) -> None: ...
  def pair(self) -> None: ...
  def pairing_qr(self) -> rl.Texture | None: ...   # the comma connect pairing code, refreshed every 5 minutes
  def driver_camera(self) -> None: ...
  def recalibrate(self) -> None: ...
  def review_guide(self) -> None: ...
  def remote_access(self) -> None: ...
  def reset_driver_monitoring(self) -> None: ...
  def change_language(self) -> None: ...
  def regulatory(self) -> None: ...
  def restart(self) -> None: ...
  def power_off(self) -> None: ...


class ThisDevicePanel(ListPanel):
  def __init__(self, device: Device, open_pairing: Callable[[], None] | None = None):
    """open_pairing shows the pairing page; without it, Pair falls back to upstream's dialog."""
    self._device = device

    def action(label: str, on_click, style: ButtonStyle = ButtonStyle.SECONDARY, offroad_only: bool = False) -> Button:
      button = Button(label, on_click, style)
      if offroad_only:
        button.set_enabled(device.is_offroad)
      return button

    pair = action("Pair", open_pairing or device.pair, ButtonStyle.PRIMARY)
    pair.set_visible(lambda: not device.is_paired())
    power_off = Button("Power Off", device.power_off, ButtonStyle.DANGER_SOFT, height=T.px(52))
    power_off.set_visible(device.is_offroad)

    super().__init__([
      SettingRow("Phone App", lambda: "Paired" if device.is_paired() else "Change settings and see drives from your phone", pair,
                 subtitle_color=lambda: T.SUCCESS_TEXT if device.is_paired() else T.TEXT_TERTIARY),
      SettingRow("Driver Camera", "Check that it can see your face. The car must be off.",
                 action("Preview", device.driver_camera, offroad_only=True)),
      SettingRow("Camera Calibration", device.calibration, action("Recalibrate", device.recalibrate),
                 subtitle_color=lambda: T.SUCCESS_TEXT if device.calibration() == Calibration.CALIBRATED else T.TEXT_TERTIARY),
      SettingRow("How It Works", "Rules, features and limits", action("Review", device.review_guide, offroad_only=True)),
      SectionHeader("MORE"),
      SettingRow("Remote Access", "Reach this device from the Galaxy web app",
                 Button(device.remote_access_label, device.remote_access)),
      SettingRow("Driver Monitoring", "Forget which side of the car the driver sits on",
                 action("Reset", device.reset_driver_monitoring, offroad_only=True)),
      SettingRow("Language", None, action("Change", device.change_language)),
      regulatory := SettingRow("Regulatory", None, action("View", device.regulatory, offroad_only=True)),
      SettingRow("Device ID and Serial", device.ids),
    ], title="This Device", footer=ButtonRow([Button("Restart", device.restart, height=T.px(52), weight=T.FONT_BOLD), power_off]))
    regulatory.set_visible(device.show_regulatory)

  def show_event(self):
    super().show_event()
    self._device.refresh()


PAIRING_STEPS = [
  ("Open connect.comma.ai", "Bookmark it to your home screen to use it like an app"),
  ("Tap Add new device", "Sign in first if it asks"),
  ("Scan the code", "The Phone App row shows Paired when it's done"),
]


class PairingSteps(Component):
  """Numbered steps: a blue number in a round well, a title and a line."""
  grow_touch_target = False
  ROW = T.px(46)   # a title and a line

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    return max_width, len(PAIRING_STEPS) * self.ROW + (len(PAIRING_STEPS) - 1) * T.px(22)

  def _render(self, rect: rl.Rectangle):
    y = rect.y
    for i, (title, line) in enumerate(PAIRING_STEPS):
      well = rl.Rectangle(rect.x, y, T.px(40), T.px(40))
      draw.fill(well, T.ACCENT_SURFACE, well.width / 2)
      draw.text(well, str(i + 1), T.font_px(19), T.ACCENT_TEXT, T.FONT_EXTRABOLD, Align.CENTER)
      x = rect.x + T.px(56)
      title_h, line_h = draw.line_height(T.font_px(20)), draw.line_height(T.font_px(15))
      draw.text(rl.Rectangle(x, y, rect.width - T.px(56), title_h), title, T.font_px(20), T.TEXT, T.FONT_BOLD)
      draw.text(rl.Rectangle(x, y + title_h + T.px(3), rect.width - T.px(56), line_h), line, T.font_px(15), T.TEXT_TERTIARY)
      y += self.ROW + T.px(22)


class PairingCode(Component):
  """The QR code on a white tile, so it scans in any theme, with a line under it; centered in its card."""
  grow_touch_target = False
  TILE, PAD = T.px(268), T.px(16)

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    return max_width, self.TILE + T.px(14) + draw.line_height(T.font_px(14))

  def __init__(self, device: Device):
    super().__init__()
    self._device = device

  def _render(self, rect: rl.Rectangle):
    line_h = draw.line_height(T.font_px(14))
    group = place(rect, self.TILE, self.TILE + T.px(14) + line_h)
    tile = rl.Rectangle(group.x, group.y, self.TILE, self.TILE)
    draw.fill(tile, rl.WHITE, T.px(18))
    code = self._device.pairing_qr()
    inner = rl.Rectangle(tile.x + self.PAD, tile.y + self.PAD, tile.width - self.PAD * 2, tile.height - self.PAD * 2)
    if code is not None and code.id != 0:
      rl.draw_texture_pro(code, rl.Rectangle(0, 0, code.width, code.height), inner, rl.Vector2(0, 0), 0, rl.WHITE)
    else:
      draw.text(inner, "Getting a code…", T.font_px(16), T.TEXT_MUTED, T.FONT_SEMIBOLD, Align.CENTER)
    below = rl.Rectangle(group.x - T.px(40), tile.y + tile.height + T.px(14), self.TILE + T.px(80), line_h)
    if self._device.is_paired():
      draw.text(below, "Paired", T.font_px(14), T.SUCCESS_TEXT, T.FONT_BOLD, Align.CENTER)
    else:
      draw.text(below, "A new code every 5 minutes", T.font_px(14), T.TEXT_MUTED, T.FONT, Align.CENTER)


def pairing_page(device: Device):
  """Pair the phone app: the steps on the left, the code on the right (design/pairing.html)."""
  from openpilot.selfdrive.ui.tandem.settings.pages import TitledPage
  steps = Card([Label("ON YOUR PHONE", color=T.ACCENT_TEXT, caption=True), PairingSteps()], gap=T.px(22))
  code = Card([PairingCode(device)], padding=(T.px(22), T.px(20)), grow=0)
  return TitledPage("Pair the phone app", "Change settings and see drives from your phone", Columns([steps, code], [1.25, 1]))


class UpstreamDevice:
  """Device backed by upstream's DeviceLayout and ui_state. Imported only on the device."""

  def __init__(self):
    from openpilot.selfdrive.ui.layouts.settings.device import DeviceLayout
    from openpilot.selfdrive.ui.ui_state import ui_state
    from openpilot.system.hardware import TICI
    self._layout = DeviceLayout()
    self._ui_state = ui_state
    self._params = ui_state.ui_params
    self._tici = TICI
    self._calibration = Calibration.UNKNOWN
    self._ids = ""
    self._pairing = None   # upstream PairingDialog, made on first use
    self.refresh()

  def refresh(self) -> None:
    """Calibration and IDs change rarely, so they're read when the screen opens, not every frame."""
    self._calibration = self._read_calibration()
    dongle = self._params.get("DongleId") or "N/A"
    serial = self._params.get("HardwareSerial") or "N/A"
    self._ids = f"{dongle} · {serial}"

  def _read_calibration(self) -> str:
    from cereal import log, messaging
    data = self._params.get("CalibrationParams")
    if not data:
      return Calibration.UNKNOWN
    try:
      status = messaging.log_from_bytes(data, log.Event).liveCalibration.calStatus
    except Exception:
      return Calibration.UNKNOWN
    if status == log.LiveCalibrationData.Status.calibrated:
      return Calibration.CALIBRATED
    return Calibration.UNKNOWN if status == log.LiveCalibrationData.Status.uncalibrated else Calibration.CALIBRATING

  def is_paired(self) -> bool:
    return self._ui_state.prime_state.is_paired()

  def is_offroad(self) -> bool:
    return self._ui_state.is_offroad()

  def calibration(self) -> str:
    return self._calibration

  def remote_access_label(self) -> str:
    return "Manage" if self._layout._is_galaxy_paired() else "Set Up"

  def ids(self) -> str:
    return self._ids

  def show_regulatory(self) -> bool:
    return self._tici

  def pair(self) -> None:
    self._layout._pair_device()

  def pairing_qr(self) -> rl.Texture | None:
    """Upstream's pairing dialog makes the code (its token request and 5-minute refresh); we only draw it."""
    if self._pairing is None:
      from openpilot.selfdrive.ui.widgets.pairing_dialog import PairingDialog
      self._pairing = PairingDialog()
    self._pairing._check_qr_refresh()
    return self._pairing.qr_texture

  def driver_camera(self) -> None:
    self._layout._show_driver_camera()

  def recalibrate(self) -> None:
    self._layout._reset_calibration_prompt()

  def review_guide(self) -> None:
    self._layout._on_review_training_guide()

  def remote_access(self) -> None:
    self._layout._pair_galaxy()

  def reset_driver_monitoring(self) -> None:
    self._layout._reset_driver_monitoring_prompt()

  def change_language(self) -> None:
    self._layout._show_language_dialog()

  def regulatory(self) -> None:
    self._layout._on_regulatory()

  def restart(self) -> None:
    self._layout._reboot_prompt()

  def power_off(self) -> None:
    self._layout._power_off_prompt()
