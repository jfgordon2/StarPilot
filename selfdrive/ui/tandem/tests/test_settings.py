from enum import IntEnum

from openpilot.system.ui.widgets import DialogResult, Widget
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
  window._roots[Tab.DEVICE] = lambda: SectionPage("DEVICE", [Section(n, lambda n=n: Page(n, events)) for n in "abcde"] +
                                                  [Section("dev", lambda: Page("dev", events))])
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


# ── Display and Alerts ──

def test_path_style_presets_round_trip():
  from openpilot.selfdrive.ui.tandem.settings.display import Display
  store, cache = _store({"PathWidth": 6.1, "AccelerationPath": True})
  display = Display(store)
  assert display.path_style == 3
  for i in range(4):
    display.set_path_style(i)
    assert display.path_style == i
  display.set_path_style(1)
  assert cache.values["PathWidth"] == 3.0 and not cache.values["AccelerationPath"]


def test_signal_animation_turns_on_custom_themes():
  from openpilot.selfdrive.ui.tandem.settings.display import Display
  store, cache = _store()
  display = Display(store)
  assert display.signal_name() == "None"
  display.set_signal(1)
  assert cache.values["SignalAnimation"] == "sequential" and cache.values["CustomThemes"] and display.signal_name() == "Sequential"


def test_clean_screen_needs_every_banner_hidden():
  from openpilot.selfdrive.ui.tandem.settings.display import Display
  store, cache = _store()
  display = Display(store)
  display.set_clean_screen(True)
  assert display.clean_screen and cache.values["AdvancedCustomUI"]
  cache.values["HideTurningBanner"] = False
  assert not display.clean_screen


def test_volume_presets_and_custom_levels():
  from openpilot.selfdrive.ui.tandem.settings.alerts import AUTO, CUSTOM, GROUPS, Alerts
  store, cache = _store({k: AUTO for g in GROUPS for k in g.keys})
  alerts = Alerts(store)
  assert alerts.preset == 0 and alerts.level_label(GROUPS[0]) == "Auto"
  alerts.set_preset(2)
  assert cache.values["AlertVolumeControl"] and alerts.preset == 2 and alerts.level_label(GROUPS[2]) == "80%"
  alerts.set_level(GROUPS[0], 40)
  assert alerts.preset == CUSTOM and cache.values["EngageVolume"] == cache.values["DisengageVolume"] == 40


def test_safety_volumes_never_go_below_the_floor():
  from openpilot.selfdrive.ui.tandem.settings.alerts import GROUPS, SAFETY_FLOOR, Alerts
  store, cache = _store()
  alerts = Alerts(store)
  alerts.set_level(GROUPS[3], 5)
  assert cache.values["WarningImmediateVolume"] == SAFETY_FLOOR
  alerts.set_level(GROUPS[0], 5)
  assert cache.values["EngageVolume"] == 5


def test_custom_level_from_auto_starts_other_groups_at_normal():
  from openpilot.selfdrive.ui.tandem.settings.alerts import GROUPS, Alerts
  store, cache = _store({"AlertVolumeControl": False})
  Alerts(store).set_level(GROUPS[1], 50)
  assert cache.values["EngageVolume"] == GROUPS[0].levels[1] and cache.values["PromptVolume"] == 50


def test_window_overlay_blocks_page_and_back_dismisses_it():
  window, _, closed = _window()
  sheet = Page("sheet", [])
  window.present(sheet)
  assert window.overlay is sheet
  window.back()
  assert window.overlay is None and not closed


# ── Driving Model and Vehicle ──

def test_model_states_and_use_recommended():
  from openpilot.selfdrive.ui.tandem.tests.fakes import FakeModels
  from openpilot.selfdrive.ui.tandem.settings.model import Models
  store, cache = _store({"AutomaticallyDownloadModels": True})
  source = FakeModels()
  models = Models(store, source)
  assert models.use_recommended and models.summary() == "Recommended"
  assert [models.status(m) for m in source.items] == ["active", "on_device", "download", "unavailable"]
  source.download("nlp")
  assert models.status(source.items[2]) == "downloading" and models.update_summary() == "Downloading"
  source.use("vtx")
  assert not models.use_recommended and models.summary() == "Vortex"
  models.set_use_recommended(True)
  assert source.current == "rdf43" and cache.values["AutomaticallyDownloadModels"]


