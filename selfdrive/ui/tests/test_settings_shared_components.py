"""Regressions for the settings review fixes: scroll touch rejection, the Maintenance
header button, font coverage of on-screen text, and Map Data's shared components.

pytest -q -c /dev/null --confcutdir=selfdrive/ui/tests selfdrive/ui/tests/test_settings_shared_components.py
"""
import ast
import importlib.util
import re
import sys
import types
from pathlib import Path
from typing import NamedTuple

import pyray as rl

ROOT = Path(__file__).resolve().parents[3]
SETTINGS = ROOT / "selfdrive/ui/layouts/settings/starpilot"


class _MouseEvent(NamedTuple):
  pos: object
  slot: int
  left_pressed: bool
  left_released: bool
  left_down: bool
  t: float


def _event(x, y, *, pressed=False, released=False, down=False, t=0.0):
  return _MouseEvent(rl.Vector2(x, y), 0, pressed, released, down, t)


def _scroll_panel_module(monkeypatch):
  """scroll_panel2 with the application module stubbed (importing it headless needs a display)."""
  app = types.ModuleType("openpilot.system.ui.lib.application")
  app.gui_app = types.SimpleNamespace(target_fps=60, last_mouse_event=None)
  app.MouseEvent = _MouseEvent
  monkeypatch.setitem(sys.modules, "openpilot.system.ui.lib.application", app)
  spec = importlib.util.spec_from_file_location("scroll_panel2_under_test", ROOT / "system/ui/lib/scroll_panel2.py")
  module = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(module)
  return module


def test_a_new_press_outside_the_list_is_valid_after_scrolling(monkeypatch):
  """After a drag, fixed controls outside the list (Driving Model header, download manager close)
  must accept the next tap; before the fix it was ignored until a tap landed inside the list."""
  module = _scroll_panel_module(monkeypatch)
  panel = module.GuiScrollPanel2(horizontal=False)
  bounds = rl.Rectangle(0, 200, 1000, 600)

  def feed(*events):
    module.gui_app.mouse_events = list(events)
    panel._process_mouse_events(bounds, bounds.height, 3000)

  t = 0.0
  for y in (500, 480, 440, 380, 320):  # drag inside the list
    feed(_event(400, y, pressed=y == 500, down=True, t=t))
    t += 0.016
  assert not panel.is_touch_valid()  # still scrolling: not a tap
  feed(_event(400, 320, released=True, t=t))
  assert not panel.is_touch_valid()  # the release that ends a scroll is not a tap
  feed(_event(400, 100, pressed=True, down=True, t=t + 1.0))
  assert panel.is_touch_valid()      # a fresh press above the list is a tap


def _font_codepoints() -> set[int]:
  text = (ROOT / "selfdrive/assets/fonts/Inter-Medium.fnt").read_text()
  return {int(code) for code in re.findall(r"^char id=(\d+)", text, re.MULTILINE)}


def test_settings_text_only_uses_characters_the_bundled_font_can_draw():
  """The UI fonts are pre-baked bitmaps; a missing glyph renders as '?' on the device."""
  glyphs = _font_codepoints()
  missing = {}
  for path in SETTINGS.glob("*.py"):
    for node in ast.walk(ast.parse(path.read_text())):
      if isinstance(node, ast.Call) and getattr(node.func, "id", None) in ("tr", "tr_noop") and node.args \
         and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
        bad = {ch for ch in node.args[0].value if ord(ch) > 127 and ord(ch) not in glyphs}
        if bad:
          missing[f"{path.name}:{node.lineno}"] = bad
  assert missing == {}


def _source(path: str) -> str:
  return (SETTINGS / path).read_text()


def test_maintenance_is_a_header_button_like_reset_all():
  source = _source("system_settings.py")
  assert "def use_page_header(self) -> AetherButton:" in source and "return self._maintenance_button" in source
  assert "_draw_breadcrumb_first_aid" not in source and "first_aid" not in source


def test_system_rows_use_the_shared_status_rows():
  source = _source("system_settings.py")
  assert "status=row_status[key]" in source
  keys = re.findall(r'"(\w+)": lambda[^\n]*RowStatus|"(\w+)": lambda: brightness_status', source)
  assert {k for pair in keys for k in pair if k} == {"ScreenBrightness", "ScreenBrightnessOnroad", "ScreenTimeout",
                                                     "ScreenTimeoutOnroad", "DeviceShutdown", "LowVoltageShutdown"}


def test_map_data_uses_shared_components_and_touch_sized_buttons():
  source = _source("maps.py")
  for legacy in ("draw_selection_list_row", "draw_action_pill", "gui_text_box", "FIXED_HEADER_HEIGHT", "BROWSER_INSET"):
    assert legacy not in source
  assert "draw_settings_card_row(" in source and "draw_settings_group(" in source
  assert "REGION_ACTION_HEIGHT = AS.VALUE_PILL_HEIGHT" in source
  assert "STATUS_CARD_HEIGHT = AS.SETTINGS_CARD_INSET * 2 + AS.MIN_TOUCH * 2 + STATUS_BUTTON_GAP" in source
  assert "font_size=26" not in source  # schedule/remove use the shared 34 px button text
  assert "self._remove_button = self._child(" in source


