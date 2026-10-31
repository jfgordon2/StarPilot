"""Display: the driving screen, theme and startup, and the map."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

import pyray as rl

from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.base import Component
from openpilot.selfdrive.ui.tandem.blocks import Grid
from openpilot.selfdrive.ui.tandem.layout import Align, inset, place
from openpilot.selfdrive.ui.tandem.controls import Button, ButtonStyle, Segmented, Switch, ValueButton
from openpilot.selfdrive.ui.tandem.overlays import Sheet
from openpilot.selfdrive.ui.tandem.rows import ListPanel, SectionHeader, SettingRow
from openpilot.selfdrive.ui.tandem.settings.bundles import DEVELOPER_VIEW, LEAD_INSIGHTS, Bundle
from openpilot.selfdrive.ui.tandem.settings.store import SettingsStore

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
# (BootLogo slug, name). Tandem's is the Essentials default; StarPilot installs it from its boot logos folder like any other.
TANDEM_LOGO = "tandem"
BUILT_IN_LOGOS = [(TANDEM_LOGO, "Tandem"), ("starpilot", "StarPilot"), ("stock", "comma")]
TANDEM_LOGO_FILE = Path(__file__).resolve().parents[1] / "assets" / "boot_logo.jpg"
_STARPILOT_IMAGES = Path(__file__).resolve().parents[4] / "starpilot" / "assets" / "other_images"
BUILT_IN_IMAGES = {TANDEM_LOGO: TANDEM_LOGO_FILE, "starpilot": _STARPILOT_IMAGES / "starpilot_boot_logo.jpg",
                   "stock": _STARPILOT_IMAGES / "stock_bg.jpg"}


class BootLogoSource(Protocol):
  def installed(self) -> list[tuple[str, str]]: ...   # (slug, name) of each boot logo StarPilot downloaded to the device
  def install_tandem(self) -> None: ...                 # puts Tandem's logo where StarPilot looks for boot logos
  def image(self, slug: str) -> Path | None: ...        # a downloaded logo's file, for its preview
STARTUP_TOP = "StartupMessageTop"
STARTUP_BOTTOM = "StartupMessageBottom"
STARTUP_DEFAULTS = ("Be ready to take over at any time", "Always keep hands on wheel and eyes on road")


class Display:
  def __init__(self, store: SettingsStore, boot_logos: Callable[[], BootLogoSource] | None = None):
    """boot_logos makes the boot logo source the first time the picker needs it."""
    self._store = store
    self._boot_logos = boot_logos
    self._boot_logo_source: BootLogoSource | None = None

  @property
  def boot_logos(self) -> BootLogoSource | None:
    if self._boot_logo_source is None and self._boot_logos is not None:
      self._boot_logo_source = self._boot_logos()
    return self._boot_logo_source

  # Driving screen

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
  def boot_logo(self) -> str:
    return self._store.get_str("BootLogo") or "starpilot"

  def boot_logo_options(self) -> list[tuple[str, str]]:
    """The built-in logos, then those downloaded to the device."""
    installed = self.boot_logos.installed() if self.boot_logos is not None else []
    return BUILT_IN_LOGOS + [(slug, name) for slug, name in installed if slug not in dict(BUILT_IN_LOGOS)]

  def boot_logo_image(self, slug: str) -> Path | None:
    if slug in BUILT_IN_IMAGES:
      return BUILT_IN_IMAGES[slug]
    return self.boot_logos.image(slug) if self.boot_logos is not None else None

  def boot_logo_name(self) -> str:
    slug = self.boot_logo
    if slug == TANDEM_LOGO:
      return "Default"
    return dict(self.boot_logo_options()).get(slug) or slug.replace("_", " ").replace("-", " ").title()

  def set_boot_logo(self, slug: str) -> None:
    """For Tandem's, the file goes in place first: StarPilot applies the logo as soon as the param changes."""
    if slug == TANDEM_LOGO and self.boot_logos is not None:
      self.boot_logos.install_tandem()
    self._store.write({"BootLogo": slug})

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
    return clean

  def path_summary(self) -> str:
    return f"{PATH_STYLES[self.path_style][0]} path"


