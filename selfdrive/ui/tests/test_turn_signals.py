"""Host regressions; texture uploads are mocked, raylib geometry is real.

pytest -c /dev/null --confcutdir=selfdrive/ui/tests selfdrive/ui/tests/test_turn_signals.py
"""
import ast
import re
from pathlib import Path
from types import SimpleNamespace

import pyray as rl
import pytest

from openpilot.selfdrive.ui.onroad.starpilot import turn_signals

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def scene(monkeypatch, tmp_path):
  class SubMaster(dict):
    valid = {"carState": True}
    alive = {"carState": True}
    recv_frame = {"carState": 100}

  car = SimpleNamespace(leftBlinker=True, rightBlinker=False, leftBlindspot=False, rightBlindspot=False)
  state = SimpleNamespace(started=True, started_frame=10, sm=SubMaster(carState=car), starpilot_toggles={"signal_icons": "frog"})
  uploaded, unloaded, draws = [], [], []
  clock = [10.0]

  def load(path):
    texture = SimpleNamespace(id=len(uploaded) + 1, width=350, height=500, name=Path(path).name, path=Path(path))
    uploaded.append(texture)
    return texture

  def draw(texture, source, dest, *_args):
    draws.append(SimpleNamespace(texture=texture, source=source, dest=dest))

  monkeypatch.setattr(turn_signals.time, "monotonic", lambda: clock[0])
  monkeypatch.setattr(turn_signals, "ACTIVE_SIGNALS_PATH", tmp_path / "unlinked_signals")
  monkeypatch.setattr(turn_signals.rl, "load_texture", load)
  monkeypatch.setattr(turn_signals.rl, "set_texture_filter", lambda *_args: None)
  monkeypatch.setattr(turn_signals.rl, "unload_texture", unloaded.append)
  monkeypatch.setattr(turn_signals.rl, "draw_texture_pro", draw)
  renderer = turn_signals.TurnSignalRenderer()
  return SimpleNamespace(renderer=renderer, state=state, car=car, clock=clock, uploaded=uploaded, unloaded=unloaded, draws=draws,
                         rect=rl.Rectangle(30, 30, 2100, 1020))


def test_left_frog_hops_at_125ms_and_loops_without_reupload(scene):
  renderer, state, rect = scene.renderer, scene.state, scene.rect
  renderer.render(rect, state)
  first_x = scene.draws[-1].dest.x
  assert scene.draws[-1].texture.name == "turn_signal_1.png"
  scene.clock[0] += 0.126
  renderer.render(rect, state)
  assert scene.draws[-1].texture.name == "turn_signal_2.png"
  assert scene.draws[-1].dest.x < first_x
  scene.clock[0] = 10.626
  renderer.render(rect, state)
  assert scene.draws[-1].texture.name == "turn_signal_6.png"
  scene.clock[0] = 10.751
  renderer.render(rect, state)
  assert scene.draws[-1].texture.name == "turn_signal_1.png"
  assert len(scene.uploaded) == 7
  assert not scene.unloaded


def test_right_frog_is_mirrored_and_moves_right(scene):
  scene.car.leftBlinker, scene.car.rightBlinker = False, True
  scene.renderer.render(scene.rect, scene.state)
  first = scene.draws[-1]
  scene.clock[0] += 0.251
  scene.renderer.render(scene.rect, scene.state)
  assert first.source.width == -350
  assert scene.draws[-1].dest.x > first.dest.x


def test_hazards_draw_both_sides_with_independent_blindspot_images(scene):
  scene.car.rightBlinker, scene.car.rightBlindspot = True, True
  scene.renderer.render(scene.rect, scene.state)
  left, right = scene.draws
  assert left.texture.name == "turn_signal_1.png"
  assert right.texture.name == "turn_signal_blindspot.png"
  assert left.source.width > 0 > right.source.width


def test_cancelling_switching_sides_and_new_drive_restart_the_animation(scene):
  scene.renderer.render(scene.rect, scene.state)
  scene.clock[0] += 0.3
  scene.renderer.render(scene.rect, scene.state)
  assert scene.draws[-1].texture.name == "turn_signal_3.png"
  scene.car.leftBlinker = False
  scene.renderer.render(scene.rect, scene.state)
  assert len(scene.draws) == 2
  scene.car.rightBlinker = True
  scene.renderer.render(scene.rect, scene.state)
  assert scene.draws[-1].texture.name == "turn_signal_1.png"
  scene.clock[0] += 0.3
  scene.state.started_frame = 90
  scene.renderer.render(scene.rect, scene.state)
  assert scene.draws[-1].texture.name == "turn_signal_1.png"


@pytest.mark.parametrize("condition", ["offroad", "invalid", "dead", "previous_drive", "disabled", "simple", "stock", "none"])
def test_no_animation_with_disabled_or_stale_vehicle_data(scene, condition):
  kwargs = {}
  if condition == "offroad":
    scene.state.started = False
  elif condition == "invalid":
    scene.state.sm.valid["carState"] = False
  elif condition == "dead":
    scene.state.sm.alive["carState"] = False
  elif condition == "previous_drive":
    scene.state.started_frame = 101
  elif condition == "disabled":
    kwargs["enabled"] = False
  elif condition == "simple":
    scene.state.starpilot_toggles["simple_mode"] = True
  else:
    scene.state.starpilot_toggles["signal_icons"] = condition
  scene.renderer.render(scene.rect, scene.state, **kwargs)
  assert not scene.draws
  assert not scene.uploaded


