from openpilot.selfdrive.ui.tandem.onroad.layers import AT_LIMIT, COMFORTABLE, LIMIT_HOLD, WORKING, Headroom
from openpilot.selfdrive.ui.tandem.onroad.status import ChipPicker, ChipTone, Snapshot, chip_for, weather_name


def test_chip_priority_paused_then_stopping_then_slowing_then_waiting():
  s = Snapshot(lateral_paused=True, red_light=True, curve_control=True, engaged=True, standstill=True)
  assert chip_for(s).key == "pause_speed" and chip_for(s).tone == ChipTone.PAUSED
  s.lateral_paused = False
  assert chip_for(s).key == "red_light"
  s.red_light = False
  assert chip_for(s).label == "Slowing for curve"
  s.curve_control = False
  assert chip_for(s).key == "ready" and chip_for(s).tone == ChipTone.WAITING
  s.engaged = False
  assert chip_for(s) is None


def test_chip_labels_use_units_and_direction():
  assert chip_for(Snapshot(lateral_paused=True, pause_lateral_speed=30, metric=True)).label == "Steering paused · under 30 km/h"
  assert chip_for(Snapshot(lateral_paused=True, signal_on=True)).label == "Steering paused for signal"
  assert chip_for(Snapshot(lane_change="starting", lane_change_direction="right")).label == "Changing lanes right"
  assert chip_for(Snapshot(lane_change="pre", blindspot=True)).label == "Lane change blocked"
  assert chip_for(Snapshot(limit_changed=True, speed_limit=45)).label == "Matching limit 45"
  assert chip_for(Snapshot(events={"greenLight"})).label == "Light is green"
  assert chip_for(Snapshot(always_on_lateral=True)).label == "Steering only"


def test_chip_holds_two_seconds_and_hides_under_alerts():
  picker = ChipPicker()
  assert picker.update(Snapshot(curve_control=True), 0.0, False).key == "curve"
  assert picker.update(Snapshot(), 1.5, False).key == "curve"
  assert picker.update(Snapshot(), 2.1, False) is None
  assert picker.update(Snapshot(curve_control=True), 3.0, True) is None


def test_weather_groups():
  assert [weather_name(i) for i in (211, 501, 502, 601, 741, 800)] == ["Heavy rain", "Rain", "Heavy rain", "Snow", "Fog", ""]


def test_headroom_stages_need_a_held_limit():
  h = Headroom()
  assert h.stage(0.3, 0.0) == COMFORTABLE
  assert h.stage(-0.7, 0.1) == WORKING
  assert h.stage(0.9, 0.2) == WORKING
  assert h.stage(0.9, 0.2 + LIMIT_HOLD + 0.01) == AT_LIMIT
  assert h.stage(0.5, 1.0) == COMFORTABLE
  assert h.stage(0.9, 1.1) == WORKING


# ── Home and first-run setup ──

def test_home_readiness_and_setup_line():
  from openpilot.selfdrive.ui.tandem.home import HomeState, readiness, setup_line
  from openpilot.selfdrive.ui.tandem.settings.speed_steering import SpeedSteering
  from openpilot.selfdrive.ui.tandem.settings.store import SettingsStore
  from openpilot.selfdrive.ui.tandem.tests.test_settings import FakeCache
  assert readiness(HomeState(ignition=True))[:2] == ("READY", "Press cruise to engage")
  assert readiness(HomeState())[1] == "Start the car to drive"
  assert readiness(HomeState(alerts=1))[:2] == ("NEEDS ATTENTION", "Check 1 alert")
  speed = SpeedSteering(SettingsStore(FakeCache({"SpeedLimitController": True, "NudgelessLaneChange": True}), lambda: None))
  assert setup_line(speed) == "Standard style · Matching speed limits · Auto lane change"