def driving_screen_panel(model: Display, window) -> ListPanel:
  def path_sheet():
    window.present(Sheet("Path Style", PathStylePicker(lambda: model.path_style, model.set_path_style),
                         subtitle="Sets path color, width, edges and lane lines together",
                         actions=[Button("Done", window.dismiss, ButtonStyle.PRIMARY)], on_dismiss=window.dismiss))

  dev_get, dev_set = model.bundle(DEVELOPER_VIEW)
  lead_get, lead_set = model.bundle(LEAD_INSIGHTS)
  return ListPanel([
    SettingRow("Path Style", "Color, width and edges as one preset", ValueButton(lambda: PATH_STYLES[model.path_style][0], path_sheet)),
    SettingRow("Clean Screen", "Hides lane change, turn and profile banners", Switch(lambda: model.clean_screen, model.set_clean_screen)),
    SettingRow("Blind Spot Highlights", "Colors the screen edge and lane when a car is beside you",
               Switch(lambda: model.blind_spot, model.set_blind_spot)),
    SectionHeader("POWER USER"),
    SettingRow(DEVELOPER_VIEW.name, DEVELOPER_VIEW.description, Switch(dev_get, dev_set)),
    SettingRow(LEAD_INSIGHTS.name, LEAD_INSIGHTS.description, Switch(lead_get, lead_set)),
  ], title="Driving Screen")


def boot_logo_sheet(model: Display, window) -> None:
  """Pick a boot logo from previews: the built-in ones, and any StarPilot already downloaded to the device."""
  def pick(slug: str) -> None:
    model.set_boot_logo(slug)
    window.dismiss()

  cards = [LogoCard(name, model.boot_logo_image(slug), lambda s=slug: model.boot_logo == s, lambda s=slug: pick(s))
           for slug, name in model.boot_logo_options()]
  window.present(Sheet("Boot Logo", ListPanel([Grid(cards, columns=4, gap=T.px(14))], background=T.SURFACE_2, dividers=False),
                       subtitle="Shown while the device starts up",
                       actions=[Button("Done", window.dismiss, ButtonStyle.PRIMARY)], on_dismiss=window.dismiss))


def theme_panel(model: Display, edit_startup_message: Callable[[], None], window=None) -> ListPanel:
  return ListPanel([
    SettingRow("Camera View", "Wide shows more of the road at low speed",
               Segmented([name for name, _ in CAMERA_VIEWS], lambda: model.camera_view, model.set_camera_view)),
    SettingRow("Driver Camera in Reverse", "Shows the inside camera while backing up",
               Switch(lambda: model.driver_camera_in_reverse, model.set_driver_camera_in_reverse)),
    SettingRow("Boot Logo", "Shown while the device starts up", ValueButton(model.boot_logo_name, lambda: boot_logo_sheet(model, window))),
    SettingRow("Startup Message", lambda: "The banner when you start the car" if model.startup_is_default() else model.startup_message()[0],
               ValueButton(lambda: "Default" if model.startup_is_default() else "Custom", edit_startup_message)),
  ], title="Theme & Startup", end_divider=True)


def map_panel(model: Display, open_offline_maps: Callable[[], None]) -> ListPanel:
  return ListPanel([
    SettingRow("Turn-by-Turn on Screen", "Next turn, arrival time and distance while navigating",
               Switch(lambda: model.turn_by_turn, model.set_turn_by_turn)),
    SettingRow("Speed Limit Sign", "US style, or the round Vienna style used in most other countries",
               SignPicker(lambda: model.vienna, model.set_vienna), height=T.px(96)),
    SettingRow("Offline Maps", "Speed limits and routing without a connection", on_click=open_offline_maps),
  ], title="Map", end_divider=True,
     footnote="The street name is always shown in the onroad bar. Speed limit sources and their order are in Tuner Mode.")