@pytest.mark.parametrize("width,height,margin", [(2100, 1020, 0), (1200, 1020, 300), (424, 240, 0), (424, 240, 200)])
@pytest.mark.parametrize("alert_at_top", [False, True])
def test_animation_fits_viewport_and_leaves_alert_space(scene, width, height, margin, alert_at_top):
  rect = rl.Rectangle(75, 35, width, height)
  scene.car.rightBlinker = True
  for index in range(6):
    scene.clock[0] = 10 + index * 0.126
    scene.renderer.render(rect, scene.state, top_margin=margin if alert_at_top else 0, bottom_margin=0 if alert_at_top else margin)
  for draw in scene.draws:
    assert draw.dest.x >= rect.x - 0.001
    assert draw.dest.y >= rect.y + (margin if alert_at_top else 0) - 0.001
    assert draw.dest.x + draw.dest.width <= rect.x + rect.width + 0.001
    assert draw.dest.y + draw.dest.height <= rect.y + rect.height - (0 if alert_at_top else margin) + 0.001


def _start_new_signal(scene):
  """Turn the blinker(s) off for a frame and back on, like a new signal."""
  left, right = scene.car.leftBlinker, scene.car.rightBlinker
  scene.car.leftBlinker = scene.car.rightBlinker = False
  scene.renderer.render(scene.rect, scene.state)
  scene.car.leftBlinker, scene.car.rightBlinker = left, right


def test_signal_folder_is_scanned_on_pack_change_and_new_signals_only(scene, monkeypatch):
  scans = []
  original = turn_signals.TurnSignalRenderer._scan
  monkeypatch.setattr(turn_signals.TurnSignalRenderer, "_scan", staticmethod(lambda d: (d == turn_signals.ACTIVE_SIGNALS_PATH and scans.append(d)) or original(d)))
  # (one check = one look at the active folder, plus the bundled fallback if needed)
  scene.car.leftBlinker = False
  scene.renderer.render(scene.rect, scene.state)  # drive start: initial load
  initial_scans, initial_uploads = len(scans), len(scene.uploaded)
  assert initial_uploads == 7

  for _ in range(100):  # idle for a long time: no file system access
    scene.clock[0] += 0.5
    scene.renderer.render(scene.rect, scene.state)
  assert len(scans) == initial_scans

  scene.car.leftBlinker = True  # new signal: one rescan, nothing reloaded
  scene.renderer.render(scene.rect, scene.state)
  assert len(scans) == initial_scans + 1
  for _ in range(100):  # mid-signal: no further scans
    scene.clock[0] += 0.5
    scene.renderer.render(scene.rect, scene.state)
  assert len(scans) == initial_scans + 1
  assert len(scene.uploaded) == initial_uploads and not scene.unloaded

  scene.renderer.render(scene.rect, scene.state, enabled=False)  # e.g. full alert mid-signal
  scene.renderer.render(scene.rect, scene.state)
  assert len(scans) == initial_scans + 2

  scene.state.starpilot_toggles["signal_icons"] = "halloween_week"  # pack change: immediate rescan
  scene.renderer.render(scene.rect, scene.state)
  assert len(scans) > initial_scans + 2


def test_missing_corrupt_and_empty_themes_are_harmless(scene, monkeypatch, tmp_path):
  monkeypatch.setattr(turn_signals, "ACTIVE_SIGNALS_PATH", tmp_path / "missing")
  scene.state.starpilot_toggles["signal_icons"] = "custom"
  scene.renderer.render(scene.rect, scene.state)
  directory = tmp_path / "missing"
  directory.mkdir()
  (directory / "traditional_0").touch()
  (directory / "turn_signal_1.png").write_bytes(b"invalid PNG")
  monkeypatch.setattr(turn_signals.rl, "load_texture", lambda _path: SimpleNamespace(id=0))
  _start_new_signal(scene)
  scene.renderer.render(scene.rect, scene.state)
  assert not scene.draws


def test_theme_refresh_sorts_frames_numerically_and_releases_old_textures(scene, monkeypatch, tmp_path):
  directory = tmp_path / "theme"
  directory.mkdir()
  for name in ("turn_signal_10.png", "turn_signal_2.png", "traditional_125"):
    (directory / name).touch()
  active = tmp_path / "active"
  active.symlink_to(directory, target_is_directory=True)
  monkeypatch.setattr(turn_signals, "ACTIVE_SIGNALS_PATH", active)
  scene.renderer.render(scene.rect, scene.state)
  old_textures = scene.uploaded.copy()
  scene.state.starpilot_toggles["signal_icons"] = "custom"
  scene.renderer.render(scene.rect, scene.state)
  assert scene.draws[-1].texture.name == "turn_signal_2.png"
  assert sorted(t.id for t in scene.unloaded) == sorted(t.id for t in old_textures)
  scene.clock[0] += 0.126
  scene.renderer.render(scene.rect, scene.state)
  assert scene.draws[-1].texture.name == "turn_signal_10.png"
  replacement = tmp_path / "replacement"
  replacement.mkdir()
  (replacement / "turn_signal.png").touch()
  (replacement / "static_0").touch()
  active.unlink()
  active.symlink_to(replacement, target_is_directory=True)
  _start_new_signal(scene)
  scene.renderer.render(scene.rect, scene.state)
  assert scene.draws[-1].texture.name == "turn_signal.png"
  assert len(scene.unloaded) == len(old_textures) + 2


def test_close_is_idempotent_and_reenabling_loads_immediately(scene):
  scene.renderer.render(scene.rect, scene.state)
  scene.state.starpilot_toggles["signal_icons"] = "stock"
  scene.renderer.render(scene.rect, scene.state)
  assert len(scene.unloaded) == 7
  scene.renderer.close()
  assert len(scene.unloaded) == 7
  scene.state.starpilot_toggles["signal_icons"] = "frog"
  scene.renderer.render(scene.rect, scene.state)
  assert len(scene.draws) == 2
  assert len(scene.uploaded) == 14


