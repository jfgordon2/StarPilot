"""Behaviour of the group-two conversions: segmented reselect, Driving Model sort, download manager taps.

Imports the real widgets, so (like test_simple_download_manager) it needs a display; run under xvfb-run.
"""
from types import SimpleNamespace

import pyray as rl

from openpilot.selfdrive.ui.layouts.settings.starpilot import simple_download_manager as downloads
from openpilot.selfdrive.ui.layouts.settings.starpilot.aethergrid import AetherSegmentedControl
from openpilot.selfdrive.ui.layouts.settings.starpilot.driving_model import DrivingModelManagerView


class FakeParams:
  def __init__(self, **values):
    self.values = dict(values)

  def get(self, key, encoding=None):
    return self.values.get(key, "")

  def put(self, key, value):
    self.values[key] = value

  def get_bool(self, key):
    return bool(self.values.get(key))

  def remove(self, key):
    self.values.pop(key, None)


def _tap(control, index):
  rect = control._option_rects[index]
  point = rl.Vector2(rect.x + rect.width / 2, rect.y + rect.height / 2)
  control._handle_mouse_press(point)
  control._handle_mouse_release(point)


def test_segmented_control_reports_a_tap_on_the_selected_option():
  changes, reselects = [], []
  control = AetherSegmentedControl(["A", "B"], 1, changes.append, on_reselect=reselects.append)
  control._option_rects = [rl.Rectangle(0, 0, 100, 100), rl.Rectangle(110, 0, 100, 100)]
  _tap(control, 1)
  assert changes == [] and reselects == [1]
  _tap(control, 0)
  assert changes == [0] and reselects == [1]


def _driving_model_view(sort_mode):
  params = FakeParams(ModelSortMode=sort_mode)
  controller = SimpleNamespace(
    _params=params,
    _get_sort_mode=lambda: params.get("ModelSortMode") or "alphabetical",
    secondary_header_button_state=lambda: ("Refresh Catalog", True),
    primary_header_button_state=lambda: ("Download All Missing (2)", True),
    refresh_manifest=lambda: None, cancel_active_download=lambda: None, download_all_missing=lambda: None,
    _is_download_active=lambda: False, _on_blacklist_clicked=lambda: None, _on_scores_clicked=lambda: None,
  )
  return DrivingModelManagerView(controller), params


def test_driving_model_date_segment_flips_direction_when_tapped_again():
  view, params = _driving_model_view("date")
  assert view._sort_index() == 1 and view._date_status() == "Newest first"
  view._on_sort_reselect(1)
  assert params.values["ModelSortMode"] == "date_oldest"
  assert view._sort_index() == 1 and view._date_status() == "Oldest first"
  view._on_sort_reselect(1)
  assert params.values["ModelSortMode"] == "date"
  view._on_sort_reselect(0)  # other segments have no direction
  assert params.values["ModelSortMode"] == "date"
  assert view.use_page_header() is view._refresh_button


def test_download_manager_rows_scrolled_under_the_header_cannot_be_tapped(tmp_path):
  (tmp_path / "frog_logo.png").write_bytes(b"")
  manager = downloads.SimpleDownloadManager("Boot Logo", "boot logo", tmp_path, "BootLogo", "BootLogoToDownload",
                                            "DownloadableBootLogos", FakeParams(), FakeParams(), lambda *_: None)
  manager._scroll_rect = rl.Rectangle(0, 300, 1000, 600)
  manager._item_rects = {"item:0": rl.Rectangle(0, 200, 1000, 160)}  # half scrolled above the list
  assert manager._hit_target(rl.Vector2(500, 250)) is None
  assert manager._hit_target(rl.Vector2(500, 320)) == "item:0"


def test_download_manager_mode_control_switches_lists(tmp_path):
  (tmp_path / "frog_logo.png").write_bytes(b"")
  params = FakeParams(DownloadableBootLogos="frog_logo,pixel_logo")
  manager = downloads.SimpleDownloadManager("Boot Logo", "boot logo", tmp_path, "BootLogo", "BootLogoToDownload",
                                            "DownloadableBootLogos", params, FakeParams(), lambda *_: None)
  assert manager._list_items == ["Frog Logo"]
  manager._mode_control._on_change(manager.MODE_DOWNLOAD)
  assert manager._active_mode == manager.MODE_DOWNLOAD and manager._list_items == ["Pixel Logo"]
