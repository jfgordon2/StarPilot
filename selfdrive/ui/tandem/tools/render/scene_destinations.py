import pyray as rl
from openpilot.selfdrive.ui.tandem import destinations as D
from openpilot.selfdrive.ui.tandem.tests.fakes import FakePlaces


def main(frame, save, out, tap, gui_app):
  places = FakePlaces()
  screen = D.DestinationsScreen(places, lambda: None, open_maps=lambda: None)
  rect = rl.Rectangle(0, 0, 2160, 1080)
  draw = lambda: screen.render(rect)  # noqa: E731

  def shot(name, n=4):
    for _ in range(n):
      frame(draw)
    save(f"{out}/{name}.png")

  shot("destinations")
  screen._go(D.SEARCH)
  screen._keys.set_text("hardware sto")
  places.search("hardware sto")
  screen._searched = "hardware sto"
  screen._typed = "hardware sto"
  shot("navsearch")
  screen._view = D.RESULTS
  shot("navresults")
  screen._pick_result(0)
  screen._update_state()
  shot("routepreview")