def test_random_theme_uses_active_signals_even_when_saved_selection_is_stock(scene, monkeypatch, tmp_path):
  (tmp_path / "turn_signal.png").touch()
  monkeypatch.setattr(turn_signals, "ACTIVE_SIGNALS_PATH", tmp_path)
  scene.state.starpilot_toggles.update(signal_icons="stock", random_themes=True)
  scene.renderer.render(scene.rect, scene.state)
  assert scene.draws[-1].texture.name == "turn_signal.png"


def test_halloween_overrides_saved_frogs_and_frogs_return_afterward(scene, monkeypatch):
  halloween = turn_signals.ASSETS_PATH / "holiday_themes/halloween_week/signals"
  scene.renderer.render(scene.rect, scene.state)
  assert scene.draws[-1].texture.path.parent == turn_signals.FROG_SIGNALS_PATH

  # The theme manager publishes the holiday as the effective signal_icons;
  # it leaves the user's saved SignalAnimation preference intact.
  monkeypatch.setattr(turn_signals, "ACTIVE_SIGNALS_PATH", halloween)
  scene.state.starpilot_toggles.update(signal_icons="halloween_week", current_holiday_theme="halloween_week")
  for index in range(6):
    scene.clock[0] = 10 + index * 0.126
    scene.renderer.render(scene.rect, scene.state)
    assert scene.draws[-1].texture.path == halloween / f"turn_signal_{index + 1}.png"

  scene.car.leftBlindspot = True
  scene.renderer.render(scene.rect, scene.state)
  assert scene.draws[-1].texture.path == halloween / "turn_signal_blindspot.png"

  scene.car.leftBlindspot = False
  monkeypatch.setattr(turn_signals, "ACTIVE_SIGNALS_PATH", turn_signals.FROG_SIGNALS_PATH)
  scene.state.starpilot_toggles.update(signal_icons="frog", current_holiday_theme="stock")
  scene.renderer.render(scene.rect, scene.state)
  assert scene.draws[-1].texture.path.parent == turn_signals.FROG_SIGNALS_PATH
  assert scene.draws[-1].texture.name == "turn_signal_1.png"


def test_active_frog_edits_take_precedence_and_reload_without_restart(scene, monkeypatch, tmp_path):
  installed = tmp_path / "theme_packs/frog/signals"
  installed.mkdir(parents=True)
  frame = installed / "turn_signal_1.png"
  frame.write_bytes(b"custom frog")
  active = tmp_path / "active"
  active.symlink_to(installed, target_is_directory=True)
  monkeypatch.setattr(turn_signals, "ACTIVE_SIGNALS_PATH", active)
  scene.renderer.render(scene.rect, scene.state)
  assert len(scene.uploaded) == 1
  assert scene.draws[-1].texture.path.resolve() == frame
  old_texture = scene.draws[-1].texture
  frame.write_bytes(b"edited frog frame")
  _start_new_signal(scene)
  scene.renderer.render(scene.rect, scene.state)
  assert scene.unloaded == [old_texture]
  assert len(scene.uploaded) == 2
  assert scene.draws[-1].texture.path.resolve() == frame


def test_switching_to_frog_does_not_show_previous_pack_while_link_is_stale(scene, monkeypatch, tmp_path):
  previous = tmp_path / "theme_packs/previous/signals"
  previous.mkdir(parents=True)
  (previous / "turn_signal_1.png").touch()
  active = tmp_path / "active"
  active.symlink_to(previous, target_is_directory=True)
  monkeypatch.setattr(turn_signals, "ACTIVE_SIGNALS_PATH", active)
  scene.state.starpilot_toggles["signal_icons"] = "previous"
  scene.renderer.render(scene.rect, scene.state)
  assert scene.draws[-1].texture.path.resolve().parent == previous

  scene.state.starpilot_toggles["signal_icons"] = "frog"
  scene.clock[0] += 0.01
  scene.renderer.render(scene.rect, scene.state)
  assert scene.draws[-1].texture.path.parent == turn_signals.FROG_SIGNALS_PATH

  installed = tmp_path / "theme_packs/frog/signals"
  installed.mkdir(parents=True)
  (installed / "turn_signal_1.png").touch()
  active.unlink()
  active.symlink_to(installed, target_is_directory=True)
  _start_new_signal(scene)
  scene.renderer.render(scene.rect, scene.state)
  assert scene.draws[-1].texture.path.resolve().parent == installed


def _source_class(path, class_name, methods, namespace):
  """Exercise settings/layer methods without importing native messaging."""
  tree = ast.parse((ROOT / path).read_text())
  cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name)
  cls.body = [node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name in methods]
  cls.bases = []
  exec(compile(ast.fix_missing_locations(ast.Module(body=[cls], type_ignores=[])), path, "exec"), namespace)
  return namespace[class_name]


class Params:
  def __init__(self, **values):
    self.values = values

  def get(self, key, **_kwargs):
    return self.values.get(key)

  def get_bool(self, key):
    return bool(self.values.get(key))

  def put(self, key, value):
    self.values[key] = value

  put_bool = put


