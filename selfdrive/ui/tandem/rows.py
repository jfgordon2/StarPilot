"""Setting rows and the panels that stack them."""
from __future__ import annotations

from collections.abc import Callable

import pyray as rl

from openpilot.system.ui.lib.scroll_panel2 import GuiScrollPanel2
from openpilot.system.ui.widgets import Widget
from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.base import Bindable, Component, resolve, size_of
from openpilot.selfdrive.ui.tandem.layout import Align, column, inset, place


class Text(Component):
  """A wrapped block of text: notes, dialog bodies, footnotes."""
  grow_touch_target = False

  def __init__(self, value: Bindable[str], size: int = T.SIZE_SUBTITLE, color: rl.Color = T.TEXT_MUTED, weight=T.FONT,
               padding: tuple[float, float] = (T.PANEL_HEADER_INSET, T.px(12))):
    super().__init__()
    self._value = value
    self._size = size
    self._color = color
    self._weight = weight
    self._padding = padding

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    px, py = self._padding
    return max_width, draw.paragraph_height(resolve(self._value), self._size, self._weight, max_width - px * 2) + py * 2

  def _render(self, rect: rl.Rectangle):
    px, py = self._padding
    draw.paragraph(inset(rect, x=px, y=py), resolve(self._value), self._size, self._color, self._weight)


class SectionHeader(Component):
  """POWER USER, RECENT, MY DEVICES ..."""
  grow_touch_target = False

  def __init__(self, label: str, color: rl.Color = T.TEXT_MUTED, trailing: Widget | None = None, background: rl.Color | None = None):
    super().__init__()
    self._label = label
    self._color = color
    self._trailing = trailing
    self._background = background
    if trailing is not None:
      self._child(trailing)

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    return max_width, T.px(40)

  def _render(self, rect: rl.Rectangle):
    if self._background is not None:
      draw.fill(rect, self._background)
    body = inset(rect, left=T.PANEL_HEADER_INSET, right=T.px(16), top=T.px(12), bottom=T.px(4))
    draw.caption(body, self._label, self._color)
    if self._trailing is not None:
      w, h = size_of(self._trailing, body.width)
      self._trailing.render(place(body, w, h, Align.END))


class SettingRow(Component):
  """Title and optional subtitle on the left, an optional control on the right.

  With on_click the whole row is a button and shows a chevron. indent=True draws the
  nested style used for options that belong to the row above (e.g. Offset under Speed Limits).
  """
  grow_touch_target = False

  def __init__(self, title: Bindable[str], subtitle: Bindable[str | None] = None, control: Widget | None = None,
               on_click: Callable[[], None] | None = None, indent: bool = False, height: float | None = None,
               leading: Widget | None = None, subtitle_color: Bindable[rl.Color] = T.TEXT_TERTIARY, chevron: bool | None = None):
    super().__init__()
    self._title = title
    self._subtitle = subtitle
    self._control = control
    self._leading = leading
    self._indent = indent
    self._height = height
    self._subtitle_color = subtitle_color
    self._chevron = on_click is not None if chevron is None else chevron
    self.set_click_callback(on_click)
    for w in (control, leading):
      if w is not None:
        self._child(w)

  def set_enabled(self, enabled) -> None:
    super().set_enabled(enabled)
    for w in (self._control, self._leading):
      if w is not None:
        w.set_enabled(enabled)

  def set_touch_valid_callback(self, touch_callback) -> None:
    super().set_touch_valid_callback(touch_callback)
    for w in (self._control, self._leading):
      if w is not None:
        w.set_touch_valid_callback(touch_callback)

  def set_parent_rect(self, parent_rect: rl.Rectangle) -> None:
    super().set_parent_rect(parent_rect)
    for w in (self._control, self._leading):
      if w is not None:
        w.set_parent_rect(parent_rect)

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    default = T.SUB_ROW_HEIGHT if self._indent else T.ROW_HEIGHT
    return max_width, self._height or default

  def _render(self, rect: rl.Rectangle):
    if self._indent:
      draw.fill(rect, T.SURFACE_1)
    if self._click_callback and self.is_pressed and self.enabled:
      draw.pressed(rect)

    body = inset(rect, left=T.px(46) if self._indent else T.PANEL_HEADER_INSET, right=T.px(16))
    if self._chevron:
      size = T.px(16)
      draw.chevron(rl.Rectangle(body.x + body.width - size, body.y, size, body.height), T.TEXT_TERTIARY, size)
      body = inset(body, right=size + T.px(12))
    if self._control is not None and self._control.is_visible:
      w, h = size_of(self._control, body.width * 0.6)
      self._control.render(place(body, w, h, Align.END))
      body = inset(body, right=w + T.px(16))
    if self._leading is not None and self._leading.is_visible:
      w, h = size_of(self._leading, body.width)
      self._leading.render(place(body, w, h, Align.START))
      body = inset(body, left=w + T.px(14))

    dim = 1.0 if self.enabled else T.DISABLED_ALPHA
    title_size = T.font_px(17) if self._indent else T.SIZE_ROW_TITLE
    subtitle = resolve(self._subtitle)
    if not subtitle:
      draw.text(body, resolve(self._title), title_size, draw.alpha(T.TEXT, dim), T.FONT_SEMIBOLD)
      return
    gap = T.px(3)
    block = draw.line_height(title_size) + gap + draw.line_height(T.SIZE_SUBTITLE)
    top = place(body, body.width, block)
    title_rect, sub_rect = column(top, [draw.line_height(title_size), draw.line_height(T.SIZE_SUBTITLE)], gap)
    draw.text(title_rect, resolve(self._title), title_size, draw.alpha(T.TEXT, dim), T.FONT_SEMIBOLD)
    draw.text(sub_rect, subtitle, T.SIZE_SUBTITLE, draw.alpha(resolve(self._subtitle_color), dim))


