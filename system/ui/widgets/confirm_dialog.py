"""Confirmation and alert dialogs in the comma 3/3X Aether Cards style.

Same API as before (text, confirm_text, cancel_text, rich, callback, set_text, Enter/Escape),
so every caller picks up the shared look: an outlined card on the settings ground, the message
centered as before, and the shared 112 px Cancel / confirm pills sharing the card's width.
"""
from __future__ import annotations

import pyray as rl
from collections.abc import Callable
from openpilot.system.ui.lib.application import gui_app, FontWeight, FONT_SCALE
from openpilot.system.ui.lib.multilang import tr
from openpilot.system.ui.lib.text_measure import measure_text_cached
from openpilot.system.ui.widgets import DialogResult
from openpilot.system.ui.widgets.html_render import HtmlRenderer, ElementType
from openpilot.system.ui.widgets import Widget
from openpilot.system.ui.widgets.scroller_tici import Scroller
from openpilot.selfdrive.ui.lib import aether_style as AS

MAX_CARD_WIDTH = 1500
MESSAGE_SIZE = 70        # the original openpilot dialog sizes: read at a glance from the driver's seat
MESSAGE_MAX_LINES = 6
RICH_TEXT_SIZE = 50
RICH_HEADING_GAP = 40    # space under a heading before its body text (the renderer's default is 16 px)


def _wrap(font: rl.Font, text: str, width: float, size: int, max_lines: int) -> list[str]:
  """Wrap paragraphs to `width`; the last kept line ends in "..." if text is cut (the fonts have no "…")."""
  lines: list[str] = []
  for paragraph in text.split("\n"):
    current = ""
    for word in paragraph.split():
      candidate = f"{current} {word}".strip()
      if current and measure_text_cached(font, candidate, size).x > width:
        lines.append(current)
        current = word
      else:
        current = candidate
    lines.append(current)
  if len(lines) > max_lines:
    lines = lines[:max_lines]
    last = lines[-1]
    while last and measure_text_cached(font, last + "...", size).x > width:
      last = last.rsplit(" ", 1)[0] if " " in last else last[:-1]
    lines[-1] = last.rstrip(" ,.;:") + "..."
  return lines