@pytest.mark.parametrize("saved", ["stock", "gif_only", "missing"])
def test_comma3_picker_only_offers_packs_with_renderable_png_frames(tmp_path, saved):
  packs = {
    "gif_only": "turn_signal.gif",
    "blindspot_only": "turn_signal_blindspot.png",
    "unsupported_name": "turn_signal_bad.png",
    "static": "turn_signal.png",
    "sequence": "turn_signal_10.PNG",
    "directory_only": "turn_signal_1.png",
  }
  for name, filename in packs.items():
    directory = tmp_path / "theme_packs" / name / "signals"
    directory.mkdir(parents=True)
    if name == "directory_only":
      (directory / filename).mkdir()
    else:
      (directory / filename).touch()
  cls = _source_class("selfdrive/ui/layouts/settings/starpilot/appearance.py", "StarPilotAppearanceLayout",
                      {"_build_theme_options"}, dict(
                        THEME_KEY_CONFIG={"SignalAnimation": {"default": "stock", "extra": [("stock", "None"), ("frog", "Frog")]}},
                        THEME_SAVE_PATH=tmp_path, SIGNAL_FRAME_PATTERN=turn_signals.FRAME_PATTERN, _theme_display_name=str.title))
  layout = cls()
  layout._params = Params(SignalAnimation=saved)
  options, mapping, current = layout._build_theme_options("SignalAnimation")
  assert options == ["Frog", "None", "Sequence", "Static"]
  assert mapping == {"None": "stock", "Frog": "frog", "Static": "static", "Sequence": "sequence"}
  assert current == "None"


@pytest.mark.parametrize("custom_enabled", [False, True])
def test_comma3_selection_disables_saved_random_themes_without_resetting_other_preferences(tmp_path, custom_enabled):
  dialogs = []
  config = {"SignalAnimation": {"default": "stock", "extra": [("stock", "None"), ("frog", "Frog")]}}
  def dialog(_title, _themes, _current, callback):
    return SimpleNamespace(selection="Frog", confirm=lambda: callback(1))
  cls = _source_class("selfdrive/ui/layouts/settings/starpilot/appearance.py", "StarPilotAppearanceLayout",
                      {"_build_theme_options", "_get_theme_value", "_show_theme_selector"},
                      dict(THEME_KEY_CONFIG=config, THEME_SAVE_PATH=tmp_path, _theme_display_name=str.title, tr=str,
                           MultiOptionDialog=dialog, DialogResult=SimpleNamespace(CONFIRM=1),
                           gui_app=SimpleNamespace(push_widget=dialogs.append)))
  layout = cls()
  layout._params = Params(SignalAnimation="stock", CustomThemes=custom_enabled, RandomThemes=True, ColorScheme="saved_colors")
  layout._show_theme_selector("SignalAnimation")
  dialogs[0].confirm()
  assert layout._params.values == {"SignalAnimation": "frog", "CustomThemes": True, "RandomThemes": False, "ColorScheme": "saved_colors"}
  assert layout._get_theme_value("SignalAnimation") == "Frog"


@pytest.mark.parametrize("custom_enabled", [False, True])
def test_comma4_selection_disables_random_themes_and_preserves_other_preferences(custom_enabled):
  dialogs, notifications = [], []
  def dialog(**kwargs):
    return SimpleNamespace(get_selected_option=lambda: "Frog", confirm=kwargs["right_btn_callback"])
  cls = _source_class("selfdrive/ui/mici/layouts/settings/visuals.py", "TurnSignalAnimationBigButton",
                      {"refresh", "_show_selector"},
                      dict(BigMultiOptionDialog=dialog, gui_app=SimpleNamespace(push_widget=dialogs.append),
                           update_starpilot_toggles=lambda: notifications.append(True)))
  button = cls()
  button._params = Params(SignalAnimation="stock", CustomThemes=custom_enabled, RandomThemes=True, IconPack="saved_icons")
  labels = []
  button.set_value = labels.append
  button._show_selector()
  dialogs[0].confirm()
  assert button._params.values == {"SignalAnimation": "frog", "CustomThemes": True, "RandomThemes": False, "IconPack": "saved_icons"}
  assert labels == ["frog"]
  assert notifications == [True]
  dialogs[0].get_selected_option = lambda: "None"
  dialogs[0].confirm()
  assert button._params.values["SignalAnimation"] == "stock"
  assert labels[-1] == "none"


@pytest.mark.parametrize("alert_size,expected_enabled,expected_margin", [(None, True, 0), (1, True, 200), (3, False, 0)])
def test_comma3_integration_reserves_alert_space_and_clips(scene, monkeypatch, alert_size, expected_enabled, expected_margin):
  calls, clipping = [], []
  monkeypatch.setattr(rl, "begin_scissor_mode", lambda *_args: clipping.append("begin"))
  monkeypatch.setattr(rl, "end_scissor_mode", lambda: clipping.append("end"))
  cls = _source_class("selfdrive/ui/onroad/starpilot/starpilot_onroad_view.py", "StarPilotOnroadView",
                      {"_render_turn_signals"}, dict(rl=rl, ui_state=scene.state, AlertSize=SimpleNamespace(full=3)))
  view = cls()
  view._content_rect = scene.rect
  alert = None if alert_size is None else SimpleNamespace(size=alert_size)
  view.alert_renderer = SimpleNamespace(will_render=lambda: (alert, False),
                                        rect=rl.Rectangle(30, 30 + 1020 - expected_margin, 2100, expected_margin))
  view._turn_signals = SimpleNamespace(render=lambda *args, **kwargs: calls.append(kwargs))
  view._turn_signal_margin = SimpleNamespace(update=lambda target: target)
  view._render_turn_signals()
  assert calls == [dict(enabled=expected_enabled, bottom_margin=expected_margin)]
  assert clipping == ["begin", "end"]


