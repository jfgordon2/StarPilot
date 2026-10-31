"""Display: the driving screen, theme and startup, and the map."""
from __future__ import annotations

from collections.abc import Callable

from openpilot.selfdrive.ui.tandem import tokens as T
from openpilot.selfdrive.ui.tandem.controls import Button, ButtonStyle, ChoiceCards, Segmented, Switch, ValueButton
from openpilot.selfdrive.ui.tandem.overlays import Sheet
from openpilot.selfdrive.ui.tandem.rows import ListPanel, OptionList, SectionHeader, SettingRow, Text
from openpilot.selfdrive.ui.tandem.settings.bundles import DEVELOPER_VIEW, LEAD_INSIGHTS, Bundle
from openpilot.selfdrive.ui.tandem.settings.store import SettingsStore

# Turn signal animations built into StarPilot (slug, name). Theme packs can add more; those still show by name.
SIGNALS = [("stock", "None"), ("sequential", "Sequential"), ("flow", "Flow"), ("open_flow", "Open Flow"), ("glide", "Glide"),
           ("frog", "Frog"), ("pouncing_cat", "Pouncing Cat"), ("shooting_star", "Shooting Star"), ("bouncing_ball", "Bouncing Ball")]

# Path Style -> the path and lane line params it sets. Standard is upstream's path without the acceleration tint.
_STANDARD_PATH = {"ModelUI": True, "CustomUI": True, "PathWidth": 6.1, "PathEdgeWidth": 20.0, "LaneLinesWidth": 4.0,
                  "RainbowPath": False, "AccelerationPath": False, "DynamicPathWidth": False}
PATH_STYLES = [
  ("Standard", "The usual path and lane lines", _STANDARD_PATH),
  ("Thin", "A narrower path and lighter lines", _STANDARD_PATH | {"PathWidth": 3.0, "PathEdgeWidth": 10.0, "LaneLinesWidth": 2.0}),
  ("Rainbow", "A rainbow path", _STANDARD_PATH | {"RainbowPath": True}),
  ("Acceleration", "Green when speeding up, amber when slowing", _STANDARD_PATH | {"AccelerationPath": True}),
]
CLEAN_SCREEN = ["HideChangingLanesBanner", "HideTurningBanner", "HideDistanceProfileBanner"]

# CameraView values: 0 Auto, 1 Driver, 2 Standard, 3 Wide. Driver is left to upstream's developer screens.
CAMERA_VIEWS = [("Auto", 0), ("Standard", 2), ("Wide", 3)]
BOOT_LOGOS = [("StarPilot", "starpilot"), ("comma", "stock")]
STARTUP_TOP = "StartupMessageTop"
STARTUP_BOTTOM = "StartupMessageBottom"
STARTUP_DEFAULTS = ("Be ready to take over at any time", "Always keep hands on wheel and eyes on road")


