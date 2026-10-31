"""Speed & Steering: the everyday driving choices, each one setting several StarPilot params together."""
from __future__ import annotations

from openpilot.starpilot.common.accel_profile import ACCELERATION_PROFILES as ACCEL, DECELERATION_PROFILES as DECEL
from openpilot.selfdrive.ui.tandem import tokens as T
from openpilot.selfdrive.ui.tandem.controls import Segmented, Stepper, Switch
from openpilot.selfdrive.ui.tandem.rows import ListPanel, SettingRow
from openpilot.selfdrive.ui.tandem.settings.store import SettingsStore

STYLES = ["Relaxed", "Standard", "Sport"]
SPEED_LIMITS = ["Off", "Show", "Match"]
HIGHER_LIMITS = ["Update automatically", "Tap to confirm"]
LANE_CHANGES = ["Nudge", "Auto"]

# Driving Style -> (LongitudinalPersonality, AccelerationProfile, DecelerationProfile). Standard is StarPilot's default.
STYLE_PARAMS = [
  (2, ACCEL["ECO"], DECEL["ECO"]),
  (1, ACCEL["STANDARD"], DECEL["ECO"]),
  (0, ACCEL["SPORT"], DECEL["SPORT"]),
]
OFFSET_KEYS = [f"Offset{i}" for i in range(1, 8)]
OFFSET_MAX = 15


class SpeedSteering:
  """Reads and writes the grouped settings; the screen and the hub tile both use it."""

  def __init__(self, store: SettingsStore):
    self._store = store

  @property
  def style(self) -> int:
    personality = self._store.get_int("LongitudinalPersonality")
    return next((i for i, (p, _, _) in enumerate(STYLE_PARAMS) if p == personality), 1)

  def set_style(self, index: int) -> None:
    personality, accel, decel = STYLE_PARAMS[index]
    self._store.write({"LongitudinalPersonality": personality, "AccelerationProfile": accel, "DecelerationProfile": decel})

  @property
  def speed_limits(self) -> int:
    if self._store.get_bool("SetSpeedLimit"):
      return 2
    return 1 if self._store.get_bool("ShowSpeedLimits") else 0

  def set_speed_limits(self, index: int) -> None:
    self._store.write({"ShowSpeedLimits": index > 0, "SetSpeedLimit": index == 2})

  @property
  def matching(self) -> bool:
    return self.speed_limits == 2

  @property
  def offset(self) -> float:
    return self._store.get_float(OFFSET_KEYS[0])

  def set_offset(self, value: float) -> None:
    """One offset for every speed range, so a matched limit is always the sign plus the same amount."""
    self._store.write({key: float(value) for key in OFFSET_KEYS})

  @property
  def unit(self) -> str:
    return "km/h" if self._store.get_bool("IsMetric") else "mph"

  @property
  def lane_change_speed(self) -> int:
    return round(self._store.get_float("MinimumLaneChangeSpeed"))

  @property
  def higher_limits(self) -> int:
    return 1 if self._store.get_bool("SLCConfirmation") else 0

  def set_higher_limits(self, index: int) -> None:
    confirm = index == 1
    values: dict[str, bool | int | float] = {"SLCConfirmation": confirm}
    if confirm:
      values |= {"SLCConfirmationHigher": True, "SLCConfirmationLower": False}
    self._store.write(values)

  @property
  def lane_changes(self) -> int:
    return 1 if self._store.get_bool("NudgelessLaneChange") else 0

  def set_lane_changes(self, index: int) -> None:
    self._store.write({"NudgelessLaneChange": index == 1})

  @property
  def smart_slowdowns(self) -> bool:
    return self._store.get_bool("ConditionalExperimental") and self._store.get_bool("CurveSpeedController")

  def set_smart_slowdowns(self, on: bool) -> None:
    self._store.write({"ConditionalExperimental": on, "CurveSpeedController": on})

  @property
  def always_on_steering(self) -> bool:
    return self._store.get_bool("AlwaysOnLateral")

  def set_always_on_steering(self, on: bool) -> None:
    self._store.write({"AlwaysOnLateral": on})

  def summary(self) -> str:
    lanes = "Auto lane change" if self.lane_changes else "Nudge to change lanes"
    return f"{STYLES[self.style]} · {lanes}"

  def speed_limit_summary(self) -> str:
    return ["Speed limits off", "Showing speed limits", "Matching speed limits"][self.speed_limits]


def everyday_panel(model: SpeedSteering) -> ListPanel:
  offset = SettingRow("Offset", "Added to every matched limit", indent=True,
                      control=Stepper(lambda: model.offset, model.set_offset, 0, OFFSET_MAX,
                                      fmt=lambda v: f"+{v:g} {model.unit}", value_width=T.px(104)))
  higher = SettingRow("Higher limits", "Lower limits always apply on their own", indent=True,
                      control=Segmented(HIGHER_LIMITS, lambda: model.higher_limits, model.set_higher_limits,
                                        height=T.px(36), font_size=T.font_px(15)))
  for row in (offset, higher):
    row.set_visible(lambda: model.matching)

  return ListPanel([
    SettingRow("Driving Style", "Sets following gap, acceleration and braking together",
               Segmented(STYLES, lambda: model.style, model.set_style)),
    SettingRow("Speed Limits", "Match sets cruise to the posted limit",
               Segmented(SPEED_LIMITS, lambda: model.speed_limits, model.set_speed_limits)),
    offset,
    higher,
    SettingRow("Lane Changes", lambda: f"Auto starts one change per signal, above {model.lane_change_speed} {model.unit}",
               Segmented(LANE_CHANGES, lambda: model.lane_changes, model.set_lane_changes)),
    SettingRow("Smart Slowdowns", "Slows for curves, stop lights and stopped traffic on its own",
               Switch(lambda: model.smart_slowdowns, model.set_smart_slowdowns)),
    SettingRow("Always-On Steering", "Keeps steering with cruise off. Pauses while you brake.",
               Switch(lambda: model.always_on_steering, model.set_always_on_steering)),
  ], title="Everyday")
