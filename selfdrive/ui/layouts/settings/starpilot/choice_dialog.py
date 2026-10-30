"""Shared scrolling choices below the common settings selection header."""
from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

import pyray as rl

from openpilot.system.ui.lib.application import gui_app, FontWeight, FONT_SCALE
from openpilot.system.ui.lib.multilang import tr
from openpilot.system.ui.lib.scroll_panel2 import GuiScrollPanel2
from openpilot.system.ui.widgets import DialogResult
from openpilot.system.ui.widgets.label import gui_label
from openpilot.selfdrive.ui.lib import aether_style as AS
from openpilot.selfdrive.ui.layouts.settings.starpilot.aethergrid import (
  AetherSelectionDialog, AetherScrollbar, aether_begin_scissor_mode, aether_end_scissor_mode,
  draw_settings_card, draw_list_scroll_fades, point_hits, snap_rect, wrap_text,
)


@dataclass(frozen=True)
class PreviewChoice:
  key: str
  label: str
  preview: Callable[[rl.Rectangle], None] | None = None
  close_preview: Callable[[], None] | None = None
  description: str = ""


class AetherChoiceDialog(AetherSelectionDialog):
  """Select locally, then apply once; scrolling never commits a choice."""

  def __init__(self, title: str, options: list[PreviewChoice], current: str = "", *, subtitle: str = "",
               callback: Callable[[DialogResult], None] | None = None, layout: Literal["grid", "list"] = "grid",
               option_font_weight: FontWeight = FontWeight.SEMI_BOLD):
    super().__init__(title, subtitle, callback)
    self.options = options
    self.current = current
    self.selection = current if any(option.key == current for option in options) else ""
    self._layout_mode = layout
    self._option_font_weight = option_font_weight
    self._released = False
    self._initial_scroll = True
    self._scroll_panel = GuiScrollPanel2(horizontal=False)
    self._scrollbar = AetherScrollbar(track_inset_x=-16)
    self._scroll_rect = rl.Rectangle()
    self._content_height = 0.0
    self._option_rects: dict[str, rl.Rectangle] = {}
    self._pressed_choice: str | None = None

  def _can_apply(self) -> bool:
    return any(option.key == self.selection for option in self.options)

  def _choice_selected(self, key: str) -> bool:
    return key == self.selection

  def _select_choice(self, key: str):
    self.selection = key

  def _release_previews(self):
    if not self._released:
      self._released = True
      for option in self.options:
        if option.close_preview is not None:
          option.close_preview()

  def hide_event(self):
    self._release_previews()
    super().hide_event()

  def _before_close(self):
    self._release_previews()

  def _target_at(self, point):
    return next((key for key, bounds in self._option_rects.items()
                 if point_hits(point, bounds, self._scroll_rect, pad_x=0, pad_y=0)), None)

  def _handle_mouse_press(self, point):
    self._pressed_choice = self._target_at(point) if not self._closed and self._scroll_panel.is_touch_valid() else None

  def _handle_mouse_event(self, event):
    if not self._scroll_panel.is_touch_valid() or self._target_at(event.pos) != self._pressed_choice:
      self._pressed_choice = None

  def _handle_mouse_release(self, point):
    pressed, self._pressed_choice = self._pressed_choice, None
    if not self._closed and pressed is not None and self._scroll_panel.is_touch_valid() and self._target_at(point) == pressed:
      self._select_choice(pressed)

  def _draw_choice(self, rect: rl.Rectangle, choice: PreviewChoice):
    selected = self._choice_selected(choice.key)
    fill = AS.ACCENT_TINT if selected else AS.SETTINGS_CHOICE_FILL
    border = AS.ACCENT if selected else AS.SETTINGS_TILE_BORDER
    if self._pressed_choice == choice.key:
      border = AS.SETTINGS_CARD_BORDER_PRESSED
    draw_settings_card(rect, fill=fill, border=border, radius_px=AS.SETTINGS_TILE_RADIUS)
    inset, gap, mark_size = AS.SETTINGS_CARD_INSET, 32, 48
    text_x = rect.x + inset
    if self._layout_mode == "grid":
      preview = snap_rect(rl.Rectangle(text_x, rect.y + (rect.height - AS.SETTINGS_CHOICE_PREVIEW_HEIGHT) / 2,
                                      AS.SETTINGS_CHOICE_PREVIEW_WIDTH, AS.SETTINGS_CHOICE_PREVIEW_HEIGHT))
      draw_settings_card(preview, fill=AS.SETTINGS_BG, border=AS.SETTINGS_TILE_BORDER, radius_px=24)
      if choice.preview is not None:
        choice.preview(rl.Rectangle(preview.x + 16, preview.y + 16, preview.width - 32, preview.height - 32))
      else:
        center = rl.Vector2(preview.x + preview.width / 2, preview.y + preview.height / 2)
        rl.draw_line_ex(rl.Vector2(center.x - 24, center.y), rl.Vector2(center.x + 24, center.y), 7, AS.TEXT_DISABLED)
      text_x = preview.x + preview.width + gap
    reserve_mark = selected or self._layout_mode == "list"
    text_width = max(1.0, rect.x + rect.width - inset - text_x - (mark_size + 12 if reserve_mark else 0))
    font_size = 40
    lines = wrap_text(gui_app.font(self._option_font_weight), choice.label, text_width, font_size, max_lines=2, spacing=0)
    descriptions = wrap_text(gui_app.font(FontWeight.NORMAL), choice.description, text_width, 28, max_lines=2, spacing=0) if choice.description else []
    line_height = max(48.0, font_size * FONT_SCALE)
    description_height = max(36.0, 28 * FONT_SCALE)
    block_height = len(lines) * line_height + (AS.SETTINGS_TEXT_GAP + len(descriptions) * description_height if descriptions else 0)
    text_y = rect.y + (rect.height - block_height) / 2
    for line in lines:
      gui_label(rl.Rectangle(text_x, text_y, text_width, line_height), line, font_size, AS.TEXT, self._option_font_weight)
      text_y += line_height
    text_y += AS.SETTINGS_TEXT_GAP
    for line in descriptions:
      gui_label(rl.Rectangle(text_x, text_y, text_width, description_height), line, 28, AS.TEXT_SECONDARY)
      text_y += description_height
    if selected:
      center = rl.Vector2(rect.x + rect.width - inset - mark_size / 2, rect.y + rect.height / 2)
      rl.draw_circle_v(center, mark_size / 2, AS.ACCENT_SOLID)
      rl.draw_line_ex(rl.Vector2(center.x - 10, center.y), rl.Vector2(center.x - 2, center.y + 8), 6, AS.TEXT)
      rl.draw_line_ex(rl.Vector2(center.x - 2, center.y + 8), rl.Vector2(center.x + 12, center.y - 9), 6, AS.TEXT)

  def _render_content(self, rect: rl.Rectangle):
    self._scroll_rect = rect
    gap = AS.SETTINGS_TILE_GAP if self._layout_mode == "grid" else AS.SETTINGS_ROW_GAP
    columns = min(3, max(1, int((rect.width + gap) / (440 + gap)))) if self._layout_mode == "grid" else 1
    card_width = (rect.width - gap * (columns - 1)) / columns
    card_height = min(AS.SETTINGS_CHOICE_CARD_HEIGHT, max(184.0, (rect.height - gap * 2) / 3)) if self._layout_mode == "grid" else AS.SETTINGS_ROW_CARD_HEIGHT
    rows = math.ceil(len(self.options) / columns)
    self._content_height = rows * card_height + max(0, rows - 1) * gap
    if self._initial_scroll:
      self._initial_scroll = False
      index = next((i for i, choice in enumerate(self.options) if self._choice_selected(choice.key)), 0)
      selected_y = (index // columns) * (card_height + gap)
      if selected_y + card_height > rect.height:
        self._scroll_panel.set_offset(max(rect.height - self._content_height, -selected_y))
    offset = self._scroll_panel.update(rect, max(self._content_height, rect.height))
    self._option_rects.clear()
    aether_begin_scissor_mode(int(rect.x), int(rect.y), int(rect.width), int(rect.height))
    for index, choice in enumerate(self.options):
      row, column = divmod(index, columns)
      bounds = snap_rect(rl.Rectangle(rect.x + column * (card_width + gap), rect.y + offset + row * (card_height + gap), card_width, card_height))
      self._option_rects[choice.key] = bounds
      if bounds.y + bounds.height >= rect.y and bounds.y <= rect.y + rect.height:
        self._draw_choice(bounds, choice)
    aether_end_scissor_mode()
    self._scrollbar.render(rect, self._content_height, offset)
    draw_list_scroll_fades(rect, self._content_height, offset, AS.SETTINGS_DIALOG_FILL)


class AetherMultiSelectDialog(AetherChoiceDialog):
  """The same scrolling choices, allowing several selections or an empty set."""

  def __init__(self, title: str, options: dict[str, str], current_values: list[str], on_close: Callable, *, subtitle: str = ""):
    super().__init__(title, [PreviewChoice(key, tr(label)) for key, label in options.items()],
                     subtitle=subtitle or tr("Choose any options to include, then tap Apply."), layout="list")
    self._selected = set(current_values) & options.keys()
    self._user_callback = on_close

  def _can_apply(self) -> bool:
    return True

  def _choice_selected(self, key: str) -> bool:
    return key in self._selected

  def _select_choice(self, key: str):
    if key in self._selected:
      self._selected.remove(key)
    else:
      self._selected.add(key)

  def _on_result(self, result: DialogResult):
    self._user_callback(result, [choice.key for choice in self.options if choice.key in self._selected])
