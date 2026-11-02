import pyray as rl
from openpilot.selfdrive.ui.tandem import draw as D, tokens as T
from openpilot.selfdrive.ui.tandem.settings.display import bundle_sheet


class Win:
  top = None

  def present(self, o):
    self.top = o
    o.show_event()

  def dismiss(self):
    pass


def main(frame, save, out, tap, gui_app):
  win, rect = Win(), rl.Rectangle(0, 0, 2160, 1080)
  win.present(bundle_sheet(win, 0))
  for _ in range(30):
    frame(lambda: (D.fill(rect, T.BG), D.fill(rl.Rectangle(38, 34, 2084, 220), T.SURFACE_2, T.RADIUS_PANEL), win.top.render(rect)))
  save(f"{out}/bundlesheet.png")
