from enum import IntEnum

from openpilot.system.ui.widgets import Widget
from openpilot.selfdrive.ui.tandem.settings import upstream
from openpilot.selfdrive.ui.tandem.settings.pages import Section, SectionPage
from openpilot.selfdrive.ui.tandem.settings.speed_steering import OFFSET_KEYS, SpeedSteering
from openpilot.selfdrive.ui.tandem.settings.live import FakeLive
from openpilot.selfdrive.ui.tandem.settings.store import SettingsStore
from openpilot.selfdrive.ui.tandem.settings.window import SettingsWindow, Tab

DEFAULTS = {"LongitudinalPersonality": 1, "ShowSpeedLimits": True, "SpeedLimitController": False, "Offset1": 5.0,
            "ConditionalExperimental": True, "CurveSpeedController": True, "MinimumLaneChangeSpeed": 20.0}


class FakeCache:
  def __init__(self, values=None):
    self.values = dict(DEFAULTS, **(values or {}))
    self.invalidations = 0

  def get_bool(self, key):
    return bool(self.values.get(key, False))

  def get_int(self, key, return_default=False):
    return int(self.values.get(key, 0))

  def get_float(self, key, return_default=False):
    return float(self.values.get(key, 0.0))

  def get(self, key, return_default=False):
    return self.values.get(key)

  def put_bool(self, key, value):
    self.values[key] = value

  put = put_int = put_float = put_bool

  def invalidate(self):
    self.invalidations += 1


def _model(values=None):
  cache = FakeCache(values)
  notified = []
  return SpeedSteering(SettingsStore(cache, lambda: notified.append(1))), cache, notified


class Page(Widget):
  def __init__(self, name, events, inner_depth=0):
    super().__init__()
    self.name = name
    self.events = events
    self.inner_depth = inner_depth

  def can_go_back(self):
    return self.inner_depth > 0

  def go_back(self):
    self.inner_depth -= 1

  def show_event(self):
    self.events.append(("show", self.name))

  def hide_event(self):
    self.events.append(("hide", self.name))

  def _render(self, rect):
    pass


def _window():
  events = []
  window = SettingsWindow(store=SettingsStore(FakeCache(), lambda: None), live=FakeLive())
  window._roots = [lambda n=n: Page(n, events) for n in ("driving", "device", "network", "bluetooth", "software")]
  closed = []
  window.set_callbacks(on_close=lambda: closed.append(1))
  return window, events, closed


# ── store and Speed & Steering ──

def test_store_writes_typed_values_then_notifies_once():
  cache = FakeCache()
  notified = []
  SettingsStore(cache, lambda: notified.append(1)).write({"A": True, "B": 2, "C": 1.5})
  assert (cache.values["A"], cache.values["B"], cache.values["C"]) == (True, 2, 1.5)
  assert type(cache.values["C"]) is float
  assert notified == [1] and cache.invalidations == 1


def test_driving_style_sets_gap_acceleration_and_braking_together():
  model, cache, notified = _model()
  assert model.style == 1
  model.set_style(2)
  assert (cache.values["LongitudinalPersonality"], cache.values["AccelerationProfile"], cache.values["DecelerationProfile"]) == (0, 2, 2)
  assert model.style == 2
  model.set_style(0)
  assert (cache.values["LongitudinalPersonality"], cache.values["AccelerationProfile"], cache.values["DecelerationProfile"]) == (2, 1, 1)
  assert model.style == 0 and len(notified) == 2


def test_speed_limits_off_show_match():
  model, cache, _ = _model()
  assert model.speed_limits == 1 and not model.matching
  model.set_speed_limits(2)
  assert cache.values["ShowSpeedLimits"] and cache.values["SpeedLimitController"] and cache.values["SetSpeedLimit"] and model.matching
  model.set_speed_limits(0)
  assert not cache.values["ShowSpeedLimits"] and not cache.values["SpeedLimitController"] and model.speed_limits == 0


