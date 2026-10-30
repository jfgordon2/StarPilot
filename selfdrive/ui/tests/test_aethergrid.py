import importlib
import math
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


MODULE_NAME = "openpilot.selfdrive.ui.layouts.settings.starpilot.aethergrid"
PANEL_MODULE_NAME = "openpilot.selfdrive.ui.layouts.settings.starpilot.panel"
SECTIONED_PANEL_MODULE_NAME = "openpilot.selfdrive.ui.layouts.settings.starpilot.sectioned_panel"


@pytest.fixture(autouse=True)
def restore_ui_modules():
  modules = {name: module for name, module in sys.modules.items() if name == "pyray" or name.startswith("openpilot.")}
  yield
  for name in tuple(sys.modules):
    if (name == "pyray" or name.startswith("openpilot.")) and name not in modules:
      sys.modules.pop(name, None)
  sys.modules.update(modules)


def _clear_modules(*module_names):
  for module_name in module_names:
    sys.modules.pop(module_name, None)


def _register_modules(module_map):
  for name, module in module_map.items():
    sys.modules[name] = module


def _make_texture(width=80, height=80):
  return types.SimpleNamespace(width=width, height=height)


def _collision_rect(a, b):
  x, y = max(a.x, b.x), max(a.y, b.y)
  return types.SimpleNamespace(x=x, y=y, width=max(0, min(a.x + a.width, b.x + b.width) - x),
                               height=max(0, min(a.y + a.height, b.y + b.height) - y))


def _install_aethergrid_stubs():
  rl = types.SimpleNamespace(
    Color=lambda r, g, b, a=255: types.SimpleNamespace(r=r, g=g, b=b, a=a),
    Rectangle=lambda x=0, y=0, width=0, height=0: types.SimpleNamespace(x=x, y=y, width=width, height=height),
    Vector2=lambda x=0, y=0: types.SimpleNamespace(x=x, y=y),
    Texture2D=type("Texture2D", (), {}),
    Font=type("Font", (), {}),
    GuiTextAlignment=types.SimpleNamespace(TEXT_ALIGN_CENTER=0, TEXT_ALIGN_LEFT=1, TEXT_ALIGN_RIGHT=2),
    BlendMode=types.SimpleNamespace(BLEND_ALPHA_PREMULTIPLY=1),
    WHITE=types.SimpleNamespace(r=255, g=255, b=255, a=255),
    draw_rectangle_rounded=lambda *a, **k: None,
    draw_rectangle_rounded_lines_ex=lambda *a, **k: None,
    draw_rectangle_rec=lambda *a, **k: None,
    draw_rectangle=lambda *a, **k: None,
    draw_rectangle_gradient_v=lambda *a, **k: None,
    draw_ring=lambda *a, **k: None,
    draw_circle=lambda *a, **k: None,
    draw_circle_v=lambda *a, **k: None,
    draw_line=lambda *a, **k: None,
    draw_line_ex=lambda *a, **k: None,
    draw_triangle=lambda *a, **k: None,
    draw_texture_pro=lambda *a, **k: None,
    begin_blend_mode=lambda *a, **k: None,
    end_blend_mode=lambda *a, **k: None,
    draw_text_ex=lambda *a, **k: None,
    check_collision_point_rec=lambda p, r: (r.x <= p.x <= r.x + r.width) and (r.y <= p.y <= r.y + r.height),
    get_collision_rec=_collision_rect,
    get_frame_time=lambda: 0.016,
    get_mouse_position=lambda: types.SimpleNamespace(x=0, y=0),
    is_key_pressed=lambda key: False,
    KeyboardKey=types.SimpleNamespace(KEY_ESCAPE=256),
  )
  sys.modules["pyray"] = rl

  app_mod = types.ModuleType("openpilot.system.ui.lib.application")
  app_mod.FontWeight = types.SimpleNamespace(BOLD=700, NORMAL=400, MEDIUM=500, SEMI_BOLD=600)
  app_mod.MousePos = type("MousePos", (), {})
  app_mod.MouseEvent = type("MouseEvent", (), {})
  app_mod.FONT_SCALE = 1.0
  app_mod.font_fallback = lambda font: font
  app_mod.gui_app = types.SimpleNamespace(
    width=1920,
    height=1080,
    last_mouse_event=types.SimpleNamespace(pos=types.SimpleNamespace(x=0, y=0)),
    font=lambda *_a, **_k: object(),
    texture=lambda *_a, **_k: _make_texture(),
    pop_widget=lambda: None,
  )
  sys.modules["openpilot.system.ui.lib.application"] = app_mod

  scroll_panel_mod = types.ModuleType("openpilot.system.ui.lib.scroll_panel2")
  class GuiScrollPanel2:
    def __init__(self, horizontal=True, handle_out_of_bounds=True):
      self._enabled = True
      self._offset = 0.0

    def set_enabled(self, enabled):
      self._enabled = enabled

    def update(self, bounds, content_size):
      return 0.0

    def is_touch_valid(self):
      return True

    def set_offset(self, offset):
      self._offset = offset

  scroll_panel_mod.GuiScrollPanel2 = GuiScrollPanel2
  sys.modules["openpilot.system.ui.lib.scroll_panel2"] = scroll_panel_mod

  multilang_mod = types.ModuleType("openpilot.system.ui.lib.multilang")
  multilang_mod.tr = lambda text: text
  sys.modules["openpilot.system.ui.lib.multilang"] = multilang_mod

  text_measure_mod = types.ModuleType("openpilot.system.ui.lib.text_measure")
  text_measure_mod.measure_text_cached = lambda *_a, **_k: types.SimpleNamespace(x=100, y=20)
  sys.modules["openpilot.system.ui.lib.text_measure"] = text_measure_mod

  widgets_mod = types.ModuleType("openpilot.system.ui.widgets")
  widgets_mod.__path__ = [str(Path(__file__).parents[3] / "system/ui/widgets")]

  class Widget:
    def __init__(self):
      self._rect = rl.Rectangle()
      self._parent_rect = None
      self._enabled = True
      self.is_pressed = False
      self._children = []

    def _child(self, widget):
      self._children.append(widget)
      return widget

    @property
    def enabled(self):
      return self._enabled() if callable(self._enabled) else self._enabled

    def set_rect(self, rect):
      self._rect = rect

    def set_parent_rect(self, rect):
      self._parent_rect = rect

    def render(self, rect):
      self._rect = rect
      return self._render(rect)

    def set_click_callback(self, callback):
      self.on_click = callback

    def set_touch_valid_callback(self, callback):
      self._touch_valid_callback = callback

    def set_enabled(self, enabled):
      self._enabled = enabled

    def _render(self, rect):
      return None

    def hide_event(self):
      pass

  widgets_mod.Widget = Widget
  widgets_mod.DialogResult = types.SimpleNamespace(CONFIRM=1, CANCEL=0, NO_ACTION=-1)
  sys.modules["openpilot.system.ui.widgets"] = widgets_mod

  option_dialog_mod = types.ModuleType("openpilot.system.ui.widgets.option_dialog")
  option_dialog_mod.MultiOptionDialog = type("MultiOptionDialog", (), {})
  sys.modules["openpilot.system.ui.widgets.option_dialog"] = option_dialog_mod

  label_mod = types.ModuleType("openpilot.system.ui.widgets.label")
  label_mod.gui_label = lambda *a, **k: None
  sys.modules["openpilot.system.ui.widgets.label"] = label_mod

  asset_loader_mod = types.ModuleType("openpilot.selfdrive.ui.layouts.settings.starpilot.asset_loader")
  asset_loader_mod.starpilot_texture = lambda *_a, **_k: _make_texture()
  sys.modules["openpilot.selfdrive.ui.layouts.settings.starpilot.asset_loader"] = asset_loader_mod


def _install_panel_stubs(aethergrid):
  sectioned_mod = types.ModuleType(SECTIONED_PANEL_MODULE_NAME)
  sectioned_mod.SectionedTileLayout = type("SectionedTileLayout", (), {})
  sectioned_mod.TileSection = type("TileSection", (), {})
  starpilot_variables_mod = types.ModuleType("openpilot.starpilot.common.starpilot_variables")
  starpilot_variables_mod.update_starpilot_toggles = lambda: None

  _register_modules({
    SECTIONED_PANEL_MODULE_NAME: sectioned_mod,
    "openpilot.common.params": types.SimpleNamespace(Params=type("Params", (), {}), UnknownKeyName=Exception),
    "openpilot.starpilot.common.starpilot_variables": starpilot_variables_mod,
    MODULE_NAME: aethergrid,
  })


def _import_module(module_name):
  _install_aethergrid_stubs()
  _clear_modules(module_name)
  return importlib.import_module(module_name)


def _import_aethergrid():
  return _import_module(MODULE_NAME)


def _import_panel(monkeypatch_module=None):
  aethergrid = _import_aethergrid()
  _install_panel_stubs(aethergrid)
  _clear_modules(PANEL_MODULE_NAME)
  return importlib.import_module(PANEL_MODULE_NAME)


def _import_real_sectioned_panel():
  _install_aethergrid_stubs()
  _clear_modules(SECTIONED_PANEL_MODULE_NAME)
  return importlib.import_module(SECTIONED_PANEL_MODULE_NAME)


class RenderSpy:
  def __init__(self):
    self.rects = []
    self.parent_rect = None

  def render(self, rect):
    self.rects.append(rect)

  def show_event(self):
    pass

  def hide_event(self):
    pass

  def set_parent_rect(self, rect):
    self.parent_rect = rect


@pytest.mark.parametrize("height, body_size, body_height", [(208, 26, None), (208, 24, None), (400, 26, 80), (128, 26, None)])
@pytest.mark.parametrize("body", ["A long explanation " * 30, "unbroken" * 50, "First line\nSecond line\nThird line"])
def test_empty_state_body_wraps_within_card(height, body_size, body_height, body):
  mod = _import_aethergrid()
  wrapper = importlib.import_module("openpilot.system.ui.lib.wrap_text")
  mod.FONT_SCALE = 1.242
  font = types.SimpleNamespace(texture=types.SimpleNamespace(id=1))
  mod.gui_app.font = lambda *_: font
  labels = []

  def measure(_font, text, size, spacing=0):
    return types.SimpleNamespace(x=len(text) * size * mod.FONT_SCALE / 2, y=size * mod.FONT_SCALE)

  with patch.object(mod, "measure_text_cached", measure), patch.object(wrapper, "measure_text_cached", measure), \
       patch.object(mod, "gui_label", lambda rect, text, *a, **kw: labels.append((rect, text))):
    mod.draw_empty_state_card(mod.rl.Rectangle(0, 0, 500, height), "Title", body,
                              title_size=30, body_size=body_size, body_height=body_height)

  body_labels = labels[1:]
  assert body_labels
  for rect, text in body_labels:
    assert rect.y >= labels[0][0].y + labels[0][0].height
    assert rect.y + rect.height <= height
    assert measure(font, text, body_size).x <= rect.width
  if body.startswith(("A long", "unbroken")):
    assert body_labels[-1][1].endswith("...")


