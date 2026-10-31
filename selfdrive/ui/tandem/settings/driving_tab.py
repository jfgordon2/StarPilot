"""The Driving tab: a hub of five tiles and the power-user switches."""
from __future__ import annotations

from collections.abc import Callable

import pyray as rl

from openpilot.system.ui.widgets import Widget
from openpilot.selfdrive.ui.tandem.chrome import HubTile
from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.controls import Button, ButtonStyle, ToggleButton
from openpilot.selfdrive.ui.tandem.settings import upstream
from openpilot.selfdrive.ui.tandem.settings.bundles import BUNDLES, TUNER_MODE
from openpilot.selfdrive.ui.tandem.settings.alerts import Alerts, alerts_panel, sound_player
from openpilot.selfdrive.ui.tandem.settings.tuner import Tuner, tuner_page
from openpilot.selfdrive.ui.tandem.settings.maps import Maps, MapsPage, RegionsPage
from openpilot.selfdrive.ui.tandem.settings.model import CatalogPage, Models, model_page
from openpilot.selfdrive.ui.tandem.settings.vehicle import Vehicle, vehicle_panel
from openpilot.selfdrive.ui.tandem.settings.display import Display, driving_screen_panel, edit_startup_message, map_panel, theme_panel
from openpilot.selfdrive.ui.tandem.settings.pages import HubPage, PanelPage, Section, SectionPage, Strip
from openpilot.selfdrive.ui.tandem.settings.speed_steering import (Assistance, Navigation, SpeedSteering, VehicleProfile, Weather,
                                                                   assistance_panel, everyday_panel, navigation_panel,
                                                                   vehicle_profile_panel, weather_panel)


class Lazy:
  def __init__(self, make: Callable):
    self._make = make
    self._value = None

  def get(self):
    if self._value is None:
      self._value = self._make()
    return self._value


def chevron_glyph(rect: rl.Rectangle, color: rl.Color, size: float) -> None:
  draw.chevron(rect, color, size)


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
  # Model and car data come from StarPilot's own screens, built the first time they're needed.
  models = Lazy(lambda: Models(store, window.model_source()))
  vehicle = Lazy(lambda: Vehicle(store, window.car_catalog()))
  maps = Lazy(lambda: Maps(store, window.maps_source()))

  def open_maps() -> None:
    def open_regions() -> None:
      def download() -> None:
        maps.get().source.download()
        window.pop()
      window.push(RegionsPage(maps.get(), download))
    window.push(MapsPage(maps.get(), open_regions))

  def tuner() -> bool:
    return TUNER_MODE.is_on(store)

  def set_bundle(bundle, on: bool) -> None:
    bundle.set(store, on)
    if bundle is TUNER_MODE and on:
      open_tuner()

  def starpilot(panel: str) -> Callable[[], Widget]:
    return lambda: upstream.StarPilotPage(panel, on_exit=window.pop)

  def opener(make: Callable[[], Widget]) -> Callable[[], None]:
    return lambda: window.push(make())

  def open_tuner() -> None:
    window.push(tuner_page(Tuner(store), window))

  def speed_steering() -> Widget:
    tuner_button = Button("Tuner Mode", open_tuner, ButtonStyle.SECONDARY, width=T.SIDEBAR_WIDTH, accessory=chevron_glyph)
    tuner_button.set_visible(tuner)
    return SectionPage("SPEED & STEERING", [
      Section("Everyday", lambda: everyday_panel(speed)),
      Section("Vehicle Profile", lambda: vehicle_profile_panel(profile), value=profile.summary),
      Section("Weather", lambda: weather_panel(weather), value=weather.summary),
      Section("Navigation", lambda: navigation_panel(navigation, opener(starpilot("NAVIGATION")), open_maps)),
      Section("Assistance", lambda: assistance_panel(assistance)),
    ], footer=[tuner_button])

  def display() -> Widget:
    return SectionPage("DISPLAY", [
      Section("Driving Screen", lambda: driving_screen_panel(screen, window)),
      Section("Theme & Startup", lambda: theme_panel(screen, lambda: edit_startup_message(screen))),
      Section("Map", lambda: map_panel(screen, open_maps)),
    ])

  def car() -> str:
    return store.get_str("CarModelName") or "Detected on the first drive"

  strip = Strip("POWER USER", "Extra detail and fine tuning, each behind one switch", [
    ToggleButton(b.name, lambda b=b: b.is_on(store), lambda on, b=b: set_bundle(b, on)) for b in BUNDLES])

  return HubPage("Driving", "Good defaults are on. Change only what matters to you.", [
    HubTile("Speed & Steering", [speed.summary, speed.speed_limit_summary], opener(speed_steering), icon="wheel"),
    HubTile("Display", [screen.summary, screen.path_summary], opener(display), icon="display"),
    HubTile("Alerts", [alerts.summary, alerts.chimes_summary], opener(lambda: PanelPage(alerts_panel(alerts, window))),
            icon="volume"),
    HubTile("Driving Model", [lambda: models.get().summary(), lambda: models.get().update_summary()],
            opener(lambda: PanelPage(model_page(models.get(), opener(lambda: CatalogPage(models.get()))))), icon="model"),
    HubTile("Vehicle", [car, lambda: f"{profile.summary()} profile · {vehicle.get().buttons_summary()}"],
            opener(lambda: PanelPage(vehicle_panel(vehicle.get(), window, opener(starpilot("VEHICLE"))))), icon="car"),
  ], rows=[3, 2], strip=strip)