class Display:
  def __init__(self, store: SettingsStore):
    self._store = store

  # Driving screen

  @property
  def signal(self) -> int:
    if not self._store.get_bool("CustomThemes"):
      return 0
    slug = self._store.get_str("SignalAnimation") or "stock"
    return next((i for i, (s, _) in enumerate(SIGNALS) if s == slug), 0)

  def signal_name(self) -> str:
    slug = self._store.get_str("SignalAnimation")
    if self.signal == 0 and slug and slug != "stock" and self._store.get_bool("CustomThemes"):
      return slug.replace("_", " ").title()   # a theme pack's animation
    return SIGNALS[self.signal][1]

  def set_signal(self, index: int) -> None:
    slug = SIGNALS[index][0]
    values: dict = {"SignalAnimation": slug}
    if slug != "stock":
      values |= {"CustomThemes": True, "RandomThemes": False}
    self._store.write(values)

  @property
  def path_style(self) -> int:
    if self._store.get_bool("RainbowPath"):
      return 2
    if self._store.get_bool("AccelerationPath"):
      return 3
    return 1 if self._store.get_float("PathWidth") < 4.5 else 0

  def set_path_style(self, index: int) -> None:
    self._store.write(PATH_STYLES[index][2])

  @property
  def clean_screen(self) -> bool:
    return self._store.get_bool("AdvancedCustomUI") and all(self._store.get_bool(k) for k in CLEAN_SCREEN)

  def set_clean_screen(self, on: bool) -> None:
    self._store.write({"AdvancedCustomUI": True} | dict.fromkeys(CLEAN_SCREEN, on))

  @property
  def blind_spot(self) -> bool:
    return self._store.get_bool("BlindSpotPath")

  def set_blind_spot(self, on: bool) -> None:
    self._store.write({"CustomUI": True, "BlindSpotPath": on})

  def bundle(self, bundle: Bundle) -> tuple[Callable[[], bool], Callable[[bool], None]]:
    return (lambda: bundle.is_on(self._store)), (lambda on: bundle.set(self._store, on))

  # Theme & startup

  @property
  def camera_view(self) -> int:
    value = self._store.get_int("CameraView")
    return next((i for i, (_, v) in enumerate(CAMERA_VIEWS) if v == value), 1)

  def set_camera_view(self, index: int) -> None:
    self._store.write({"QOLVisuals": True, "CameraView": CAMERA_VIEWS[index][1]})

  @property
  def driver_camera_in_reverse(self) -> bool:
    return self._store.get_bool("DriverCamera")

  def set_driver_camera_in_reverse(self, on: bool) -> None:
    self._store.write({"QOLVisuals": True, "DriverCamera": on})

  @property
  def boot_logo(self) -> int:
    slug = self._store.get_str("BootLogo") or "starpilot"
    return next((i for i, (_, s) in enumerate(BOOT_LOGOS) if s == slug), 0)

  def set_boot_logo(self, index: int) -> None:
    self._store.write({"BootLogo": BOOT_LOGOS[index][1]})

  def startup_message(self) -> tuple[str, str]:
    return self._store.get_str(STARTUP_TOP), self._store.get_str(STARTUP_BOTTOM)

  def startup_is_default(self) -> bool:
    return self.startup_message() == STARTUP_DEFAULTS

  def set_startup_message(self, top: str, bottom: str) -> None:
    self._store.write({STARTUP_TOP: top, STARTUP_BOTTOM: bottom})

  # Map

  @property
  def turn_by_turn(self) -> bool:
    return self._store.get_bool("NavigationUI")

  def set_turn_by_turn(self, on: bool) -> None:
    self._store.write({"NavigationUI": on})

  @property
  def vienna(self) -> int:
    return 1 if self._store.get_bool("UseVienna") else 0

  def set_vienna(self, index: int) -> None:
    self._store.write({"NavigationUI": True, "UseVienna": index == 1})

  def summary(self) -> str:
    clean = "Clean screen" if self.clean_screen else "All banners"
    return f"{clean} · {self.signal_name()}"

  def path_summary(self) -> str:
    return f"{PATH_STYLES[self.path_style][0]} path"