@pytest.mark.parametrize("action_text", ["DELETE", "DOWNLOAD", "Current", "Reset", "Set Key"])
def test_auto_action_pill_keeps_readable_text_inside_action_rail(action_text):
  mod = _import_aethergrid()
  mod.FONT_SCALE = 1.242
  draws = []

  def measure(_font, text, size, spacing=0):
    return types.SimpleNamespace(x=len(text) * size * mod.FONT_SCALE * 0.65, y=size * mod.FONT_SCALE)

  with patch.object(mod, "measure_text_cached", measure), \
       patch.object(mod.rl, "draw_text_ex", lambda font, text, pos, size, spacing, color: draws.append((text, pos, size))):
    pill = mod.draw_selection_list_row(mod.rl.Rectangle(0, 0, 1500, 128), title="Asset", action_text=action_text,
                                      action_pill=True, action_text_size=26)

  text, pos, size = next(draw for draw in draws if draw[0] == action_text)
  assert size == 26
  assert pill.x >= 1500 - mod.AETHER_LIST_METRICS.action_width
  assert pill.x + pill.width <= 1500
  assert pos.x >= pill.x + 11
  assert pos.x + measure(None, text, size).x <= pill.x + pill.width - 11


def test_action_pill_preserves_explicit_width_and_rail_limit():
  mod = _import_aethergrid()
  row = mod.rl.Rectangle(0, 0, 1500, 128)
  for requested_width in (120, 1000):
    pill = mod.draw_selection_list_row(row, title="Asset", action_text="Download", action_pill=True,
                                      action_pill_width=requested_width)
    assert pill.width == min(requested_width, mod.AETHER_LIST_METRICS.action_width - 28)


