"""The on-screen keyboard in the Essentials style (design/keyboard.html, from the destination search mock's keys).

It subclasses upstream's Keyboard and keeps its behavior: typing through its InputBox (cursor, password masking
with the last character briefly shown), shift and caps lock, the 123 and #+= layers, backspace repeat, the
minimum length, and closing itself with DialogResult. Only the drawing, the key layout and the action label change.
"""
from __future__ import annotations

import time
from functools import partial

import pyray as rl

from openpilot.system.ui.widgets import Widget
from openpilot.system.ui.widgets import keyboard as upstream
from openpilot.system.ui.widgets.inputbox import InputBox
from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.controls import Button, ButtonStyle
from openpilot.selfdrive.ui.tandem.layout import FILL, Align, column, inset, place, row

BACKSPACE, ENTER, SPACE = upstream.BACKSPACE_KEY, upstream.ENTER_KEY, upstream.SPACE_KEY
SHIFT_OFF, SHIFT_ON, CAPS = upstream.SHIFT_INACTIVE_KEY, upstream.SHIFT_ACTIVE_KEY, upstream.CAPS_LOCK_KEY
NUMBERS, SYMBOLS, LETTERS = upstream.NUMERIC_KEY, upstream.SYMBOL_KEY, upstream.ABC_KEY

# The mock's rows: ten keys, then nine and backspace (inset), then shift, seven and two marks, then 123, space and the
# action. The number and symbol layers keep upstream's characters in the same shape.
LAYOUTS = {
  "lowercase": [list("qwertyuiop"), [*"asdfghjkl", BACKSPACE], [SHIFT_OFF, *"zxcvbnm", ",", "."], [NUMBERS, SPACE, ENTER]],
  "uppercase": [list("QWERTYUIOP"), [*"ASDFGHJKL", BACKSPACE], [SHIFT_ON, *"ZXCVBNM", ",", "."], [NUMBERS, SPACE, ENTER]],
  "numbers": [list("1234567890"), ["-", "/", ":", ";", "(", ")", "$", "&", "@", BACKSPACE],
              [SYMBOLS, "_", "'", "\"", "?", "!", "`", "#", ",", "."], [LETTERS, SPACE, ENTER]],
  "specials": [list("[]{}#%^*+="), ["_", "\\", "|", "~", "<", ">", "€", "£", "¥", BACKSPACE],
               [NUMBERS, "•", "'", "\"", "?", "!", "@", "-", ",", "."], [LETTERS, SPACE, ENTER]],
}
BOTTOM_ROW = [1.4, 6.0, 2.6]                     # 123, space, action, as wide as in the mock
FUNCTION_KEYS = {BACKSPACE, SHIFT_OFF, SHIFT_ON, CAPS, NUMBERS, SYMBOLS, LETTERS}
ICONS = {BACKSPACE: "backspace", SHIFT_OFF: "shift", SHIFT_ON: "shift", CAPS: "shift"}
LABELS = {NUMBERS: "123", SYMBOLS: "#+=", LETTERS: "ABC", SPACE: "space"}

KEY_FILL = T._hex("262A31")
FUNCTION_FILL = T._hex("353A43")
PANEL_FILL = T._hex("13161A")
FIELD_FILL = T._hex("1A1D22")
DIVIDER = T._hex("1F242B")
FIELD_FONT = T.font_px(20)


class _Field(InputBox):
  """Upstream's input box (cursor, masking, taps), drawn on our field: no fill of its own, our text color and size."""

  def _render(self, rect, *_):
    super()._render(rect, rl.BLANK, rl.BLANK, T.TEXT, FIELD_FONT)


class _Key(Widget):
  """One key: a rounded cap, a letter, a label or an icon. Pressing darkens it, as the mock's buttons do."""

  def __init__(self, key: str, on_press, keyboard: EssentialsKeyboard):
    super().__init__()
    self.key = key
    self._keyboard = keyboard
    self._multi_touch = True        # as upstream's keys: a second finger can type while the first lifts
    self.set_click_callback(on_press)

  def _render(self, rect: rl.Rectangle):
    kb, key = self._keyboard, self.key
    ink, weight, size = T.TEXT, T.FONT_MEDIUM, T.font_px(24)
    if key == ENTER:
      ready = self.enabled
      fill, ink, weight, size = (T.ACCENT, T.ACCENT_INK, T.FONT_BOLD, T.font_px(19)) if ready else (T.TRACK, T.TEXT_MUTED, T.FONT_BOLD,
                                                                                                    T.font_px(19))
    elif key == CAPS:
      fill, ink = T.ACCENT, T.ACCENT_INK
    elif key == SHIFT_ON:
      fill, ink = T.ACCENT_SURFACE, T.ACCENT_TEXT
    elif key in FUNCTION_KEYS:
      fill, weight, size = FUNCTION_FILL, T.FONT_SEMIBOLD, T.font_px(18)
    else:
      fill = KEY_FILL
    draw.fill(rect, fill, T.px(12))
    if self.is_pressed and self.enabled:
      draw.pressed(rect, T.px(12))
    if key in ICONS:
      draw.icon(rect, ICONS[key], ink, T.px(26) if key == BACKSPACE else T.px(24))
    elif key == ENTER:
      draw.text(inset(rect, x=T.px(10)), draw.fit(kb.action, size, weight, rect.width - T.px(20)), size, ink, weight, Align.CENTER)
    elif key == SPACE:
      draw.text(rect, LABELS[key], T.font_px(16), T.TEXT_MUTED, T.FONT, Align.CENTER)
    else:
      draw.text(rect, LABELS.get(key, key), size, ink, weight, Align.CENTER)