def test_remove_unused_keeps_active_and_recommended():
  from openpilot.selfdrive.ui.tandem.tests.fakes import FakeModels
  from openpilot.selfdrive.ui.tandem.settings.model import Models
  store, _ = _store()
  source = FakeModels()
  source.use("vtx")
  Models(store, source).remove_unused()
  assert [m.key for m in source.items if m.installed] == ["rdf43", "vtx"]
  source.use("rdf43")
  Models(store, source).remove_unused()
  assert [m.key for m in source.items if m.installed] == ["rdf43"]


def test_choosing_a_car_turns_off_detection():
  from openpilot.selfdrive.ui.tandem.tests.fakes import FakeCars
  from openpilot.selfdrive.ui.tandem.settings.vehicle import CarPicker, Vehicle
  store, cache = _store({"CarMake": "Toyota", "CarModelName": "RAV4 2019-21"})
  vehicle = Vehicle(store, FakeCars())
  picker = CarPicker(vehicle)
  assert picker._make == 2 and picker._model == 0
  picker._pick_model(1)
  assert picker.save()
  assert cache.values["ForceFingerprint"] and cache.values["CarModel"] == "TOYOTA_RAV4H_TSS2" and vehicle.manual
  picker._pick_make(1)
  assert not picker.save()    # a make alone isn't a car
  vehicle.use_detection()
  assert not vehicle.manual


def test_wheel_button_actions():
  from openpilot.selfdrive.ui.tandem.tests.fakes import FakeCars
  from openpilot.selfdrive.ui.tandem.settings.vehicle import Vehicle
  store, cache = _store()
  vehicle = Vehicle(store, FakeCars())
  lkas = vehicle.catalog.buttons()[2]
  assert vehicle.action_name(lkas) == "Car default" and vehicle.buttons_summary() == "Car default buttons"
  vehicle.set_action(lkas, 9)
  assert cache.values["LKASButtonControl"] == 9 and vehicle.action_name(lkas) == "Always-on steering"
  assert vehicle.buttons_summary() == "Buttons customized"


# ── Tuner Mode ──

def test_tunable_default_override_and_reset_to_the_cars_value():
  from openpilot.selfdrive.ui.tandem.settings.tuner import DEFAULT, OVERRIDE, STEERING, Tuner
  store, cache = _store({"SteerFriction": 0.12, "SteerFrictionStock": 0.12})
  tuner = Tuner(store)
  friction = STEERING[1]
  assert tuner.status(friction) == DEFAULT
  before = tuner.changed(STEERING)
  tuner.set_value(friction, 0.2)
  assert tuner.status(friction) == OVERRIDE and cache.values["AdvancedLateralTune"] and tuner.changed(STEERING) == before + 1
  tuner.reset(friction)
  assert cache.values["SteerFriction"] == 0.12 and tuner.status(friction) == DEFAULT


def test_steering_delay_is_learned_until_overridden():
  from openpilot.selfdrive.ui.tandem.settings.tuner import LEARNED, OVERRIDE, STEERING, Tuner
  store, cache = _store({"UseAutoSteerDelay": True, "SteerDelay": 0.2, "SteerDelayStock": 0.2})
  tuner = Tuner(store)
  delay = STEERING[0]
  assert tuner.status(delay) == LEARNED
  tuner.set_value(delay, 0.3)
  assert not cache.values["UseAutoSteerDelay"] and tuner.status(delay) == OVERRIDE
  tuner.reset(delay)
  assert cache.values["UseAutoSteerDelay"] and tuner.status(delay) == LEARNED


def test_profiles_follow_driving_style_until_overridden():
  from openpilot.selfdrive.ui.tandem.settings.tuner import FROM_STYLE, OVERRIDE, Tuner
  store, cache = _store()
  SpeedSteering(store).set_style(2)
  tuner = Tuner(store)
  assert tuner.profile_status("AccelerationProfile") == FROM_STYLE
  before = tuner.gas_brake_changes()
  tuner.set_accel_profile(3)
  assert tuner.profile_status("AccelerationProfile") == OVERRIDE and tuner.gas_brake_changes() == before + 1


def test_steering_controller_choices():
  from openpilot.selfdrive.ui.tandem.settings.tuner import Tuner
  store, cache = _store()
  tuner = Tuner(store)
  for i in range(4):
    tuner.set_controller(i)
    assert tuner.controller == i


def test_bundle_overrides_count_items_that_differ():
  from openpilot.selfdrive.ui.tandem.settings.bundles import DEVELOPER_VIEW
  from openpilot.selfdrive.ui.tandem.settings.tuner import Tuner
  store, cache = _store()
  DEVELOPER_VIEW.set(store, True)
  tuner = Tuner(store)
  assert tuner.bundle_changes(DEVELOPER_VIEW) == 0
  tuner.set_switch("ShowGPU", False)
  assert tuner.item_differs(DEVELOPER_VIEW, "ShowGPU") and tuner.bundle_changes(DEVELOPER_VIEW) == 1