class TestAethergridContracts(unittest.TestCase):
  def test_aethergrid_module_imports_with_headless_stubs(self):
    mod = _import_aethergrid()

    self.assertTrue(hasattr(mod, "TileGrid"))
    self.assertTrue(hasattr(mod, "HubTile"))
    self.assertTrue(hasattr(mod, "ToggleTile"))
    self.assertTrue(hasattr(mod, "ValueTile"))
    self.assertTrue(hasattr(mod, "RadioTileGroup"))
    self.assertTrue(hasattr(mod, "AetherSliderDialog"))


  def test_tile_grid_column_contract_stays_stable(self):
    mod = _import_aethergrid()
    grid = mod.TileGrid(columns=None, padding=mod.SPACING.tile_gap)

    self.assertEqual(grid.get_column_count(1), 1)
    self.assertEqual(grid.get_column_count(2), 2)
    self.assertEqual(grid.get_column_count(3), 3)
    self.assertEqual(grid.get_column_count(4), 2)
    self.assertEqual(grid.get_column_count(5), 3)
    self.assertEqual(grid.get_column_count(7), 4)


  def test_build_list_panel_frame_contract(self):
    mod = _import_aethergrid()
    frame = mod.build_list_panel_frame(mod.rl.Rectangle(0, 0, 1920, 1080))

    self.assertGreater(frame.shell.width, 0)
    self.assertEqual(frame.header.height, mod.AETHER_LIST_METRICS.header_height)
    self.assertGreater(frame.scroll.height, 0)


  def test_hit_rect_keeps_touch_slop_after_surface_flattening(self):
    mod = _import_aethergrid()
    tile = mod.AetherTile(surface_color="#3B82F6")
    tile.set_rect(mod.rl.Rectangle(100, 200, 300, 150))
    hit = tile._hit_rect

    self.assertGreater(hit.width, tile._rect.width)
    self.assertGreater(hit.height, tile._rect.height)


  def test_hub_tile_preserves_status_progress_api(self):
    mod = _import_aethergrid()
    tile = mod.HubTile("Driving Controls", "Desc", bg_color="#3B82F6", get_status=lambda: "Download 50%")

    self.assertEqual(tile.get_status(), "Download 50%")

  def test_custom_icon_draws_directly_while_cache_fill_is_pending(self):
    mod = _import_aethergrid()
    scribble = sys.modules["openpilot.selfdrive.ui.layouts.settings.starpilot.scribble"]
    geometry = MagicMock()
    cache = MagicMock(return_value=None)

    color = mod.rl.Color(255, 255, 255, 255)
    with patch.object(scribble, "_draw_custom_icon_geometry", geometry), \
         patch.object(scribble.gui_app, "cached_render_texture", cache, create=True):
      scribble.draw_custom_icon("sound", 10, 20, 1.0, color)

    cache.assert_called_once()
    geometry.assert_called_once_with("sound", 10, 20, 1.0, color)

  def test_custom_icon_uses_completed_cache_without_redrawing_geometry(self):
    mod = _import_aethergrid()
    scribble = sys.modules["openpilot.selfdrive.ui.layouts.settings.starpilot.scribble"]
    geometry = MagicMock()
    cache = MagicMock(return_value=object())
    draw_texture = MagicMock()

    with patch.object(scribble, "_draw_custom_icon_geometry", geometry), \
         patch.object(scribble.gui_app, "cached_render_texture", cache, create=True), \
         patch.object(scribble.rl, "draw_texture_pro", draw_texture):
      scribble.draw_custom_icon("sound", 10, 20, 1.0, mod.rl.Color(255, 255, 255, 255))

    geometry.assert_not_called()
    draw_texture.assert_called_once()
    destination = draw_texture.call_args.args[2]
    self.assertLess(destination.x, 10)
    self.assertLess(destination.y, 20)

  def test_translucent_custom_icon_uses_premultiplied_blending(self):
    mod = _import_aethergrid()
    scribble = sys.modules["openpilot.selfdrive.ui.layouts.settings.starpilot.scribble"]
    geometry = MagicMock()
    cache = MagicMock(return_value=object())
    begin_blend = MagicMock()
    end_blend = MagicMock()

    color = mod.rl.Color(160, 170, 185, 80)
    with patch.object(scribble, "_draw_custom_icon_geometry", geometry), \
         patch.object(scribble.gui_app, "cached_render_texture", cache, create=True), \
         patch.object(scribble.rl, "begin_blend_mode", begin_blend), \
         patch.object(scribble.rl, "end_blend_mode", end_blend):
      scribble.draw_custom_icon("first_aid", 10, 20, 0.8, color)

    cache.assert_called_once()
    geometry.assert_not_called()
    begin_blend.assert_called_once_with(mod.rl.BlendMode.BLEND_ALPHA_PREMULTIPLY)
    end_blend.assert_called_once()

  def test_tile_grid_reflows_to_wider_tiles_when_width_is_tight(self):
    mod = _import_aethergrid()
    grid = mod.TileGrid(columns=None, padding=mod.SPACING.tile_gap)

    spies = [RenderSpy() for _ in range(7)]
    for spy in spies:
      grid.add_tile(spy)

    grid.render(mod.rl.Rectangle(0, 0, 700, 500))

    self.assertTrue(spies[0].rects)
    self.assertGreater(spies[0].rects[0].width, 300)


  def test_toggle_and_value_tiles_keep_enabled_contract(self):
    mod = _import_aethergrid()
    toggle = mod.ToggleTile("Feature", lambda: True, lambda _v: None, is_enabled=lambda: False)
    value = mod.ValueTile("Value", lambda: "42", lambda: None, is_enabled=lambda: False)

    self.assertFalse(toggle.enabled)
    self.assertFalse(value.enabled)

  def test_disabled_value_tile_does_not_trigger_click(self):
    mod = _import_aethergrid()
    on_click = MagicMock()
    value = mod.ValueTile("Value", lambda: "42", on_click, is_enabled=lambda: False)
    value.set_rect(mod.rl.Rectangle(0, 0, 300, 150))

    value._handle_mouse_press(types.SimpleNamespace(x=10, y=10))
    value._handle_mouse_release(types.SimpleNamespace(x=10, y=10))

    on_click.assert_not_called()


  def test_slider_dialog_keeps_color_and_callback_contract(self):
    mod = _import_aethergrid()
    captured = []
    dialog = mod.AetherSliderDialog("Test", 0, 10, 1, 5, lambda result, value: captured.append((result, value)), color="#8B5CF6")

    self.assertGreaterEqual(dialog._color.r, 0)
    self.assertEqual(dialog._current_val, 5)


  def test_radio_tile_group_preserves_selection_api(self):
    mod = _import_aethergrid()
    group = mod.RadioTileGroup("", ["A", "B", "C"], 1, lambda idx: None)
    group.set_index(2)

    self.assertEqual(group.current_index, 2)

  def test_zero_span_sliders_do_not_divide_by_zero(self):
    mod = _import_aethergrid()
    slider = mod.AetherSlider(5, 5, 1, 5, lambda _v: None)
    thumb_x = slider._get_thumb_x(mod.rl.Rectangle(0, 0, 320, 80))

    self.assertGreaterEqual(thumb_x, 0)

  def test_panel_module_can_import_against_refactored_aethergrid(self):
    panel_mod = _import_panel()

    self.assertTrue(hasattr(panel_mod, "StarPilotPanel"))
    self.assertTrue(hasattr(panel_mod, "create_tile_panel"))

  def test_sectioned_layout_short_height_uses_scrollable_compact_profile(self):
    mod = _import_aethergrid()
    sectioned_mod = _import_real_sectioned_panel()

    layout = sectioned_mod.SectionedTileLayout()
    grid = mod.TileGrid(columns=2, padding=mod.SPACING.tile_gap, uniform_width=True)

    for _ in range(6):
      grid.add_tile(RenderSpy())

    layout.set_sections([sectioned_mod.TileSection("Test", grid)])
    title_h, title_gap, section_gap, row_h = layout._layout_profile(mod.rl.Rectangle(0, 0, 800, 220), layout._sections)

    self.assertGreaterEqual(row_h, 0)
    self.assertLessEqual(title_h, layout._title_height)

  def test_slider_dialog_on_change_callback(self):
    mod = _import_aethergrid()
    captured_changes = []
    captured_close = []

    dialog = mod.AetherSliderDialog(
      "Test", 0, 10, 1, 5,
      on_close=lambda res, val: captured_close.append((res, val)),
      color="#8B5CF6",
      on_change=lambda val: captured_changes.append(val)
    )

    # Run render to compute button and track rects
    dialog._render(mod.rl.Rectangle(0, 0, 1920, 1080))

    # Mock mouse position hitting the plus rect and press it
    plus_center = mod.rl.Vector2(
      dialog._plus_rect.x + dialog._plus_rect.width / 2,
      dialog._plus_rect.y + dialog._plus_rect.height / 2
    )

    # Mock collision detection to return True when checking the plus button
    old_collision = mod.rl.check_collision_point_rec
    def mock_collision(point, rec):
      if rec == dialog._plus_rect:
        return True
      return False
    mod.rl.check_collision_point_rec = mock_collision

    try:
      dialog._handle_mouse_press(plus_center)
      dialog._handle_mouse_release(plus_center)
    finally:
      mod.rl.check_collision_point_rec = old_collision

    self.assertEqual(dialog._current_val, 6)
    self.assertEqual(captured_changes, [6])

  def test_tile_grid_measure_height_with_explicit_tile_height(self):
    mod = _import_aethergrid()
    grid = mod.TileGrid(columns=2, padding=10, tile_height=140)
    for _ in range(5):
      grid.add_tile(RenderSpy())
    
    h = grid.measure_height(500)
    self.assertEqual(h, 740)

  def test_tile_grid_measure_height_with_min_max_clamping(self):
    mod = _import_aethergrid()
    grid = mod.TileGrid(columns=2, padding=10, tile_height=None, min_tile_height=100.0, max_tile_height=150.0)
    for _ in range(5):
      grid.add_tile(RenderSpy())
    
    h = grid.measure_height(500)
    self.assertEqual(h, 790)

    spy = RenderSpy()
    grid.add_tile(spy)
    grid.render(mod.rl.Rectangle(0, 0, 500, 1000))
    self.assertTrue(spy.rects)
    self.assertEqual(spy.rects[0].height, 150.0)

  def test_tile_grid_measure_height_default_fallback(self):
    mod = _import_aethergrid()
    grid = mod.TileGrid(columns=2, padding=10, tile_height=None)
    for _ in range(5):
      grid.add_tile(RenderSpy())
    
    h = grid.measure_height(500)
    self.assertEqual(h, 940)

  def test_tile_grid_render_top_left_aligned_with_tile_height(self):
    mod = _import_aethergrid()
    grid = mod.TileGrid(columns=2, padding=10, tile_height=140)
    spy = RenderSpy()
    grid.add_tile(spy)
    
    grid.render(mod.rl.Rectangle(0, 50, 500, 300))
    self.assertTrue(spy.rects)
    self.assertEqual(spy.rects[0].y, 130)
    self.assertEqual(spy.rects[0].x, 0)

  def test_disabled_tiles_hud_mode_rendering(self):
    mod = _import_aethergrid()
    
    # ToggleTile disabled
    toggle = mod.ToggleTile(
      title="Test Loud",
      get_state=lambda: True,
      set_state=lambda s: None,
      is_enabled=lambda: False,
    )
    # Grid toggles share the settings-row component, including disabled state.
    with patch.object(mod, "draw_settings_card_row") as row:
      toggle.render(mod.rl.Rectangle(0, 0, 500, 184))
    self.assertFalse(row.call_args.kwargs["enabled"])
    self.assertEqual(row.call_args.kwargs["subtitle"], "Unavailable")

    # ValueTile disabled
    spy_called = []
    value_tile = mod.ValueTile(
      title="Test Value",
      get_value=lambda: "Off",
      on_click=lambda: None,
      is_enabled=lambda: False
    )
    orig_value_hud_bg = value_tile._render_hud_background
    def spy_value_hud_bg(*a, **k):
      spy_called.append("value")
      return orig_value_hud_bg(*a, **k)
    value_tile._render_hud_background = spy_value_hud_bg
    value_tile.render(mod.rl.Rectangle(0, 0, 150, 130))
    self.assertIn("value", spy_called)

    # SliderTile disabled
    slider_tile = mod.SliderTile(
      title="Test Slider",
      get_value=lambda: 50.0,
      set_value=lambda v: None,
      min_val=0.0,
      max_val=100.0,
      step=1.0,
      is_enabled=lambda: False
    )
    orig_slider_hud_bg = slider_tile._render_hud_background
    def spy_slider_hud_bg(*a, **k):
      spy_called.append("slider")
      return orig_slider_hud_bg(*a, **k)
    slider_tile._render_hud_background = spy_slider_hud_bg
    slider_tile.render(mod.rl.Rectangle(0, 0, 150, 130))
    self.assertIn("slider", spy_called)

  def test_tile_grid_force_square(self):
    mod = _import_aethergrid()
    grid = mod.TileGrid(columns=2, padding=10, min_tile_width=100, force_square=True)
    spies = [RenderSpy() for _ in range(5)]
    for spy in spies:
      grid.add_tile(spy)
    
    # col_w = (500 - 10) / 2 = 245
    # rows = 3, gap_h = 2 * 10 = 20
    # expected height = 3 * 245 + 20 = 755
    self.assertEqual(grid.measure_height(500), 755)
    
    grid.render(mod.rl.Rectangle(0, 0, 500, 300))
    self.assertTrue(spies[0].rects)
    self.assertEqual(spies[0].rects[0].width, 245)
    self.assertEqual(spies[0].rects[0].height, 245)

  def test_tile_grid_column_preservation_with_single_tile(self):
    mod = _import_aethergrid()
    grid = mod.TileGrid(columns=2, padding=10, min_tile_width=100, force_square=True)
    spy = RenderSpy()
    grid.add_tile(spy)

    # With only 1 tile in a 2-column layout, it should still calculate the tile size based on 2 columns
    # col_w = (500 - 10) / 2 = 245
    grid.render(mod.rl.Rectangle(0, 0, 500, 300))
    self.assertTrue(spy.rects)
    self.assertEqual(spy.rects[0].width, 245)
    self.assertEqual(spy.rects[0].height, 245)

  def test_hud_background_glow_overflow_protection(self):
    mod = _import_aethergrid()
    tile = mod.ToggleTile("Test", lambda: True, lambda v: None)
    # Test with extreme glow values (negative and large positive) to verify no OverflowError occurs
    try:
      tile._render_hud_background(mod.rl.Rectangle(0, 0, 150, 130), mod.rl.Color(255, 0, 0, 255), glow=5.0)
      tile._render_hud_background(mod.rl.Rectangle(0, 0, 150, 130), mod.rl.Color(255, 0, 0, 255), glow=-2.0)
    except OverflowError:
      self.fail("OverflowError raised with extreme glow values")

  def test_aether_category_tile_view(self):
    mod = _import_aethergrid()
    controller_mock = MagicMock()
    
    toggle_visible = True
    rows = [
      mod.SettingRow("toggle_row", "toggle", "Toggle Title", subtitle="Toggle Subtitle",
                     get_state=lambda: True, set_state=lambda v: None,
                     visible=lambda: toggle_visible),
      mod.SettingRow("value_row", "value", "Value Title", subtitle="Value Subtitle",
                     get_value=lambda: "Value", on_click=lambda: None),
      mod.SettingRow("action_row", "action", "Action Title", action_text="Run", on_click=lambda: None),
    ]

    view = mod.AetherCategoryTileView(controller_mock, "Category Title", rows, color="#FF0000", subtitle="Category Description")
    
    self.assertEqual(len(view._sections), 1)
    self.assertEqual(len(view._sections[0].rows), 3)
    
    visible = view._visible_rows(view._sections[0])
    self.assertEqual(len(visible), 3)
    
    toggle_visible = False
    visible = view._visible_rows(view._sections[0])
    self.assertEqual(len(visible), 2)
    self.assertNotIn(rows[0], visible)

    view._back_btn_rect = mod.rl.Rectangle(196, 56, 68, 68)
    view._slide_progress = 1.0 # fully slide-in
    view.set_rect(mod.rl.Rectangle(0, 0, 1920, 1080))
    
    self.assertEqual(view._target_at(mod.rl.Vector2(200, 60)), mod.BACK_BTN)
    self.assertEqual(view._target_at(mod.rl.Vector2(1000, 60)), "__dismiss__")

    app_mod = sys.modules["openpilot.system.ui.lib.application"]
    app_mod.gui_app.pop_widget = MagicMock()
    
    view._activate_target(mod.BACK_BTN)
    app_mod.gui_app.pop_widget.assert_called_once()

  def test_toggle_grid_keeps_every_item_in_one_vertical_scroll_region(self):
    mod = _import_aethergrid()
    view = mod.PanelManagerView()
    grid = mod.TileGrid(columns=1)
    view.register_scroll_grid(grid)
    items = [{"title": f"Setting {i}", "get_state": lambda: False, "set_state": lambda _v: None} for i in range(9)]
    view.set_toggle_items(items)
    self.assertEqual([tile.title for tile in grid.tiles], [item["title"] for item in items])
    height = view.measure_scroll_grid_height(grid, 1000)
    self.assertGreater(height, 800)
    self.assertEqual(height, 9 * mod.AS.SETTINGS_ROW_CARD_HEIGHT + 8 * mod.AS.SETTINGS_ROW_GAP)
    self.assertTrue(grid._touch_valid_callback())
    view._scroll_panel.is_touch_valid = lambda: False
    self.assertFalse(grid._touch_valid_callback())

  def test_scroll_grid_keeps_the_last_item_reachable(self):
    mod = _import_aethergrid()
    view = mod.PanelManagerView()
    grid = mod.TileGrid(columns=1)
    view.register_scroll_grid(grid)
    cards = [RenderSpy() for _ in range(9)]
    for card in cards:
      grid.add_tile(card)
    height = view.measure_scroll_grid_height(grid, 1000)
    view._scroll_rect = mod.rl.Rectangle(48, 200, 1000, 800)
    view._render_scroll_grid(grid, mod.rl.Rectangle(48, 200 + 800 - height, 1000, 800))
    last = cards[-1].rects[-1]
    self.assertEqual(last.y + last.height, view._scroll_rect.y + view._scroll_rect.height)
    self.assertEqual(last.height, mod.AS.SETTINGS_ROW_CARD_HEIGHT)

  def test_scrolling_does_not_open_an_adjustor_on_release(self):
    mod = _import_aethergrid()
    activate = MagicMock()
    row = mod.AetherAdjustorRow("Brightness", "", 0, 100, 1, lambda: 50, lambda _v: None,
                                is_active=lambda: False, set_active=activate)
    row._pressed_zone = "header"
    row._touch_valid = lambda: False
    row._handle_mouse_release(types.SimpleNamespace(x=100, y=100))
    activate.assert_not_called()
    self.assertIsNone(row._pressed_zone)



# ── Aether Cards (comma 3/3X settings share the driving-screen card language) ──

def _calls(mod, name):
  calls = []
  setattr(mod.rl, name, lambda *a, **k: calls.append(a))
  return calls


def test_driving_widgets_and_settings_share_one_style_source():
  from openpilot.selfdrive.ui.lib import aether_style
  from openpilot.selfdrive.ui.onroad.starpilot import widget_style
  assert widget_style.CONTROL_BG is aether_style.CARD_FILL
  assert widget_style.CONTROL_BORDER is aether_style.CARD_BORDER
  assert widget_style.CONTROL_RADIUS == aether_style.CARD_RADIUS
  assert widget_style.UNIFIED_ACCENT is aether_style.ACCENT


