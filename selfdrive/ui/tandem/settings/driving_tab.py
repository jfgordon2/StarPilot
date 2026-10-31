"""The Driving tab: a hub of five tiles and the power-user switches."""
from __future__ import annotations

from collections.abc import Callable

import pyray as rl

from openpilot.system.ui.widgets import Widget
from openpilot.selfdrive.ui.tandem.chrome import HubTile
from openpilot.selfdrive.ui.tandem.controls import Glyph, ToggleButton
from openpilot.selfdrive.ui.tandem.settings import upstream
from openpilot.selfdrive.ui.tandem.settings.bundles import BUNDLES, TUNER_MODE
from openpilot.selfdrive.ui.tandem.settings.alerts import Alerts, alerts_panel, sound_player
from openpilot.selfdrive.ui.tandem.settings.display import Display, driving_screen_panel, edit_startup_message, map_panel, theme_panel
from openpilot.selfdrive.ui.tandem.settings.pages import HubPage, PanelPage, Section, SectionPage, Strip
from openpilot.selfdrive.ui.tandem.settings.speed_steering import (Assistance, Navigation, SpeedSteering, VehicleProfile, Weather,
                                                                   assistance_panel, everyday_panel, navigation_panel,
                                                                   vehicle_profile_panel, weather_panel)


def scribble(key: str) -> Glyph:
  """StarPilot's vector icons (drawn on a 60 px canvas), as a glyph."""
  def glyph(rect: rl.Rectangle, color: rl.Color, size: float) -> None:
    from openpilot.selfdrive.ui.layouts.settings.starpilot.scribble import draw_custom_icon
    draw_custom_icon(key, rect.x + (rect.width - size) / 2, rect.y + (rect.height - size) / 2, size / 60, color)
  return glyph


def driving_hub(window) -> Widget:
  """window provides store, live, push and pop."""
  store, live = window.store, window.live
  speed = SpeedSteering(store)
  profile = VehicleProfile(store)
  weather = Weather(store)
  navigation = Navigation(store)
  assistance = Assistance(store, live)
  screen = Display(store)
  alerts = Alerts(store, sound_player())

  def tuner() -> bool:
    return TUNER_MODE.is_on(store)

  def starpilot(panel: str) -> Callable[[], Widget]:
    return lambda: upstream.StarPilotPage(panel, on_exit=window.pop)

  def opener(make: Callable[[], Widget]) -> Callable[[], None]:
    return lambda: window.push(make())

  def speed_steering() -> Widget:
    return SectionPage("SPEED & STEERING", [
      Section("Everyday", lambda: everyday_panel(speed)),
      Section("Vehicle Profile", lambda: vehicle_profile_panel(profile), value=profile.summary),
      Section("Weather", lambda: weather_panel(weather), value=weather.summary),
      Section("Navigation", lambda: navigation_panel(navigation, opener(starpilot("NAVIGATION")), opener(starpilot("MAPS")))),
      Section("Assistance", lambda: assistance_panel(assistance)),
      Section("Gas & Brake", lambda: upstream.StarPilotPage("LONGITUDINAL"), visible=tuner),
      Section("Steering", lambda: upstream.StarPilotPage("LATERAL"), visible=tuner),
    ])

  def display() -> Widget:
    return SectionPage("DISPLAY", [
      Section("Driving Screen", lambda: driving_screen_panel(screen, window)),
      Section("Theme & Startup", lambda: theme_panel(screen, lambda: edit_startup_message(screen))),
      Section("Map", lambda: map_panel(screen, opener(starpilot("MAPS")))),
    ])

  def car() -> str:
    return store.get_str("CarModelName") or "Detected on the first drive"

  strip = Strip("POWER USER", "Extra detail and fine tuning, each behind one switch", [
    ToggleButton(b.name, lambda b=b: b.is_on(store), lambda on, b=b: b.set(store, on)) for b in BUNDLES])

  return HubPage("Driving", "Good defaults are on. Change only what matters to you.", [
    HubTile("Speed & Steering", [speed.summary, speed.speed_limit_summary], opener(speed_steering), scribble("steering")),
    HubTile("Display", [screen.summary, screen.path_summary], opener(display), scribble("display")),
    HubTile("Alerts", [alerts.summary, alerts.chimes_summary], opener(lambda: PanelPage(alerts_panel(alerts, window))),
            scribble("sound")),
    HubTile("Driving Model", ["Choose and download models"], opener(starpilot("DRIVING_MODEL")), scribble("aicar")),
    HubTile("Vehicle", [car, lambda: f"{profile.summary()} profile"], opener(starpilot("VEHICLE")), scribble("vehicle")),
  ], rows=[3, 2], strip=strip)
