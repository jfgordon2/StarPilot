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
  waiting_for_resume: bool = False         # the car's cruise is held at a stop until the driver resumes
  speed: float = 0.0                       # m/s
  accel: float = 0.0                       # m/s², the car's own
  metric: bool = False
  lateral_paused: bool = False
  pause_lateral_speed: float = 0.0         # display units; 0 when the setting is off
  signal_on: bool = False
  signal_direction: str = "none"           # left, right, both, none
  always_on_lateral: bool = False          # steering with cruise off
  lane_change: str = "off"                 # off, pre, starting, finishing
  lane_change_direction: str = "none"      # left, right, none
  blindspot: bool = False                  # on the side of the requested lane change
  curve_control: bool = False
  red_light: bool = False
  stop_sign: bool = False
  slowing_for_lead: bool = False
  nav_turn: bool = False
  nav_turn_maneuver: str = ""
  nav_turn_modifier: str = ""
  limit_changed: bool = False
  speed_limit: float = 0.0                 # display units
  weather: str = ""                        # "Rain", "Snow", "Fog" ... when Weather is acting
  events: set[str] = field(default_factory=set)


def turn_icon(maneuver: str, modifier: str) -> str:
  """The same maneuver icon for navigation cards and turn-progress chips; unknown directions stay neutral."""
  if maneuver in ("arrive", "depart"):
    return "pin"
  if maneuver in ("roundabout", "rotary", "roundabout turn") or "uturn" in modifier.lower():
    return "restart"
  modifier = modifier.lower()
  if "left" in modifier:
    return "turn_left"
  if "right" in modifier:
    return "turn_right"
  return "shift" if modifier == "straight" else "map"


SLOWING_ACCEL = -0.3     # m/s²: below this the car is braking, not just following
MOVING_SPEED = 0.5       # m/s


def chips_for(s: Snapshot) -> list[Chip]:
  """Every chip that applies now, highest priority first: paused or blocked, stopping, slowing, then waiting. Reasons that
  exclude each other (the two pauses, blocked or changing lanes, a sign or the model's stop) give one chip."""
  unit = "km/h" if s.metric else "mph"
  out: list[Chip] = []
  if s.lateral_paused and s.signal_on:
    icon = {"left": "signal", "right": "signal_right", "both": "warning"}.get(s.signal_direction, "wheel_pause")
    out.append(Chip("pause_signal", "Steering paused for signal", ChipTone.PAUSED, icon))
  elif s.lateral_paused:
    below = f" · under {s.pause_lateral_speed:.0f} {unit}" if s.pause_lateral_speed else ""
    out.append(Chip("pause_speed", f"Steering paused{below}", ChipTone.PAUSED, "wheel_pause"))
  if s.lane_change in ("pre", "starting") and s.blindspot:
    out.append(Chip("lane_blocked", "Lane change blocked", ChipTone.PAUSED, "lane_blocked"))
  elif s.lane_change in ("starting", "finishing") and s.lane_change_direction in ("left", "right"):
    out.append(Chip("lane_change", f"Changing lanes {s.lane_change_direction}", ChipTone.INFO, f"lane_{s.lane_change_direction}"))
  green = "greenLight" in s.events
  if s.standstill and green:   # at a stop the news is the light changing, not that we're stopped
    out.append(Chip("green_light", "Light is green", ChipTone.WAITING, "light_green"))
  else:
    stop = "Stopped" if s.standstill else "Stopping"   # once the car is stopped, the chip says so
    if s.stop_sign:
      out.append(Chip("stop_sign", f"{stop} for stop sign", ChipTone.INFO, "stop_sign"))
    elif s.red_light:
      # StarPilot's redLight is the model predicting a stop, for a light or a sign alike; only the dashboard confirms a sign.
      out.append(Chip("red_light", "Stopped" if s.standstill else "Stopping ahead", ChipTone.INFO, "stop"))
  if s.curve_control:
    out.append(Chip("curve", "Slowing for curve", ChipTone.INFO, "curve"))
  if s.nav_turn:
    out.append(Chip("turn", "Slowing for turn", ChipTone.INFO, turn_icon(s.nav_turn_maneuver, s.nav_turn_modifier)))
  # Turn events stand on their own, including steering-only turns with the driver on the pedals.
  if "turningLeft" in s.events:
    out.append(Chip("turning", "Turning left", ChipTone.INFO, "turn_left"))
  elif "turningRight" in s.events:
    out.append(Chip("turning", "Turning right", ChipTone.INFO, "turn_right"))
  if s.slowing_for_lead and not s.standstill and s.speed > MOVING_SPEED and s.accel < SLOWING_ACCEL:
    out.append(Chip("traffic", "Slowing for traffic", ChipTone.INFO, "car"))
  if s.limit_changed and s.speed_limit:
    out.append(Chip("limit", f"Matching limit {s.speed_limit:.0f}", ChipTone.INFO, "gauge"))
  if s.weather:
    out.append(Chip("weather", f"{s.weather} · longer gap", ChipTone.INFO, {"Snow": "snow", "Fog": "fog"}.get(s.weather, "rain")))
  if green and not s.standstill:
    out.append(Chip("green_light", "Light is green", ChipTone.WAITING, "light_green"))
  if "leadDeparting" in s.events:
    out.append(Chip("lead_moved", "Car ahead moved", ChipTone.WAITING, "car_up"))
  if s.engaged and s.standstill and s.waiting_for_resume:   # cars that resume on their own aren't waiting on you
    out.append(Chip("ready", "Ready · tap resume", ChipTone.WAITING, "play"))
  if s.always_on_lateral and not s.engaged:
    out.append(Chip("steering_only", "Steering only", ChipTone.INFO, "wheel"))
  return out


