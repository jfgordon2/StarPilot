"""First-run setup: three questions (driving style, speed limits, lane changes), or Use defaults.

It runs once, after upstream's onboarding (terms and training). Either way out applies the Essentials defaults first,
then the answers, so everything the questions don't cover starts from a good default too.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pyray as rl

from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.base import Component
from openpilot.selfdrive.ui.tandem.controls import Button, ButtonStyle, ChoiceCards
from openpilot.selfdrive.ui.tandem.layout import FILL, column, inset, row
from openpilot.selfdrive.ui.tandem.settings.store import SettingsStore

MARKER = ".tandem_setup_done"   # beside the params folder, so no new param key (upstream's registry stays untouched)


@dataclass(frozen=True)
class Question:
  name: str
  title: str
  options: list[tuple[str, str]]
  default: int


QUESTIONS = [
  Question("driving style", "How should your car drive?", [
    ("Relaxed", "Longer following gap, gentle starts and early, soft braking."),
    ("Standard · recommended", "Keeps pace with traffic. A good fit for most drivers and roads."),
    ("Sport", "Shorter gap, quicker acceleration and later braking."),
  ], 1),
  Question("speed limits", "What should it do with speed limits?", [
    ("Off", "Speed limits aren't shown or used."),
    ("Show", "Shows the limit next to your speed. You set the speed."),
    ("Match · recommended", "Sets cruise to the limit plus 3. Asks before speeding up."),
  ], 2),
  Question("lane changes", "How should lane changes start?", [
    ("Nudge", "Signal, then nudge the wheel toward the lane."),
    ("Auto · recommended", "Signal and the car changes lanes when it's clear."),
  ], 1),
]


class Setup:
  def __init__(self, store: SettingsStore, done: Callable[[], None]):
    self._store = store
    self._done = done
    self.step = 0
    self.answers = [q.default for q in QUESTIONS]

  @property
  def question(self) -> Question:
    return QUESTIONS[self.step]

  def pick(self, index: int) -> None:
    self.answers[self.step] = index

  def back(self) -> None:
    self.step = max(0, self.step - 1)

  def next(self) -> None:
    if self.step < len(QUESTIONS) - 1:
      self.step += 1
    else:
      self.finish(use_answers=True)

  def finish(self, use_answers: bool) -> None:
    from openpilot.selfdrive.ui.tandem.settings.defaults import apply_essentials
    from openpilot.selfdrive.ui.tandem.settings.speed_steering import SpeedSteering
    with self._store.batch():
      apply_essentials(self._store)
      if use_answers:
        speed = SpeedSteering(self._store)
        speed.set_style(self.answers[0])
        speed.set_speed_limits(self.answers[1])
        speed.set_lane_changes(self.answers[2])
    self._done()


class SetupWindow(Component):
  grow_touch_target = False

  def __init__(self, setup: Setup):
    super().__init__()
    self._setup = setup
    self._cards = [self._child(ChoiceCards(q.options, lambda i=i: setup.answers[i], setup.pick, columns=1, card_height=T.px(100)))
                   for i, q in enumerate(QUESTIONS)]
    self._defaults = self._child(Button("Use defaults", lambda: setup.finish(use_answers=False), ButtonStyle.GHOST))
    self._back = self._child(Button("Back", setup.back, ButtonStyle.SECONDARY))
    self._back.set_visible(lambda: setup.step > 0)
    self._next = self._child(Button(lambda: "Next" if setup.step < len(QUESTIONS) - 1 else "Start driving", setup.next,
                                    ButtonStyle.PRIMARY))

  def _render(self, rect: rl.Rectangle):
    draw.fill(rect, T.BG)
    s = self._setup
    body = inset(rect, x=T.px(60), y=T.px(36))
    left, right = row(body, [T.px(400), FILL], T.px(40))
    cap, title, note, _ = column(left, [T.px(28), draw.line_height(T.font_px(34)) * 2 + T.px(8), FILL, T.px(10)], T.px(14))
    draw.caption(cap, f"STEP {s.step + 1} OF {len(QUESTIONS)}", T.ACCENT_TEXT)
    draw.paragraph(title, s.question.title, T.font_px(34), T.TEXT, T.FONT_EXTRABOLD)
    remaining = [q.name for q in QUESTIONS[s.step + 1:]]
    hint = "You can change all of these later in Settings › Driving."
    draw.paragraph(rl.Rectangle(note.x, note.y, note.width, T.px(120)), hint if not remaining else
                   f"Next: {', then '.join(remaining)}. {hint}", T.font_px(16), T.TEXT_TERTIARY)

    cards, buttons = column(right, [FILL, T.px(64)], T.px(20))
    card = self._cards[s.step]
    h = card.preferred_height(cards.width)
    card.render(rl.Rectangle(cards.x, cards.y, cards.width, h))
    defaults_w = self._defaults.preferred_size(buttons.width)[0]
    left_b, _, back, nxt = row(buttons, [defaults_w, FILL, T.px(160), T.px(220)], T.px(12))
    self._defaults.render(left_b)
    self._back.render(back)
    self._next.render(nxt)


def setup_done_marker() -> Path:
  from openpilot.common.params import Params
  return Path(Params().get_param_path()).parent / MARKER


def maybe_show_setup() -> bool:
  """Push setup once nothing else (onboarding, a dialog) is on top of the main layout.

  Returns True once handled (shown now, or done before); False means try again later.
  """
  from openpilot.system.ui.lib.application import gui_app
  if len(getattr(gui_app, "_nav_stack", [])) != 1:
    return False
  marker = setup_done_marker()
  if marker.exists():
    return True

  def done() -> None:
    marker.touch()
    gui_app.pop_widget()

  gui_app.push_widget(SetupWindow(Setup(SettingsStore(), done)))
  return True