class ConfirmDialog(Widget):
  def __init__(self, text: str, confirm_text: str, cancel_text: str | None = None, rich: bool = False,
               callback: Callable[[DialogResult], None] | None = None):
    super().__init__()
    # Imported here: aethergrid itself uses ConfirmDialog for confirmations.
    from openpilot.selfdrive.ui.layouts.settings.starpilot.aethergrid import AetherButton, draw_settings_card

    if cancel_text is None:
      cancel_text = tr("Cancel")
    self._text = text
    self._rich = rich
    self._callback = callback
    self._cancel_text = cancel_text
    self._closed = False
    self._draw_card = draw_settings_card
    self._html_renderer = HtmlRenderer(text=text, text_size={ElementType.P: RICH_TEXT_SIZE}, text_color=AS.TEXT,
                                       center_text=True)
    # Headings get more room below them in this dialog only; margins apply when the text is parsed.
    for heading in (ElementType.H1, ElementType.H2, ElementType.H3):
      self._html_renderer.styles[heading]["margin_bottom"] = RICH_HEADING_GAP
    self._html_renderer.parse_html_content(text)
    self._scroller = Scroller([self._html_renderer], line_separator=False, spacing=0)
    self._cancel_button = self._child(AetherButton(cancel_text, self._cancel_button_callback, neutral=True))
    self._confirm_button = self._child(AetherButton(confirm_text, self._confirm_button_callback,
                                                    emphasized=True, accent_color=AS.ACCENT_SOLID))

  def set_text(self, text):
    self._text = text
    if self._rich:
      self._html_renderer.parse_html_content(text)

  def _finish(self, result: DialogResult):
    if self._closed:
      return
    self._closed = True
    gui_app.pop_widget()
    if self._callback:
      self._callback(result)

  def _cancel_button_callback(self):
    self._finish(DialogResult.CANCEL)

  def _confirm_button_callback(self):
    self._finish(DialogResult.CONFIRM)

  def _button_rects(self, card: rl.Rectangle, inset: float) -> tuple[rl.Rectangle, rl.Rectangle | None]:
    """As the original dialog: Cancel and confirm share the card's width; a lone button spans it."""
    height = self._confirm_button.measure_height()
    y = card.y + card.height - inset - height
    width = card.width - inset * 2
    if not self._cancel_text:
      return rl.Rectangle(card.x + inset, y, width, height), None
    half = (width - AS.SETTINGS_TILE_GAP) / 2
    cancel = rl.Rectangle(card.x + inset, y, half, height)
    return rl.Rectangle(cancel.x + half + AS.SETTINGS_TILE_GAP, y, half, height), cancel

  def _render(self, rect: rl.Rectangle):
    if self._closed:
      return
    rl.draw_rectangle_rec(rect, AS.SETTINGS_BG)
    margin_x = min(AS.SETTINGS_DIALOG_MARGIN_X, rect.width * 0.05)
    margin_y = min(AS.SETTINGS_DIALOG_MARGIN_Y, rect.height * 0.05)
    inset = AS.SETTINGS_DIALOG_INSET
    actions_h = self._confirm_button.measure_height()

    if self._rich:
      # Long formatted text: the full-size picker shell, scrolling text above the actions.
      card = rl.Rectangle(rect.x + margin_x, rect.y + margin_y, rect.width - margin_x * 2, rect.height - margin_y * 2)
      self._draw_card(card, fill=AS.SETTINGS_DIALOG_FILL, border=AS.SETTINGS_TILE_BORDER, radius_px=AS.SETTINGS_DIALOG_RADIUS)
      text_rect = rl.Rectangle(card.x + inset, card.y + inset, card.width - inset * 2,
                               card.height - inset * 2 - actions_h - AS.SETTINGS_TILE_GAP)
      html_rect = rl.Rectangle(text_rect.x, text_rect.y, text_rect.width, self._html_renderer.get_total_height(int(text_rect.width)))
      self._html_renderer.set_rect(html_rect)
      self._scroller.render(text_rect)
    else:
      # A short question or notice: a card sized to its message, centered on the screen.
      width = min(MAX_CARD_WIDTH, rect.width - margin_x * 2)
      font = gui_app.font(FontWeight.BOLD)
      line_h = MESSAGE_SIZE * FONT_SCALE + 6
      lines = _wrap(font, self._text, width - inset * 2, MESSAGE_SIZE, MESSAGE_MAX_LINES)
      text_h = len(lines) * line_h
      height = min(rect.height - margin_y * 2, inset * 2 + text_h + AS.SETTINGS_HEADER_GAP + actions_h)
      card = rl.Rectangle(rect.x + (rect.width - width) / 2, rect.y + (rect.height - height) / 2, width, height)
      self._draw_card(card, fill=AS.SETTINGS_DIALOG_FILL, border=AS.SETTINGS_TILE_BORDER, radius_px=AS.SETTINGS_DIALOG_RADIUS)
      y = card.y + inset
      for line in lines:
        line_w = measure_text_cached(font, line, MESSAGE_SIZE).x
        rl.draw_text_ex(font, line, rl.Vector2(card.x + (card.width - line_w) / 2, y), MESSAGE_SIZE, 0, AS.TEXT)
        y += line_h

    confirm_rect, cancel_rect = self._button_rects(card, inset)
    if cancel_rect is not None:
      self._cancel_button.render(cancel_rect)
    self._confirm_button.render(confirm_rect)
    if self._closed:
      return

    if rl.is_key_pressed(rl.KeyboardKey.KEY_ENTER):
      self._confirm_button_callback()
    elif rl.is_key_pressed(rl.KeyboardKey.KEY_ESCAPE):
      self._cancel_button_callback()


def alert_dialog(message: str, button_text: str | None = None):
  if button_text is None:
    button_text = tr("OK")
  return ConfirmDialog(message, button_text, cancel_text="")