def test_comma3_frogs_ease_with_alerts_instead_of_snapping(scene, monkeypatch):
  from openpilot.common.filter_simple import FirstOrderFilter
  monkeypatch.setattr(rl, "begin_scissor_mode", lambda *_args: None)
  monkeypatch.setattr(rl, "end_scissor_mode", lambda: None)
  cls = _source_class("selfdrive/ui/onroad/starpilot/starpilot_onroad_view.py", "StarPilotOnroadView",
                      {"_render_turn_signals"}, dict(rl=rl, ui_state=scene.state, AlertSize=SimpleNamespace(full=3)))
  view = cls()
  view._content_rect = scene.rect
  margins = []
  view._turn_signals = SimpleNamespace(render=lambda *args, **kwargs: margins.append(kwargs["bottom_margin"]))
  view._turn_signal_margin = FirstOrderFilter(0.0, 0.1, 1 / 20)
  small = SimpleNamespace(size=1)
  state = {"alert": None, "out": True}
  view.alert_renderer = SimpleNamespace(will_render=lambda: (state["alert"], state["out"]),
                                        rect=rl.Rectangle(30, 30 + 1020 - 271, 2100, 271))

  def frames(count):
    for _ in range(count):
      view._render_turn_signals()

  frames(3)
  assert margins == [0, 0, 0]
  state.update(alert=small, out=False)  # lane-change alert appears mid-hop
  frames(20)
  rising = margins[3:]
  assert 0 < rising[0] < 271 * 0.5
  assert all(b >= a for a, b in zip(rising, rising[1:], strict=False))
  assert rising[-1] == pytest.approx(271, abs=1)
  state["out"] = True  # alert fading out: frogs settle back down smoothly
  frames(20)
  falling = margins[23:]
  assert 271 * 0.5 < falling[0] < 271
  assert all(b <= a for a, b in zip(falling, falling[1:], strict=False))
  assert falling[-1] == pytest.approx(0, abs=1)
  state.update(alert=SimpleNamespace(size=3), out=False)  # full alert: hidden, no baseline climb
  frames(5)
  assert margins[-1] == pytest.approx(0, abs=1)


def _load_mici_alert_background_height():
  path = "selfdrive/ui/mici/onroad/alert_renderer.py"
  tree = ast.parse((ROOT / path).read_text())
  function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "get_alert_background_height")
  namespace = {"Alert": object}
  exec(compile(ast.Module(body=[function], type_ignores=[]), path, "exec"), namespace)
  return namespace["get_alert_background_height"]


MICI_ALERT_CASES = [
  (None, "", True, True, 0),
  (1, "preLaneChangeLeft/warning", True, True, 140),
  (2, "preLaneChangeRight/warning", True, True, 140),
  (1, "laneChange/warning", True, True, 140),
  (1, "laneChangeBlocked/warning", True, True, 200),
  (1, "laneChangeBlockedLoud/warning", True, False, 240),
  (1, "personalityChanged/permanent", True, False, 240),
  (2, "steerSaturated/warning", True, False, 240),
  (3, "preLaneChangeLeft/warning", True, False, 140),
  (3, "", True, False, 240),
  (None, "", False, False, 0),
]


@pytest.mark.parametrize("alert_size,alert_type,enabled,expected_enabled,margin", MICI_ALERT_CASES)
def test_comma4_integration_reserves_alert_space(scene, alert_size, alert_type, enabled, expected_enabled, margin):
  calls = []
  cls = _source_class("selfdrive/ui/mici/onroad/augmented_road_view.py", "AugmentedRoadView",
                      {"_render_turn_signals"}, dict(ui_state=scene.state, log=SimpleNamespace(
                        SelfdriveState=SimpleNamespace(AlertSize=SimpleNamespace(full=3))),
                        get_alert_background_height=_load_mici_alert_background_height()))
  view = cls()
  view._content_rect = rl.Rectangle(0, 0, 424, 240)
  view._turn_signals = SimpleNamespace(render=lambda *args, **kwargs: calls.append(kwargs))
  view._render_turn_signals(None if alert_size is None else SimpleNamespace(size=alert_size, alert_type=alert_type), enabled)
  assert calls == [dict(enabled=expected_enabled, top_margin=margin)]


@pytest.mark.parametrize("alert_size,alert_type,_enabled,_expected_enabled,margin", MICI_ALERT_CASES)
def test_comma4_background_and_signal_margin_use_the_same_actual_event_layout(scene, monkeypatch,
                                                                            alert_size, alert_type, _enabled, _expected_enabled, margin):
  draws = []
  monkeypatch.setattr(rl, "draw_rectangle", lambda *_args: draws.append(_args))
  monkeypatch.setattr(rl, "draw_rectangle_gradient_v", lambda *_args: draws.append(_args))
  cls = _source_class("selfdrive/ui/mici/onroad/alert_renderer.py", "AlertRenderer", {"_draw_background"},
                      dict(rl=rl, Alert=object, ALERT_COLORS={0: rl.Color(0, 0, 0, 255)}, AlertStatus=SimpleNamespace(normal=0),
                           get_alert_background_height=_load_mici_alert_background_height()))
  renderer = cls()
  renderer._rect = rl.Rectangle(0, 0, 424, 240)
  renderer._alpha_filter = SimpleNamespace(x=1)
  alert = None if alert_size is None else SimpleNamespace(size=alert_size, alert_type=alert_type, status=0)
  if alert is None:
    assert _load_mici_alert_background_height()(None, 240) == 0
  else:
    renderer._draw_background(alert)
    assert sum(call[3] for call in draws) == margin


def test_comma3_holiday_themes_row_reads_and_writes_the_setting():
  tree = ast.parse((ROOT / "selfdrive/ui/layouts/settings/starpilot/appearance.py").read_text())
  call = next(node for node in ast.walk(tree) if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "SettingRow"
              and node.args and isinstance(node.args[0], ast.Constant) and node.args[0].value == "HolidayThemes")
  view = SimpleNamespace(_params=Params(HolidayThemes=True))
  args, kwargs = eval(compile(ast.Expression(call), "appearance.py", "eval"),
                      dict(SettingRow=lambda *a, **k: (a, k), tr_noop=str, self=view))
  assert args[:3] == ("HolidayThemes", "toggle", "Holiday Themes")
  assert "visible" not in kwargs  # shown even when driving-screen widgets are off
  assert kwargs["get_state"]() is True
  kwargs["set_state"](False)
  assert view._params.values["HolidayThemes"] is False
  assert kwargs["get_state"]() is False