def test_setup_answers_apply_over_the_defaults():
  from openpilot.selfdrive.ui.tandem.settings.speed_steering import SpeedSteering
  from openpilot.selfdrive.ui.tandem.settings.store import SettingsStore
  from openpilot.selfdrive.ui.tandem.setup import Setup
  from openpilot.selfdrive.ui.tandem.tests.test_settings import FakeCache
  cache = FakeCache()
  notified, done = [], []
  store = SettingsStore(cache, lambda: notified.append(1))
  setup = Setup(store, lambda: done.append(1))
  setup.pick(0)          # Relaxed
  setup.next()
  setup.pick(1)          # Show
  setup.back()
  assert setup.step == 0 and setup.answers[:2] == [0, 1]
  setup.next()
  setup.next()
  setup.pick(0)          # Nudge
  setup.next()
  speed = SpeedSteering(store)
  assert done == [1] and notified == [1]
  assert (speed.style, speed.speed_limits, speed.lane_changes) == (0, 1, 0)
  assert cache.values["WeatherPresets"]     # defaults the questions don't cover still applied


def test_setup_use_defaults():
  from openpilot.selfdrive.ui.tandem.settings.speed_steering import SpeedSteering
  from openpilot.selfdrive.ui.tandem.settings.store import SettingsStore
  from openpilot.selfdrive.ui.tandem.setup import Setup
  from openpilot.selfdrive.ui.tandem.tests.test_settings import FakeCache
  store = SettingsStore(FakeCache({"LongitudinalPersonality": 0}), lambda: None)
  Setup(store, lambda: None).finish(use_answers=False)
  speed = SpeedSteering(store)
  assert (speed.style, speed.matching, speed.lane_changes) == (1, True, 0)


def test_sidebar_network_status():
  from openpilot.selfdrive.ui.tandem.sidebar import Health, network_status
  assert (network_status("--", 0).value, network_status("--", 0).health) == ("Offline", Health.OFF)
  assert network_status("Wi-Fi", 4).health == Health.GOOD
  assert network_status("LTE", 1).health == Health.WARN
  from openpilot.selfdrive.ui.tandem.sidebar import connect_status
  assert [connect_status(h).value for h in (Health.GOOD, Health.WARN, Health.BAD)] == ["Online", "Offline", "Error"]


def test_every_icon_named_has_a_png():
  import re
  from pathlib import Path
  from openpilot.selfdrive.ui.tandem import draw
  root = Path(draw.__file__).parent
  pngs = {p.stem for p in draw.ICON_DIR.glob("*.png")}
  assert pngs == {p.stem for p in (draw.ICON_DIR / "svg").glob("*.svg")}
  source = "\n".join(p.read_text() for p in root.rglob("*.py") if "tests" not in p.parts)
  named = set(re.findall(r'draw\.icon\([^,]+, "(\w+)"', source)) | set(re.findall(r'icon="(\w+)"', source))
  named |= set(re.findall(r'ChipTone\.\w+, "(\w+)"', source)) | {"lane_left", "lane_right"}
  assert named and {draw.MIRRORED.get(n, n) for n in named} <= pngs


def test_turn_card_icons_by_maneuver():
  from openpilot.selfdrive.ui.tandem import draw
  from openpilot.selfdrive.ui.tandem.onroad.layers import turn_icon
  cases = {("turn", "right"): "turn_right", ("turn", "slightLeft"): "turn_left", ("turn", "straight"): "shift",
           ("arrive", "straight"): "pin", ("roundabout", "right"): "restart", ("turn", "uturn"): "restart"}
  assert {key: turn_icon(*key) for key in cases} == cases
  pngs = {p.stem for p in draw.ICON_DIR.glob("*.png")}
  assert {draw.MIRRORED.get(name, name) for name in cases.values()} <= pngs


def test_home_software_card_shows_only_the_version_number():
  from openpilot.selfdrive.ui.tandem.home import short_version
  assert short_version("6.7.9 / design/essentials / 4b3a097 / Oct 31 - Regret Driven") == "6.7.9"
  assert short_version(b"0.10.1 / release / Oct 28") == "0.10.1"
  assert short_version(None) == ""
