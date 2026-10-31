import pyray as rl
import pytest

from openpilot.system.ui.lib.application import MousePos
from openpilot.system.ui.widgets import DialogResult
from openpilot.selfdrive.ui.tandem import (BottomNav, Component, Dialog, Segmented, Sidebar, SidebarItem, Slider, Stepper, Switch, resolve,
                                               tokens as T)
from openpilot.selfdrive.ui.tandem.layout import FILL, Align, Fill, column, grid, grow, inset, place, row


def _r(rect: rl.Rectangle) -> tuple[float, float, float, float]:
  return round(rect.x, 3), round(rect.y, 3), round(rect.width, 3), round(rect.height, 3)


# ── layout ──

def test_row_gives_fixed_sizes_first_and_splits_the_rest_by_weight():
  parts = row(rl.Rectangle(0, 0, 1000, 50), [100, FILL, Fill(3), 200], gap=10)
  assert [_r(p) for p in parts] == [(0, 0, 100, 50), (110, 0, 167.5, 50), (287.5, 0, 502.5, 50), (800, 0, 200, 50)]


def test_column_never_goes_negative_when_fixed_sizes_overflow():
  top, rest = column(rl.Rectangle(0, 0, 100, 50), [80, FILL], gap=10)
  assert _r(top) == (0, 0, 100, 80)
  assert rest.height == 0


def test_grid_fills_left_to_right_then_down():
  cells = grid(rl.Rectangle(0, 0, 290, 210), columns=3, rows=2, gap=10)
  assert [_r(c)[:2] for c in cells] == [(0, 0), (100, 0), (200, 0), (0, 110), (100, 110), (200, 110)]
  assert all(_r(c)[2:] == (90, 100) for c in cells)


def test_inset_place_and_grow():
  assert _r(inset(rl.Rectangle(0, 0, 100, 100), 10, left=20)) == (20, 10, 70, 80)
  assert _r(place(rl.Rectangle(0, 0, 100, 100), 20, 10, Align.END, Align.CENTER)) == (80, 45, 20, 10)
  assert _r(grow(rl.Rectangle(50, 50, 40, 40), 112, 20)) == (14, 50, 112, 40)


def test_tokens_convert_mock_pixels_to_device_pixels():
  assert T.px(1125) == 2160
  assert T.ROW_HEIGHT == T.px(60)
  assert T.MIN_TOUCH >= 112


# ── values ──

def test_resolve_calls_getters_but_not_raylib_structs():
  color = rl.Color(1, 2, 3, 4)
  assert resolve(color) is color
  assert resolve(lambda: 5) == 5
  assert resolve("x") == "x"


# ── controls ──

def test_stepper_steps_and_clamps():
  value = {"v": 9.0}
  stepper = Stepper(lambda: value["v"], lambda v: value.__setitem__("v", v), minimum=-10, maximum=10, step=1)
  assert stepper.stepped(1) == 10
  value["v"] = 10
  assert stepper.stepped(1) == 10
  assert stepper.stepped(-1) == 9
  value["v"] = -10
  assert stepper.stepped(-1) == -10


def test_slider_snaps_to_step_and_respects_floor():
  slider = Slider(50, lambda v: None, minimum=0, maximum=100, step=5, floor=25)
  slider.set_rect(rl.Rectangle(0, 0, 1028, 66))
  assert slider.value_at(slider.x_for(62)) == 60
  assert slider.value_at(slider.x_for(10)) == 25
  assert slider.value_at(-100) == 25
  assert slider.value_at(5000) == 100


def test_switch_reports_the_flipped_value():
  changes = []
  switch = Switch(True, changes.append)
  switch._handle_mouse_release(MousePos(0, 0))
  assert changes == [False]


def test_segmented_tap_picks_the_segment_under_the_finger():
  changes = []
  seg = Segmented(["A", "B", "C"], selected=0, on_change=changes.append, equal=True)
  seg.set_rect(rl.Rectangle(0, 0, 308, 40))
  rects = seg.segment_rects()
  seg._handle_mouse_release(MousePos(rects[2].x + 5, 20))
  seg._handle_mouse_release(MousePos(rects[0].x + 5, 20))   # already selected: no change
  assert changes == [2]