def test_comma4_holiday_themes_toggle_saves_and_refreshes_starpilot_toggles():
  tree = ast.parse((ROOT / "selfdrive/ui/mici/layouts/settings/visuals.py").read_text())
  cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "StarPilotBigParamControl")
  layout = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "VisualsLayoutMici")
  assert "StarPilotBigParamControl('holiday themes', 'HolidayThemes')" in ast.unparse(layout)
  notifications = []

  class BigParamControl:  # mirrors the real widget: flip, then save
    def __init__(self, text, param):
      self.param, self.params, self._checked = param, Params(HolidayThemes=True), True

    def _handle_mouse_release(self, _pos):
      self._checked = not self._checked
      self.params.put_bool(self.param, self._checked)

  namespace = dict(BigParamControl=BigParamControl,
                   update_starpilot_toggles=lambda: notifications.append(dict(control.params.values)))
  exec(compile(ast.Module(body=[cls], type_ignores=[]), "visuals.py", "exec"), namespace)
  control = namespace["StarPilotBigParamControl"]("holiday themes", "HolidayThemes")
  control._handle_mouse_release(None)
  assert notifications == [{"HolidayThemes": False}]  # saved before StarPilot is told to refresh


# Hopping animations use the frog's 350x500 frames; static indicators use a short
# 350x170 canvas so the static style places them level with the current speed.
BUNDLED_LAYOUTS = {
  "pouncing_cat": ("traditional_125", 6, (350, 500)),
  "shooting_star": ("traditional_125", 6, (350, 500)),
  "sequential": ("static_125", 6, (350, 170)),
  "flow": ("static_62", 12, (350, 170)),
  "open_flow": ("static_62", 12, (350, 170)),
  "glide": ("static_62", 12, (350, 170)),
  # full screen height so the ball can drop in from the top; narrow because the renderer moves it
  "bouncing_ball": ("traditional_75", 40, (64, 1080)),
}
STATIC_PACKS = ["sequential", "flow", "open_flow", "glide"]


def _png_size(path):
  import struct
  header = path.read_bytes()[:26]
  assert header[:8] == b"\x89PNG\r\n\x1a\n"
  return struct.unpack(">II", header[16:24]), header[25]


@pytest.mark.parametrize("pack", sorted(BUNDLED_LAYOUTS))
def test_bundled_signal_packs_have_the_expected_layout(pack):
  marker, frames, size = BUNDLED_LAYOUTS[pack]
  directory = turn_signals.ASSETS_PATH / f"signal_packs/{pack}/signals"
  assert turn_signals.BUNDLED_SIGNAL_PATHS[pack] == directory
  names = sorted(path.name for path in directory.iterdir())
  assert names == sorted([marker, *(f"turn_signal_{i}.png" for i in range(1, frames + 1)), "turn_signal_blindspot.png"])
  for name in (n for n in names if n.endswith(".png")):
    png_size, color_type = _png_size(directory / name)
    assert png_size == size
    assert color_type == 6  # RGBA: transparent background like the frog frames


def test_every_bundled_pack_is_offered_on_both_devices():
  appearance = (ROOT / "selfdrive/ui/layouts/settings/starpilot/appearance.py").read_text()
  visuals = (ROOT / "selfdrive/ui/mici/layouts/settings/visuals.py").read_text()
  for slug in turn_signals.BUNDLED_SIGNAL_PATHS:
    assert f'("{slug}", ' in appearance
    assert f': "{slug}"' in visuals


@pytest.mark.parametrize("pack", ["frog", *sorted(BUNDLED_LAYOUTS)])
def test_bundled_packs_render_before_the_theme_manager_links_them(scene, monkeypatch, tmp_path, pack):
  stock = tmp_path / "stock_theme/signals"
  stock.mkdir(parents=True)
  active = tmp_path / "active"
  active.symlink_to(stock, target_is_directory=True)
  monkeypatch.setattr(turn_signals, "ACTIVE_SIGNALS_PATH", active)
  scene.state.starpilot_toggles["signal_icons"] = pack
  scene.renderer.render(scene.rect, scene.state)
  assert scene.draws[-1].texture.path == turn_signals.BUNDLED_SIGNAL_PATHS[pack] / "turn_signal_1.png"

  installed = tmp_path / f"theme_packs/{pack}/signals"
  installed.mkdir(parents=True)
  (installed / "turn_signal_1.png").write_bytes(b"installed copy")
  active.unlink()
  active.symlink_to(installed, target_is_directory=True)
  _start_new_signal(scene)
  scene.renderer.render(scene.rect, scene.state)
  assert scene.draws[-1].texture.path.resolve() == installed / "turn_signal_1.png"


def test_switching_between_frog_and_cat_swaps_textures(scene):
  scene.renderer.render(scene.rect, scene.state)
  assert scene.draws[-1].texture.path.parent == turn_signals.FROG_SIGNALS_PATH
  frog_textures = scene.uploaded.copy()
  scene.state.starpilot_toggles["signal_icons"] = "pouncing_cat"
  scene.renderer.render(scene.rect, scene.state)
  assert scene.draws[-1].texture.path.parent == turn_signals.POUNCING_CAT_SIGNALS_PATH
  assert sorted(t.id for t in scene.unloaded) == sorted(t.id for t in frog_textures)


