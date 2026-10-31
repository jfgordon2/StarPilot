"""Bottom sheets, confirm dialogs and toasts."""
from __future__ import annotations

from collections.abc import Callable

import pyray as rl

from openpilot.system.ui.widgets import DialogResult, Widget
from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.base import Bindable, Component, resolve, size_of
from openpilot.selfdrive.ui.tandem.controls import Button, ButtonStyle, Glyph, Tone
from openpilot.selfdrive.ui.tandem.layout import FILL, Align, column, inset, place, row


def _ease_out(t: float) -> float:
  t = min(1.0, max(0.0, t))
  return 1 - (1 - t) ** 3


class Sheet(Component):
  """Slides up from the bottom over a scrim: handle, title and subtitle, actions on the right, then the body."""
  grow_touch_target = False

  def __init__(self, title: Bindable[str], body: Widget, subtitle: Bindable[str] | None = None,
               actions: list[Button] | None = None, height: float | None = None):
    super().__init__()
    self._title = title
    self._subtitle = subtitle
    self._body = self._child(body)
    self._actions = [self._child(a) for a in actions or []]
    self._height = height
    self._shown_at: float | None = None

  def show_event(self):
    super().show_event()
    self._shown_at = rl.get_time()

  def _sheet_height(self, rect: rl.Rectangle) -> float:
    if self._height is not None:
      return self._height
    width = rect.width - T.px(52)
    return min(rect.height - T.px(90), T.px(110) + size_of(self._body, width)[1] + T.px(24))

  def _render(self, rect: rl.Rectangle):
    t = 1.0 if self._shown_at is None else _ease_out((rl.get_time() - self._shown_at) * 1000 / T.SHEET_MS)
    draw.fill(rect, draw.alpha(T.SCRIM, 0.85 * t))
    height = self._sheet_height(rect)
    sheet = rl.Rectangle(rect.x, rect.y + rect.height - height * t, rect.width, height)
    draw.fill(sheet, T.SURFACE_2, T.RADIUS_SHEET)
    draw.fill(rl.Rectangle(sheet.x, sheet.y + T.RADIUS_SHEET, sheet.width, sheet.height - T.RADIUS_SHEET), T.SURFACE_2)
    draw.fill(place(rl.Rectangle(sheet.x, sheet.y + T.px(14), sheet.width, T.px(6)), T.px(64), T.px(6)), T.KEY_MOD, T.px(3))

    body = inset(sheet, left=T.px(26), right=T.px(26), top=T.px(34), bottom=T.px(22))
    header, content = column(body, [T.px(64), FILL], T.px(14))
    x_end = header.x + header.width
    for action in reversed(self._actions):
      w, h = size_of(action, header.width / 3)
      x_end -= w
      action.render(rl.Rectangle(x_end, header.y + (header.height - h) / 2, w, h))
      x_end -= T.px(12)
    text_rect = rl.Rectangle(header.x, header.y, x_end - header.x, header.height)
    if self._subtitle is not None:
      title_rect, sub_rect = column(place(text_rect, text_rect.width, draw.line_height(T.SIZE_TITLE) + T.px(4) + draw.line_height(T.SIZE_LABEL)),
                                    [draw.line_height(T.SIZE_TITLE), draw.line_height(T.SIZE_LABEL)], T.px(4))
      draw.text(sub_rect, resolve(self._subtitle), T.SIZE_LABEL, T.TEXT_TERTIARY)
    else:
      title_rect = text_rect
    draw.text(title_rect, resolve(self._title), T.SIZE_TITLE, T.TEXT, T.FONT_EXTRABOLD)
    self._body.render(content)