def test_rows_are_separate_cards_with_touch_sized_height():
  mod = _import_aethergrid()
  AS = mod.AS
  slot = mod.rl.Rectangle(0, 100, 1000, mod.ROW_HEIGHT)
  card = mod.row_card_rect(slot)
  assert card.y == 100 and card.height == mod.ROW_HEIGHT - AS.SETTINGS_ROW_GAP
  assert card.height >= AS.MIN_TOUCH
  short = mod.row_card_rect(mod.rl.Rectangle(0, 0, 500, AS.MIN_TOUCH))
  assert short.height == AS.MIN_TOUCH  # never shrinks a short row below a comfortable target
  assert mod.AETHER_LIST_METRICS.toggle_height * 1.5 >= AS.MIN_TOUCH * 0.95


def test_card_rows_draw_their_own_card_and_brighten_when_on():
  mod = _import_aethergrid()
  AS = mod.AS
  outlines = _calls(mod, "draw_rectangle_rounded_lines_ex")
  dividers = _calls(mod, "draw_rectangle_rec")
  slot = mod.rl.Rectangle(0, 0, 1000, mod.ROW_HEIGHT)
  mod.draw_list_row_shell(slot, card=True)
  mod.draw_list_row_shell(slot, card=True, emphasis=True)
  mod.draw_list_row_shell(slot, card=True, current=True)
  assert dividers == []
  assert [c[-1].a for c in outlines] == [AS.SETTINGS_CARD_BORDER_IDLE.a, AS.SETTINGS_CARD_BORDER_ON.a, AS.ACCENT_EDGE.a]


def test_grouped_rows_share_one_container_and_use_thin_dividers():
  mod = _import_aethergrid()
  AS = mod.AS
  outlines = _calls(mod, "draw_rectangle_rounded_lines_ex")
  dividers = _calls(mod, "draw_rectangle_rec")
  mod.draw_list_group_shell(mod.rl.Rectangle(0, 0, 1000, 300))
  assert len(outlines) == 1 and outlines[0][-1].a == AS.SETTINGS_TILE_BORDER.a
  row = mod.rl.Rectangle(0, 0, 1000, 100)
  mod.draw_list_row_shell(row)
  mod.draw_list_row_shell(row, is_last=True)
  assert len(outlines) == 1                      # rows inside a group draw no card of their own
  assert len(dividers) == 1                      # one divider, none under the last row
  (line, color), = dividers
  assert line.height == AS.SETTINGS_DIVIDER_WIDTH and line.x == 24 and color.a == AS.SETTINGS_DIVIDER.a


def test_tile_containers_and_explicit_colours():
  mod = _import_aethergrid()
  fills = _calls(mod, "draw_rectangle_rounded")
  mod.draw_list_group_shell(mod.rl.Rectangle(0, 0, 100, 100), kind="tiles")
  assert fills == []                             # tiles are cards already
  mod.draw_list_group_shell(mod.rl.Rectangle(0, 0, 100, 100), fill=mod.rl.Color(1, 2, 3, 255))
  assert len(fills) == 1


@pytest.mark.parametrize("on,expected_side", [(True, "right"), (False, "left")])
def test_switch_is_an_accent_pill_with_a_round_knob(on, expected_side):
  mod = _import_aethergrid()
  fills = _calls(mod, "draw_rectangle_rounded")
  knobs = _calls(mod, "draw_circle_v")
  row = mod.rl.Rectangle(0, 0, 1000, 146)
  mod.draw_toggle_switch(row, on)
  track = fills[-1]
  assert (track[-1].r, track[-1].g, track[-1].b) == ((139, 79, 214) if on else (58, 67, 80))
  (center, radius, _color), = knobs
  m = mod.AETHER_LIST_METRICS
  track_x = 1000 - m.toggle_right_inset - m.toggle_width
  assert (center.x > track_x + m.toggle_width / 2) == (expected_side == "right")
  assert radius == m.toggle_height / 2 - 8


def test_long_subtitles_wrap_to_two_lines_and_end_with_an_ellipsis():
  mod = _import_aethergrid()
  width_per_char = 10
  measure = lambda _font, text, *_a, **_k: types.SimpleNamespace(x=len(text) * width_per_char, y=20)
  with patch.object(mod, "measure_text_cached", measure):
    short = mod.wrap_subtitle(None, "Fits on one line", 400, 28)
    long = mod.wrap_subtitle(None, "word " * 40, 200, 28)
  assert short == ["Fits on one line"]
  assert len(long) == 2 and long[-1].endswith("...") and len(long[-1]) * width_per_char <= 200


def test_value_pill_is_touch_sized_and_right_aligned():
  mod = _import_aethergrid()
  with patch.object(mod, "measure_text_cached", lambda *_a, **_k: types.SimpleNamespace(x=120, y=20)):
    pill = mod.draw_value_pill(900, 80, "Sequential", max_width=400)
  assert pill.x + pill.width == 900
  assert pill.height == mod.VALUE_PILL_HEIGHT >= 80
  assert pill.width >= mod.AS.MIN_TOUCH


def test_constellations_are_off_for_aether_cards():
  mod = _import_aethergrid()
  assert mod.SHOW_CONSTELLATIONS is False
  tile = mod.HubTile("Appearance", "", icon_key="display")
  tile._generate_and_cache_constellation = MagicMock()
  tile._draw_constellation(mod.rl.Rectangle(0, 0, 100, 100), mod.rl.Color(1, 1, 1, 255), 1.0)
  tile._generate_and_cache_constellation.assert_not_called()



def test_settings_follow_the_mockup_measurements():
  mod = _import_aethergrid()
  AS = mod.AS
  card = mod.row_card_rect(mod.rl.Rectangle(0, 0, 1000, mod.ROW_HEIGHT))
  assert card.height == AS.SETTINGS_ROW_CARD_HEIGHT == 184
  assert (mod.AETHER_LIST_METRICS.toggle_width, mod.AETHER_LIST_METRICS.toggle_height) == (136, 76)
  assert mod.VALUE_PILL_HEIGHT == 112 and AS.ROUND_BUTTON == 128 and AS.SETTINGS_CARD_BORDER_WIDTH == 6


def test_long_sections_flow_into_two_columns_of_cards():
  mod = _import_aethergrid()
  rows = [mod.SettingRow(f"R{i}", "toggle", f"Row {i}", get_state=lambda: False, set_state=lambda _v: None) for i in range(5)]
  view = mod.AetherSettingsView(MagicMock(), [mod.SettingSection("", rows)])
  drawn = []
  view._draw_row = lambda rect, row, is_last: drawn.append((row.id, rect))
  end = view._draw_section(0.0, 0.0, 2000.0, view._sections[0], rows)
  assert end == 3 * mod.ROW_HEIGHT
  xs = {row_id: rect.x for row_id, rect in drawn}
  assert xs["R0"] == xs["R2"] == 0 and xs["R1"] == xs["R3"] > 900
  assert view._draw_section(0.0, 0.0, 2000.0, view._sections[0], rows[:4]) == 2 * mod.ROW_HEIGHT
  assert view._draw_section(0.0, 0.0, 2000.0, view._sections[0], rows[:3]) == 3 * mod.ROW_HEIGHT  # short sections stay in one column
  assert view._draw_section(0.0, 0.0, 1000.0, view._sections[0], rows) == 5 * mod.ROW_HEIGHT     # narrow panels stay in one column



def test_switches_and_value_buttons_are_true_pills():
  mod = _import_aethergrid()
  m = mod.AETHER_LIST_METRICS
  calls = _calls(mod, "draw_rectangle_rounded")
  _calls(mod, "draw_circle_v")
  mod.draw_toggle_switch(mod.rl.Rectangle(0, 0, 1000, 184), True)
  with patch.object(mod, "measure_text_cached", lambda *_a, **_k: types.SimpleNamespace(x=120, y=20)):
    mod.draw_value_pill(900, 92, "Sequential", max_width=400)
  assert [c[1] for c in calls] == [1.0, 1.0]  # raylib roundness 1.0: fully rounded ends
  assert mod.aether_roundness(mod.rl.Rectangle(0, 0, 400, 184), mod.AS.SETTINGS_CARD_RADIUS) == 2 * 40 / 184
  assert m.toggle_right_inset == 44


def test_page_frames_keep_header_and_content_aligned_at_any_origin():
  mod = _import_aethergrid()
  for bounds in (mod.rl.Rectangle(0, 0, 2160, 1080), mod.rl.Rectangle(456, 0, 1704, 1080)):
    frame = mod.build_settings_page_frame(bounds)
    assert frame.header.x == frame.content.x == bounds.x + mod.AS.SETTINGS_PAGE_MARGIN
    assert frame.header.width == frame.content.width
    assert frame.content.y - frame.header.y - frame.header.height == mod.AS.SETTINGS_HEADER_GAP
    assert frame.content.y + frame.content.height == bounds.y + bounds.height - mod.AS.SETTINGS_PAGE_MARGIN


@pytest.mark.parametrize("width", [800, 1020])
def test_group_headings_clear_the_outline_and_align_with_control_labels(width):
  mod = _import_aethergrid()
  bounds = mod.rl.Rectangle(48, 200, width, 600)
  headings, shells = [], []
  with patch.object(mod, "draw_section_header", lambda rect, *_a, **_k: headings.append(rect)), \
       patch.object(mod, "draw_list_group_shell", lambda rect, **_k: shells.append(rect)):
    body = mod.draw_settings_group(bounds, "Volumes")
  (heading,), (shell,) = headings, shells
  assert shell is body
  assert heading.y + heading.height + mod.AS.SETTINGS_GROUP_HEADING_GAP == body.y
  assert heading.height >= mod.AS.SETTINGS_GROUP_HEADING_SIZE * 1.242  # device font scale
  assert body.y + body.height == bounds.y + bounds.height

  texts = _calls(mod, "draw_text_ex")
  row = mod.AetherAdjustorRow("Warning", "", 0, 100, 1, lambda: 50, lambda _v: None)
  row.render(mod.rl.Rectangle(body.x, body.y, body.width, row.measure_height(body.width)))
  title_x = next(call[2].x for call in texts if call[1] == "Warning")
  card = mod.build_settings_row_layout(mod.rl.Rectangle(body.x, body.y, body.width, 184))
  assert heading.x == title_x == card.text.x
  assert heading.x + heading.width == row._progress_bar_rect.x + row._progress_bar_rect.width