def edit_startup_message(model: Display) -> None:
  """Two keyboard steps (top line, then bottom line). Empty text restores the default line."""
  from openpilot.system.ui.lib.application import gui_app
  from openpilot.system.ui.widgets import DialogResult
  from openpilot.selfdrive.ui.tandem.keyboard import EssentialsKeyboard

  keyboard = EssentialsKeyboard(min_text_size=0, action="Next")
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
      keyboard.set_action("Save")
      ask("Startup Message: second line", bottom)
    else:
      model.set_startup_message(*lines)

  keyboard.set_callback(on_result)
  ask("Startup Message: first line", top)


VIENNA_RED = rl.Color(0xD9, 0x43, 0x4F, 255)


class SignPicker(Component):
  """The two speed limit sign styles as small pictures: a US "55" sign and a round Vienna "90"."""
  CARD_W, CARD_H = T.px(86), T.px(72)

  def __init__(self, selected: Callable[[], int], on_change: Callable[[int], None]):
    super().__init__()
    self._selected = selected
    self._on_change = on_change

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    return self.CARD_W * 2 + T.px(8), self.CARD_H

  def _cards(self) -> list[rl.Rectangle]:
    return [rl.Rectangle(self._rect.x + i * (self.CARD_W + T.px(8)), self._rect.y, self.CARD_W, self.CARD_H) for i in range(2)]

  def _handle_mouse_release(self, mouse_pos) -> None:
    super()._handle_mouse_release(mouse_pos)
    for i, r in enumerate(self._cards()):
      if rl.check_collision_point_rec(mouse_pos, r) and i != self._selected():
        self._on_change(i)

  def _render(self, rect: rl.Rectangle):
    for i, r in enumerate(self._cards()):
      chosen = i == self._selected()
      draw.fill(r, T.ACCENT_SELECTED if chosen else T.SURFACE_4, T.px(14))
      if chosen:
        draw.stroke(r, T.ACCENT, T.px(14), T.px(2))
      if i == 0:
        sign = place(r, T.px(36), T.px(46))
        draw.fill(sign, rl.WHITE, T.px(5))
        draw.stroke(inset(sign, T.px(3)), T.BG, T.px(3), T.px(2))
        draw.text(sign, "55", T.font_px(16), T.BG, T.FONT_EXTRABOLD, Align.CENTER)
      else:
        sign = place(r, T.px(46), T.px(46))
        draw.fill(sign, VIENNA_RED, T.px(23))
        draw.fill(inset(sign, T.px(6)), rl.WHITE, T.px(17))
        draw.text(sign, "90", T.font_px(16), T.BG, T.FONT_EXTRABOLD, Align.CENTER)


def _hex(value: str, alpha: float = 1.0) -> rl.Color:
  return rl.Color(int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16), round(255 * alpha))


# Each style's preview, from the mock (a 220 x 150 picture): path corners at the top and bottom, lane line width, and the
# path's colors from the bottom of the path to the top, with its opacity.
PREVIEWS = [
  ((104, 116, 70, 150), 3, [(0.0, "3A73B3"), (1.0, "3A73B3")], 0.65),
  ((108, 112, 96, 124), 2, [(0.0, "7DBBF9"), (1.0, "7DBBF9")], 0.8),
  ((104, 116, 70, 150), 3, [(0.0, "E5484D"), (0.25, "F5A524"), (0.5, "F5E06B"), (0.75, "3FD08A"), (1.0, "5AAAF8")], 0.75),
  ((104, 116, 70, 150), 3, [(0.0, "3FD08A"), (0.6, "3FD08A"), (1.0, "F0B35A")], 0.6),
]
PREVIEW_W, PREVIEW_H = 220, 150
ROAD = _hex("132231")
LANE = _hex("5C6B7A")


def _gradient(stops: list[tuple[float, str]], t: float, alpha: float) -> rl.Color:
  for (t0, c0), (t1, c1) in zip(stops, stops[1:], strict=False):
    if t <= t1:
      f = 0.0 if t1 == t0 else (t - t0) / (t1 - t0)
      a, b = _hex(c0), _hex(c1)
      return rl.Color(round(a.r + (b.r - a.r) * f), round(a.g + (b.g - a.g) * f), round(a.b + (b.b - a.b) * f), round(255 * alpha))
  return _hex(stops[-1][1], alpha)


