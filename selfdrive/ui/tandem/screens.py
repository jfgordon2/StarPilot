"""The Essentials screens MainLayout creates. Each falls back to upstream's when its variable is "0":
TANDEM_SETTINGS, TANDEM_HOME, TANDEM_ONROAD, TANDEM_SIDEBAR.
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


def sidebar() -> Widget:
  if not _enabled("TANDEM_SIDEBAR"):
    from openpilot.selfdrive.ui.layouts.sidebar import Sidebar
    return Sidebar()
  from openpilot.selfdrive.ui.tandem.sidebar import essentials_sidebar
  return essentials_sidebar()


def _sidebar_width() -> int:
  if not _enabled("TANDEM_SIDEBAR"):
    from openpilot.selfdrive.ui.layouts.sidebar import SIDEBAR_WIDTH as upstream_width
    return upstream_width
  from openpilot.selfdrive.ui.tandem.sidebar import WIDTH
  return int(WIDTH)


MAIN_SIDEBAR_WIDTH = _sidebar_width()   # the left sidebar; StarPilot's developer sidebar on the right keeps its own width
