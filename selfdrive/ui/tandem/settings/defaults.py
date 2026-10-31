"""The Essentials defaults: what Reset Settings restores. Each line uses the same control a driver would."""
from __future__ import annotations

from openpilot.selfdrive.ui.tandem.settings.alerts import Alerts
from openpilot.selfdrive.ui.tandem.settings.bundles import BUNDLES
from openpilot.selfdrive.ui.tandem.settings.display import Display
from openpilot.selfdrive.ui.tandem.settings.speed_steering import SpeedSteering, Weather
from openpilot.selfdrive.ui.tandem.settings.store import SettingsStore
from openpilot.selfdrive.ui.tandem.settings.tuner import Tuner

SPEED_LIMIT_OFFSET = 3


def apply_essentials(store: SettingsStore) -> None:
  """Vehicle choices (profile, car, buttons) and device choices (units, Wi-Fi, pairing) are left alone."""
  with store.batch():
    _apply(store)


def _apply(store: SettingsStore) -> None:
  speed = SpeedSteering(store)
  speed.set_style(1)                      # Standard
  speed.set_speed_limits(2)               # Match
  speed.set_offset(SPEED_LIMIT_OFFSET)
  speed.set_higher_limits(1)              # Tap to confirm
  speed.set_lane_changes(1)               # Auto
  speed.set_smart_slowdowns(True)
  speed.set_always_on_steering(True)
  Weather(store).set_mode(0)              # Auto

  display = Display(store)
  display.set_path_style(0)               # Standard
  display.set_clean_screen(True)
  display.set_blind_spot(True)
  display.set_signal(1)                   # Sequential
  display.set_camera_view(1)              # Standard

  alerts = Alerts(store)
  alerts.set_preset(0)                    # Auto
  for key, on in (("GreenLightAlert", True), ("LeadDepartingAlert", True), ("SpeedLimitChangedAlert", False),
                  ("LoudBlindspotAlert", False)):
    alerts.set_chime(key, on)

  for bundle in BUNDLES:
    bundle.set(store, False)
  Tuner(store).reset_all()
  store.write({"HolidayThemes": False})   # this redesign has no holiday themes
