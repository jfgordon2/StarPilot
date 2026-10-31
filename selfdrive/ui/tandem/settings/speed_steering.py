"""Speed & Steering: the everyday driving choices, each one setting several StarPilot params together."""
from __future__ import annotations

from openpilot.starpilot.common.accel_profile import ACCELERATION_PROFILES as ACCEL, DECELERATION_PROFILES as DECEL
from openpilot.selfdrive.ui.tandem import tokens as T
from openpilot.selfdrive.ui.tandem.controls import Button, ChoiceCards, Segmented, Stepper, Switch
from openpilot.selfdrive.ui.tandem.rows import ListPanel, Padded, SectionHeader, SettingRow
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
SMART_SLOWDOWN_TRIGGERS = ["CECurves", "CEStopLights", "CELead", "CESlowerLead", "CEStoppedLead"]
OFFSET_MAX = 15


class SpeedSteering:
  """Reads and writes the grouped settings; the screen and the hub tile both use it."""

  def __init__(self, store: SettingsStore):
    self._store = store

  @property
  def safe_mode(self) -> bool:
    return self._store.get_bool("SafeMode")

  @property
  def style(self) -> int:
    personality = self._store.get_int("LongitudinalPersonality")
    return next((i for i, (p, _, _) in enumerate(STYLE_PARAMS) if p == personality), 1)

  def set_style(self, index: int) -> None:
    personality, accel, decel = STYLE_PARAMS[index]
    self._store.write({"LongitudinalPersonality": personality, "AccelerationProfile": accel, "DecelerationProfile": decel})

  @property
  def speed_limits(self) -> int:
    if self._store.get_bool("SpeedLimitController"):
      return 2
    return 1 if self._store.get_bool("ShowSpeedLimits") else 0

  def set_speed_limits(self, index: int) -> None:
    """Match runs the speed limit controller, and also sets cruise to the limit when engaging."""
    match = index == 2
    self._store.write({"ShowSpeedLimits": index > 0, "SpeedLimitController": match, "SetSpeedLimit": match})

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
    self._store.write({"LaneChanges": True, "NudgelessLaneChange": index == 1})

  @property
  def smart_slowdowns(self) -> bool:
    return self._store.get_bool("ConditionalExperimental") and self._store.get_bool("CurveSpeedController")

  def set_smart_slowdowns(self, on: bool) -> None:
    """Switches to experimental mode for curves, lights and slower or stopped cars, and slows for curves ahead."""
    values: dict[str, bool | int | float] = {"ConditionalExperimental": on, "CurveSpeedController": on}
    if on:
      values |= {"ConditionalChill": False} | dict.fromkeys(SMART_SLOWDOWN_TRIGGERS, True)
    self._store.write(values)

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
  style = SettingRow("Driving Style", lambda: "Relaxed while Safe Mode is on" if model.safe_mode else
                     "Sets following gap, acceleration and braking together", Segmented(STYLES, lambda: model.style, model.set_style))
  style.set_enabled(lambda: not model.safe_mode)
  offset = SettingRow("Offset", "Added to every matched limit", indent=True,
                      control=Stepper(lambda: model.offset, model.set_offset, 0, OFFSET_MAX,
                                      fmt=lambda v: f"+{v:g} {model.unit}", value_width=T.px(104)))
  higher = SettingRow("Higher limits", "Lower limits always apply on their own", indent=True,
                      control=Segmented(HIGHER_LIMITS, lambda: model.higher_limits, model.set_higher_limits,
                                        height=T.px(36), font_size=T.font_px(15)))
  for row in (offset, higher):
    row.set_visible(lambda: model.matching)

  return ListPanel([
    style,
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


# ── Vehicle Profile ──

PROFILES = [("Car", "Standard tuning for most cars and SUVs"), ("EV", "Smoother take-off and regen-aware braking"),
            ("Truck", "Gentler acceleration for heavier vehicles"), ("Towing", "Truck tuning plus room for a trailer")]
TRAILER_LOADS = ["Light", "Medium", "Heavy"]
TRAILER_POUNDS = [2000, 5000, 8000]   # StarPilot's TrailerLoad is in pounds


class VehicleProfile:
  def __init__(self, store: SettingsStore):
    self._store = store

  @property
  def profile(self) -> int:
    if self._store.get_bool("TruckTuning"):
      return 3 if self._store.get_int("TrailerLoad") > 0 else 2
    return 1 if self._store.get_bool("EVTuning") else 0

  def set_profile(self, index: int) -> None:
    load = TRAILER_POUNDS[self.trailer_load] if index == 3 else 0
    self._store.write({"EVTuning": index == 1, "TruckTuning": index >= 2, "TrailerLoad": load})

  @property
  def towing(self) -> bool:
    return self.profile == 3

  @property
  def trailer_load(self) -> int:
    """Nearest preset to the stored weight; Medium when nothing is set."""
    pounds = self._store.get_int("TrailerLoad") or TRAILER_POUNDS[1]
    return min(range(len(TRAILER_POUNDS)), key=lambda i: abs(TRAILER_POUNDS[i] - pounds))

  def set_trailer_load(self, index: int) -> None:
    self._store.write({"TrailerLoad": TRAILER_POUNDS[index]})

  def summary(self) -> str:
    return PROFILES[self.profile][0]


def vehicle_profile_panel(model: VehicleProfile) -> ListPanel:
  load = SettingRow("Trailer Load", lambda: "Weight of a loaded trailer" if model.towing else "Available with Towing",
                    Segmented(TRAILER_LOADS, lambda: model.trailer_load, model.set_trailer_load))
  load.set_enabled(lambda: model.towing)
  return ListPanel([
    Padded(ChoiceCards(PROFILES, lambda: model.profile, model.set_profile)),
    load,
  ], title="Vehicle Profile", subtitle="Adjusts acceleration and braking for what you drive")


# ── Weather ──

WEATHER = ["Auto", "Off"]
# Condition -> (param suffix, extra following seconds, % less acceleration, % less curve speed). Placeholders to tune on real drives.
WEATHER_PRESETS = [
  ("LowVisibility", 0.5, 0, 0),
  ("Rain", 0.5, 10, 10),
  ("RainStorm", 1.0, 20, 20),
  ("Snow", 1.5, 30, 25),
]


class Weather:
  def __init__(self, store: SettingsStore):
    self._store = store

  @property
  def mode(self) -> int:
    return 0 if self._store.get_bool("WeatherPresets") else 1

  def set_mode(self, index: int) -> None:
    values: dict = {"WeatherPresets": index == 0}
    if index == 0:
      for suffix, following, accel, lateral in WEATHER_PRESETS:
        values |= {f"IncreaseFollowing{suffix}": following, f"ReduceAcceleration{suffix}": accel,
                   f"ReduceLateralAcceleration{suffix}": lateral}
    self._store.write(values)

  def summary(self) -> str:
    return WEATHER[self.mode]


def weather_panel(model: Weather) -> ListPanel:
  conditions = [("Fog or low visibility", "Longer following gap"), ("Rain", "Longer gap, earlier braking"),
                ("Heavy rain or storms", "More gap, softer acceleration"), ("Snow or ice", "Most gap, gentlest starts and stops")]
  rows = [SettingRow(title, subtitle) for title, subtitle in conditions]
  for row in rows:
    row.set_enabled(lambda: model.mode == 0)
  return ListPanel([SectionHeader("WHAT CHANGES"), *rows], title="Weather",
                   subtitle="Drives more cautiously in bad conditions, using local weather",
                   header_control=Segmented(WEATHER, lambda: model.mode, model.set_mode),
                   footnote="Needs an internet connection. The status chip shows when it's active.")


# ── Assistance: openpilot's own switches ──

class Assistance:
  def __init__(self, store: SettingsStore, live):
    self._store = store
    self._live = live

  def get(self, key: str) -> bool:
    return self._store.get_bool(key)

  def setter(self, key: str):
    return lambda on: self._store.write({key: on})

  def set_safe_mode(self, on: bool) -> None:
    """Safe Mode turns off experimental mode and drives Relaxed, as upstream's toggle screen does."""
    values: dict = {"SafeMode": on}
    if on:
      values |= {"ExperimentalMode": False, "LongitudinalPersonality": STYLE_PARAMS[0][0]}
    self._store.write(values)

  def parked_or_disengaged(self) -> bool:
    return not self._live.engaged()


def assistance_panel(model: Assistance) -> ListPanel:
  def switch(title: str, subtitle: str, key: str, on_change=None, restarts: bool = False) -> SettingRow:
    row = SettingRow(title, subtitle + (" Restarts openpilot if the car is on." if restarts else ""),
                     Switch(lambda: model.get(key), on_change or model.setter(key)))
    if restarts:
      row.set_enabled(model.parked_or_disengaged)
    return row

  return ListPanel([
    switch("openpilot", "Adaptive cruise and lane keeping. Your attention is required at all times.", "OpenpilotEnabledToggle",
           restarts=True),
    switch("Disengage on Gas Pedal", "Pressing the accelerator turns openpilot off", "DisengageOnAccelerator"),
    switch("Lane Departure Warnings", "Alerts when you drift over a lane line without signaling, above 31 mph (50 km/h)", "IsLdwEnabled"),
    switch("Always-On Driver Monitoring", "Watches for distraction even when openpilot is off", "AlwaysOnDM"),
    switch("Safe Mode", "Uses stock tuning, the default model and Relaxed until turned off.", "SafeMode", model.set_safe_mode,
           restarts=True),
  ], title="Assistance", subtitle="openpilot's core switches")


# ── Navigation ──

class Navigation:
  """Home, Work and favorites are StarPilot's FavoriteDestinations; picking a place uses its destination search."""

  def __init__(self, store: SettingsStore):
    self._store = store

  def _favorites(self) -> list[dict]:
    value = self._store.get_json("FavoriteDestinations")
    return value if isinstance(value, list) else []

  def _place(self, flag: str) -> str | None:
    place = next((f for f in self._favorites() if f.get(flag)), None)
    return str(place.get("name") or "Saved place") if place else None

  def home(self) -> str | None:
    return self._place("is_home")

  def work(self) -> str | None:
    return self._place("is_work")

  def others(self) -> int:
    return sum(1 for f in self._favorites() if not f.get("is_home") and not f.get("is_work"))

  @property
  def end_when_parked(self) -> bool:
    return self._store.get_bool("ClearNavOnOffroad")

  def set_end_when_parked(self, on: bool) -> None:
    self._store.write({"ClearNavOnOffroad": on})


def navigation_panel(model: Navigation, open_destinations, open_offline_maps) -> ListPanel:
  def place(title: str, get) -> SettingRow:
    return SettingRow(title, lambda: get() or "Not set", Button(lambda: "Change" if get() else "Set", open_destinations))

  return ListPanel([
    place("Home", model.home),
    place("Work", model.work),
    SettingRow("Other favorites", lambda: f"{model.others()} saved", on_click=open_destinations),
    SettingRow("End Route When Parked", "Clears the destination when you turn off the car",
               Switch(lambda: model.end_when_parked, model.set_end_when_parked)),
    SettingRow("Offline Maps", "Speed limits and routing without a connection", on_click=open_offline_maps),
  ], title="Navigation", subtitle="While a route is active, the car slows for turns and uses route speed limits")
