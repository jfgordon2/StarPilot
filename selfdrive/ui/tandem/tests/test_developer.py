from openpilot.system.ui.widgets import DialogResult
from openpilot.selfdrive.ui.tandem.settings.developer import Developer, developer_panel
from openpilot.selfdrive.ui.tandem.settings.store import SettingsStore
from openpilot.selfdrive.ui.tandem.tests.fakes import FakeDeveloperSource
from openpilot.selfdrive.ui.tandem.tests.test_settings import FakeCache


class Window:
  def __init__(self):
    self.shown = None

  def present(self, overlay):
    self.shown = overlay

  def dismiss(self):
    pass


def _rows(panel):
  return {row._title: row for row in panel.items if hasattr(row, "_title")}


def _dev(**kw):
  return Developer(SettingsStore(FakeCache({}), lambda: None), FakeDeveloperSource(**kw))


def test_switches_write_upstreams_params():
  dev = _dev()
  rows = _rows(developer_panel(dev, Window()))
  rows["SSH"]._control._on_change(True)
  rows["Joystick Debug Mode"]._control._on_change(True)
  rows["UI Debug Mode"]._control._on_change(True)
  assert dev.flag("SshEnabled") and dev.flag("JoystickDebugMode") and not dev.flag("LongitudinalManeuverMode")
  assert dev.flag("ShowDebugInfo") and dev.source.ui_debug == [True]


def test_alpha_longitudinal_warns_first_and_hides_where_unavailable():
  dev, window = _dev(), Window()
  rows = _rows(developer_panel(dev, window))
  rows["openpilot Longitudinal (Alpha)"]._control._on_change(True)
  assert not dev.flag("AlphaLongitudinalEnabled")
  window.shown._finish(DialogResult.CONFIRM)
  assert dev.flag("AlphaLongitudinalEnabled") and dev.flag("OnroadCycleRequested")
  assert not _rows(developer_panel(_dev(alpha=False), Window()))["openpilot Longitudinal (Alpha)"].is_visible


def test_offroad_only_switches_and_key_fetch():
  dev = _dev(offroad=False)
  rows = _rows(developer_panel(dev, Window()))
  assert not rows["ADB"]._control.enabled and not rows["Joystick Debug Mode"]._control.enabled
  dev.add_keys("octocat")
  assert dev.fetching and dev.source.fetched == ["octocat"]
  dev.source.pending("No SSH keys found for user 'octocat'")
  assert not dev.fetching and "No SSH keys" in dev.error


def test_car_extras_ask_before_restarting_or_flashing():
  from openpilot.selfdrive.ui.tandem.settings.vehicle import extras_page
  from openpilot.selfdrive.ui.tandem.tests.fakes import FakeCarExtras
  extras, window = FakeCarExtras(), Window()
  page = extras_page(extras, window)
  rows = _rows(page._panel)
  rows["Auto-unlock doors"]._control._on_change(False)
  assert extras.calls == [("toggle", "UnlockDoors")]                      # plain switches act at once
  rows["Use the car's own cruise control"]._control._on_change(True)
  assert len(extras.calls) == 1
  window.shown._finish(DialogResult.CONFIRM)
  assert extras.calls[-1] == ("toggle", "DisableOpenpilotLongitudinal")
  rows["CAN ignition only"]._control._on_change(True)
  window.shown._finish(DialogResult.CONFIRM)
  assert extras.calls[-1] == ("flash", "IgnoreIgnitionLine")
  rows["Lock doors after"]._control._click_callback()
  window.shown._body._on_change(4)
  assert extras.timer() == 120
