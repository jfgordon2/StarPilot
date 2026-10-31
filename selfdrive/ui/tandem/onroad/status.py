"""What the car is doing on its own, read from the driving messages, and which status chip explains it.

Snapshot holds plain values, so the chip rules can be tested without cereal. snapshot() fills one from ui_state.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ChipTone(Enum):
  INFO = "info"         # blue: the car is changing speed or steering on its own
  PAUSED = "paused"     # amber: steering paused or a change blocked
  WAITING = "waiting"   # green: waiting on the driver


@dataclass(frozen=True)
class Chip:
  key: str
  label: str
  tone: ChipTone
  icon: str


@dataclass
class Snapshot:
  engaged: bool = False
  standstill: bool = False
  speed: float = 0.0                       # m/s
  metric: bool = False
  lateral_paused: bool = False
  pause_lateral_speed: float = 0.0         # display units; 0 when the setting is off
  signal_on: bool = False
  always_on_lateral: bool = False          # steering with cruise off
  lane_change: str = "off"                 # off, pre, starting, finishing
  lane_change_direction: str = "none"      # left, right, none
  blindspot: bool = False                  # on the side of the requested lane change
  curve_control: bool = False
  red_light: bool = False
  stop_sign: bool = False
  slowing_for_lead: bool = False
  nav_turn: bool = False
  limit_changed: bool = False
  speed_limit: float = 0.0                 # display units
  weather: str = ""                        # "Rain", "Snow", "Fog" ... when Weather is acting
  events: set[str] = field(default_factory=set)


def chip_for(s: Snapshot) -> Chip | None:
  """The one chip to show now, highest priority first: paused or blocked, stopping, slowing, then waiting."""
  unit = "km/h" if s.metric else "mph"
  if s.lateral_paused and s.signal_on:
    return Chip("pause_signal", "Steering paused for signal", ChipTone.PAUSED, "signal")
  if s.lateral_paused:
    below = f" · under {s.pause_lateral_speed:.0f} {unit}" if s.pause_lateral_speed else ""
    return Chip("pause_speed", f"Steering paused{below}", ChipTone.PAUSED, "wheel_pause")
  if s.lane_change in ("pre", "starting") and s.blindspot:
    return Chip("lane_blocked", "Lane change blocked", ChipTone.PAUSED, "lane_blocked")
  if s.lane_change in ("starting", "finishing") and s.lane_change_direction in ("left", "right"):
    return Chip("lane_change", f"Changing lanes {s.lane_change_direction}", ChipTone.INFO, f"lane_{s.lane_change_direction}")
  if s.stop_sign:
    return Chip("stop_sign", "Stopping for stop sign", ChipTone.INFO, "stop_sign")
  if s.red_light:
    return Chip("red_light", "Stopping for light", ChipTone.INFO, "light_red")
  if s.curve_control:
    return Chip("curve", "Slowing for curve", ChipTone.INFO, "curve")
  if s.nav_turn:
    return Chip("turn", "Slowing for turn", ChipTone.INFO, "turn")
  if s.slowing_for_lead:
    return Chip("traffic", "Slowing for traffic", ChipTone.INFO, "car")
  if s.limit_changed and s.speed_limit:
    return Chip("limit", f"Matching limit {s.speed_limit:.0f}", ChipTone.INFO, "gauge")
  if s.weather:
    return Chip("weather", f"{s.weather} · longer gap", ChipTone.INFO, "rain")
  if "greenLight" in s.events:
    return Chip("green_light", "Light is green", ChipTone.WAITING, "light_green")
  if "leadDeparting" in s.events:
    return Chip("lead_moved", "Car ahead moved", ChipTone.WAITING, "car_up")
  if s.engaged and s.standstill:
    return Chip("ready", "Ready · tap resume", ChipTone.WAITING, "play")
  if s.always_on_lateral and not s.engaged:
    return Chip("steering_only", "Steering only", ChipTone.INFO, "wheel")
  return None


class ChipPicker:
  """Holds a chip for HOLD seconds after its reason ends, so it doesn't flicker. Hidden while an alert shows."""
  HOLD = 2.0

  def __init__(self):
    self._chip: Chip | None = None
    self._until = 0.0

  def update(self, s: Snapshot, now: float, alert_showing: bool) -> Chip | None:
    chip = chip_for(s)
    if chip is not None:
      self._chip, self._until = chip, now + self.HOLD
    elif now >= self._until:
      self._chip = None
    return None if alert_showing else self._chip


# OpenWeather-style condition ids StarPilot's weather checker publishes, grouped the way Weather presets are.
def weather_name(weather_id: int) -> str:
  if 200 <= weather_id < 300 or 502 <= weather_id <= 531:
    return "Heavy rain"
  if 300 <= weather_id < 600:
    return "Rain"
  if 600 <= weather_id < 700:
    return "Snow"
  if 700 <= weather_id < 800:
    return "Fog"
  return ""


def snapshot(ui_state, nav_active: bool = False) -> Snapshot:
  """Fill a Snapshot from upstream's ui_state. Missing messages leave defaults."""
  sm = ui_state.sm
  valid = sm.valid
  s = Snapshot(engaged=bool(ui_state.engaged), metric=bool(ui_state.is_metric), always_on_lateral=bool(ui_state.always_on_lateral_active))
  speed_conversion = 3.6 if s.metric else 2.236936
  if valid.get("carState", False):
    cs = sm["carState"]
    s.standstill, s.speed = bool(cs.standstill), float(cs.vEgo)
    s.signal_on = bool(cs.leftBlinker or cs.rightBlinker)
    direction_left = cs.leftBlinker
    s.blindspot = bool(cs.leftBlindspot if direction_left else cs.rightBlindspot)
  if valid.get("modelV2", False):
    meta = sm["modelV2"].meta
    s.lane_change = {1: "pre", 2: "starting", 3: "finishing"}.get(int(meta.laneChangeState), "off")
    s.lane_change_direction = {1: "left", 2: "right"}.get(int(meta.laneChangeDirection), "none")
  if valid.get("starpilotCarState", False):
    s.lateral_paused = bool(sm["starpilotCarState"].pauseLateral)
  toggles = ui_state.starpilot_toggles or {}
  s.pause_lateral_speed = float(toggles.get("pause_lateral_below_speed", 0) or 0) * speed_conversion
  if valid.get("starpilotPlan", False):
    plan = sm["starpilotPlan"]
    s.curve_control = bool(plan.cscControllingSpeed)
    s.red_light = bool(plan.redLight or plan.forcingStop)
    s.stop_sign = bool(plan.stopSignConfirmed)
    s.limit_changed = bool(plan.speedLimitChanged)
    s.speed_limit = float(plan.slcSpeedLimit) * speed_conversion
    s.slowing_for_lead = bool(plan.experimentalMode and plan.trackingLead and not s.red_light)
    s.nav_turn = nav_active and bool(plan.experimentalMode) and not s.red_light and not s.slowing_for_lead and not s.curve_control
    if toggles.get("weather_presets"):
      s.weather = weather_name(int(plan.weatherId))
    s.events = {str(e.name) for e in plan.starpilotEvents}
  return s
