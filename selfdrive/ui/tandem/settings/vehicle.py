"""Vehicle: the detected car, choosing it by hand, auto-lock, and what the steering wheel buttons do.

Car-specific extras (Toyota, Subaru, Bolt, Jeep, panda flashing ...) stay on StarPilot's vehicle screen,
one tap away under "More for your car".
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import pyray as rl

from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.system.ui.widgets import Widget
from openpilot.selfdrive.ui.tandem.base import Component
from openpilot.selfdrive.ui.tandem.blocks import SPACER, Card, Columns, Inline, Label, Sized, Stack
from openpilot.selfdrive.ui.tandem.controls import Button, ButtonStyle, Switch, ValueButton
from openpilot.selfdrive.ui.tandem.layout import FILL, column, row
from openpilot.selfdrive.ui.tandem.overlays import Sheet
from openpilot.selfdrive.ui.tandem.rows import ListPanel, OptionList, SettingRow
from openpilot.selfdrive.ui.tandem.settings.pages import FillPage
from openpilot.selfdrive.ui.tandem.settings.store import SettingsStore


# StarPilot's button action ids, named for what they do.
ACTION_NAMES = {0: "Car default", 1: "Change driving style", 2: "Coast", 3: "Pause steering", 4: "Pause gas and brake",
                5: "Switch experimental mode", 6: "Traffic mode", 7: "Switchback mode", 8: "Save a clip", 9: "Always-on steering",
                10: "Match the speed limit", 11: "Navigate to favorite 1", 12: "Navigate to favorite 2", 13: "Navigate to favorite 3"}


@dataclass(frozen=True)
class CarOption:
  value: str     # CarModel, the fingerprint
  label: str     # CarModelName, e.g. "RAV4 Hybrid 2019-21"


@dataclass(frozen=True)
class WheelButton:
  name: str
  press: str
  key: str
  cruise_main: bool = False


class CarCatalog(Protocol):
  def makes(self) -> list[str]: ...
  def models(self, make: str) -> list[CarOption]: ...
  def actions(self, button: WheelButton) -> list[tuple[int, str]]: ...
  def buttons(self) -> list[WheelButton]: ...
  def has_auto_lock(self) -> bool: ...


class Vehicle:
  def __init__(self, store: SettingsStore, catalog: CarCatalog):
    self._store = store
    self.catalog = catalog

  def car(self) -> str:
    return self._store.get_str("CarModelName") or "Detected on the first drive"

  def make(self) -> str:
    return self._store.get_str("CarMake")

  @property
  def manual(self) -> bool:
    return self._store.get_bool("ForceFingerprint")

  def choose(self, make: str, option: CarOption) -> None:
    """Saving a car turns off automatic detection, as on StarPilot's screen."""
    self._store.write({"ForceFingerprint": True, "CarMake": make, "CarModel": option.value, "CarModelName": option.label})

  def use_detection(self) -> None:
    self._store.write({"ForceFingerprint": False})

  @property
  def auto_lock(self) -> bool:
    return self._store.get_bool("LockDoors")

  def set_auto_lock(self, on: bool) -> None:
    self._store.write({"LockDoors": on})

  def action(self, button: WheelButton) -> int:
    return self._store.get_int(button.key)

  def action_name(self, button: WheelButton) -> str:
    current = self.action(button)
    return next((name for i, name in self.catalog.actions(button) if i == current), ACTION_NAMES[0])

  def set_action(self, button: WheelButton, action: int) -> None:
    self._store.write({button.key: action})

  def buttons_summary(self) -> str:
    return "Buttons customized" if any(self.action(b) for b in self.catalog.buttons()) else "Car default buttons"


class CarPicker(Component):
  """Makes on the left, that make's models on the right."""
  grow_touch_target = False

  def __init__(self, vehicle: Vehicle):
    super().__init__()
    self._vehicle = vehicle
    makes = vehicle.catalog.makes()
    self._makes = makes
    self._make = makes.index(vehicle.make()) if vehicle.make() in makes else 0
    self._model = self._current_model()
    self._make_list = self._child(OptionList(makes, lambda: self._make, self._pick_make))
    self._model_list: OptionList | None = None
    self._built_for = -1

  def _options(self) -> list[CarOption]:
    return self._vehicle.catalog.models(self._makes[self._make]) if self._makes else []

  def _current_model(self) -> int:
    name = self._vehicle._store.get_str("CarModelName")
    return next((i for i, o in enumerate(self._options()) if o.label == name), -1)

  def _pick_make(self, index: int) -> None:
    self._make = index
    self._model = -1

  def _pick_model(self, index: int) -> None:
    self._model = index

  def save(self) -> bool:
    options = self._options()
    if not 0 <= self._model < len(options):
      return False
    self._vehicle.choose(self._makes[self._make], options[self._model])
    return True

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    return max_width, T.px(330)

  def _render(self, rect: rl.Rectangle):
    if self._built_for != self._make:
      self._built_for = self._make
      self._model_list = OptionList([o.label for o in self._options()], lambda: self._model, self._pick_model)
    left, right = row(rect, [T.px(260), FILL], T.px(18))
    for title, area, widget in (("MAKE", left, self._make_list), ("MODEL", right, self._model_list)):
      caption, body = column(area, [T.px(28), FILL], T.px(6))
      draw.caption(caption, title)
      draw.fill(body, T.SURFACE_1, T.RADIUS_CARD)
      widget.render(body)


