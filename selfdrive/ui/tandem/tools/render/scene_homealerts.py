import pyray as rl
from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.home_alerts import AlertsView, HomeAlert, UpdateView
from openpilot.selfdrive.ui.tandem.settings.software_tab import notes_text
from openpilot.selfdrive.ui.tandem.sidebar import WIDTH, Health, SidebarState, SidebarView, Status, connect_status, network_status


def main(frame, save, out, tap, gui_app):
  state = SidebarState([network_status("Wi-Fi", 4), connect_status(Health.GOOD), Status("Temperature", "Good", Health.GOOD),
                        Status("Vehicle", "Connected", Health.GOOD), Status("Maps", "Up to date", Health.GOOD)])
  side = SidebarView(lambda: state, lambda: None, lambda: None, lambda: None)
  alerts = [HomeAlert("Offroad_ConnectivityNeeded", "Connect to internet to check for updates. openpilot won't automatically start until it "
                      + "connects to internet to check for updates.", True),
            HomeAlert("Offroad_Recalibration", "openpilot detected a change in the device's mounting position. Ensure the device is fully "
                      + "seated in the mount and the mount is firmly secured to the windshield.", False)]
  notes = "<h2>Version 0.10.2</h2><ul><li>Smoother lane changes on curvy roads</li><li>Speed limits from offline maps in more states</li>" \
          + "<li>Fixes for Toyota and Hyundai</li></ul>"
  views = {"homealerts": AlertsView(lambda: alerts, lambda: None, lambda: ("Snooze update", lambda: None)),
           "homeupdate": UpdateView(lambda: "0.10.2", lambda: notes_text(notes), lambda: None, lambda: None)}
  for name, view in views.items():
    def render(view=view):
      draw.fill(rl.Rectangle(0, 0, 2160, 1080), T.BG)
      side.render(rl.Rectangle(0, 0, WIDTH, 1080))
      view.render(rl.Rectangle(WIDTH + T.px(16), T.px(18), 2160 - WIDTH - T.px(34), 1080 - T.px(36)))
    for _ in range(3):
      frame(render)
    save(f"{out}/{name}.png")