@pytest.mark.parametrize("paired", [False, True])
def test_standard_section_headings_follow_the_same_group_alignment(paired):
  mod = _import_aethergrid()
  sections = [mod.SettingSection("First", [mod.SettingRow("one", "toggle", "One")])]
  if paired:
    sections.append(mod.SettingSection("Second", [mod.SettingRow("two", "toggle", "Two")]))
    for section in sections:
      section.column_pair = "pair"
  view = mod.AetherSettingsView(MagicMock(), sections)
  headings, rows = [], []
  view._draw_row = lambda rect, *_a, **_k: rows.append(rect)
  with patch.object(mod, "draw_section_header", lambda rect, *_a, **_k: headings.append(rect)):
    view._draw_scroll_content(mod.rl.Rectangle(48, 200, 2000, 800), 2000)
  assert len(headings) == len(rows) == len(sections)
  for heading, row in zip(headings, rows, strict=True):
    frame = mod.build_settings_group_frame(mod.rl.Rectangle(row.x, 200, row.width, 600))
    assert heading.x == frame.heading.x
    assert heading.y + heading.height + mod.AS.SETTINGS_GROUP_HEADING_GAP == row.y


def test_small_hub_folders_keep_cards_at_the_top_without_stretching():
  mod = _import_aethergrid()
  grid = mod.HubGrid()
  cards = [RenderSpy() for _ in range(3)]
  for card in cards:
    grid.add_tile(card)
  grid.render(mod.rl.Rectangle(48, 200, 2064, 832))
  assert all(card.rects[0].y == 200 for card in cards)
  assert all(card.rects[0].height == mod.AS.SETTINGS_HUB_TILE_HEIGHT for card in cards)


@pytest.mark.parametrize("kind", ["toggle", "value", "action", "tile"])
def test_card_variants_share_text_inset_and_control_alignment(kind):
  mod = _import_aethergrid()
  face = mod.rl.Rectangle(48, 200, 1020, 184)
  slot = mod.rl.Rectangle(face.x, face.y, face.width, face.height + mod.AS.SETTINGS_ROW_GAP)
  _calls(mod, "draw_circle_v")
  texts, controls = [], []
  with patch.object(mod, "draw_row_title_subtitle", lambda rect, x, width, *_a: texts.append((rect, x, width))), \
       patch.object(mod, "draw_toggle_switch", lambda rect, *_a, **_k: controls.append(rect.x + rect.width - mod.AS.SETTINGS_CARD_INSET)), \
       patch.object(mod, "draw_value_pill", lambda right, *_a, **_k: controls.append(right)), \
       patch.object(mod, "draw_action_pill", lambda rect, *_a, **_k: controls.append(rect.x + rect.width)):
    if kind == "tile":
      mod.RowToggleTile("Example", lambda: True, lambda _v: None).render(face)
    elif kind == "action":
      mod.draw_selection_list_row(slot, title="Example", action_text="Reset", card=True)
    else:
      kwargs = {"toggle_value": True} if kind == "toggle" else {"value": "Sequential"}
      mod.draw_settings_list_row(slot, title="Example", card=True, **kwargs)
  (text_rect, x, _width), = texts
  assert text_rect.y == face.y and text_rect.height == face.height
  assert x - face.x == mod.AS.SETTINGS_CARD_INSET
  assert controls == [face.x + face.width - mod.AS.SETTINGS_CARD_INSET]


def test_card_gaps_do_not_activate_adjacent_settings():
  mod = _import_aethergrid()
  row = mod.SettingRow("one", "toggle", "One", get_state=lambda: False)
  view = mod.AetherSettingsView(MagicMock(), [mod.SettingSection("", [row])])
  view._scroll_rect = mod.rl.Rectangle(0, 0, 1000, 500)
  _calls(mod, "draw_circle_v")
  view._draw_row(mod.rl.Rectangle(0, 0, 1000, mod.ROW_HEIGHT), row, is_last=True)
  assert view._target_at(types.SimpleNamespace(x=100, y=mod.AS.SETTINGS_ROW_CARD_HEIGHT / 2)) == "toggle:one"
  assert view._target_at(types.SimpleNamespace(x=100, y=mod.ROW_HEIGHT - mod.AS.SETTINGS_ROW_GAP / 2)) is None


def test_page_header_master_switch_preserves_its_action_without_a_duplicate_row():
  mod = _import_aethergrid()
  state = [True]
  toggle = mod.ParentToggle("Widgets", lambda: state[0], lambda value: state.__setitem__(0, value))
  view = mod.AetherSettingsView(MagicMock(), [], parent_toggle=toggle)
  assert view.use_page_header() is toggle
  assert view._compute_header_height(2000) == 0
  header = mod.BreadcrumbController()
  _calls(mod, "draw_circle_v")
  with patch.object(header, "build_path", lambda: [("StarPilot", "action:home"), ("Widgets", "action:panel")]):
    header.draw_header(mod.rl.Rectangle(48, 36, 2064, 128), header_control=toggle)
  target = header.rects["action:page_toggle"]
  point = types.SimpleNamespace(x=target.x + target.width / 2, y=target.y + target.height / 2)
  header.init_interaction(point)
  action = header.finish_interaction(point)
  assert action == "action:page_toggle"
  header.handle_click(action)
  assert state == [False]


@pytest.mark.parametrize("result,expected_calls", [("CANCEL", 0), ("CONFIRM", 1)])
def test_action_button_waits_for_confirmation_before_applying_changes(monkeypatch, result, expected_calls):
  mod = _import_aethergrid()
  dialogs = []
  dialog_module = types.ModuleType("openpilot.system.ui.widgets.confirm_dialog")
  dialog_module.ConfirmDialog = lambda text, label, callback: types.SimpleNamespace(text=text, label=label, callback=callback)
  monkeypatch.setitem(sys.modules, dialog_module.__name__, dialog_module)
  mod.gui_app.push_widget = dialogs.append
  action = MagicMock()
  button = mod.AetherButton("Reset All", action, confirmation="Reset all sound settings?", confirm_label="Reset All")
  button.on_click()
  action.assert_not_called()
  (dialog,) = dialogs
  assert dialog.text == "Reset all sound settings?" and dialog.label == "Reset All"
  dialog.callback(getattr(mod.DialogResult, result))
  assert action.call_count == expected_calls


def test_disabled_action_button_does_not_open_confirmation_or_run_action():
  mod = _import_aethergrid()
  mod.gui_app.push_widget = MagicMock()
  action = MagicMock()
  button = mod.AetherButton("Reset All", action, enabled=False, confirmation="Reset settings?")
  button.on_click()
  mod.gui_app.push_widget.assert_not_called()
  action.assert_not_called()


def test_regular_action_button_preserves_immediate_actions():
  mod = _import_aethergrid()
  action = MagicMock()
  mod.AetherButton("Refresh", action).on_click()
  action.assert_called_once_with()


@pytest.mark.parametrize("value,label,is_on", [(101, "Auto", True), (50, "50%", True), (0, "Muted", False)])
def test_status_adjustors_show_configured_state_and_keep_the_entire_row_tappable(value, label, is_on):
  mod = _import_aethergrid()
  _calls(mod, "draw_circle_v")
  activate = MagicMock()
  state = [value]
  row = mod.AetherAdjustorRow("General Prompt", "", 0, 101, 1, lambda: state[0], lambda _v: None,
                             labels={0.0: "Muted", 101.0: "Auto"}, unit="%", set_active=activate,
                             status=lambda: mod.RowStatus("sound" if state[0] else "sound_muted",
                                                          "Sound enabled" if state[0] else "Sound muted", bool(state[0])))
  row._touch_valid = lambda: True
  seen = []
  with patch.object(mod, "draw_status_value_row", lambda rect, **kwargs: seen.append((rect, kwargs))), \
       patch.object(row, "_render_level_header", side_effect=AssertionError("status rows must not draw a volume meter")):
    bounds = mod.rl.Rectangle(48, 200, 1020, row.measure_height(1020))
    row.render(bounds)
  header, content = seen[0]
  assert header.height == mod.AS.SETTINGS_ROW_CARD_HEIGHT
  assert content["value"] == label
  assert content["status"].is_on is is_on
  assert content["status"].icon_key == ("sound" if is_on else "sound_muted")
  # The speaker, subtitle and trailing value all belong to the same touch target.
  for x in (bounds.x + 10, bounds.x + bounds.width / 2, bounds.x + bounds.width - 10):
    point = mod.rl.Vector2(x, bounds.y + bounds.height / 2)
    row._handle_mouse_press(point)
    row._handle_mouse_release(point)
  assert activate.call_count == 3
  row._handle_mouse_press(point)
  row._touch_valid = lambda: False
  row._handle_mouse_release(point)
  assert activate.call_count == 3
  state[0] = 0 if is_on else 50
  with patch.object(mod, "draw_status_value_row", lambda rect, **kwargs: seen.append((rect, kwargs))):
    row.render(bounds)
  assert seen[-1][1]["status"].is_on is not is_on
  assert seen[-1][1]["value"] == ("Muted" if is_on else "50%")


def test_muting_a_status_row_updates_its_icon_and_description_without_disabling_it():
  mod = _import_aethergrid()
  icons, labels = [], []
  status = mod.RowStatus("sound_muted", "Sound muted", False)
  with patch.object(mod, "draw_custom_icon", lambda key, *_a: icons.append(key)), \
       patch.object(mod, "draw_row_title_subtitle", lambda rect, x, width, title, subtitle, *_a: labels.append((x, title, subtitle))):
    mod.draw_status_value_row(mod.rl.Rectangle(48, 200, 1020, 184), title="General Prompt", value="Muted", status=status)
  assert icons == ["sound_muted"]
  assert labels[0][1:] == ("General Prompt", "Sound muted")
  assert labels[0][0] > 48 + mod.AS.SETTINGS_CARD_INSET + mod.AS.SETTINGS_STATUS_ICON_SIZE


def test_header_action_is_a_touch_sized_pill_inside_the_header():
  mod = _import_aethergrid()
  header = mod.BreadcrumbController()
  button = mod.AetherButton("Reset All")
  bounds = mod.rl.Rectangle(48, 36, 2064, 128)
  fills = _calls(mod, "draw_rectangle_rounded")
  _calls(mod, "draw_circle_v")
  with patch.object(header, "build_path", lambda: [("StarPilot", "action:home"), ("Sounds", "action:panel")]):
    header.draw_header(bounds, header_control=button)
  rect = button._rect
  assert rect.height >= mod.AS.MIN_TOUCH and rect.width >= mod.AS.MIN_TOUCH
  assert rect.y >= bounds.y and rect.y + rect.height <= bounds.y + bounds.height
  assert rect.x + rect.width == bounds.x + bounds.width
  assert button._parent_rect is bounds
  pill = next(fill for fill in fills if fill[0].x == rect.x)
  assert pill[1] == 1.0


