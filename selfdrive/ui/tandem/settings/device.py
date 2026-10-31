"""This Device: pairing, cameras, the training guide, and power.

The actions are upstream's: UpstreamDevice calls DeviceLayout's own handlers, so pairing, calibration
reset and power off keep upstream's checks and dialogs.
"""
from __future__ import annotations

from typing import Protocol

from openpilot.selfdrive.ui.tandem import tokens as T
from openpilot.selfdrive.ui.tandem.controls import Button, ButtonRow, ButtonStyle
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
  def __init__(self, device: Device):
    self._device = device

    def action(label: str, on_click, style: ButtonStyle = ButtonStyle.SECONDARY, offroad_only: bool = False) -> Button:
      button = Button(label, on_click, style)
      if offroad_only:
        button.set_enabled(device.is_offroad)
      return button

    pair = action("Pair", device.pair, ButtonStyle.PRIMARY)
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
    ], title="This Device", footer=ButtonRow([Button("Restart", device.restart, height=T.px(52)), power_off]))
    regulatory.set_visible(device.show_regulatory)

  def show_event(self):
    super().show_event()
    self._device.refresh()


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