def draw_path_preview(rect: rl.Rectangle, index: int) -> None:
  """The mock's little road picture: two lane lines and the path in this style, scaled to cover rect."""
  (top_l, top_r, bottom_l, bottom_r), lane_w, stops, alpha = PREVIEWS[index]
  scale = max(rect.width / PREVIEW_W, rect.height / PREVIEW_H)
  ox = rect.x + (rect.width - PREVIEW_W * scale) / 2
  oy = rect.y + (rect.height - PREVIEW_H * scale) / 2

  def at(x: float, y: float) -> rl.Vector2:
    return rl.Vector2(ox + x * scale, oy + y * scale)

  draw.fill(rect, ROAD, T.px(12))
  rl.begin_scissor_mode(int(rect.x), int(rect.y), int(rect.width), int(rect.height))
  for a, b in (((100, 10), (30, 150)), ((120, 10), (190, 150))):
    rl.draw_line_ex(at(*a), at(*b), lane_w * scale, LANE)
  y0, y1 = at(0, 10).y, at(0, 150).y
  for i in range(int(y1 - y0)):   # the path, one pixel row at a time, so the color can change along it
    t = i / max(1.0, y1 - y0)
    left = top_l + (bottom_l - top_l) * t
    right = top_r + (bottom_r - top_r) * t
    x0 = at(left, 0).x
    rl.draw_rectangle_rec(rl.Rectangle(x0, y0 + i, at(right, 0).x - x0, 1), _gradient(stops, 1 - t, alpha))
  rl.end_scissor_mode()


class PathStylePicker(Component):
  """The path styles side by side, each a picture of the path in that style, with its name under it."""
  GAP = T.px(14)

  def __init__(self, selected: Callable[[], int], on_change: Callable[[int], None]):
    super().__init__()
    self._selected = selected
    self._on_change = on_change
    self._pressed: int | None = None

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    return max_width, T.px(214) + T.px(14) + draw.line_height(T.SIZE_SUBTITLE)

  def _cards(self) -> list[rl.Rectangle]:
    w = (self._rect.width - self.GAP * (len(PATH_STYLES) - 1)) / len(PATH_STYLES)
    return [rl.Rectangle(self._rect.x + i * (w + self.GAP), self._rect.y, w, T.px(214)) for i in range(len(PATH_STYLES))]

  def _hit(self, pos) -> int | None:
    return next((i for i, r in enumerate(self._cards()) if rl.check_collision_point_rec(pos, r)), None)

  def _handle_mouse_press(self, mouse_pos) -> None:
    self._pressed = self._hit(mouse_pos)

  def _handle_mouse_release(self, mouse_pos) -> None:
    super()._handle_mouse_release(mouse_pos)
    hit = self._hit(mouse_pos)
    if hit is not None and hit == self._pressed and hit != self._selected():
      self._on_change(hit)
    self._pressed = None

  def _render(self, rect: rl.Rectangle):
    selected = self._selected()
    for i, card in enumerate(self._cards()):
      chosen = i == selected
      draw.fill(card, T.SURFACE_4, T.px(20))
      if chosen:
        draw.stroke(card, T.ACCENT, T.px(20), T.px(2))
      elif self.is_pressed and i == self._pressed:
        draw.pressed(card, T.px(20))
      body = inset(card, T.px(12))
      label_h = draw.line_height(T.font_px(18))
      draw_path_preview(rl.Rectangle(body.x, body.y, body.width, body.height - label_h - T.px(12)), i)
      draw.text(rl.Rectangle(body.x, body.y + body.height - label_h, body.width, label_h), PATH_STYLES[i][0], T.font_px(18), T.TEXT,
                T.FONT_BOLD if chosen else T.FONT_SEMIBOLD, Align.CENTER)
    note = rl.Rectangle(rect.x, rect.y + T.px(214) + T.px(14), rect.width, draw.line_height(T.SIZE_SUBTITLE))
    draw.text(note, "Acceleration tints the path green when speeding up and amber when slowing. Each value can be changed in Tuner Mode.",
              T.SIZE_SUBTITLE, T.TEXT_TERTIARY)