@pytest.mark.parametrize("current_index", [0, 1, 2])
@pytest.mark.parametrize("height", [120, 98, 68])
@pytest.mark.parametrize("pressed", [False, True])
def test_segmented_highlights_stay_inside_the_rounded_outer_border(current_index, height, pressed):
  mod = _import_aethergrid()
  bounds = mod.rl.Rectangle(48, 200, 2064, height)
  control = mod.AetherSegmentedControl(["Auto", "Onroad", "Offroad"], current_index, lambda _v: None,
                                      style=mod.DEFAULT_PANEL_STYLE)
  control._touch_valid = lambda: True
  if pressed:
    control._option_offsets = [float(i == current_index) for i in range(3)]
    control._option_targets = list(control._option_offsets)
  fills = _calls(mod, "draw_rectangle_rounded")
  shines = _calls(mod, "draw_rectangle_rec")
  control.render(bounds)
  assert len(fills) == 4  # shared shell and three segments
  bounds = control._rect
  assert bounds.height == control.measure_height() == mod.AS.SETTINGS_SEGMENTED_HEIGHT
  assert not shines  # a rectangular top shine would cross the curved corners

  inset = mod.AS.SETTINGS_CARD_BORDER_WIDTH
  inner = mod._inset_rect(bounds, inset)
  inner_radius = mod.AS.SETTINGS_CARD_RADIUS - inset
  for face, roundness, _segments, _color in fills[1:]:
    radius = roundness * min(face.width, face.height) / 2
    corners = [(face.x + radius, face.y + radius, 180),
               (face.x + face.width - radius, face.y + radius, 270),
               (face.x + face.width - radius, face.y + face.height - radius, 0),
               (face.x + radius, face.y + face.height - radius, 90)]
    for cx, cy, start in corners:
      for degrees in range(start, start + 91, 15):
        x = cx + radius * math.cos(math.radians(degrees))
        y = cy + radius * math.sin(math.radians(degrees))
        assert inner.x - 1e-6 <= x <= inner.x + inner.width + 1e-6
        assert inner.y - 1e-6 <= y <= inner.y + inner.height + 1e-6
        nearest_x = min(max(x, inner.x + inner_radius), inner.x + inner.width - inner_radius)
        nearest_y = min(max(y, inner.y + inner_radius), inner.y + inner.height - inner_radius)
        assert math.hypot(x - nearest_x, y - nearest_y) <= inner_radius + 1e-6


@pytest.mark.parametrize("options,old_height", [(["Auto", "Onroad", "Offroad"], 120),
                                               (["OFF", "Experimental", "Chill"], 98),
                                               (["U.S. States & Regions", "Other Countries"], 68)])
@pytest.mark.parametrize("width", [2064, 1020])
@pytest.mark.parametrize("has_status", [False, True])
def test_segmented_controls_share_height_font_insets_and_equal_segments(options, old_height, width, has_status):
  mod = _import_aethergrid()
  control = mod.AetherSegmentedControl(options, 0, lambda _v: None, statuses=["Current mode"] * len(options) if has_status else None)
  control._touch_valid = lambda: True
  labels = []
  with patch.object(mod, "gui_label", lambda rect, text, size, color, weight, **_k: labels.append((rect, text, size, weight))):
    control.render(mod.rl.Rectangle(48, 200, width, old_height))
  assert control._rect.width == width
  assert control._rect.height == control.measure_height(width) == mod.AS.SETTINGS_SEGMENTED_HEIGHT
  titles = [call for call in labels if call[1] in options]
  assert len(titles) == len(options)
  assert {(size, weight) for _, _, size, weight in titles} == {(mod.AS.SETTINGS_SEGMENTED_FONT_SIZE, mod.FontWeight.MEDIUM)}
  segments = control._option_rects
  assert segments[0].x - control._rect.x == mod.AS.SETTINGS_SEGMENTED_INSET
  assert abs(control._rect.x + width - segments[-1].x - segments[-1].width - mod.AS.SETTINGS_SEGMENTED_INSET) <= 1
  assert max(r.width for r in segments) - min(r.width for r in segments) <= 1
  assert all(r.height >= mod.AS.MIN_TOUCH for r in segments)
  for previous, current in zip(segments, segments[1:]):
    assert abs(current.x - previous.x - previous.width - mod.AS.SETTINGS_SEGMENTED_GAP) <= 1
  for (text_rect, _, _, _), segment in zip(titles, segments, strict=True):
    assert text_rect.x - segment.x == mod.AS.SETTINGS_SEGMENTED_TEXT_INSET
    assert text_rect.width == segment.width - mod.AS.SETTINGS_SEGMENTED_TEXT_INSET * 2


def test_segmented_control_preserves_selection_and_scroll_cancellation():
  mod = _import_aethergrid()
  selected = []
  control = mod.AetherSegmentedControl(["Auto", "Onroad", "Offroad"], 0, selected.append)
  control._touch_valid = lambda: True
  control.render(mod.rl.Rectangle(48, 200, 2064, 120))
  target = control._option_rects[1]
  point = mod.rl.Vector2(target.x + target.width / 2, target.y + target.height / 2)
  control._handle_mouse_press(point)
  control._handle_mouse_release(point)
  assert selected == [1]
  control._handle_mouse_press(point)
  control._touch_valid = lambda: False
  control._handle_mouse_release(point)
  assert selected == [1]


def _independent_column_test_view(monkeypatch):
  """Use the real gesture/inertia implementation with headless drawing."""
  from pathlib import Path
  mod = _import_aethergrid()
  spec = importlib.util.spec_from_file_location("column_scroll_test", Path(__file__).parents[3] / "system/ui/lib/scroll_panel2.py")
  scroll = importlib.util.module_from_spec(spec)
  monkeypatch.setitem(sys.modules, "openpilot.system.hardware", types.SimpleNamespace(TICI=False))
  spec.loader.exec_module(scroll)
  monkeypatch.setattr(mod, "GuiScrollPanel2", scroll.GuiScrollPanel2)
  mod.rl.get_mouse_wheel_move = lambda: 0
  mod.gui_app.mouse_events = []
  _calls(mod, "begin_scissor_mode")
  _calls(mod, "end_scissor_mode")
  view = mod.PanelManagerView()
  view.is_visible = True
  view._scroll_rect = mod.rl.Rectangle(48, 200, 2064, 600)
  view._content_height = 1800
  view._build_scroll_columns = lambda width: [
    mod.SettingsColumn("left", 1800, lambda rect: view._interactive_state("left-row", mod.rl.Rectangle(rect.x, rect.y, rect.width, 1800))),
    mod.SettingsColumn("right", 1000, lambda rect: view._interactive_state("right-row", mod.rl.Rectangle(rect.x, rect.y, rect.width, 1000))),
  ]
  view._render_scroll_area(view._scroll_rect, 2064)
  return mod, scroll, view


def test_column_wheel_offsets_and_ranges_are_independent(monkeypatch):
  mod, _, view = _independent_column_test_view(monkeypatch)
  left, right = (view._column_scrolls[key] for key in ("left", "right"))
  mod.rl.get_mouse_wheel_move = lambda: -2
  mod.rl.get_mouse_position = lambda: mod.rl.Vector2(left.rect.x + 100, 400)
  view._render_scroll_area(view._scroll_rect, 2064)
  assert (left.offset, right.offset) == (-100, 0)
  mod.rl.get_mouse_position = lambda: mod.rl.Vector2(right.rect.x + 100, 400)
  view._render_scroll_area(view._scroll_rect, 2064)
  assert (left.offset, right.offset) == (-100, -100)
  assert left.panel._get_offset_bounds(left.rect.height, left.height) == (0, -1200)
  assert right.panel._get_offset_bounds(right.rect.height, right.height) == (0, -400)
  view.reset_scroll()
  assert left.panel.get_offset() == right.panel.get_offset() == 0


def test_column_drag_keeps_its_owner_across_the_gutter_and_cannot_activate_a_row(monkeypatch):
  mod, scroll, view = _independent_column_test_view(monkeypatch)
  left, right = (view._column_scrolls[key] for key in ("left", "right"))
  def event(x, y, time, pressed=False, released=False):
    return types.SimpleNamespace(pos=mod.rl.Vector2(x, y), t=time, left_pressed=pressed, left_released=released)
  press = event(left.rect.x + 100, 500, 1, pressed=True)
  mod.gui_app.mouse_events = [press]
  view._render_scroll_area(view._scroll_rect, 2064)
  view._handle_mouse_press(press.pos)
  move = event(right.rect.x + 100, 400, 1.1)
  mod.gui_app.mouse_events = [event(left.rect.x + 100, 480, 1.01), move]
  view._render_scroll_area(view._scroll_rect, 2064)
  view._handle_mouse_event(move)
  assert left.panel.state == scroll.ScrollState.MANUAL_SCROLL
  assert left.offset < 0 and right.offset == 0
  assert view._gesture_column == "left" and not view._scroll_touch_valid()
  activate = MagicMock()
  view._activate_target = activate
  view._handle_mouse_release(move.pos)
  activate.assert_not_called()


def test_tapping_one_column_does_not_interrupt_the_other_columns_fling(monkeypatch):
  mod, scroll, view = _independent_column_test_view(monkeypatch)
  left, right = (view._column_scrolls[key] for key in ("left", "right"))
  left.panel.set_offset(-300)
  left.panel._state = scroll.ScrollState.AUTO_SCROLL
  left.panel._velocity = -500
  point = mod.rl.Vector2(right.rect.x + 100, 400)
  mod.gui_app.mouse_events = [types.SimpleNamespace(pos=point, t=1.0, left_pressed=True, left_released=False)]
  view._render_scroll_area(view._scroll_rect, 2064)
  assert left.panel.state == scroll.ScrollState.AUTO_SCROLL
  assert left.offset < -300
  assert right.panel.state == scroll.ScrollState.PRESSED
  view._handle_mouse_press(point)
  assert view._gesture_column == "right" and view._scroll_touch_valid()


def test_column_scroll_release_in_one_event_batch_cannot_become_a_tap(monkeypatch):
  mod, scroll, view = _independent_column_test_view(monkeypatch)
  left, right = (view._column_scrolls[key] for key in ("left", "right"))
  def event(y, time, pressed=False, released=False):
    return types.SimpleNamespace(pos=mod.rl.Vector2(left.rect.x + 100, y), t=time,
                                 left_pressed=pressed, left_released=released)
  mod.gui_app.mouse_events = [event(600, 1, pressed=True), event(580, 1.01), event(520, 1.02), event(500, 1.03, released=True)]
  view._render_scroll_area(view._scroll_rect, 2064)
  assert left.panel.state == scroll.ScrollState.AUTO_SCROLL
  assert not left.panel.is_touch_valid()
  assert right.panel.is_touch_valid()
  # A fresh tap in the same column can be accepted once its fling has stopped.
  left.panel._velocity = 0
  mod.gui_app.mouse_events = [event(500, 2, pressed=True)]
  view._render_scroll_area(view._scroll_rect, 2064)
  assert left.panel.is_touch_valid()


