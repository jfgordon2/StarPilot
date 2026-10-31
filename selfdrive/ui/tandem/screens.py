"""The Essentials screens MainLayout creates. Each falls back to upstream's when its variable is "0":
TANDEM_SETTINGS, TANDEM_HOME, TANDEM_ONROAD.
"""
import os

from openpilot.system.ui.widgets import Widget


def _enabled(name: str) -> bool:
  return os.getenv(name, "1") != "0"


def settings_window() -> Widget:
  if not _enabled("TANDEM_SETTINGS"):
    from openpilot.selfdrive.ui.layouts.settings.settings import SettingsLayout
    return SettingsLayout()
  from openpilot.selfdrive.ui.tandem.settings.window import SettingsWindow
  return SettingsWindow()


def home_layout() -> Widget:
  if not _enabled("TANDEM_HOME"):
    from openpilot.selfdrive.ui.layouts.home import HomeLayout
    return HomeLayout()
  from openpilot.selfdrive.ui.tandem.home import essentials_home
  return essentials_home()


def onroad_view() -> Widget:
  if not _enabled("TANDEM_ONROAD"):
    from openpilot.selfdrive.ui.onroad.starpilot.starpilot_onroad_view import StarPilotOnroadView
    return StarPilotOnroadView()
  from openpilot.selfdrive.ui.tandem.onroad.view import EssentialsOnroadView
  return EssentialsOnroadView()