def test_offset_applies_to_every_speed_range():
  model, cache, notified = _model()
  model.set_offset(7)
  assert [cache.values[k] for k in OFFSET_KEYS] == [7.0] * 7
  assert model.offset == 7 and len(notified) == 1


def test_tap_to_confirm_asks_only_for_higher_limits():
  model, cache, _ = _model()
  model.set_higher_limits(1)
  assert cache.values["SLCConfirmation"] and cache.values["SLCConfirmationHigher"] and not cache.values["SLCConfirmationLower"]
  model.set_higher_limits(0)
  assert not cache.values["SLCConfirmation"] and model.higher_limits == 0


def test_grouped_switches_and_summaries():
  model, cache, _ = _model({"IsMetric": True})
  assert model.smart_slowdowns
  model.set_smart_slowdowns(False)
  assert not cache.values["ConditionalExperimental"] and not cache.values["CurveSpeedController"]
  model.set_lane_changes(1)
  assert model.summary() == "Standard · Auto lane change"
  assert model.unit == "km/h" and model.lane_change_speed == 20


# ── window navigation ──

def test_back_steps_out_of_inner_pages_then_pops_then_closes():
  window, _, closed = _window()
  window.push(Page("detail", [], inner_depth=1))
  assert window.can_go_back()
  window.back()
  assert window.depth == 2 and window.can_go_back()
  window.back()
  assert window.depth == 1 and not window.can_go_back() and not closed
  window.back()
  assert closed == [1]


def test_tabs_keep_their_own_stacks():
  window, _, _ = _window()
  window.push(Page("detail", []))
  window.select_tab(Tab.NETWORK)
  assert window.depth == 1 and window.top.name == "network"
  window.select_tab(Tab.DRIVING)
  assert window.depth == 2 and window.top.name == "detail"


def test_only_the_visible_page_gets_show_and_hide():
  window, events, _ = _window()
  window.show_event()
  window.push(Page("detail", events))
  window.select_tab(Tab.DEVICE)
  window.hide_event()
  assert events == [("show", "driving"), ("hide", "driving"), ("show", "detail"), ("hide", "detail"), ("show", "device"),
                    ("hide", "device")]


def test_opening_at_an_upstream_panel_starts_that_tab_from_its_first_page():
  PanelType = IntEnum("PanelType", "STARPILOT DEVICE NETWORK BLUETOOTH TOGGLES SOFTWARE DEVELOPER")
  window, _, _ = _window()
  window.push(Page("detail", []))
  window.set_current_panel(PanelType.SOFTWARE)
  assert window.tab == Tab.SOFTWARE
  window.set_current_panel(PanelType.TOGGLES)
  assert window.tab == Tab.DRIVING and window.depth == 1


def test_developer_opens_the_device_tab_on_its_developer_section():
  PanelType = IntEnum("PanelType", "DEVELOPER")
  window = SettingsWindow(store=SettingsStore(FakeCache(), lambda: None), live=FakeLive())
  events = []
  window._roots[Tab.DEVICE] = lambda: SectionPage("DEVICE", [Section(n, lambda n=n: Page(n, events)) for n in ("a", "b", "dev")])
  window.set_current_panel(PanelType.DEVELOPER)
  assert window.tab == Tab.DEVICE and window.top.current.name == "dev"


def test_section_page_builds_sections_when_chosen_and_forwards_events():
  events, built = [], []

  def make(name):
    built.append(name)
    return Page(name, events, inner_depth=1)

  page = SectionPage("X", [Section("A", lambda: make("a")), Section("B", lambda: make("b"))])
  page.show_event()
  page.select(1)
  assert built == ["a", "b"]
  assert events == [("show", "a"), ("hide", "a"), ("show", "b")]
  assert page.can_go_back()
  page.go_back()
  assert not page.can_go_back()


# ── hosted StarPilot panels ──