def test_column_hit_targets_remain_clipped_to_their_own_viewport(monkeypatch):
  mod, _, view = _independent_column_test_view(monkeypatch)
  left = view._column_scrolls["left"]
  left.panel.set_offset(-400)
  view._render_scroll_area(view._scroll_rect, 2064)
  assert view._target_at(mod.rl.Vector2(left.rect.x + 100, left.rect.y - 10)) is None
  assert view._target_at(mod.rl.Vector2(left.rect.x + 100, left.rect.y + 100)) == "left-row"


def test_settings_column_planning_preserves_paired_sections_and_narrow_fallback():
  mod = _import_aethergrid()
  left_rows = [mod.SettingRow(f"left-{i}", "toggle", f"Left {i}") for i in range(9)]
  right_rows = [mod.SettingRow(f"right-{i}", "toggle", f"Right {i}") for i in range(3)]
  view = mod.AetherSettingsView(MagicMock(), [mod.SettingSection("Left", left_rows, column_pair="pair"),
                                           mod.SettingSection("Right", right_rows, column_pair="pair")])
  columns = view._build_scroll_columns(2064)
  assert columns[0].height > columns[1].height
  seen = []
  view._draw_row = lambda rect, row, *_a: seen.append(row.id)
  columns[0].draw(mod.rl.Rectangle(48, 200, 1020, 600))
  assert seen == [row.id for row in left_rows]
  seen.clear()
  columns[1].draw(mod.rl.Rectangle(1092, 200, 1020, 600))
  assert seen == [row.id for row in right_rows]
  assert view._build_scroll_columns(1000) == []


def _choice_dialog_test(monkeypatch, count=9, callback=None):
  grid, scroll, _ = _independent_column_test_view(monkeypatch)
  name = "openpilot.selfdrive.ui.layouts.settings.starpilot.choice_dialog"
  _clear_modules(name)
  mod = importlib.import_module(name)
  monkeypatch.setattr(mod, "GuiScrollPanel2", scroll.GuiScrollPanel2)
  monkeypatch.setattr(grid.Widget, "hide_event", lambda self: None)
  mod.rl.KeyboardKey = types.SimpleNamespace(KEY_ESCAPE=256)
  mod.rl.is_key_pressed = lambda key: False
  mod.rl.draw_circle_v = lambda *args: None
  options = [mod.PreviewChoice(str(i), f"Choice {i}", close_preview=MagicMock()) for i in range(count)]
  dialog = mod.AetherChoiceDialog("Animation", options, "0", subtitle="Preview", callback=callback)
  dialog.render(mod.rl.Rectangle(0, 0, 2160, 1080))
  return mod, dialog


@pytest.mark.parametrize("result", [0, 1])
def test_preview_choice_stays_local_until_apply_or_cancel_and_releases_once(monkeypatch, result):
  completed, popped = [], []
  mod, dialog = _choice_dialog_test(monkeypatch, callback=completed.append)
  monkeypatch.setattr(mod.gui_app, "pop_widget", lambda: popped.append(True))
  target = dialog._option_rects["1"]
  point = mod.rl.Vector2(target.x + 100, target.y + 100)
  dialog._handle_mouse_press(point)
  dialog._handle_mouse_release(point)
  assert dialog.selection == "1" and completed == []
  dialog._finish(result)
  dialog._finish(result)
  dialog.hide_event()
  assert completed == [result] and popped == [True]
  for option in dialog.options:
    option.close_preview.assert_called_once_with()


def test_preview_grid_has_equal_three_by_three_cards_and_scrolls_additional_choices(monkeypatch):
  mod, dialog = _choice_dialog_test(monkeypatch, count=15)
  bounds = list(dialog._option_rects.values())
  assert len({r.x for r in bounds}) == 3
  assert len({r.y for r in bounds}) == 5
  assert max(r.width for r in bounds) - min(r.width for r in bounds) <= 1
  assert len({r.height for r in bounds}) == 1
  assert bounds[0].height >= mod.AS.MIN_TOUCH
  assert bounds[1].x - bounds[0].x - bounds[0].width == mod.AS.SETTINGS_TILE_GAP
  assert bounds[3].y - bounds[0].y - bounds[0].height == mod.AS.SETTINGS_TILE_GAP
  assert bounds[8].y + bounds[8].height <= dialog._scroll_rect.y + dialog._scroll_rect.height
  assert dialog._content_height > dialog._scroll_rect.height
  assert not dialog._scroll_panel._horizontal and dialog._scroll_panel.snap_interval is None
  header = vars(dialog._apply._rect).copy()
  dialog._scroll_panel.set_offset(dialog._scroll_rect.height - dialog._content_height)
  dialog.render(mod.rl.Rectangle(0, 0, 2160, 1080))
  assert vars(dialog._apply._rect) == header
  assert dialog._target_at(mod.rl.Vector2(bounds[0].x + 100, dialog._scroll_rect.y - 10)) is None
  last = dialog._option_rects["14"]
  point = mod.rl.Vector2(last.x + 100, last.y + last.height / 2)
  assert dialog._target_at(point) == "14"
  dialog._handle_mouse_press(point)
  dialog._handle_mouse_release(point)
  assert dialog.selection == "14"


def test_preview_grid_drag_release_cannot_select_a_card(monkeypatch):
  mod, dialog = _choice_dialog_test(monkeypatch, count=15)
  card = dialog._option_rects["4"]
  def event(y, time, pressed=False, released=False):
    return types.SimpleNamespace(pos=mod.rl.Vector2(card.x + 100, y), t=time, left_pressed=pressed, left_released=released)
  events = [event(card.y + 180, 1, pressed=True), event(card.y + 160, 1.01),
            event(card.y + 130, 1.02), event(card.y + 120, 1.03, released=True)]
  mod.gui_app.mouse_events = events
  dialog.render(mod.rl.Rectangle(0, 0, 2160, 1080))
  assert dialog._scroll_panel.get_offset() < 0
  assert not dialog._scroll_panel.is_touch_valid()
  for touch in events:
    if touch.left_pressed:
      dialog._handle_mouse_press(touch.pos)
    dialog._handle_mouse_event(touch)
    if touch.left_released:
      dialog._handle_mouse_release(touch.pos)
  assert dialog.selection == "0"


def test_preview_choice_must_release_on_the_same_visible_card(monkeypatch):
  mod, dialog = _choice_dialog_test(monkeypatch)
  first, second = (dialog._option_rects[key] for key in ("1", "2"))
  dialog._handle_mouse_press(mod.rl.Vector2(first.x + 100, first.y + 100))
  dialog._handle_mouse_release(mod.rl.Vector2(second.x + 100, second.y + 100))
  assert dialog.selection == "0"
  assert dialog._content_height <= dialog._scroll_rect.height


def test_preview_choice_apply_is_disabled_without_choices(monkeypatch):
  completed = MagicMock()
  mod, dialog = _choice_dialog_test(monkeypatch, count=0, callback=completed)
  popped = MagicMock()
  monkeypatch.setattr(mod.gui_app, "pop_widget", popped)
  assert dialog.selection == "" and not dialog._apply.enabled
  dialog._finish(mod.DialogResult.CONFIRM)
  completed.assert_not_called()
  popped.assert_not_called()


def test_signal_thumbnail_uses_numeric_frame_order_caches_and_releases_texture(monkeypatch, tmp_path):
  grid = _import_aethergrid()
  import re
  bundled = tmp_path / "bundled"
  bundled.mkdir()
  for name in ("turn_signal_1.png", "turn_signal_2.png", "turn_signal_10.png", "turn_signal_blindspot.png"):
    (bundled / name).touch()
  monkeypatch.setitem(sys.modules, "openpilot.selfdrive.ui.onroad.starpilot.turn_signals",
                      types.SimpleNamespace(FRAME_PATTERN=re.compile(r"turn_signal(?:_(\d+))?\.png"),
                                            BUNDLED_SIGNAL_PATHS={"test": bundled}))
  name = "openpilot.selfdrive.ui.layouts.settings.starpilot.signal_preview"
  _clear_modules(name)
  mod = importlib.import_module(name)
  image = types.SimpleNamespace(width=100, height=200)
  texture = types.SimpleNamespace(id=1, width=100, height=200)
  grid.rl.load_image = MagicMock(return_value=image)
  grid.rl.image_alpha_crop = MagicMock()
  grid.rl.load_texture_from_image = MagicMock(return_value=texture)
  grid.rl.set_texture_filter = MagicMock()
  grid.rl.TextureFilter = types.SimpleNamespace(TEXTURE_FILTER_BILINEAR=1)
  grid.rl.unload_image = MagicMock()
  grid.rl.unload_texture = MagicMock()
  grid.rl.draw_texture_pro = MagicMock()
  preview = mod.SignalPreview("test", tmp_path)
  preview(grid.rl.Rectangle(0, 0, 160, 100))
  preview(grid.rl.Rectangle(0, 0, 160, 100))
  grid.rl.load_image.assert_called_once_with(str(bundled / "turn_signal_2.png"))
  grid.rl.unload_image.assert_called_once_with(image)
  destination = grid.rl.draw_texture_pro.call_args.args[2]
  assert (destination.x, destination.y, destination.width, destination.height) == (55, 0, 50, 100)
  preview.close()
  preview.close()
  grid.rl.unload_texture.assert_called_once_with(texture)
  installed = tmp_path / "theme_packs/test/signals"
  installed.mkdir(parents=True)
  (installed / "turn_signal.png").touch()
  assert mod.SignalPreview("test", tmp_path)._path == installed / "turn_signal.png"
  missing = mod.SignalPreview("missing", tmp_path)
  missing(grid.rl.Rectangle(0, 0, 160, 100))
  missing.close()
  assert grid.rl.load_image.call_count == 1


def _text_dialog_test(monkeypatch, count=20, current="0", callback=None):
  mod, _ = _choice_dialog_test(monkeypatch)
  name = "openpilot.system.ui.widgets.option_dialog"
  _clear_modules(name)
  text_dialog = importlib.import_module(name)
  dialog = text_dialog.MultiOptionDialog("Camera View", [str(i) for i in range(count)], current,
                                         callback=callback, subtitle="Choose the view shown while driving.")
  dialog.render(mod.rl.Rectangle(0, 0, 2160, 1080))
  return mod, dialog


def test_text_grid_slider_and_multi_select_share_the_same_header(monkeypatch):
  mod, grid = _choice_dialog_test(monkeypatch)
  text_name = "openpilot.system.ui.widgets.option_dialog"
  _clear_modules(text_name)
  text_dialog = importlib.import_module(text_name)
  from openpilot.selfdrive.ui.layouts.settings.starpilot.aethergrid import AetherSelectionDialog, AetherSliderDialog
  dialogs = [grid,
             text_dialog.MultiOptionDialog("Camera View", ["Auto", "Wide"], "Auto", subtitle="Choose a view."),
             AetherSliderDialog("Volume", 0, 100, 1, 50, lambda *_: None, subtitle="Adjust the volume."),
             mod.AetherMultiSelectDialog("Models", {"one": "One", "two": "Two"}, ["one"], lambda *_: None)]
  for dialog in dialogs:
    assert isinstance(dialog, AetherSelectionDialog)
    dialog.render(mod.rl.Rectangle(0, 0, 2160, 1080))
    assert vars(dialog._cancel_rect) == vars(grid._cancel_rect)
    assert vars(dialog._ok_rect) == vars(grid._ok_rect)
    assert vars(dialog._content_rect) == vars(grid._content_rect)
    assert dialog._cancel.text == "Cancel" and dialog._apply.text == "Apply"


