#!/usr/bin/env python3
"""Render real comma 3/3X settings pages with isolated preview inputs.

Run from the repo root with its UI dependencies installed:
  python starpilot/tools/render_settings_preview.py --out /tmp/settings-preview
  python starpilot/tools/render_settings_preview.py --page hud --out /tmp/settings-preview

Uses the on-road preview's messaging/compiled-module fallbacks. All page,
card, text and control drawing comes from the production settings widgets.
On Linux without a display, run under xvfb-run -a.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from render_onroad_preview import HEIGHT, WIDTH, export_preview_frame, init_preview_window, install_stubs


PAGES = ("hub", "appearance", "hud", "signal-picker", "camera-picker", "metric-picker", "button-picker", "maintenance-picker",
         "sounds", "sounds-states", "sounds-volume", "system", "controls", "vehicle",
         "gas-brake", "conditional", "maps", "sounds-reset", "alert-dialog", "rich-dialog")
DIALOG_PAGES = {"sounds-reset", "alert-dialog", "rich-dialog", "sounds-volume", "signal-picker", "camera-picker",
                "metric-picker", "button-picker", "maintenance-picker"}


def render(pages: list[str], destination: Path, include_scrolled: bool = False) -> list[Path]:
  os.environ["BIG"] = "1"
  os.environ.setdefault("OPENPILOT_PREFIX", f"_settings_preview_{os.getpid()}")
  install_stubs()

  import pyray as rl
  from openpilot.common.params import Params
  from openpilot.system.ui.lib.application import gui_app
  from openpilot.selfdrive.ui.layouts.settings.settings import PanelType, SettingsLayout
  from openpilot.selfdrive.ui.lib.ui_param_cache import shared_ui_params

  params = Params()
  for key in ("CustomUI", "CustomThemes", "HolidayThemes", "SpeedAtBottom", "EnableTorqueBarWidget", "StoppedTimer",
              "OnroadDistanceButton", "ConditionalExperimental"):
    params.put_bool(key, True)
  params.put("SignalAnimation", "sequential")
  shared_ui_params().invalidate()

  init_preview_window("StarPilot settings preview")
  target = rl.load_render_texture(WIDTH, HEIGHT)
  destination.mkdir(parents=True, exist_ok=True)
  written = []
  try:
    layout = SettingsLayout()
    starpilot = layout._panels[PanelType.STARPILOT].instance
    for page in pages:
      sample_values = {"WarningSoftVolume": 50, "RefuseVolume": 0, "EngageVolume": 50, "PromptVolume": 0} \
        if page in ("sounds-states", "sounds-volume") else {}
      original_values = {key: params.get_int(key, return_default=True, default=101) for key in sample_values}
      for key, value in sample_values.items():
        params.put_int(key, value)
      starpilot.reset_to_root()
      if page == "controls":
        starpilot._open_folder(next(c for c in starpilot.CATEGORIES if "children" in c))
      elif page in ("gas-brake", "conditional", "maps"):
        folder = next(c for c in starpilot.CATEGORIES if "children" in c)
        starpilot._open_folder(folder)
        if page == "maps":
          navigation = next(c for c in folder["children"] if c["title"] == "Navigation & Maps")
          starpilot._open_folder(navigation)
          starpilot._open_leaf(next(c for c in navigation["children"] if c.get("panel") == "MAPS"))
        else:
          starpilot._open_leaf(next(c for c in folder["children"] if c.get("panel") == "LONGITUDINAL"))
          if page == "conditional":
            starpilot._push_sub_panel("ce")
      elif page != "hub":
        title = {"appearance": "Appearance", "hud": "Appearance", "signal-picker": "Appearance", "sounds": "Sounds & Alerts",
                 "system": "System", "vehicle": "Vehicle Settings", "sounds-reset": "Sounds & Alerts",
                 "alert-dialog": "System", "rich-dialog": "System",
                 "camera-picker": "Appearance", "metric-picker": "Appearance", "button-picker": "Vehicle Settings", "maintenance-picker": "System",
                 "sounds-states": "Sounds & Alerts", "sounds-volume": "Sounds & Alerts"}[page]
        starpilot._open_leaf(next(c for c in starpilot.CATEGORIES if c["title"] == title))
        if page in ("hud", "signal-picker", "camera-picker", "metric-picker"):
          starpilot._push_sub_panel("hud")
      screen = layout
      if page not in ("hub", "controls"):
        panel = starpilot._panels[starpilot._current_panel].instance
        view = panel._sub_panels.get(panel._current_sub_panel, panel._manager_view)
        view.reset_scroll()
      if page in DIALOG_PAGES:
        panel = starpilot._panels[starpilot._current_panel].instance
        if page == "sounds-reset":
          panel._manager_view._reset_button._activate()
        elif page == "alert-dialog":
          from openpilot.system.ui.widgets.confirm_dialog import alert_dialog
          gui_app.push_widget(alert_dialog("Park to remove downloaded maps."))
        elif page == "rich-dialog":
          from openpilot.system.ui.widgets.confirm_dialog import ConfirmDialog
          text = ("<h1>Enable Experimental Mode?</h1><p>openpilot defaults to driving in chill mode. Experimental mode "
                  + "enables alpha-level features that aren't ready for chill mode.</p><p>Always keep your hands on the "
                  + "wheel and eyes on the road.</p>")
          gui_app.push_widget(ConfirmDialog(text, "Enable", rich=True))
        elif page == "sounds-volume":
          panel._manager_view._show_volume_slider("EngageVolume")
        elif page == "signal-picker":
          panel._show_theme_selector("SignalAnimation")
        elif page == "camera-picker":
          panel._show_camera_view_selector()
        elif page == "metric-picker":
          panel._show_developer_sidebar_metric_selector(1)
        elif page == "button-picker":
          panel._show_button_combo_dialog("combo:distance")
        elif page == "maintenance-picker":
          from openpilot.selfdrive.ui.layouts.settings.starpilot.system_settings import AetherBackupsCareDialog
          gui_app.push_widget(AetherBackupsCareDialog(panel))
        screen = gui_app._nav_stack[-1]
      for _ in range(3):
        rl.begin_texture_mode(target)
        rl.clear_background(rl.BLACK)
        screen.render(rl.Rectangle(0, 0, WIDTH, HEIGHT))
        rl.end_texture_mode()
      path = destination / f"{page}.png"
      export_preview_frame(target, path)
      written.append(path)
      if include_scrolled and page in DIALOG_PAGES and hasattr(screen, "_scroll_panel") and screen._content_height > screen._scroll_rect.height:
        screen._scroll_panel.set_offset(screen._scroll_rect.height - screen._content_height)
        rl.begin_texture_mode(target)
        screen.render(rl.Rectangle(0, 0, WIDTH, HEIGHT))
        rl.end_texture_mode()
        path = destination / f"{page}-bottom.png"
        export_preview_frame(target, path)
        written.append(path)
      elif include_scrolled and page not in {"hub", "controls", *DIALOG_PAGES}:
        panel = starpilot._panels[starpilot._current_panel].instance
        view = panel._sub_panels.get(panel._current_sub_panel, panel._manager_view)
        captures = []
        if view._active_scroll_columns:
          overflowing = [key for key in view._active_scroll_columns
                         if view._column_scrolls[key].height > view._column_scrolls[key].rect.height]
          captures = [(f"{key}-bottom", [key]) for key in overflowing]
          if overflowing:
            captures.append(("bottom", overflowing))
        elif view._content_height > view._scroll_rect.height:
          captures = [("bottom", [])]
        for suffix, column_keys in captures:
          view.reset_scroll()
          if column_keys:
            for key in column_keys:
              column = view._column_scrolls[key]
              column.panel.set_offset(min(0.0, column.rect.height - column.height))
          else:
            view._scroll_panel.set_offset(min(0.0, view._scroll_rect.height - view._content_height))
          for _ in range(3):
            rl.begin_texture_mode(target)
            rl.clear_background(rl.BLACK)
            layout.render(rl.Rectangle(0, 0, WIDTH, HEIGHT))
            rl.end_texture_mode()
          path = destination / f"{page}-{suffix}.png"
          export_preview_frame(target, path)
          written.append(path)
      if page in DIALOG_PAGES:
        gui_app._nav_stack.pop().hide_event()
      for key, value in original_values.items():
        params.put_int(key, value)
  finally:
    rl.unload_render_texture(target)
    gui_app.close()
  return written


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--page", choices=PAGES, action="append", help="page to render; repeat for multiple (default: all)")
  parser.add_argument("--out", type=Path, default=Path("settings_preview"))
  parser.add_argument("--include-scrolled", action="store_true", help="also capture the bottom of each overflowing page")
  args = parser.parse_args()
  written = render(args.page or list(PAGES), args.out, args.include_scrolled)
  print(f"Wrote {len(written)} settings preview(s) to {args.out}")


if __name__ == "__main__":
  main()