def test_reset_all_restores_defaults_and_bundle_values():
  from openpilot.selfdrive.ui.tandem.settings.bundles import DEVELOPER_VIEW
  from openpilot.selfdrive.ui.tandem.settings.tuner import GAPS, STEERING, Tuner
  store, cache = _store({"SteerKPStock": 1.1})
  DEVELOPER_VIEW.set(store, True)
  tuner = Tuner(store)
  tuner.set_value(STEERING[3], 2.0)
  tuner.set_gap("RelaxedFollow", 2.5)
  tuner.set_switch("ShowGPU", False)
  tuner.reset_all()
  assert cache.values["SteerKP"] == 1.1 and cache.values["RelaxedFollow"] == GAPS[0][2] and cache.values["ShowGPU"]


def test_reset_all_tuning_asks_first():
  from openpilot.system.ui.widgets import DialogResult
  from openpilot.selfdrive.ui.tandem.overlays import Dialog
  from openpilot.selfdrive.ui.tandem.settings.tuner import STEERING, Tuner, tuner_page

  class Window:
    overlay = None

    def present(self, overlay):
      self.overlay = overlay

    def dismiss(self):
      self.overlay = None

  store, cache = _store({"SteerKPStock": 1.1})
  tuner, window = Tuner(store), Window()
  tuner.set_value(STEERING[3], 2.0)
  reset = tuner_page(tuner, window)._sidebar._footer[0]
  assert reset._label == "Reset all tuning"
  reset._click_callback()
  assert isinstance(window.overlay, Dialog) and cache.values["SteerKP"] == 2.0   # nothing changes until confirmed
  window.overlay._finish(DialogResult.CANCEL)
  assert window.overlay is None and cache.values["SteerKP"] == 2.0
  reset._click_callback()
  window.overlay._finish(DialogResult.CONFIRM)
  assert cache.values["SteerKP"] == 1.1


# ── Device sections ──

def _general(values=None, engaged=False):
  from openpilot.selfdrive.ui.tandem.settings.device_sections import General
  from openpilot.selfdrive.ui.tandem.tests.fakes import FakeData
  store, cache = _store(values)
  return General(store, FakeData(), FakeLive(engaged=engaged)), cache


def test_general_brightness_uploads_and_language():
  general, cache = _general({"ScreenBrightness": 101})
  assert general.brightness == 1
  general.set_brightness(0)
  assert cache.values["ScreenBrightness"] == 40 and cache.values["ScreenBrightnessOnroad"] == 30 and general.brightness == 0
  general.set_uploads(1)
  assert not cache.values["NoUploads"] and cache.values["DisableOnroadUploads"] and general.uploads == 1
  general.set_uploads(0)
  assert cache.values["NoUploads"] and general.uploads == 0
  general.data.set_language("es")
  assert general.language_name() == "Español"


def test_recording_switches_wait_until_disengaged():
  general, _ = _general(engaged=True)
  assert general.recording_locked()
  general, cache = _general({"RecordFrontLock": True})
  assert general.recording_locked()
  general, _ = _general()
  assert not general.recording_locked()


def test_report_needs_a_category_and_includes_details():
  from openpilot.selfdrive.ui.tandem.settings.device_sections import REPORT_CATEGORIES, Report
  from openpilot.selfdrive.ui.tandem.tests.fakes import FakeData
  store, cache = _store()
  data = FakeData()
  report = Report(data, store)
  report.send()
  assert not data.reports
  report.category, report.details, report.discord = 1, "on the highway", "driver42"
  report.send()
  assert data.reports == [(f"{REPORT_CATEGORIES[1]}: on the highway", "driver42")] and cache.values["DiscordUsername"] == "driver42"


def test_backup_restore_asks_first():
  from openpilot.selfdrive.ui.tandem.settings.device_sections import confirm
  window, _, _ = _window()
  done = []
  confirm(window, "Restore?", "Replaces settings.", "Restore", lambda: done.append(1))
  window.overlay._on_result(DialogResult.CANCEL)
  assert not done and window.overlay is None
  confirm(window, "Restore?", "Replaces settings.", "Restore", lambda: done.append(1))
  window.overlay._on_result(DialogResult.CONFIRM)
  assert done == [1]