def test_comma3_menu_offers_cat_once_whether_or_not_it_is_installed(tmp_path):
  import re
  tree = ast.parse((ROOT / "selfdrive/ui/layouts/settings/starpilot/appearance.py").read_text())
  config = next(node for node in tree.body if isinstance(node, ast.Assign) and node.targets[0].id == "THEME_KEY_CONFIG")
  display = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_theme_display_name")
  namespace = {"re": re}
  exec(compile(ast.Module(body=[config, display], type_ignores=[]), "appearance.py", "exec"), namespace)
  cls = _source_class("selfdrive/ui/layouts/settings/starpilot/appearance.py", "StarPilotAppearanceLayout",
                      {"_build_theme_options", "_get_theme_value"},
                      dict(namespace, THEME_SAVE_PATH=tmp_path, SIGNAL_FRAME_PATTERN=turn_signals.FRAME_PATTERN, tr=str))
  layout = cls()
  layout._params = Params(SignalAnimation="pouncing_cat", CustomThemes=True)
  expected = ["Bouncing Ball", "Flow", "Frog", "Glide", "None", "Open Flow", "Pouncing Cat", "Sequential", "Shooting Star"]
  assert layout._build_theme_options("SignalAnimation")[0] == expected
  for pack in turn_signals.BUNDLED_SIGNAL_PATHS:  # after boot these are also installed theme packs
    (tmp_path / f"theme_packs/{pack}/signals").mkdir(parents=True)
    (tmp_path / f"theme_packs/{pack}/signals/turn_signal_1.png").touch()
  options, mapping, current = layout._build_theme_options("SignalAnimation")
  assert options == expected
  assert mapping["Pouncing Cat"] == "pouncing_cat" and current == "Pouncing Cat"
  assert mapping["Shooting Star"] == "shooting_star" and mapping["Sequential"] == "sequential"
  assert mapping["Open Flow"] == "open_flow"
  assert layout._get_theme_value("SignalAnimation") == "Pouncing Cat"


def test_comma4_menu_offers_and_saves_the_cat():
  dialogs = []
  def dialog(**kwargs):
    dialogs.append(kwargs)
    return SimpleNamespace(get_selected_option=lambda: "Pouncing Cat", confirm=kwargs["right_btn_callback"])
  cls = _source_class("selfdrive/ui/mici/layouts/settings/visuals.py", "TurnSignalAnimationBigButton",
                      {"refresh", "_show_selector"},
                      dict(BigMultiOptionDialog=dialog, gui_app=SimpleNamespace(push_widget=lambda d: None),
                           update_starpilot_toggles=lambda: None))
  button = cls()
  button._params = Params(SignalAnimation="frog", CustomThemes=True)
  labels = []
  button.set_value = labels.append
  button._show_selector()
  assert dialogs[0]["options"] == ["None", "Sequential", "Flow", "Open Flow", "Glide", "Frog", "Pouncing Cat",
                                   "Shooting Star", "Bouncing Ball"]
  assert dialogs[0]["default"] == "Frog"
  dialogs[0]["right_btn_callback"]()
  assert button._params.values["SignalAnimation"] == "pouncing_cat"
  assert labels == ["pouncing cat"]


def test_shooting_star_trail_points_back_along_its_arc():
  """The star rises then falls; its trail must stream behind it (where it came from)."""
  import importlib.util
  spec = importlib.util.spec_from_file_location("star", ROOT / "starpilot/tools/make_shooting_star_signals.py")
  star = importlib.util.module_from_spec(spec)
  try:
    spec.loader.exec_module(star)
  except ModuleNotFoundError:
    pytest.skip("cairosvg is a dev-only dependency of the drawing script")
  heights = [star.TOP + star.ARC_K * (t - (star.FRAMES - 1) / 2) ** 2 for t in range(star.FRAMES)]
  assert heights[0] > heights[2] and heights[-1] > heights[3]  # one full arc: up, then down
  for t in range(star.FRAMES):
    svg = star.frame_svg(t)
    x1, y1, x2, y2 = (float(v) for v in re.search(r'id="t%da".*?x1="([\d.-]+)" y1="([\d.-]+)" x2="([\d.-]+)" y2="([\d.-]+)"' % t, svg).groups())
    assert x2 > x1  # the star travels left, so its trail extends to the right
    if t < 2:
      assert y2 > y1  # rising: trail trails downwards
    elif t > 3:
      assert y2 < y1  # falling: trail trails upwards


@pytest.mark.parametrize("pack", STATIC_PACKS)
def test_static_indicators_stay_level_with_the_speed_and_animate_in_place(scene, monkeypatch, pack):
  """The card never moves; left sits left of centre, right is mirrored right of centre, both at speed height."""
  def load(path):  # real frame sizes, so the 350x170 placement is exercised
    (width, height), _ = _png_size(Path(path))
    texture = SimpleNamespace(id=len(scene.uploaded) + 1, width=width, height=height, name=Path(path).name)
    scene.uploaded.append(texture)
    return texture
  monkeypatch.setattr(turn_signals.rl, "load_texture", load)
  marker, frames, _ = BUNDLED_LAYOUTS[pack]
  step = int(marker.split("_")[1]) / 1000 + 0.001
  scene.state.starpilot_toggles["signal_icons"] = pack
  scene.car.rightBlinker = True  # hazards: both sides
  for index in range(frames):
    scene.clock[0] = 10 + index * step
    scene.renderer.render(scene.rect, scene.state)
  left = [d for d in scene.draws if d.source.width > 0]
  right = [d for d in scene.draws if d.source.width < 0]
  assert [d.texture.name for d in left] == [f"turn_signal_{i}.png" for i in range(1, frames + 1)]
  assert len({d.dest.x for d in left}) == 1 and len({d.dest.x for d in right}) == 1
  assert len({d.dest.y for d in scene.draws}) == 1
  rect = scene.rect
  assert left[0].dest.x + left[0].dest.width == pytest.approx(rect.x + rect.width * 0.375)
  assert right[0].dest.x == pytest.approx(rect.x + rect.width * 0.625)
  # Current speed is centred at y=180 on a 2160x1080 screen; the cards (canvas y 9..121) straddle it.
  scale = min(rect.width / 2160, rect.height / 1080)
  card_top, card_bottom = left[0].dest.y + 9 * scale, left[0].dest.y + 121 * scale
  assert card_top < 180 < card_bottom


