import pytest
import pyray as rl

import openpilot.system.ui.widgets as widgets
from openpilot.system.ui.lib.application import gui_app, MouseEvent, MousePos
from openpilot.selfdrive.ui.tandem import draw
from openpilot.selfdrive.ui.tandem.controls import Button
from openpilot.selfdrive.ui.tandem.settings.network_tab import Network, SignalGlyph, wifi_panel
from openpilot.selfdrive.ui.tandem.settings.store import SettingsStore
from openpilot.selfdrive.ui.tandem.tests.fakes import FakeWifi
from openpilot.selfdrive.ui.tandem.tests.test_settings import FakeCache


@pytest.mark.parametrize("pc", [False, True])
@pytest.mark.parametrize("same_frame", [False, True])
def test_wifi_forget_does_not_activate_the_network_row(monkeypatch, pc, same_frame):
  # Keep the real row layout, rendering order and event processing; drawing itself needs no GPU here.
  for name in ("fill", "text", "chevron"):
    monkeypatch.setattr(draw, name, lambda *args, **kwargs: 0)
  monkeypatch.setattr(draw, "text_width", lambda text, *args, **kwargs: len(text) * 12)
  monkeypatch.setattr(Button, "_render", lambda self, rect: None)
  monkeypatch.setattr(SignalGlyph, "_render", lambda self, rect: None)
  monkeypatch.setattr(gui_app, "_mouse_events", [])
  monkeypatch.setattr(widgets, "PC", pc)
  wifi, asked = FakeWifi(), []
  wifi.connected_ssid = ""
  model = Network(wifi, SettingsStore(FakeCache(), lambda: None), ask=lambda *args: asked.append(args))
  panel = wifi_panel(model)
  panel._update_state()
  row = panel._content.items[0]
  row.set_touch_valid_callback(lambda: True)
  rect = rl.Rectangle(0, 0, 1000, 140)
  row.render(rect)
  button = row._control.rect
  pos = MousePos(button.x + button.width / 2, button.y + button.height / 2)

  def tap(where):
    press = MouseEvent(where, 0, True, False, True, 0.0)
    release = MouseEvent(where, 0, False, True, False, 0.1)
    for batch in ([press, release],) if same_frame else ([press], [release]):
      gui_app.mouse_events[:] = batch
      row.render(rect)
    gui_app.mouse_events.clear()

  tap(pos)
  assert "Home Wi-Fi" not in wifi.saved
  assert not asked and not wifi.calls

  # Its former button area becomes part of the row once Forget is hidden.
  tap(pos)
  assert len(asked) == 1 and asked[0][0] == "Enter password"