# ── Network, Bluetooth, Software ──

def _network(values=None):
  from openpilot.selfdrive.ui.tandem.settings.network_tab import Network
  from openpilot.selfdrive.ui.tandem.tests.fakes import FakeWifi
  store, cache = _store(values)
  asked = []
  wifi = FakeWifi()
  net = Network(wifi, store, ask=lambda title, sub, current, done, *a, **k: asked.append((title, done)))
  return net, wifi, cache, asked


def test_wifi_connects_saved_open_and_secured_networks():
  net, wifi, _, asked = _network()
  home, cafe, neighbor = wifi.networks
  assert net.status("Home Wi-Fi") == "Connected" and net.status("Neighbor") == ""
  net.choose(cafe)
  assert wifi.calls[-1] == ("connect", "Coffee Shop", "", False)
  net.choose(neighbor)
  title, done = asked[-1]
  assert title == "Enter password"
  done("hunter2hunter2")
  assert wifi.calls[-1] == ("connect", "Neighbor", "hunter2hunter2", False)
  wifi.need_auth("Neighbor")
  assert asked[-1][0] == "Wrong password"


def test_save_data_marks_cellular_and_current_wifi_metered():
  net, wifi, cache, _ = _network({"GsmApn": "fast.apn"})
  net.set_save_data(True)
  assert cache.values["GsmMetered"] and ("gsm", False, "fast.apn", True) in wifi.calls and ("metered", 1) in wifi.calls


def test_wheel_buttons_highlight_and_assign():
  from openpilot.selfdrive.ui.tandem.settings.bluetooth_tab import AssignSheet, WheelButtons
  from openpilot.selfdrive.ui.tandem.tests.fakes import FakeWheel
  source = FakeWheel()
  wheel = WheelButtons(source)
  first = wheel.buttons()[0]
  assert wheel.action_name(first) == "Engage" and not wheel.is_pressed(first)
  source.state["last_tested"] = {"mapped": True, "slot": 3}
  assert wheel.is_pressed(first)
  source.state["last_tested"] = {"mapped": False}
  assert wheel.unassigned_pressed()

  sheet = AssignSheet(wheel)
  sheet.show_event()
  assert source.learning == 5 and not sheet.ready
  source.maps.append({"id": "c", "device_name": "Wheel Remote", "event_name": "BTN_C", "slot": 5})
  source.state["last_learned"] = source.maps[-1]
  sheet._update_state()
  sheet._pick(2)
  assert sheet.ready and sheet.save()
  assert wheel.action_name(source.maps[-1]) == "Change driving style"


def test_cancelling_assignment_removes_a_learned_button():
  from openpilot.selfdrive.ui.tandem.settings.bluetooth_tab import AssignSheet, WheelButtons
  from openpilot.selfdrive.ui.tandem.tests.fakes import FakeWheel
  source = FakeWheel()
  sheet = AssignSheet(WheelButtons(source))
  sheet.show_event()
  source.maps.append({"id": "c", "device_name": "Wheel Remote", "event_name": "BTN_C", "slot": 5})
  source.state["last_learned"] = source.maps[-1]
  sheet._update_state()
  sheet.cancel()
  assert [m["id"] for m in source.maps] == ["a", "b"] and source.learning is None


def test_software_states_and_actions():
  from openpilot.selfdrive.ui.tandem.settings.software_tab import Software
  from openpilot.selfdrive.ui.tandem.tests.fakes import FakeUpdates
  store, cache = _store({"UpdaterState": "idle", "UpdaterCurrentDescription": "0.10.1 / release"})
  updates = FakeUpdates()
  software = Software(store, updates, lambda: None)
  assert software.state() == "current" and software.action_label() == "Check now"
  assert software.version_parts() == ("0.10.1", "release")
  software.act()
  cache.values["UpdaterFetchAvailable"] = True
  assert software.action_label() == "Download"
  cache.values["UpdateAvailable"] = True
  software.act()
  assert updates.calls == ["check_or_download", "install"]
  cache.values["UpdaterState"] = "downloading"
  assert software.state() == "busy" and software.status_line() == "Downloading the update"


