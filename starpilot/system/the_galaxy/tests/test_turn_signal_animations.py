import json
import re
from pathlib import Path

from test_navigation_params import _params_client, the_galaxy

REPO_ROOT = Path(__file__).resolve().parents[4]
BUNDLED = [
  "sequential", "flow", "open_flow", "glide",
  "frog", "pouncing_cat", "shooting_star", "bouncing_ball",
]


def _client(monkeypatch, tmp_path, values):
  client, fake_params = _params_client(monkeypatch, values, "tici")
  monkeypatch.setattr(the_galaxy, "THEME_SAVE_PATH", tmp_path)
  monkeypatch.setattr(the_galaxy, "_get_param_type_info", lambda: (
    {"SignalAnimation", "CustomThemes", "RandomThemes"},
    {"SignalAnimation": str, "CustomThemes": bool, "RandomThemes": bool},
  ))
  refreshes = []
  monkeypatch.setattr(the_galaxy, "update_starpilot_toggles", lambda: refreshes.append(True))
  return client, fake_params, refreshes


def _install_pack(root, name, *frames):
  signals = root / "theme_packs" / name / "signals"
  signals.mkdir(parents=True)
  for frame in frames:
    (signals / frame).write_bytes(b"")


def test_dropdown_lists_none_bundled_animations_then_downloaded_png_packs(monkeypatch, tmp_path):
  _install_pack(tmp_path, "zebra_stripes", "turn_signal_1.png", "turn_signal_2.png", "traditional_125")
  _install_pack(tmp_path, "aurora", "turn_signal.png", "static_0")
  _install_pack(tmp_path, "gif_only", "turn_signal.gif")              # the raylib renderer can't draw GIFs
  _install_pack(tmp_path, "blindspot_only", "turn_signal_blindspot.png")
  _install_pack(tmp_path, "frog", "turn_signal_1.png")                 # boot-time copy of a bundled pack
  client, _, _ = _client(monkeypatch, tmp_path, {"SignalAnimation": "stock"})

  options = client.get("/api/turn_signal_animations").get_json()

  assert [option["value"] for option in options] == ["stock", *BUNDLED, "aurora", "zebra_stripes"]
  assert options[0] == {"value": "stock", "label": "None"}
  assert {"value": "open_flow", "label": "Open Flow"} in options
  assert {"value": "zebra_stripes", "label": "Zebra Stripes"} in options


def test_saved_pack_that_is_no_longer_installed_is_shown_but_not_selectable(monkeypatch, tmp_path):
  client, fake_params, _ = _client(monkeypatch, tmp_path, {"SignalAnimation": "old_pack", "CustomThemes": True})

  options = client.get("/api/turn_signal_animations").get_json()
  assert options[-1] == {"value": "old_pack", "label": "Old Pack (not installed)", "missing": True}

  response = client.put("/api/params", json={"key": "SignalAnimation", "value": "old_pack"})
  assert response.status_code == 400
  assert fake_params.writes == []


def test_choosing_an_animation_enables_custom_themes_and_disables_random_themes(monkeypatch, tmp_path):
  client, fake_params, refreshes = _client(monkeypatch, tmp_path, {
    "SignalAnimation": "stock", "CustomThemes": False, "RandomThemes": True, "IconPack": "saved_icons",
  })

  response = client.put("/api/params", json={"key": "SignalAnimation", "value": "sequential", "label": "Sequential"})

  assert response.status_code == 200
  body = response.get_json()
  assert body["updated"] == {"SignalAnimation": "sequential", "CustomThemes": True, "RandomThemes": False}
  assert body["message"] == "Turn signal animation set to Sequential."
  assert fake_params.values["SignalAnimation"] == "sequential"
  assert fake_params.values["CustomThemes"] is True and fake_params.values["RandomThemes"] is False
  assert fake_params.values["IconPack"] == "saved_icons"   # other saved theme choices are left alone
  assert refreshes == [True]


def test_choosing_none_only_clears_the_animation(monkeypatch, tmp_path):
  client, fake_params, refreshes = _client(monkeypatch, tmp_path, {
    "SignalAnimation": "frog", "CustomThemes": True, "RandomThemes": False,
  })

  response = client.put("/api/params", json={"key": "SignalAnimation", "value": "stock"})

  assert response.status_code == 200
  assert response.get_json()["updated"] == {"SignalAnimation": "stock"}
  assert fake_params.writes == [("SignalAnimation", "stock")]
  assert refreshes == [True]


def test_downloaded_pack_can_be_chosen_and_unknown_values_are_rejected(monkeypatch, tmp_path):
  _install_pack(tmp_path, "aurora", "turn_signal.png")
  client, fake_params, _ = _client(monkeypatch, tmp_path, {"SignalAnimation": "stock"})

  assert client.put("/api/params", json={"key": "SignalAnimation", "value": "aurora"}).status_code == 200
  assert fake_params.values["SignalAnimation"] == "aurora"

  fake_params.writes.clear()
  response = client.put("/api/params", json={"key": "SignalAnimation", "value": "../../etc"})
  assert response.status_code == 400
  assert fake_params.writes == []


def test_settings_show_the_animation_actually_in_effect(monkeypatch, tmp_path):
  cases = [
    ({"SignalAnimation": "frog", "CustomThemes": False}, "stock"),   # saved but inactive, like the device menus
    ({"SignalAnimation": "frog", "CustomThemes": True}, "frog"),
    ({"SignalAnimation": "none", "CustomThemes": True}, "stock"),
  ]
  for values, expected in cases:
    client, _, _ = _client(monkeypatch, tmp_path, values)
    assert client.get("/api/params/all").get_json()["SignalAnimation"] == expected


def test_layout_offers_the_dropdown_next_to_holiday_themes():
  layout = json.loads((REPO_ROOT / "starpilot/common/assets/device_settings_layout.json").read_text())
  visual = next(section for section in layout if section["name"] == "Visual (Display & UI)")
  keys = [param["key"] for param in visual["params"]]
  entry = visual["params"][keys.index("SignalAnimation")]
  assert keys.index("SignalAnimation") == keys.index("HolidayThemes") + 1
  assert entry["ui_type"] == "dropdown" and entry["data_type"] == "string"
  assert entry["options_endpoint"] == "/api/turn_signal_animations"
  assert "parent_key" not in entry  # visible without enabling another feature first


def test_bundled_list_matches_the_device_renderer_and_comma_4_menu():
  renderer = (REPO_ROOT / "selfdrive/ui/onroad/starpilot/turn_signals.py").read_text()
  bundled_block = renderer.split("BUNDLED_SIGNAL_PATHS = {", 1)[1].split("}", 1)[0]
  renderer_slugs = re.findall(r'"([a-z_]+)":', bundled_block)
  galaxy_slugs = [slug for slug, _ in the_galaxy.BUNDLED_SIGNAL_ANIMATIONS]
  assert sorted(galaxy_slugs) == sorted(renderer_slugs)

  visuals = (REPO_ROOT / "selfdrive/ui/mici/layouts/settings/visuals.py").read_text()
  menu = visuals.split("options = {", 1)[1].split("}", 1)[0]
  comma4_order = [slug for slug in re.findall(r':\s*"([a-z_]+)"', menu) if slug != "stock"]
  assert galaxy_slugs == comma4_order
  comma4_labels = {slug: label for label, slug in re.findall(r'"([^"]+)":\s*"([a-z_]+)"', menu) if slug != "stock"}
  assert dict(the_galaxy.BUNDLED_SIGNAL_ANIMATIONS) == comma4_labels
