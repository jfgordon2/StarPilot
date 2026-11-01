from openpilot.selfdrive.ui.tandem.setup import Setup, SetupWindow
from openpilot.selfdrive.ui.tandem.settings.store import SettingsStore
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "tests"))
from test_settings import FakeCache
import pyray as rl


def main(frame, save, out, tap, gui_app):
  setup = Setup(SettingsStore(FakeCache(), lambda: None), lambda: None)
  win = SetupWindow(setup)
  for step in range(3):
    setup.step = step
    for _ in range(3):
      frame(lambda: win.render(rl.Rectangle(0, 0, 2160, 1080)))
    save(f"{out}/setup{step}.png")