def test_reset_settings_applies_essentials_with_one_signal():
  from openpilot.selfdrive.ui.tandem.settings.bundles import DEVELOPER_VIEW
  from openpilot.selfdrive.ui.tandem.settings.defaults import apply_essentials
  cache = FakeCache({"LongitudinalPersonality": 0, "SpeedLimitController": False})
  notified = []
  store = SettingsStore(cache, lambda: notified.append(1))
  DEVELOPER_VIEW.set(store, True)
  notified.clear()
  apply_essentials(store)
  assert notified == [1]
  speed = SpeedSteering(store)
  assert speed.style == 1 and speed.matching and speed.offset == 3 and speed.higher_limits == 1 and speed.lane_changes == 1
  assert not DEVELOPER_VIEW.is_on(store) and cache.values["GreenLightAlert"] and not cache.values["HolidayThemes"]


def test_maps_download_waits_for_parked_online_and_a_selection():
  from openpilot.selfdrive.ui.tandem.settings.maps import Maps
  from openpilot.selfdrive.ui.tandem.tests.fakes import FakeMaps
  store, cache = _store({"PreferredSchedule": 2})
  source = FakeMaps()
  maps = Maps(store, source)
  assert maps.ready() and maps.schedule == 2
  source.online = False
  assert not maps.ready() and maps.blocked_reason() == "Waiting: online"
  source.online = True
  source.set_selected("pkg:west", False)
  assert maps.blocked_reason() == "Choose at least one region"
  source.set_selected("s:CA", True)
  source.download()
  assert not maps.ready() and maps.status() == "Downloading California · 42%"
  maps.set_schedule(0)
  assert cache.values["PreferredSchedule"] == 0


def test_download_fraction_reads_the_percent():
  from openpilot.selfdrive.ui.tandem.settings.model import download_fraction
  assert download_fraction("45% · about 3 min left") == 0.45
  assert download_fraction("starting") == 0.0 and download_fraction("") == 0.0


def test_boot_logo_picker_lists_built_ins_then_downloads():
  from openpilot.selfdrive.ui.tandem.overlays import Sheet
  from openpilot.selfdrive.ui.tandem.settings.display import Display, boot_logo_sheet
  from openpilot.selfdrive.ui.tandem.tests.fakes import FakeBootLogos

  class Window:
    overlay = None

    def present(self, overlay):
      self.overlay = overlay

    def dismiss(self):
      self.overlay = None

  store, cache = _store()
  logos = FakeBootLogos()
  display, window = Display(store, lambda: logos), Window()
  assert display.boot_logo_name() == "StarPilot"   # StarPilot's own default until Essentials is applied
  assert display.boot_logo_options() == [("tandem", "Tandem"), ("starpilot", "StarPilot"), ("stock", "comma"), ("aurora_logo", "Aurora Logo"),
                                         ("pixel_logo", "Pixel Logo")]   # a downloaded "stock" doesn't repeat comma's
  boot_logo_sheet(display, window)
  window.overlay._body._on_change(0)
  assert cache.values["BootLogo"] == "tandem" and logos.installs == 1 and display.boot_logo_name() == "Default"
  boot_logo_sheet(display, window)
  assert isinstance(window.overlay, Sheet)
  window.overlay._body._on_change(3)
  assert cache.values["BootLogo"] == "aurora_logo" and display.boot_logo_name() == "Aurora Logo" and window.overlay is None
  boot_logo_sheet(display, window)
  assert [a._label for a in window.overlay._actions] == ["Done"]   # nothing to download


def test_essentials_choose_and_install_the_tandem_boot_logo():
  from openpilot.selfdrive.ui.tandem.settings.defaults import apply_essentials
  from openpilot.selfdrive.ui.tandem.settings.display import TANDEM_LOGO_FILE
  from openpilot.selfdrive.ui.tandem.tests.fakes import FakeBootLogos
  store, cache = _store({"BootLogo": "starpilot"})
  logos = FakeBootLogos()
  apply_essentials(store, lambda: logos)
  assert cache.values["BootLogo"] == "tandem" and logos.installs == 1
  from PIL import Image
  with Image.open(TANDEM_LOGO_FILE) as image:
    assert image.size == (2160, 1080)   # StarPilot's boot logo size


def test_upstream_boot_logos_install_tandem_once(tmp_path):
  from openpilot.selfdrive.ui.tandem.settings.display import TANDEM_LOGO_FILE, UpstreamBootLogos
  logos = UpstreamBootLogos.__new__(UpstreamBootLogos)   # skip the StarPilot import; point it at a temp folder
  logos._folder = tmp_path / "bootlogos"
  logos.install_tandem()
  installed = logos._folder / "tandem.jpg"
  assert installed.read_bytes() == TANDEM_LOGO_FILE.read_bytes()
  mtime = installed.stat().st_mtime_ns
  logos.install_tandem()
  assert installed.stat().st_mtime_ns == mtime   # already there: not copied again