def test_sequential_chevrons_light_towards_the_turn():
  seq = _load_tool("make_sequential_signals")
  # Frames point left (mirrored for right turns): chevron 0 is nearest the speed.
  assert seq.CHEVRON_X == sorted(seq.CHEVRON_X, reverse=True)
  assert seq.SEQUENCE == [(), (0,), (0, 1), (0, 1, 2), (0, 1, 2), ()]


def _load_tool(name):
  import importlib.util
  spec = importlib.util.spec_from_file_location(name, ROOT / f"starpilot/tools/{name}.py")
  module = importlib.util.module_from_spec(spec)
  try:
    spec.loader.exec_module(module)
  except ModuleNotFoundError:
    pytest.skip("cairosvg is a dev-only dependency of the drawing scripts")
  return module


def test_flow_chevrons_glide_towards_the_turn_and_loop_seamlessly():
  motion = _load_tool("make_motion_signals")
  step = 2 * motion.FLOW_SPACING / motion.FRAMES
  x, _, w, _ = motion.FLOW_CARD
  for frame in range(motion.FRAMES):
    now, nxt = motion.flow_chevrons(frame), motion.flow_chevrons(frame + 1)
    # every chevron that stays visible has moved left (towards a left turn) by one step
    moved = {round(cx - step, 3) for cx, _ in now}
    assert {round(cx, 3) for cx, _ in nxt if round(cx, 3) in moved}
    assert all(x < cx < x + w for cx, _ in now)
    assert all(0 < opacity <= 1 for _, opacity in now)
  start = sorted(round(cx, 3) for cx, _ in motion.flow_chevrons(0))
  assert sorted(round(cx, 3) for cx, _ in motion.flow_chevrons(motion.FRAMES)) == start  # seamless loop
  # chevrons appear at the inner (speed) edge and fade out at the outer edge
  assert motion.edge_fade(x + 18, x + 18, x + w - 18) == 0 == motion.edge_fade(x + w - 18, x + 18, x + w - 18)


def test_glide_chevrons_slide_out_and_fade():
  motion = _load_tool("make_motion_signals")
  x, _, w, _ = motion.GLIDE_CARD
  assert w == 176  # Set Speed card width (CONTROL_WIDTH)
  for frame in range(motion.FRAMES):
    marks = motion.glide_chevrons(frame)
    assert 1 <= len(marks) <= 2
    assert all(x < cx < x + w and 0 < opacity <= 1 for cx, opacity in marks)
  # The lead chevron (offset 0) moves left every frame and fades in, then out.
  lead = [motion.glide_chevrons(f)[0] for f in range(1, motion.FRAMES)]
  xs, opacities = [cx for cx, _ in lead], [o for _, o in lead]
  assert xs == sorted(xs, reverse=True)
  peak = opacities.index(max(opacities))
  assert opacities[:peak + 1] == sorted(opacities[:peak + 1]) and opacities[peak:] == sorted(opacities[peak:], reverse=True)


@pytest.mark.parametrize("tool", ["make_sequential_signals", "make_motion_signals"])
def test_indicator_cards_use_the_on_road_widget_tokens(tool):
  module = _load_tool(tool)
  style = (ROOT / "selfdrive/ui/onroad/starpilot/widget_style.py").read_text()
  assert f"CONTROL_RADIUS = {module.RADIUS}" in style and f"CONTROL_BORDER_WIDTH = {module.BORDER_WIDTH}" in style
  assert "CONTROL_BG = rl.Color(0, 0, 0, 166)" in style and "CONTROL_BORDER = rl.Color(196, 205, 208, 180)" in style
  assert (module.W, module.H) == (350, 170)


def test_bouncing_ball_drops_in_touches_down_four_times_and_bounces_off_screen():
  ball = _load_tool("make_bouncing_ball_signals")
  assert ball.FRAMES * ball.FRAME_MS == 3000  # an unhurried 3 s pass
  touchdowns = ball.contacts()
  assert len(touchdowns) == ball.TOUCHDOWNS == 4
  heights = [ball.ball_height(f) for f in range(ball.FRAMES)]
  assert ball.REST_Y - heights[0] < ball.RADIUS  # first frame: entering at the very top of the screen
  assert [f for f, h in enumerate(heights) if h == 0] == [round(t) for t in touchdowns]  # rigid: visible touchdowns only
  apexes = [max(heights[round(a) + 1:round(b)]) for a, b in zip(touchdowns, touchdowns[1:], strict=False)]
  assert apexes == sorted(apexes, reverse=True) and apexes[0] < heights[0]
  # After the fourth touchdown it is airborne and still rising as it leaves the far edge.
  assert touchdowns[-1] < ball.FRAMES - 2
  assert 0 < heights[-2] < heights[-1]


def test_bouncing_ball_is_a_rigid_ping_pong_ball():
  ball = _load_tool("make_bouncing_ball_signals")
  for frame in range(ball.FRAMES):
    svg = ball.frame_svg(frame)
    assert f'r="{ball.RADIUS}"' in svg and svg.count("<circle") == 1  # always round: no squash or stretch
