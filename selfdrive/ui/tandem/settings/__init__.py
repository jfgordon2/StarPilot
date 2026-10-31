"""The Essentials settings window, which takes the place of StarPilot's SettingsLayout.

TANDEM_SETTINGS=0 brings back the upstream window, e.g. to compare the two.
"""
import os

from openpilot.system.ui.widgets import Widget


def settings_window() -> Widget:
  if os.getenv("TANDEM_SETTINGS", "1") == "0":
    from openpilot.selfdrive.ui.layouts.settings.settings import SettingsLayout
    return SettingsLayout()
  from openpilot.selfdrive.ui.tandem.settings.window import SettingsWindow
  return SettingsWindow()
