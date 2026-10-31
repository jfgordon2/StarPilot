"""Alerts: one volume preset for every sound, levels per group, and the optional chimes."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pyray as rl

from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.base import Component
from openpilot.selfdrive.ui.tandem.controls import Button, ButtonStyle, Segmented, Slider, Switch, ValueButton
from openpilot.selfdrive.ui.tandem.layout import FILL, column, row
from openpilot.selfdrive.ui.tandem.overlays import Sheet
from openpilot.selfdrive.ui.tandem.rows import ListPanel, SectionHeader, SettingRow
from openpilot.selfdrive.ui.tandem.settings.store import SettingsStore

AUTO = 101          # StarPilot's "Auto": the level follows cabin noise
SAFETY_FLOOR = 25   # StarPilot never plays take-control warnings below this


@dataclass(frozen=True)
class VolumeGroup:
  name: str
  subtitle: str
  keys: tuple[str, ...]
  levels: tuple[int, int, int]   # Quiet, Normal, Loud. Placeholders to tune on real drives.
  safety: bool = False


GROUPS = [
  VolumeGroup("Engage and disengage chimes", "When openpilot turns on or off", ("EngageVolume", "DisengageVolume"), (35, 60, 85)),
  VolumeGroup("Prompts and reminders", "Gentle nudges, like steering below its minimum speed",
              ("PromptVolume", "RefuseVolume", "BelowSteerSpeedVolume"), (45, 70, 90)),
  VolumeGroup("Driver attention", "The chime that asks you to look at the road", ("PromptDistractedVolume", "WarningSoftVolume"),
              (60, 80, 100), safety=True),
  VolumeGroup("Take control warnings", "When you need to steer or brake now", ("WarningImmediateVolume",), (80, 100, 100), safety=True),
]
PRESETS = ["Auto", "Quiet", "Normal", "Loud"]
CUSTOM = -1
CHIMES = [
  ("Green Light", "When the light turns green and you are stopped", "GreenLightAlert"),
  ("Lead Departure", "When the car ahead pulls away", "LeadDepartingAlert"),
  ("Speed Limit Change", "When the posted limit changes", "SpeedLimitChangedAlert"),
  ("Loud Blind Spot", "Signalling into an occupied lane, even when paused", "LoudBlindspotAlert"),
]


class Alerts:
  def __init__(self, store: SettingsStore, play: Callable[[str], None] | None = None):
    self._store = store
    self._play = play

  def level(self, group: VolumeGroup) -> int:
    if not self._store.get_bool("AlertVolumeControl"):
      return AUTO
    return self._store.get_int(group.keys[0])

  @property
  def preset(self) -> int:
    """Index into PRESETS, or CUSTOM when the levels match none of them."""
    levels = [self.level(g) for g in GROUPS]
    if all(level == AUTO for level in levels):
      return 0
    for i in range(3):
      if levels == [g.levels[i] for g in GROUPS]:
        return i + 1
    return CUSTOM

  def set_preset(self, index: int) -> None:
    values: dict = {"AlertVolumeControl": index > 0}
    for group in GROUPS:
      values |= dict.fromkeys(group.keys, AUTO if index == 0 else group.levels[index - 1])
    self._store.write(values)

  def set_level(self, group: VolumeGroup, level: float) -> None:
    """Changing one group makes the preset Custom. The other groups keep their current levels."""
    values: dict = {"AlertVolumeControl": True}
    if not self._store.get_bool("AlertVolumeControl"):
      values |= {k: g.levels[1] for g in GROUPS for k in g.keys}
    level = max(int(level), SAFETY_FLOOR) if group.safety else int(level)
    self._store.write(values | dict.fromkeys(group.keys, level))

  def level_label(self, group: VolumeGroup) -> str:
    level = self.level(group)
    return "Auto" if level == AUTO else f"{level}%"

  def play(self, group: VolumeGroup) -> None:
    if self._play is not None:
      self._play(group.keys[0])

  def summary(self) -> str:
    return "Custom volume" if self.preset == CUSTOM else f"{PRESETS[self.preset]} volume"

  def chimes_summary(self) -> str:
    on = [name for name, _, key in CHIMES if self._store.get_bool(key)]
    return ", ".join(on).capitalize() if on else "No extra chimes"

  def chime(self, key: str) -> bool:
    return self._store.get_bool(key)

  def set_chime(self, key: str, on: bool) -> None:
    self._store.write({key: on})


class VolumeEditor(Component):
  """Big value and Play sample, then the slider with the presets marked and the safety floor hatched."""
  grow_touch_target = False

  def __init__(self, model: Alerts, group: VolumeGroup):
    super().__init__()
    self._model = model
    self._group = group
    self._play = self._child(Button("Play sample", lambda: model.play(group)))
    self._slider = self._child(Slider(lambda: self._value(), lambda v: model.set_level(group, v), 0, 100, step=5,
                                      default=group.levels[1], floor=SAFETY_FLOOR if group.safety else None,
                                      marks=[(group.levels[0], "Quiet"), (group.levels[1], "Normal"), (group.levels[2], "Loud")]))
    self._reset = self._child(Button("Reset to Normal", lambda: model.set_level(group, group.levels[1]), ButtonStyle.GHOST))

  def _value(self) -> float:
    level = self._model.level(self._group)
    return self._group.levels[1] if level == AUTO else level

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    return max_width, T.px(96) + self._slider.preferred_height(max_width) + T.px(110)

  def _render(self, rect: rl.Rectangle):
    top, slider, notes = column(rect, [T.px(96), self._slider.preferred_height(rect.width), FILL], T.px(16))
    value, play = row(top, [FILL, self._play.preferred_size(rect.width)[0]])
    label = self._model.level_label(self._group)
    draw.text(value, label, T.font_px(56), T.TEXT, T.FONT_EXTRABOLD)
    self._play.render(rl.Rectangle(play.x, play.y + (play.height - T.BUTTON_HEIGHT) / 2, play.width, T.BUTTON_HEIGHT))
    self._slider.render(slider)
    note = ("Minimum 25% for safety alerts. " if self._group.safety else "") + "Changing a level sets the preset to Custom."
    line, button = column(notes, [draw.line_height(T.SIZE_SUBTITLE), T.BUTTON_HEIGHT], T.px(10))
    draw.text(line, note, T.SIZE_SUBTITLE, T.TEXT_MUTED)
    w, _ = self._reset.preferred_size(rect.width)
    self._reset.render(rl.Rectangle(button.x, button.y, w, button.height))


def alerts_panel(model: Alerts, window) -> ListPanel:
  def editor(group: VolumeGroup) -> Callable[[], None]:
    return lambda: window.present(Sheet(group.name, VolumeEditor(model, group), subtitle=group.subtitle,
                                        actions=[Button("Done", window.dismiss, ButtonStyle.PRIMARY)], on_dismiss=window.dismiss))

  volume = [SettingRow(g.name, g.subtitle, ValueButton(lambda g=g: model.level_label(g), editor(g)), indent=True) for g in GROUPS]
  chimes = [SettingRow(title, subtitle, Switch(lambda k=key: model.chime(k), lambda on, k=key: model.set_chime(k, on)))
            for title, subtitle, key in CHIMES]
  return ListPanel([
    SettingRow("Volume", lambda: "Custom levels" if model.preset == CUSTOM else "Auto follows cabin noise",
               Segmented(PRESETS, lambda: model.preset, model.set_preset)),
    *volume,
    SectionHeader("CHIMES"),
    *chimes,
  ], title="Alerts", subtitle="One volume for everything. Safety warnings never go below 25%.")


def sound_player() -> Callable[[str], None]:
  """Plays a sample through StarPilot's sounds screen, which owns the audio player process."""
  layout = None

  def play(key: str) -> None:
    nonlocal layout
    if layout is None:
      from openpilot.selfdrive.ui.layouts.settings.starpilot.sounds import StarPilotSoundsLayout
      layout = StarPilotSoundsLayout()
    layout._test_sound(key)
  return play