class FakeStarPilot(Widget):
  CATEGORIES = [{"title": "Sounds", "panel": "SOUNDS"},
                {"title": "Controls", "children": [{"title": "Maps", "children": [{"title": "Map Data", "panel": "MAPS"}]}]}]

  def __init__(self):
    super().__init__()
    self._selected_leaf = None
    self._callback = None
    self.depth = 0

  def set_depth_callback(self, callback):
    self._callback = callback

  def _set_depth(self, depth):
    self.depth = depth
    self._callback(depth)

  def reset_to_root(self):
    self._selected_leaf = None
    self._set_depth(0)

  def _open_leaf(self, leaf):
    self._selected_leaf = leaf
    self._set_depth(1)

  def navigate_back(self):
    if self.depth == 1:
      self._selected_leaf = None
    self._set_depth(self.depth - 1)

  def _render(self, rect):
    pass


def test_find_leaf_searches_nested_folders():
  assert upstream.find_leaf(FakeStarPilot.CATEGORIES, "MAPS")["title"] == "Map Data"


def test_starpilot_page_opens_its_panel_and_pops_when_starpilot_leaves_it():
  layout = FakeStarPilot()
  exits = []
  page = upstream.StarPilotPage("MAPS", on_exit=lambda: exits.append(1), layout=lambda: layout)
  page.show_event()
  assert layout._selected_leaf["panel"] == "MAPS" and not exits
  layout._set_depth(2)
  assert page.can_go_back()
  page.go_back()
  assert not page.can_go_back()
  layout.navigate_back()      # StarPilot's own back button
  page._update_state()
  assert exits == [1]


def test_starpilot_section_reopens_instead_of_showing_the_starpilot_hub():
  layout = FakeStarPilot()
  page = upstream.StarPilotPage("SOUNDS", layout=lambda: layout)
  page.show_event()
  layout.navigate_back()
  page._update_state()
  assert layout._selected_leaf["panel"] == "SOUNDS" and layout.depth == 1


# ── This Device ──

class FakeDevice:
  def __init__(self, paired=False, offroad=True, calibration="Calibrated"):
    self.paired, self.offroad, self.cal = paired, offroad, calibration
    self.calls = []
    self.refreshes = 0

  def is_paired(self):
    return self.paired

  def is_offroad(self):
    return self.offroad

  def calibration(self):
    return self.cal

  def remote_access_label(self):
    return "Set Up"

  def ids(self):
    return "abc123 · serial"

  def show_regulatory(self):
    return False

  def refresh(self):
    self.refreshes += 1

  def __getattr__(self, name):
    return lambda: self.calls.append(name)


def _rows(panel):
  return {row._title: row for row in panel.items if hasattr(row, "_title")}


def test_this_device_buttons_call_the_device_and_respect_offroad():
  from openpilot.selfdrive.ui.tandem.settings.device import ThisDevicePanel
  device = FakeDevice(offroad=False)
  panel = ThisDevicePanel(device)
  rows = _rows(panel)
  rows["Camera Calibration"]._control._click_callback()
  assert device.calls == ["recalibrate"]
  assert not rows["Driver Camera"]._control.enabled
  assert rows["Camera Calibration"]._control.enabled
  restart, power_off = panel._footer._buttons
  assert not power_off.is_visible
  restart._click_callback()
  assert device.calls == ["recalibrate", "restart"]
  device.offroad = True
  assert power_off.is_visible and rows["Driver Camera"]._control.enabled


def test_this_device_hides_pair_once_paired_and_refreshes_on_show():
  from openpilot.selfdrive.ui.tandem.settings.device import ThisDevicePanel
  device = FakeDevice()
  panel = ThisDevicePanel(device)
  phone = _rows(panel)["Phone App"]
  assert phone._control.is_visible
  device.paired = True
  assert not phone._control.is_visible
  panel.show_event()
  assert device.refreshes == 1
  assert not _rows(panel)["Regulatory"].is_visible


# ── Driving sections and bundles ──