def chip_for(s: Snapshot) -> Chip | None:
  """The highest-priority chip, or None."""
  chips = chips_for(s)
  return chips[0] if chips else None


@dataclass
class _Shown:
  chip: Chip
  born: float        # when it joined the stack (its place: newest nearest the bar)
  until: float       # its reason was last seen at until - HOLD
  rank: int          # its priority when last seen


class ChipStack:
  """Up to MAX chips at once, newest nearest the bar. Each keeps its own hold: it stays while its reason holds, renews
  whenever the reason is seen again, then fades over FADE once HOLD has passed. With more reasons than MAX, the
  highest-priority ones show. The whole stack hides while an alert shows."""
  MAX = 4
  HOLD = 2.0
  FADE = 0.3

  def __init__(self):
    self._shown: dict[str, _Shown] = {}

  def update(self, s: Snapshot, now: float, alert_showing: bool) -> list[tuple[Chip, float]]:
    """(chip, opacity) nearest the bar first."""
    for rank, chip in enumerate(chips_for(s)):
      held = self._shown.get(chip.key)
      if held is None:
        self._shown[chip.key] = _Shown(chip, now, now + self.HOLD, rank)
      else:
        held.chip, held.until, held.rank = chip, now + self.HOLD, rank   # renewed; a changed label (Stopping → Stopped) updates
    self._shown = {k: v for k, v in self._shown.items() if now < v.until + self.FADE}
    if alert_showing:
      return []
    visible = sorted(self._shown.values(), key=lambda v: v.rank)[:self.MAX]
    visible.sort(key=lambda v: v.born, reverse=True)
    return [(v.chip, 1.0 if now < v.until else max(0.0, 1.0 - (now - v.until) / self.FADE)) for v in visible]


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
    s.standstill, s.speed, s.accel = bool(cs.standstill), float(cs.vEgo), float(cs.aEgo)
    s.waiting_for_resume = bool(cs.cruiseState.standstill)
    s.signal_on = bool(cs.leftBlinker or cs.rightBlinker)
    if cs.leftBlinker and cs.rightBlinker:
      s.signal_direction = "both"
    elif s.signal_on:
      s.signal_direction = "left" if cs.leftBlinker else "right"
    direction_left = cs.leftBlinker
    s.blindspot = bool(cs.leftBlindspot if direction_left else cs.rightBlindspot)
  if valid.get("modelV2", False):
    meta = sm["modelV2"].meta
    s.lane_change = {1: "pre", 2: "starting", 3: "finishing"}.get(meta.laneChangeState.raw, "off")
    s.lane_change_direction = {1: "left", 2: "right"}.get(meta.laneChangeDirection.raw, "none")
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
    # A route or experimental mode alone does not mean the car is slowing for a turn.
    s.nav_turn = bool(
      nav_active and plan.navTurnControllingSpeed and valid.get("carState", False)
      and sm["carState"].aEgo < -0.1 and s.speed > max(float(plan.vCruise), 0.1)
    )
    s.nav_turn_maneuver, s.nav_turn_modifier = str(plan.navTurnManeuver), str(plan.navTurnModifier)
    if toggles.get("weather_presets"):
      s.weather = weather_name(int(plan.weatherId))
    s.events = {str(e.name) for e in plan.starpilotEvents}
  # StarPilot raises greenLight and leadDeparting for a single planner frame, which the UI can miss; the alerts they start
  # are held for seconds, so their names count too (the chip stands in for the hidden banner).
  for service in ("selfdriveState", "starpilotSelfdriveState"):
    if valid.get(service, False) and sm[service].alertType:
      s.events.add(str(sm[service].alertType).split("/", 1)[0])
  return s