class Dialog(Component):
  """A centered confirm card. tone=DANGER gives the red destructive button; ACCENT a blue one."""
  grow_touch_target = False

  def __init__(self, title: str, message: str, confirm_label: str, on_result: Callable[[DialogResult], None] | None = None,
               cancel_label: str = "Cancel", tone: Tone = Tone.ACCENT, glyph: Glyph | None = None):
    super().__init__()
    self._title = title
    self._message = message
    self._tone = tone
    self._glyph = glyph
    self._on_result = on_result
    confirm_style = ButtonStyle.DANGER if tone == Tone.DANGER else ButtonStyle.PRIMARY
    self._cancel = self._child(Button(cancel_label, lambda: self._finish(DialogResult.CANCEL), height=T.px(64), font_size=T.font_px(19),
                                      radius=T.px(16)))
    self._confirm = self._child(Button(confirm_label, lambda: self._finish(DialogResult.CONFIRM), confirm_style, height=T.px(64),
                                       font_size=T.font_px(19), radius=T.px(16)))
    self.result: DialogResult = DialogResult.NO_ACTION

  def _finish(self, result: DialogResult) -> None:
    self.result = result
    if self._on_result:
      self._on_result(result)

  def _card_height(self, width: float) -> float:
    inner = width - T.px(56)
    return T.px(28) * 2 + T.px(60) + T.px(18) + draw.line_height(T.font_px(26)) + T.px(8) + \
      draw.paragraph_height(self._message, T.font_px(17), T.FONT, inner, 1.4) + T.px(24) + T.px(64)

  def _render(self, rect: rl.Rectangle):
    draw.fill(rect, draw.alpha(T.SCRIM, 0.85))
    width = min(rect.width - T.px(80), T.px(520))
    card = place(rect, width, self._card_height(width))
    draw.fill(card, T.SURFACE_3, T.px(26))
    draw.stroke(card, T.TRACK, T.px(26))
    body = inset(card, T.px(28))
    well_rect, title_rect, text_rect, _, buttons = column(
      body, [T.px(60), draw.line_height(T.font_px(26)), FILL, T.px(16), T.px(64)], T.px(12))
    well = place(well_rect, T.px(60), T.px(60), Align.START)
    danger = self._tone == Tone.DANGER
    draw.fill(well, T.DANGER_SURFACE if danger else T.ACCENT_SURFACE, T.px(18))
    if self._glyph:
      self._glyph(well, T.DANGER_TEXT if danger else T.ACCENT_TEXT, T.px(28))
    draw.text(title_rect, self._title, T.font_px(26), T.TEXT, T.FONT_EXTRABOLD)
    draw.paragraph(text_rect, self._message, T.font_px(17), T.TEXT_SECONDARY, spacing=1.4)
    cancel_rect, confirm_rect = row(buttons, [FILL, FILL], T.px(12))
    self._cancel.render(cancel_rect)
    self._confirm.render(confirm_rect)


class Toast(Component):
  """A short confirmation such as "Backup created". Call show(); it fades after TOAST_MS. Not for use while driving."""
  grow_touch_target = False

  def __init__(self):
    super().__init__()
    self._message = ""
    self._tone = Tone.SUCCESS
    self._shown_at: float | None = None

  def show(self, message: str, tone: Tone = Tone.SUCCESS) -> None:
    self._message, self._tone, self._shown_at = message, tone, rl.get_time()

  @property
  def active(self) -> bool:
    return self._shown_at is not None and (rl.get_time() - self._shown_at) * 1000 < T.TOAST_MS

  def _render(self, rect: rl.Rectangle):
    if not self.active:
      return
    elapsed = (rl.get_time() - self._shown_at) * 1000
    fade = min(1.0, elapsed / 150, (T.TOAST_MS - elapsed) / 300)
    width = draw.text_width(self._message, T.SIZE_BODY, T.FONT_SEMIBOLD) + T.px(80)
    box = place(rect, width, T.px(64), Align.CENTER, Align.END)
    box.y -= T.px(24)
    draw.fill(box, draw.alpha(T.CONTROL, fade), T.px(18))
    ink = {Tone.SUCCESS: T.SUCCESS_TEXT, Tone.WARNING: T.WARNING, Tone.DANGER: T.DANGER_TEXT}.get(self._tone, T.ACCENT_TEXT)
    mark = rl.Rectangle(box.x + T.px(18), box.y, T.px(24), box.height)
    draw.check(mark, draw.alpha(ink, fade), T.px(24))
    draw.text(inset(box, left=T.px(52), right=T.px(18)), self._message, T.SIZE_BODY, draw.alpha(T.TEXT, fade), T.FONT_SEMIBOLD)