def driving_screen_panel(model: Display, window) -> ListPanel:
  def signal_sheet():
    window.present(Sheet("Turn Signal Animation", OptionList([name for _, name in SIGNALS], lambda: model.signal, model.set_signal),
                         subtitle="Plays beside the speed while a blinker is on",
                         actions=[Button("Done", window.dismiss, ButtonStyle.PRIMARY)], on_dismiss=window.dismiss))

  def path_sheet():
    window.present(Sheet("Path Style", ChoiceCards([(name, line) for name, line, _ in PATH_STYLES], lambda: model.path_style,
                                                   model.set_path_style),
                         subtitle="Sets path color, width, edges and lane lines together",
                         actions=[Button("Done", window.dismiss, ButtonStyle.PRIMARY)], on_dismiss=window.dismiss))

  dev_get, dev_set = model.bundle(DEVELOPER_VIEW)
  lead_get, lead_set = model.bundle(LEAD_INSIGHTS)
  return ListPanel([
    SettingRow("Turn Signal Animation", "Plays beside the speed when signalling", ValueButton(model.signal_name, signal_sheet)),
    SettingRow("Path Style", "Color, width and edges as one preset", ValueButton(lambda: PATH_STYLES[model.path_style][0], path_sheet)),
    SettingRow("Clean Screen", "Hides lane change, turn and profile banners", Switch(lambda: model.clean_screen, model.set_clean_screen)),
    SettingRow("Blind Spot Highlights", "Colors the screen edge and lane when a car is beside you",
               Switch(lambda: model.blind_spot, model.set_blind_spot)),
    SectionHeader("POWER USER"),
    SettingRow(DEVELOPER_VIEW.name, DEVELOPER_VIEW.description, Switch(dev_get, dev_set)),
    SettingRow(LEAD_INSIGHTS.name, LEAD_INSIGHTS.description, Switch(lead_get, lead_set)),
  ], title="Driving Screen")


def theme_panel(model: Display, edit_startup_message: Callable[[], None]) -> ListPanel:
  return ListPanel([
    SettingRow("Camera View", "Wide shows more of the road at low speed",
               Segmented([name for name, _ in CAMERA_VIEWS], lambda: model.camera_view, model.set_camera_view)),
    SettingRow("Driver Camera in Reverse", "Shows the inside camera while backing up",
               Switch(lambda: model.driver_camera_in_reverse, model.set_driver_camera_in_reverse)),
    SettingRow("Boot Logo", "Shown while the device starts up",
               Segmented([name for name, _ in BOOT_LOGOS], lambda: model.boot_logo, model.set_boot_logo)),
    SettingRow("Startup Message", lambda: "The banner when you start the car" if model.startup_is_default() else model.startup_message()[0],
               ValueButton(lambda: "Default" if model.startup_is_default() else "Custom", edit_startup_message)),
  ], title="Theme & Startup")


def map_panel(model: Display, open_offline_maps: Callable[[], None]) -> ListPanel:
  return ListPanel([
    SettingRow("Turn-by-Turn on Screen", "Next turn, arrival time and distance while navigating",
               Switch(lambda: model.turn_by_turn, model.set_turn_by_turn)),
    SettingRow("Speed Limit Sign", "US style, or the round Vienna style used in most other countries",
               Segmented(["US", "Vienna"], lambda: model.vienna, model.set_vienna)),
    SettingRow("Offline Maps", "Speed limits and routing without a connection", on_click=open_offline_maps),
    Text("The street name is always shown in the onroad bar. Speed limit sources and their order are in Tuner Mode.",
         T.SIZE_SUBTITLE),
  ], title="Map")


def edit_startup_message(model: Display) -> None:
  """Two keyboard steps (top line, then bottom line) using upstream's keyboard. Empty text restores the default line."""
  from openpilot.system.ui.lib.application import gui_app
  from openpilot.system.ui.widgets import DialogResult
  from openpilot.system.ui.widgets.keyboard import Keyboard

  keyboard = Keyboard(min_text_size=0)
  top, bottom = model.startup_message()
  lines: list[str] = []

  def ask(title: str, current: str) -> None:
    keyboard.clear()
    keyboard.set_title(title, "Leave empty for the default")
    keyboard.set_text(current)
    gui_app.push_widget(keyboard)

  def on_result(result: int) -> None:
    # The keyboard has already closed itself.
    if result != DialogResult.CONFIRM:
      return
    lines.append(keyboard.text.strip() or STARTUP_DEFAULTS[len(lines)])
    if len(lines) == 1:
      ask("Startup Message: second line", bottom)
    else:
      model.set_startup_message(*lines)

  keyboard.set_callback(on_result)
  ask("Startup Message: first line", top)