def vehicle_page(vehicle: Vehicle, window, open_more: Callable[[], None]) -> Widget:
  def choose_car():
    picker = CarPicker(vehicle)

    def save():
      if picker.save():
        window.dismiss()
    window.present(Sheet("Choose your car", picker,
                         subtitle="Only needed if detection picked the wrong car. Choosing turns off automatic detection.",
                         actions=[Button("Cancel", window.dismiss), Button("Save", save, ButtonStyle.PRIMARY)], on_dismiss=window.dismiss))

  def pick_action(button: WheelButton) -> Callable[[], None]:
    def show():
      actions = vehicle.catalog.actions(button)
      ids = [i for i, _ in actions]

      def select(index: int):
        vehicle.set_action(button, ids[index])
        window.dismiss()
      window.present(Sheet(f"{button.name} · {button.press}", OptionList([name for _, name in actions],
                                                                         lambda: ids.index(vehicle.action(button)) if vehicle.action(button) in ids else 0,
                                                                         select),
                           subtitle="What this button does while driving", on_dismiss=window.dismiss))
    return show

  car = Card([
    Label("YOUR CAR", color=T.ACCENT_TEXT, caption=True),
    Label(vehicle.car, T.font_px(26), weight=T.FONT_EXTRABOLD),
    Label(lambda: "Chosen manually" if vehicle.manual else "Detected automatically", T.font_px(15),
          lambda: T.TEXT_TERTIARY if vehicle.manual else T.SUCCESS_TEXT, T.FONT, icon=lambda: None if vehicle.manual else "check"),
    SPACER,
    Inline(Button(lambda: "Use detection instead" if vehicle.manual else "Wrong car? Choose it manually",
                  lambda: vehicle.use_detection() if vehicle.manual else choose_car(), ButtonStyle.GHOST, height=T.px(40),
                  font_size=T.font_px(16))),
  ], gap=T.px(10), padding=(T.px(22), T.px(22)))
  lock = Sized(ListPanel([SettingRow("Auto-Lock Doors", "Locks when you shift out of park", Switch(lambda: vehicle.auto_lock,
                                                                                                   vehicle.set_auto_lock), height=T.px(76))]),
               T.px(76))
  lock.set_visible(vehicle.catalog.has_auto_lock)
  buttons = [SettingRow(f"{b.name}", b.press, ValueButton(lambda b=b: vehicle.action_name(b), pick_action(b)), height=T.px(64))
             for b in vehicle.catalog.buttons()]
  wheel = ListPanel([
    *buttons,
    SettingRow("More for your car", "Features specific to your make and model", on_click=open_more, height=T.px(64)),
  ], title="Steering Wheel Buttons", subtitle="Preset for your car. Tap a button to change what it does.", title_size=T.font_px(20),
     header_divider=False)
  return FillPage(Columns([Stack([car, lock], gap=T.px(14), grow=0), wheel], [1, 1.35]))


class UpstreamCars:
  """CarCatalog backed by StarPilot's fingerprint list, button actions and detected car state."""

  def __init__(self):
    from openpilot.selfdrive.ui.layouts.settings.starpilot import vehicle as v
    from openpilot.selfdrive.ui.lib.fingerprint_catalog import get_fingerprint_catalog
    from openpilot.selfdrive.ui.lib.starpilot_state import starpilot_state
    self._v = v
    self._state = starpilot_state
    self._makes, self._by_make, _, _ = get_fingerprint_catalog()

  def makes(self) -> list[str]:
    return list(self._makes)

  def models(self, make: str) -> list[CarOption]:
    return [CarOption(o.value, o.label) for o in self._by_make.get(make, ())]

  def actions(self, button: WheelButton) -> list[tuple[int, str]]:
    """The same choices StarPilot offers, without the developer-only Pulse and Glide."""
    longitudinal = self._state.car_state.hasOpenpilotLongitudinal
    if button.cruise_main:
      allowed = {0, 9, 10, 11, 12, 13}
    else:
      allowed = set(range(9)) | {11, 12, 13} | ({9} if button.key == "LKASButtonControl" else set())
    return [(o["id"], ACTION_NAMES.get(o["id"], o["name"])) for o in self._v.ACTION_OPTIONS
            if o["id"] in allowed and (longitudinal or not o.get("requires_longitudinal", False))]

  def buttons(self) -> list[WheelButton]:
    cs = self._state.car_state
    buttons = [WheelButton("Distance", "Press", "DistanceButtonControl"),
               WheelButton("Distance", "Long press", "LongDistanceButtonControl")]
    if not cs.isSubaru:
      buttons.append(WheelButton("LKAS", "Press", "LKASButtonControl"))
    buttons.append(WheelButton("Cruise main", "Press", "MainCruiseButtonControl", cruise_main=True))
    if cs.hasModeStarButtons:
      buttons += [WheelButton("Mode", "Press", "ModeButtonControl"), WheelButton("Star", "Press", "StarButtonControl")]
    return buttons

  def has_auto_lock(self) -> bool:
    return bool(self._state.car_state.isToyota)