class ListPanel(Component):
  """A rounded panel: optional header and banner, then items separated by dividers. Scrolls when items overflow.

  A footer (e.g. a ButtonRow) stays pinned at the bottom, above the footnote.
  """
  grow_touch_target = False

  def __init__(self, items: list[Widget], title: Bindable[str] | None = None, subtitle: Bindable[str] | None = None,
               header_control: Widget | None = None, banner: Widget | None = None, footnote: Bindable[str] | None = None,
               background: rl.Color = T.SURFACE_2, dividers: bool = True, footer: Widget | None = None):
    super().__init__()
    self._items = items
    self._title = title
    self._subtitle = subtitle
    self._header_control = header_control
    self._banner = banner
    self._footnote = Text(footnote) if footnote is not None else None
    self._footer = footer
    self._background = background
    self._dividers = dividers
    self._scroll = GuiScrollPanel2(horizontal=False)
    for w in [*items, header_control, banner, footer, self._footnote]:
      if w is not None:
        self._child(w)
        w.set_touch_valid_callback(self._scroll.is_touch_valid)

  @property
  def items(self) -> list[Widget]:
    return self._items

  def _header_height(self) -> float:
    if self._title is None:
      return 0
    height = draw.line_height(T.SIZE_PANEL_TITLE)
    if self._subtitle is not None:
      height += T.px(3) + draw.line_height(T.SIZE_SUBTITLE)
    return height + T.px(20)

  @staticmethod
  def _height_of(widget: Widget, width: float) -> float:
    return size_of(widget, width)[1]

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    visible = [w for w in self._items if w.is_visible]
    content = sum(self._height_of(w, max_width) for w in visible) + len(visible) * T.DIVIDER
    extra = self._header_height() + (self._height_of(self._banner, max_width) if self._banner else 0)
    extra += self._footnote.preferred_height(max_width) if self._footnote else 0
    extra += self._footer_height(max_width)
    return max_width, content + extra

  def _footer_height(self, width: float) -> float:
    if self._footer is None:
      return 0
    return self._height_of(self._footer, width - T.px(28)) + T.px(24)

  def _render(self, rect: rl.Rectangle):
    draw.fill(rect, self._background, T.RADIUS_PANEL)
    y = rect.y
    if self._title is not None:
      header = rl.Rectangle(rect.x, y, rect.width, self._header_height())
      body = inset(header, x=T.PANEL_HEADER_INSET, y=T.px(13))
      if self._header_control is not None:
        w, h = size_of(self._header_control, body.width / 2)
        self._header_control.render(place(body, w, h, Align.END))
        body = inset(body, right=w + T.px(14))
      if self._subtitle is not None:
        title_rect, sub_rect = column(body, [draw.line_height(T.SIZE_PANEL_TITLE), draw.line_height(T.SIZE_SUBTITLE)], T.px(3))
        draw.text(sub_rect, resolve(self._subtitle), T.SIZE_SUBTITLE, T.TEXT_TERTIARY)
      else:
        title_rect = body
      draw.text(title_rect, resolve(self._title), T.SIZE_PANEL_TITLE, T.TEXT, T.FONT_BOLD)
      y += header.height
      draw.hline(rect.x, y - T.DIVIDER, rect.width)
    if self._banner is not None:
      h = self._height_of(self._banner, rect.width)
      self._banner.render(rl.Rectangle(rect.x, y, rect.width, h))
      y += h

    footnote_h = self._footnote.preferred_height(rect.width) if self._footnote else 0
    footer_h = self._footer_height(rect.width)
    viewport = rl.Rectangle(rect.x, y, rect.width, rect.y + rect.height - y - footnote_h - footer_h)
    visible = [w for w in self._items if w.is_visible]
    heights = [self._height_of(w, rect.width) for w in visible]
    content = sum(heights) + T.DIVIDER * max(0, len(visible) - 1)
    offset = self._scroll.update(viewport, content) if content > viewport.height else 0.0

    rl.begin_scissor_mode(int(viewport.x), int(viewport.y), int(viewport.width), int(viewport.height))
    cy = viewport.y + offset
    for i, (w, h) in enumerate(zip(visible, heights, strict=True)):
      w.set_parent_rect(viewport)
      w.render(rl.Rectangle(viewport.x, cy, viewport.width, h))
      cy += h
      if self._dividers and i < len(visible) - 1:
        draw.hline(viewport.x, cy, viewport.width)
        cy += T.DIVIDER
    rl.end_scissor_mode()

    if self._footer is not None:
      footer = rl.Rectangle(rect.x, rect.y + rect.height - footnote_h - footer_h, rect.width, footer_h)
      self._footer.render(inset(footer, x=T.px(14), y=T.px(12)))
    if self._footnote is not None:
      self._footnote.render(rl.Rectangle(rect.x, rect.y + rect.height - footnote_h, rect.width, footnote_h))


class Banner(Component):
  """A tinted strip at the top of a panel, e.g. the Tuner Mode warning."""
  grow_touch_target = False

  def __init__(self, message: Bindable[str], background: rl.Color = T.WARNING_BANNER, color: rl.Color = T.WARNING_CHIP_TEXT):
    super().__init__()
    self._message = message
    self._background = background
    self._color = color

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    return max_width, T.px(52)

  def _render(self, rect: rl.Rectangle):
    draw.fill(rect, self._background)
    draw.text(inset(rect, x=T.PANEL_HEADER_INSET), resolve(self._message), T.font_px(15), self._color)