class _Eye(Widget):
  """Shows or hides the password, using upstream's toggle."""

  def __init__(self, keyboard: EssentialsKeyboard):
    super().__init__()
    self._keyboard = keyboard
    self.set_click_callback(keyboard._eye_button_callback)

  def _render(self, rect: rl.Rectangle):
    if self.is_pressed:
      draw.pressed(rect, T.px(10))
    draw.icon(rect, "eye" if self._keyboard._password_mode else "eye_off", T.TEXT_TERTIARY, T.px(24))


class EssentialsKeyboard(upstream.Keyboard):
  """Upstream's keyboard drawn as design/keyboard.html. action names what the blue key does (e.g. "Set up", "Save")."""

  def __init__(self, max_text_size: int = 255, min_text_size: int = 0, password_mode: bool = False, show_password_toggle: bool = False,
               callback=None, action: str = "Done"):
    super().__init__(max_text_size, min_text_size, password_mode, show_password_toggle, callback)
    self.action = action
    self._title_text, self._subtitle_text = "", ""
    self._input_box = _Field(max_text_size)
    self._cancel = Button("Cancel", self._cancel_button_callback, ButtonStyle.SECONDARY, height=T.px(56), font_size=T.font_px(17),
                          radius=T.px(14), weight=T.FONT_BOLD, padding=T.px(24))
    keys = {k for rows in LAYOUTS.values() for keys in rows for k in keys} | {CAPS}
    self._all_keys = {k: _Key(k, partial(self._key_callback, k), self) for k in keys}
    self._eye = _Eye(self)

  def set_title(self, title: str, sub_title: str = ""):
    self._title_text, self._subtitle_text = title, sub_title

  def set_action(self, action: str) -> None:
    self.action = action

  def _render(self, rect: rl.Rectangle):
    draw.fill(rect, T.BG)
    header, keys = column(rect, [T.px(146), FILL])
    self._render_header(inset(header, left=T.px(16), right=T.px(16), top=T.px(14), bottom=T.px(10)))
    draw.fill(keys, PANEL_FILL)
    draw.hline(keys.x, keys.y, keys.width, DIVIDER)
    self._repeat_backspace()
    self._render_keys(inset(keys, left=T.px(12), right=T.px(12), top=T.px(10), bottom=T.px(12)))

  def _render_header(self, rect: rl.Rectangle) -> None:
    top, field = column(rect, [T.px(56), T.px(56)], T.px(10))
    cancel_w = self._cancel.preferred_size(rect.width)[0]
    words, cancel = row(top, [FILL, cancel_w], T.px(12))
    self._cancel.render(cancel)
    title_h, sub_h = draw.line_height(T.font_px(24)), draw.line_height(T.font_px(15))
    block = place(inset(words, x=T.px(4)), words.width - T.px(8), title_h + (T.px(3) + sub_h if self._subtitle_text else 0))
    draw.text(rl.Rectangle(block.x, block.y, block.width, title_h),
              draw.fit(self._title_text, T.font_px(24), T.FONT_EXTRABOLD, block.width), T.font_px(24), T.TEXT, T.FONT_EXTRABOLD)
    if self._subtitle_text:
      draw.text(rl.Rectangle(block.x, block.y + title_h + T.px(3), block.width, sub_h),
                draw.fit(self._subtitle_text, T.font_px(15), T.FONT, block.width), T.font_px(15), T.TEXT_TERTIARY)
    draw.fill(field, FIELD_FILL, T.px(14))
    draw.stroke(field, T.ACCENT, T.px(14), T.px(2))
    text = inset(field, left=T.px(16), right=T.px(8))
    if self._show_password_toggle:
      text, eye = row(text, [FILL, T.px(44)], T.px(8))
      eye = place(eye, T.px(44), T.px(44))
      self._eye.render(eye)
    self._input_box.set_password_mode(self._password_mode)
    self._input_box.render(text)

  def _repeat_backspace(self) -> None:
    """Upstream's hold-to-delete: after a pause, keep deleting while backspace stays down."""
    key = self._all_keys[BACKSPACE]
    if not key.is_pressed:
      self._backspace_pressed = False
      return
    now = time.monotonic()
    if not self._backspace_pressed:
      self._backspace_pressed, self._backspace_press_time, self._backspace_last_repeat = True, now, now
    elif now - self._backspace_press_time > upstream.DELETE_REPEAT_DELAY and now - self._backspace_last_repeat > upstream.DELETE_REPEAT_INTERVAL:
      self._input_box.delete_char_before_cursor()
      self._backspace_last_repeat = now

  def _render_keys(self, rect: rl.Rectangle) -> None:
    gap = T.px(8)
    rows = column(rect, [FILL] * 4, gap)
    unit = (rect.width - 9 * gap) / 10
    for index, (keys, area) in enumerate(zip(LAYOUTS[self._layout_name], rows, strict=True)):
      if index == 1:
        area = inset(area, x=unit / 3)              # the second row sits in a little, as on the mock
      if index == 3:
        spare = area.width - gap * (len(keys) - 1)
        widths = [spare * w / sum(BOTTOM_ROW) for w in BOTTOM_ROW]
      else:
        widths = [FILL] * len(keys)
      for key, cell in zip(keys, row(area, widths, gap), strict=True):
        if key == SHIFT_ON and self._caps_lock:
          key = CAPS
        widget = self._all_keys[key]
        widget.set_enabled(key != ENTER or len(self._input_box.text) >= self._min_text_size)
        widget.render(cell)