def test_text_list_scrolls_to_current_choice_and_keeps_actions_fixed(monkeypatch):
  mod, dialog = _text_dialog_test(monkeypatch, current="19")
  assert len({bounds.x for bounds in dialog._option_rects.values()}) == 1
  assert dialog._option_rects["19"].y >= dialog._scroll_rect.y
  assert dialog._option_rects["19"].y + dialog._option_rects["19"].height <= dialog._scroll_rect.y + dialog._scroll_rect.height
  actions = (vars(dialog._cancel_rect).copy(), vars(dialog._ok_rect).copy())
  dialog._scroll_panel.set_offset(0)
  dialog.render(mod.rl.Rectangle(0, 0, 2160, 1080))
  assert (vars(dialog._cancel_rect), vars(dialog._ok_rect)) == actions
  assert dialog._target_at(mod.rl.Vector2(dialog._scroll_rect.x + 100, dialog._scroll_rect.y - 1)) is None


@pytest.mark.parametrize("result", [0, 1])
def test_text_option_tap_remains_pending_until_header_action(monkeypatch, result):
  completed = []
  mod, dialog = _text_dialog_test(monkeypatch, callback=completed.append)
  card = dialog._option_rects["1"]
  point = mod.rl.Vector2(card.x + 100, card.y + 100)
  dialog._handle_mouse_press(point)
  dialog._handle_mouse_release(point)
  assert dialog.selection == "1" and not completed
  (dialog._apply if result else dialog._cancel)._activate()
  assert completed == [result]


def test_text_actions_require_an_explicit_choice_and_escape_cancels(monkeypatch):
  completed = []
  mod, dialog = _text_dialog_test(monkeypatch, current="", callback=completed.append)
  assert not dialog._apply.enabled
  dialog._apply._activate()
  assert completed == []
  mod.rl.is_key_pressed = lambda key: True
  dialog.render(mod.rl.Rectangle(0, 0, 2160, 1080))
  assert completed == [mod.DialogResult.CANCEL]


@pytest.mark.parametrize("result", [0, 1])
def test_multi_select_stages_a_copy_and_allows_clearing_every_option(monkeypatch, result):
  completed = []
  mod, _ = _choice_dialog_test(monkeypatch)
  original = ["one", "two"]
  dialog = mod.AetherMultiSelectDialog("Models", {"one": "One", "two": "Two"}, original,
                                      lambda *args: completed.append(args))
  dialog._select_choice("one")
  dialog._select_choice("two")
  assert dialog._selected == set() and dialog._apply.enabled
  assert original == ["one", "two"] and completed == []
  dialog._finish(result)
  assert completed == [(result, [])]


def test_long_descriptions_and_narrow_headers_leave_content_below_the_actions(monkeypatch):
  mod, dialog = _text_dialog_test(monkeypatch)
  grid = sys.modules[MODULE_NAME]
  monkeypatch.setattr(grid, "measure_text_cached", lambda font, text, size, spacing=0: mod.rl.Vector2(len(text) * size * 0.6, size))
  dialog.title = "A setting with a long descriptive title that must wrap"
  dialog._subtitle = "A detailed description that wraps across several lines without colliding with Cancel and Apply."
  dialog.render(mod.rl.Rectangle(0, 0, 1000, 1080))
  assert dialog._cancel_rect.x >= 0 and dialog._cancel_rect.width >= mod.AS.MIN_TOUCH
  assert dialog._cancel_rect.x + dialog._cancel_rect.width < dialog._ok_rect.x
  assert dialog._ok_rect.y + dialog._ok_rect.height < dialog._content_rect.y
  assert dialog._content_rect.height > mod.AS.MIN_TOUCH


@pytest.mark.parametrize("result", [0, 1])
def test_button_assignments_do_not_write_until_the_parent_apply(monkeypatch, result):
  import ast
  from pathlib import Path
  grid = _import_aethergrid()
  tree = ast.parse((Path(__file__).parents[1] / "layouts/settings/starpilot/vehicle.py").read_text())
  node = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "ButtonActionComboDialog")
  namespace = dict(AetherSelectionDialog=grid.AetherSelectionDialog, AetherSettingsView=grid.AetherSettingsView,
                   SettingRow=grid.SettingRow, SettingSection=grid.SettingSection, PANEL_STYLE=grid.DEFAULT_PANEL_STYLE,
                   ACTION_NAME_BY_ID={0: "None", 1: "Action"}, ACTION_NAMES=["None", "Action"],
                   tr=str, rl=grid.rl, DialogResult=grid.DialogResult)
  exec(compile(ast.Module(body=[node], type_ignores=[]), "vehicle.py", "exec"), namespace)
  values, writes, editors = {"press": 0, "long": 1}, [], []
  params = types.SimpleNamespace(get_int=values.__getitem__, put_int=lambda key, value: writes.append((key, value)))
  controller = types.SimpleNamespace(_params=params, _show_action_picker=lambda *args, **kwargs: editors.append(kwargs))
  dialog = namespace["ButtonActionComboDialog"](controller, "Distance Button", ("press", "long"), ("Press", "Long Press"))
  dialog._edit_action("press")
  assert editors[0]["current_value"] == 0
  editors[0]["on_selected"](1)
  assert values == {"press": 0, "long": 1} and writes == []
  dialog._finish(result)
  assert writes == ([("press", 1), ("long", 1)] if result else [])


def test_picker_copy_comes_from_the_setting_row():
  grid = _import_aethergrid()
  _install_panel_stubs(grid)
  _clear_modules(PANEL_MODULE_NAME)
  panel = importlib.import_module(PANEL_MODULE_NAME)
  controller = panel._SettingsPage.__new__(panel._SettingsPage)
  controller._current_sub_panel = "hud"
  controller._manager_view = None
  controller._sub_panels = {"hud": grid.AetherSettingsView(controller, [grid.SettingSection("", [
    grid.SettingRow("CameraView", "value", "Camera View", "Choose the driving camera.")])])}
  assert controller._selection_details("CameraView") == ("Camera View", "Choose the driving camera.")
  assert controller._selection_details("UnlistedSetting") == ("Unlisted Setting", "")


@pytest.mark.parametrize("label", ["50%", "100%", "Auto", "Muted", "1.5s"])
@pytest.mark.parametrize("scale", [1.0, 1.242])
def test_value_text_centers_visible_glyphs_with_font_bearings(monkeypatch, label, scale):
  mod = _import_aethergrid()
  characters = list(dict.fromkeys(label))
  glyphs = [types.SimpleNamespace(offsetX=8 + i, offsetY=35 + i * 7, advanceX=110) for i, _ in enumerate(characters)]
  recs = [mod.rl.Rectangle(0, 0, 90, 125 - i * 4) for i, _ in enumerate(characters)]
  font = types.SimpleNamespace(baseSize=200, glyphs=glyphs, recs=recs)
  monkeypatch.setattr(mod, "FONT_SCALE", scale)
  monkeypatch.setattr(mod.gui_app, "font", lambda *_: font)
  monkeypatch.setattr(mod.rl, "get_glyph_index", lambda font, code: characters.index(chr(code)), raising=False)
  drawn = _calls(mod, "draw_text_ex")
  rect = mod.rl.Rectangle(144, 360, 1800, 184)
  mod.draw_centered_text(rect, label, 112, mod.AS.ACCENT_SOLID)
  _, _, position, size, _, _ = drawn[0]
  ink = mod.text_ink_bounds(font, label, size)
  assert abs(position.x + ink.x + ink.width / 2 - rect.x - rect.width / 2) <= 0.5
  assert abs(position.y + ink.y + ink.height / 2 - rect.y - rect.height / 2) <= 0.5


@pytest.mark.parametrize("increment", [False, True])
def test_stepper_symbols_are_centered_without_font_baselines(increment):
  mod = _import_aethergrid()
  lines = _calls(mod, "draw_line_ex")
  rect = mod.rl.Rectangle(144, 700, 160, 160)
  mod.draw_stepper_symbol(rect, increment=increment)
  assert len(lines) == (2 if increment else 1)
  points = [point for line in lines for point in line[:2]]
  assert (min(p.x for p in points) + max(p.x for p in points)) / 2 == rect.x + rect.width / 2
  assert (min(p.y for p in points) + max(p.y for p in points)) / 2 == rect.y + rect.height / 2


@pytest.mark.parametrize("kind", ["volume", "brightness"])
@pytest.mark.parametrize("result", [0, 1])
def test_live_picker_cancel_restores_original_and_apply_keeps_preview(monkeypatch, kind, result):
  import ast
  mod = _import_aethergrid()
  pushed, values = [], {"value": 50}
  sound = MagicMock()
  def set_value(value):
    values["value"] = value
  params = types.SimpleNamespace(get_int=lambda *_a, **_kw: values["value"], put_int=lambda key, value: set_value(value))
  if kind == "volume":
    path, name = "sounds.py", "_show_volume_slider"
    view = types.SimpleNamespace(_controller=types.SimpleNamespace(_params=params, _test_sound=sound,
                                 VOLUME_INFO={"value": {"title": "Sound", "subtitle": "", "min": 0}}))
  else:
    path, name = "system_settings.py", "_show_system_slider"
    spec = dict(title="Brightness", description="Preview brightness.", min=0, max=101, step=1, unit="%", labels={},
                live=True, get=lambda: values["value"], set=set_value)
    view = types.SimpleNamespace(_slider_specs={"value": spec})
  tree = ast.parse((Path(__file__).parents[1] / "layouts/settings/starpilot" / path).read_text())
  method = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == name)
  monkeypatch.setattr(mod.gui_app, "push_widget", pushed.append, raising=False)
  namespace = dict(gui_app=mod.gui_app, DialogResult=mod.DialogResult, AetherSliderDialog=mod.AetherSliderDialog,
                   PANEL_STYLE=mod.DEFAULT_PANEL_STYLE, tr=str)
  exec(compile(ast.Module(body=[method], type_ignores=[]), path, "exec"), namespace)
  namespace[name](view, "value")
  dialog = pushed[0]
  dialog._current_val = 75
  dialog._on_change(75)
  assert values["value"] == 75
  dialog._finish(result)
  assert values["value"] == (75 if result else 50)
  if kind == "volume":
    sound.assert_called_once_with("value")


if __name__ == "__main__":
  unittest.main()