def _confirm_dialog_module(monkeypatch):
  """confirm_dialog with display-dependent modules stubbed."""
  popped = []
  app = types.ModuleType("openpilot.system.ui.lib.application")
  app.gui_app = types.SimpleNamespace(pop_widget=lambda: popped.append(True), font=lambda *_a: None)
  app.FontWeight = types.SimpleNamespace(BOLD=0)
  app.FONT_SCALE = 1.0
  measure = types.ModuleType("openpilot.system.ui.lib.text_measure")
  measure.measure_text_cached = lambda _font, text, size, **_k: types.SimpleNamespace(x=len(text) * size / 2, y=size)
  html = types.ModuleType("openpilot.system.ui.widgets.html_render")
  html.ElementType = types.SimpleNamespace(P="p", H1="h1", H2="h2", H3="h3")
  html.HtmlRenderer = lambda **_k: types.SimpleNamespace(parse_html_content=lambda _t: None,
                                                         styles={tag: {"margin_bottom": 16} for tag in ("h1", "h2", "h3")})
  scroller = types.ModuleType("openpilot.system.ui.widgets.scroller_tici")
  scroller.Scroller = lambda *_a, **_k: None
  widgets = types.ModuleType("openpilot.system.ui.widgets")
  widgets.DialogResult = types.SimpleNamespace(CANCEL=0, CONFIRM=1)

  class Widget:
    def __init__(self):
      pass

    def _child(self, widget):
      return widget
  widgets.Widget = Widget

  class AetherButton:
    def __init__(self, text, callback, **kwargs):
      self.text, self.callback, self.kwargs = text, callback, kwargs
  grid = types.ModuleType("openpilot.selfdrive.ui.layouts.settings.starpilot.aethergrid")
  grid.AetherButton, grid.draw_settings_card = AetherButton, lambda *_a, **_k: None
  multilang = types.ModuleType("openpilot.system.ui.lib.multilang")
  multilang.tr = str
  for name, module in {app.__name__: app, measure.__name__: measure, html.__name__: html, scroller.__name__: scroller,
                       widgets.__name__: widgets, grid.__name__: grid, multilang.__name__: multilang}.items():
    monkeypatch.setitem(sys.modules, name, module)
  spec = importlib.util.spec_from_file_location("confirm_dialog_under_test", ROOT / "system/ui/widgets/confirm_dialog.py")
  module = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(module)
  return module, popped


def test_confirm_dialog_closes_once_and_reports_the_choice(monkeypatch):
  module, popped = _confirm_dialog_module(monkeypatch)
  results = []
  dialog = module.ConfirmDialog("Reset all?", "Reset All", callback=results.append)
  assert dialog._cancel_button.text == "Cancel" and dialog._cancel_button.kwargs == {"neutral": True}
  assert dialog._confirm_button.text == "Reset All" and dialog._confirm_button.kwargs["emphasized"]
  assert all(style["margin_bottom"] == module.RICH_HEADING_GAP for style in dialog._html_renderer.styles.values())
  dialog._confirm_button.callback()
  dialog._cancel_button.callback()  # a second tap in the same frame must not report twice
  assert results == [1] and popped == [True]

  cancelled = module.ConfirmDialog("Forget network?", "Forget", callback=results.append)
  cancelled._cancel_button_callback()
  assert results == [1, 0]


def test_alert_has_one_button_and_long_messages_wrap(monkeypatch):
  module, _ = _confirm_dialog_module(monkeypatch)
  alert = module.alert_dialog("Park to remove downloaded maps.")
  assert alert._cancel_text == "" and alert._confirm_button.text == "OK"
  lines = module._wrap(None, "word " * 200, 600, 40, 3)
  assert len(lines) == 3 and lines[-1].endswith("...")
  assert module._wrap(None, "First line\nSecond line", 2000, 40, 6) == ["First line", "Second line"]


def test_conditional_drive_mode_rows_use_the_shared_status_rows():
  source = _source("longitudinal.py")
  assert "status=row_status[key]" in source
  keys = set(re.findall(r'"(\w+)": threshold_status\(', source))
  assert keys == {"CESpeed", "CESpeedLead", "CESignalSpeed", "CEModelStopTime", "CCMSpeed", "CCMSpeedLead", "CCMSetSpeedMargin"}
  # Row heights come from the rows themselves (status rows are taller), not a fixed adjustor height.
  assert "adjustor_row_height" not in source[source.index("class ConditionalDriveModeView"):source.index("class StarPilotLongitudinalLayout")]


def test_group_two_pages_use_the_shared_rows_buttons_and_empty_state():
  for page in ("driving_model.py", "navigation.py", "simple_download_manager.py"):
    source = _source(page)
    for legacy in ("draw_selection_list_row", "draw_empty_state_card", "AetherChip", "draw_action_rail", "HEADER_BUTTON_HEIGHT"):
      assert legacy not in source, f"{page} still uses {legacy}"
    assert "draw_settings_card_row(" in source and "draw_settings_empty_state(" in source, page
  driving_model = _source("driving_model.py")
  assert "AetherSegmentedControl(" in driving_model and "on_reselect=self._on_sort_reselect" in driving_model
  assert "def use_page_header(self) -> AetherButton:" in driving_model
  assert "AetherSegmentedControl(" in _source("simple_download_manager.py")


def test_row_action_pills_are_padded_like_buttons():
  """Row pills (Search, Select, Download...) get AetherButton's side padding: a card inset either side."""
  source = _source("aethergrid.py")
  row = source[source.index("def draw_settings_card_row("):source.index("def wrap_subtitle(")]
  assert "action_text_size).x + AS.SETTINGS_CARD_INSET * 2" in row
  button = source[source.index("class AetherButton"):]
  assert "text_width + AS.SETTINGS_CARD_INSET * 2" in button[:button.index("def measure_height")]