def test_small_controls_accept_touches_across_min_touch():
  switch = Switch(False)
  switch.set_rect(rl.Rectangle(500, 500, 60, 40))
  hit = switch._hit_rect
  assert hit.width >= T.MIN_TOUCH and hit.height >= T.MIN_TOUCH


def test_dialog_reports_its_result():
  results = []
  dialog = Dialog("Delete?", "Gone for good.", "Delete", results.append)
  dialog._confirm._click_callback()
  dialog._cancel._click_callback()
  assert results == [DialogResult.CONFIRM, DialogResult.CANCEL]
  assert dialog.result == DialogResult.CANCEL


# ── chrome ──

def test_sidebar_selects_only_a_different_visible_item():
  opened = []
  sidebar = Sidebar("Driving", [SidebarItem("A", lambda: opened.append("A")), SidebarItem("Hidden", visible=False),
                                SidebarItem("C", lambda: opened.append("C"))], selected=0)
  sidebar.set_rect(rl.Rectangle(0, 0, 300, 600))
  rects = dict(sidebar.item_rects())
  assert set(rects) == {0, 2}
  for index in (0, 2):
    pos = MousePos(rects[index].x + 10, rects[index].y + 10)
    sidebar._handle_mouse_press(pos)
    sidebar._handle_mouse_release(pos)
  assert opened == ["C"]


def test_bottom_nav_selects_the_tab_that_was_pressed_and_released():
  picked = []
  nav = BottomNav(["StarPilot", "Device", "Network"], selected=0, on_select=picked.append)
  nav.set_rect(rl.Rectangle(0, 0, 2160, T.NAV_HEIGHT))
  tabs = nav.tab_rects()
  inside = MousePos(tabs[2].x + 10, tabs[2].y + 10)
  nav._handle_mouse_press(inside)
  nav._handle_mouse_release(inside)
  nav._handle_mouse_press(MousePos(tabs[1].x + 10, tabs[1].y + 10))
  nav._handle_mouse_release(inside)                       # dragged to another tab: ignored
  assert picked == [2]


@pytest.mark.parametrize("cls", [BottomNav, Sidebar])
def test_containers_do_not_grow_their_touch_area(cls):
  assert issubclass(cls, Component) and cls.grow_touch_target is False


# ── fonts ──

def _figtree_codepoints() -> set[int]:
  import re
  from pathlib import Path
  fnt = Path(__file__).resolve().parents[3] / "assets/fonts/Figtree-Medium.fnt"
  return {int(code) for code in re.findall(r"^char id=(\d+)", fnt.read_text(), re.MULTILINE)}


def _ui_strings() -> list[tuple[str, str]]:
  """Translated strings in StarPilot's settings panels, and every non-docstring string in this package."""
  import ast
  from pathlib import Path
  root = Path(__file__).resolve().parents[2]
  found = []
  for path in (root / "layouts/settings/starpilot").glob("*.py"):
    for node in ast.walk(ast.parse(path.read_text())):
      if isinstance(node, ast.Call) and getattr(node.func, "id", None) in ("tr", "tr_noop") and node.args \
         and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
        found.append((path.name, node.args[0].value))
  for path in (root / "tandem").glob("*.py"):
    tree = ast.parse(path.read_text())
    docstrings = {id(n.value) for n in ast.walk(tree) if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)}
    found += [(path.name, n.value) for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docstrings]
  return found


def test_figtree_atlas_can_draw_every_ui_string():
  """The atlases are pre-baked; a missing glyph renders as '?' on the device."""
  glyphs = _figtree_codepoints()
  strings = _ui_strings()
  scanned = {name for name, _ in strings}
  assert {"controls.py", "lateral.py"} <= scanned, "string scan found nothing; check the paths"
  missing = {(name, ch) for name, value in strings for ch in value if ord(ch) > 127 and ch.isprintable() and ord(ch) not in glyphs}
  assert not missing, sorted(missing)