def _store(values=None):
  cache = FakeCache(values)
  return SettingsStore(cache, lambda: None), cache


def test_smart_slowdowns_turns_on_its_triggers_and_off_conditional_chill():
  model, cache, _ = _model({"ConditionalChill": True, "CECurves": False})
  model.set_smart_slowdowns(True)
  assert cache.values["CECurves"] and cache.values["CEStopLights"] and not cache.values["ConditionalChill"]


def test_vehicle_profile_towing_keeps_a_trailer_weight():
  from openpilot.selfdrive.ui.tandem.settings.speed_steering import VehicleProfile
  store, cache = _store()
  profile = VehicleProfile(store)
  assert profile.summary() == "Car"
  profile.set_profile(3)
  assert cache.values["TruckTuning"] and cache.values["TrailerLoad"] == 5000 and profile.towing
  profile.set_trailer_load(2)
  assert cache.values["TrailerLoad"] == 8000 and profile.trailer_load == 2
  profile.set_profile(1)
  assert cache.values["EVTuning"] and not cache.values["TruckTuning"] and cache.values["TrailerLoad"] == 0
  assert profile.summary() == "EV"


def test_weather_auto_writes_preset_amounts():
  from openpilot.selfdrive.ui.tandem.settings.speed_steering import Weather
  store, cache = _store()
  weather = Weather(store)
  assert weather.summary() == "Off"
  weather.set_mode(0)
  assert cache.values["WeatherPresets"] and cache.values["IncreaseFollowingSnow"] > cache.values["IncreaseFollowingRain"] > 0


def test_navigation_reads_home_and_work_from_favorites():
  from openpilot.selfdrive.ui.tandem.settings.speed_steering import Navigation
  store, _ = _store({"FavoriteDestinations": [{"name": "12 Elm St", "is_home": True}, {"name": "Gym"}, {"name": "Cafe"}]})
  nav = Navigation(store)
  assert nav.home() == "12 Elm St" and nav.work() is None and nav.others() == 2


def test_safe_mode_drives_relaxed_and_locks_driving_style():
  from openpilot.selfdrive.ui.tandem.settings.live import FakeLive
  from openpilot.selfdrive.ui.tandem.settings.speed_steering import Assistance
  store, cache = _store({"ExperimentalMode": True})
  Assistance(store, FakeLive()).set_safe_mode(True)
  assert cache.values["SafeMode"] and not cache.values["ExperimentalMode"] and cache.values["LongitudinalPersonality"] == 2
  assert SpeedSteering(store).safe_mode


def test_bundles_switch_their_keys_together():
  from openpilot.selfdrive.ui.tandem.settings.bundles import DEVELOPER_VIEW, LEAD_INSIGHTS, TUNER_MODE
  store, cache = _store()
  assert not DEVELOPER_VIEW.is_on(store)
  DEVELOPER_VIEW.set(store, True)
  assert DEVELOPER_VIEW.is_on(store) and cache.values["ShowCPU"] and cache.values["DeveloperUI"]
  DEVELOPER_VIEW.set(store, False)
  assert not cache.values["ShowCPU"] and not cache.values["DeveloperSidebar"]
  LEAD_INSIGHTS.set(store, True)
  assert cache.values["LeadInfo"] and cache.values["RadarTracksUI"] and cache.values["DeveloperMetrics"]
  TUNER_MODE.set(store, True)
  assert TUNER_MODE.is_on(store) and cache.values["TuningLevel"] == 3
  TUNER_MODE.set(store, False)
  assert not TUNER_MODE.is_on(store)


def test_tuner_sections_hide_with_tuner_mode():
  events = []
  shown = {"tuner": True}
  page = SectionPage("X", [Section("A", lambda: Page("a", events)), Section("T", lambda: Page("t", events), visible=lambda: shown["tuner"])])
  page.select(1)
  shown["tuner"] = False
  page._update_state()
  assert page.selected == 0