class LogoCard(Component):
  """A boot logo's preview, the boot screen in small, with its name under it; outlined when chosen."""

  def __init__(self, name: str, image: Path | None, chosen: Callable[[], bool], on_pick: Callable[[], None]):
    super().__init__()
    self._name, self._image, self._chosen = name, image, chosen
    self.set_click_callback(on_pick)

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    return max_width, T.px(12) + (max_width - T.px(24)) / 2 + T.px(12) + draw.line_height(T.font_px(18)) + T.px(12)

  def _render(self, rect: rl.Rectangle):
    chosen = self._chosen()
    draw.fill(rect, T.SURFACE_4, T.px(20))
    if chosen:
      draw.stroke(rect, T.ACCENT, T.px(20), T.px(2))
    elif self.is_pressed:
      draw.pressed(rect, T.px(20))
    body = inset(rect, T.px(12))
    preview = rl.Rectangle(body.x, body.y, body.width, body.width / 2)   # boot logos are 2:1
    texture = _logo_texture(self._image, int(preview.width)) if self._image is not None else None
    if texture is not None:
      rl.draw_texture_pro(texture, rl.Rectangle(0, 0, texture.width, texture.height), preview, rl.Vector2(0, 0), 0, rl.WHITE)
    else:
      draw.fill(preview, T.BG, T.px(12))
      draw.text(preview, "No preview", T.SIZE_SUBTITLE, T.TEXT_MUTED, h=Align.CENTER)
    label = rl.Rectangle(body.x, preview.y + preview.height + T.px(12), body.width, draw.line_height(T.font_px(18)))
    draw.text(label, self._name, T.font_px(18), T.TEXT, T.FONT_BOLD if chosen else T.FONT_SEMIBOLD, Align.CENTER)


_TEXTURES: dict[tuple[str, int], rl.Texture | None] = {}


def _logo_texture(path: Path, width: int) -> rl.Texture | None:
  """A boot logo scaled to width, landscape (comma's is stored portrait, as the device's boot screen takes it)."""
  key = (str(path), width)
  if key not in _TEXTURES:
    texture = None
    if path.is_file():
      image = rl.load_image(str(path))
      if image.height > image.width:
        rl.image_rotate_ccw(image)
      rl.image_resize(image, width, width // 2)
      texture = rl.load_texture_from_image(image)
      rl.set_texture_filter(texture, rl.TextureFilter.TEXTURE_FILTER_BILINEAR)
      rl.unload_image(image)
    _TEXTURES[key] = texture
  return _TEXTURES[key]


class UpstreamBootLogos:
  """Boot logos as StarPilot keeps them: one file per logo in its themes folder."""

  def __init__(self):
    from openpilot.starpilot.common.starpilot_variables import THEME_SAVE_PATH
    self._folder = THEME_SAVE_PATH / "bootlogos"

  def installed(self) -> list[tuple[str, str]]:
    from openpilot.selfdrive.ui.layouts.settings.starpilot.appearance import _theme_display_name
    if not self._folder.is_dir():
      return []
    return [(f.stem, _theme_display_name(f.stem)) for f in sorted(self._folder.iterdir()) if f.is_file()]

  def image(self, slug: str) -> Path | None:
    return next((f for f in sorted(self._folder.iterdir()) if f.is_file() and f.stem == slug), None) if self._folder.is_dir() else None

  def install_tandem(self) -> None:
    import shutil
    target = self._folder / f"{TANDEM_LOGO}.jpg"
    try:
      if not target.is_file() or target.read_bytes() != TANDEM_LOGO_FILE.read_bytes():
        self._folder.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(TANDEM_LOGO_FILE, target)
    except OSError:
      pass   # StarPilot keeps its own logo if the copy fails
