"""Where to? (design/destinations.html), its search (navsearch.html) and the route preview (routepreview.html).

StarPilot's navigation controller (StarPilotNavigationLayout) still does the work: Mapbox search and resolving a result,
favorites with Home and Work, recent places, starting and ending a route. UpstreamPlaces reaches into it; this module
only draws. One full-screen widget moves between three views: the list, search (with the Essentials keyboard built
in), and the preview of a picked place.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, Protocol

import pyray as rl

from openpilot.system.ui.widgets import Widget
from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.base import Component
from openpilot.selfdrive.ui.tandem.blocks import Icon
from openpilot.selfdrive.ui.tandem.controls import Button, ButtonStyle, back_glyph
from openpilot.selfdrive.ui.tandem.keyboard import KeyPad
from openpilot.selfdrive.ui.tandem.layout import FILL, Align, column, inset, place, row
from openpilot.selfdrive.ui.tandem.rows import ListPanel, SectionHeader, SettingRow, Text

SEARCH_PAUSE = 0.6          # seconds after the last key before searching as you type
MIN_QUERY = 3               # StarPilot's minimum
FIELD_FILL = T._hex("1A1D22")
ROW = T.px(58)              # the list's rows, as in the mock


def place_name(place: dict[str, Any] | None) -> str:
  return str((place or {}).get("name") or (place or {}).get("place_name") or "")


def place_line(place: dict[str, Any] | None) -> str:
  """A second line for a place: its address, without the name when the full place name starts with it."""
  name, full = place_name(place), str((place or {}).get("place_name") or "")
  if not full or full == name:
    return ""
  return full[len(name) + 2:] if full.startswith(name + ", ") else full


class Places(Protocol):
  """What the screens need from StarPilot's navigation. UpstreamPlaces is the real one."""

  def tick(self) -> None: ...
  def refresh(self) -> None: ...
  def active(self) -> dict | None: ...
  def favorites(self) -> list[dict]: ...           # ordered: Home, Work, then by name
  def recents(self) -> list[dict]: ...
  def is_favorite(self, place: dict) -> bool: ...
  def toggle_saved(self, place: dict) -> None: ...  # a recent's star
  def search(self, query: str) -> None: ...
  def results(self) -> list[tuple[str, str]]: ...   # (name, address)
  def status(self) -> tuple[str, str] | None: ...   # searching, an error, or nothing found
  def pick_result(self, index: int) -> None: ...    # may resolve in the background; draft() fills in
  def pick(self, place: dict) -> None: ...
  def draft(self) -> dict | None: ...
  def clear_draft(self) -> None: ...
  def saved_as(self) -> tuple[bool, bool, bool]: ...   # the draft: favorite, home, work
  def toggle(self, kind: str) -> None: ...             # "favorite", "home" or "work"
  def can_start(self) -> bool: ...
  def start(self) -> bool: ...
  def end_route(self) -> None: ...
  def maps_ready(self) -> bool: ...


class UpstreamPlaces:
  """Places backed by StarPilot's navigation controller."""

  def __init__(self):
    from openpilot.selfdrive.ui.layouts.settings.starpilot.navigation import StarPilotNavigationLayout
    self._nav = StarPilotNavigationLayout()

  def tick(self) -> None:
    self._nav._update_state()   # takes finished searches and refreshes favorites and recents

  def refresh(self) -> None:
    self._nav.show_event()

  def active(self):
    return self._nav._active_destination

  def favorites(self):
    from openpilot.starpilot.navigation.destination_store import ordered_favorite_destinations
    return ordered_favorite_destinations(self._nav._favorites)

  def recents(self):
    return list(self._nav._recent_destinations)

  def is_favorite(self, place) -> bool:
    return self._nav._favorite_for_destination(place) is not None

  def toggle_saved(self, place) -> None:
    favorite = self._nav._favorite_for_destination(place)
    if favorite is not None:
      self._nav._store.remove_favorite(favorite)
      self._nav._refresh_navigation_state(force=True)
      return
    self._nav._select_destination(place)
    self._nav._ensure_favorite()
    self.clear_draft()

  def search(self, query: str) -> None:
    self._nav._start_search(query)

  def results(self):
    return [(r.name, r.subtitle) for r in self._nav._search_results]

  def status(self):
    nav = self._nav
    if nav._search_loading:
      return "Searching…", "Looking up places"
    if nav._search_error:
      return "Search unavailable", nav._search_error
    if nav._query and not nav._search_results:
      return "Nothing found", "Try a different place or address"
    return None

  def pick_result(self, index: int) -> None:
    results = self._nav._search_results
    if 0 <= index < len(results):
      self._nav._select_search_result(results[index])

  def pick(self, place) -> None:
    favorite = self._nav._favorite_for_destination(place)
    self._nav._select_destination(place, favorite)

  def draft(self):
    return self._nav._draft_destination

  def clear_draft(self) -> None:
    self._nav._draft_destination = None
    self._nav._selected_favorite = None

  def saved_as(self):
    nav = self._nav
    favorite = nav._selected_favorite or (nav._favorite_for_destination(nav._draft_destination) if nav._draft_destination else None)
    if favorite is None:
      return False, False, False
    return True, bool(favorite.get("is_home")), bool(favorite.get("is_work"))

  def toggle(self, kind: str) -> None:
    if kind == "favorite":
      self._nav._toggle_favorite()
    else:
      self._nav._toggle_special("is_home" if kind == "home" else "is_work")

  def can_start(self) -> bool:
    return self._nav._routing_available()

  def start(self) -> bool:
    self._nav._start_navigation()
    return self._nav._draft_destination is None and self._nav._active_destination is not None

  def end_route(self) -> None:
    self._nav._cancel_navigation()

  def maps_ready(self) -> bool:
    try:
      from openpilot.common.params import Params
      from openpilot.starpilot.common.maps_download_progress import MAPS_STORAGE_CACHE_PARAM, load_maps_storage_cache
      return bool(load_maps_storage_cache(Params().get(MAPS_STORAGE_CACHE_PARAM, encoding="utf-8") or "").maps_present)
    except Exception:
      return False


# ── Pieces ──

def nav_button(on_click: Callable[[], None], size: float = T.NAV_BUTTON, radius: float = T.RADIUS_CARD) -> Button:
  return Button(on_click=on_click, style=ButtonStyle.NAV, height=size, width=size, radius=radius, glyph=back_glyph)


def icon_button(name: str, on_click: Callable[[], None], color: Callable[[], rl.Color]) -> Button:
  return Button(on_click=on_click, style=ButtonStyle.GHOST, height=T.px(48), width=T.px(48), radius=T.px(12),
                glyph=lambda r, c, s: draw.icon(r, name, color(), T.px(22)))


class Footer(Component):
  """The bottom bar: back, a line of explanation, and an action on the right (as in destinations.html)."""
  grow_touch_target = False

  def __init__(self, on_back: Callable[[], None], note: Callable[[], str], action: Widget | None = None):
    super().__init__()
    self._back = self._child(nav_button(on_back))
    self._note = note
    self._action = self._child(action) if action is not None else None

  def _render(self, rect: rl.Rectangle):
    draw.fill(rect, T.NAV_BAR)
    draw.hline(rect.x, rect.y, rect.width, T.NAV_BAR_EDGE)
    body = place(inset(rect, x=T.px(16)), rect.width - T.px(32), T.NAV_BUTTON)
    action_w = self._action.preferred_size(body.width)[0] if self._action is not None and self._action.is_visible else 0
    back, note, action = row(body, [T.NAV_BUTTON, FILL, action_w], T.px(10))
    self._back.render(back)
    draw.text(inset(note, left=T.px(10)), draw.fit(self._note(), T.font_px(16), T.FONT, note.width - T.px(10)), T.font_px(16),
              T.TEXT_MUTED)
    if self._action is not None and self._action.is_visible:
      self._action.render(action)


class Tile(Component):
  """Home, Work or Add favorite: an icon well, a title and a line. dashed draws the empty slot's outline."""
  grow_touch_target = False

  def __init__(self, icon: str, title: Callable[[], str], line: Callable[[], str], on_click: Callable[[], None],
               dashed: Callable[[], bool] = lambda: False):
    super().__init__()
    self._icon, self._title, self._line, self._dashed = icon, title, line, dashed
    self.set_click_callback(on_click)

  def _render(self, rect: rl.Rectangle):
    empty = self._dashed()
    if empty:
      draw.stroke(rect, T._hex("343B45"), T.px(20), T.px(1))
    else:
      draw.fill(rect, FIELD_FILL, T.px(20))
    if self.is_pressed:
      draw.pressed(rect, T.px(20))
    body = inset(rect, x=T.px(18))
    well, words = row(body, [T.px(52), FILL], T.px(14))
    well = place(well, T.px(52), T.px(52))
    draw.fill(well, FIELD_FILL if empty else T.ACCENT_SURFACE, T.px(14))
    draw.icon(well, self._icon, T.TEXT_TERTIARY if empty else T.ACCENT_TEXT, T.px(26))
    title_h, line_h = draw.line_height(T.font_px(20)), draw.line_height(T.font_px(14))
    block = place(words, words.width, title_h + T.px(3) + line_h)
    draw.text(rl.Rectangle(block.x, block.y, block.width, title_h), draw.fit(self._title(), T.font_px(20), T.FONT_BOLD, block.width),
              T.font_px(20), T.TEXT_SECONDARY if empty else T.TEXT, T.FONT_BOLD)
    draw.text(rl.Rectangle(block.x, block.y + title_h + T.px(3), block.width, line_h),
              draw.fit(self._line(), T.font_px(14), T.FONT, block.width), T.font_px(14), T.TEXT_MUTED if empty else T.TEXT_TERTIARY)


class SearchPill(Component):
  """A quiet search field that opens the keyboard: the list's entry, and the results view's field with its query."""
  grow_touch_target = False

  def __init__(self, on_click: Callable[[], None], text: Callable[[], str] = lambda: ""):
    super().__init__()
    self._text = text
    self.set_click_callback(on_click)

  def _render(self, rect: rl.Rectangle):
    draw.fill(rect, FIELD_FILL, T.px(16))
    draw.stroke(rect, T.TRACK, T.px(16), T.px(1))
    if self.is_pressed:
      draw.pressed(rect, T.px(16))
    icon, words = row(inset(rect, x=T.px(20)), [T.px(22), FILL], T.px(14))
    draw.icon(icon, "search", T.TEXT_TERTIARY, T.px(22))
    text = self._text()
    draw.text(words, draw.fit(text or "Search for a place or address", T.font_px(18), T.FONT, words.width), T.font_px(18),
              T.TEXT if text else T.TEXT_TERTIARY)


class ResultCard(Component):
  """A result while typing: a pin, the name and the address."""
  grow_touch_target = False

  def __init__(self, index: int, places: Places, on_pick: Callable[[int], None]):
    super().__init__()
    self._index, self._places = index, places
    self.set_click_callback(lambda: on_pick(index))

  def _render(self, rect: rl.Rectangle):
    results = self._places.results()
    if self._index >= len(results):
      return
    name, line = results[self._index]
    draw.fill(rect, T.SURFACE_2, T.px(14))
    if self.is_pressed:
      draw.pressed(rect, T.px(14))
    icon, words = row(inset(rect, x=T.px(16)), [T.px(20), FILL], T.px(12))
    draw.icon(icon, "pin", T.ACCENT_TEXT, T.px(20))
    title_h, line_h = draw.line_height(T.font_px(17)), draw.line_height(T.font_px(13))
    block = place(words, words.width, title_h + (line_h if line else 0))
    draw.text(rl.Rectangle(block.x, block.y, block.width, title_h), draw.fit(name, T.font_px(17), T.FONT_BOLD, block.width),
              T.font_px(17), T.TEXT, T.FONT_BOLD)
    if line:
      draw.text(rl.Rectangle(block.x, block.y + title_h, block.width, line_h), draw.fit(line, T.font_px(13), T.FONT, block.width),
                T.font_px(13), T.TEXT_TERTIARY)


class SaveToggle(Component):
  """Favorite, Home or Work in the preview: selected wears the accent edge and a check."""
  grow_touch_target = False

  def __init__(self, icon: str, label: str, idle: str, on: Callable[[], bool], on_click: Callable[[], None]):
    super().__init__()
    self._icon, self._label, self._idle, self._on = icon, label, idle, on
    self.set_click_callback(on_click)

  def _render(self, rect: rl.Rectangle):
    on = self._on()
    draw.fill(rect, T.ACCENT_SELECTED if on else FIELD_FILL, T.px(16))
    if on:
      draw.stroke(rect, T.ACCENT, T.px(16), T.px(2))
    if self.is_pressed:
      draw.pressed(rect, T.px(16))
    body = inset(rect, x=T.px(16))
    well, label, state = row(body, [T.px(42), FILL, T.px(170)], T.px(14))
    well = place(well, T.px(42), T.px(42))
    draw.fill(well, T.ACCENT_SURFACE, T.px(12))
    draw.icon(well, self._icon, T.ACCENT_TEXT, T.px(22))
    draw.text(label, self._label, T.font_px(18), T.TEXT, T.FONT_BOLD)
    if on:
      words = "Saved" if self._icon == "star" else f"Your {self._label}"
      width = draw.text_width(words, T.font_px(15), T.FONT_BOLD)
      check = rl.Rectangle(state.x + state.width - width - T.px(24), state.y, T.px(18), state.height)
      draw.icon(check, "check", T.ACCENT_TEXT, T.px(18))
      draw.text(state, words, T.font_px(15), T.ACCENT_TEXT, T.FONT_BOLD, Align.END)
    else:
      draw.text(state, self._idle, T.font_px(15), T.TEXT_MUTED, T.FONT, Align.END)


# ── The screen ──

LIST, SEARCH, RESULTS, PREVIEW = "list", "search", "results", "preview"


class DestinationsScreen(Component):
  """Full screen: the list, search, and the preview. on_close leaves (pops the screen); open_maps, when given, shows
  Offline Maps from the list's footer."""
  grow_touch_target = False

  def __init__(self, places: Places, on_close: Callable[[], None], open_maps: Callable[[], None] | None = None):
    super().__init__()
    self._places = places
    self._on_close = on_close
    self._view = LIST
    self._history: list[str] = []
    self._intent: str | None = None      # "home" or "work" when a tile is setting one
    self._awaiting = False               # a picked result is resolving
    self._typed, self._typed_at, self._searched = "", 0.0, ""
    self._keys = KeyPad(self._search_now, "Search", MIN_QUERY)

    # List
    self._search_pill = self._child(SearchPill(lambda: self._go(SEARCH)))
    self._tiles = [self._child(Tile("home", lambda: "Home" if self._special("is_home") else "Set Home",
                                    lambda: self._address("is_home") or "Search for your home address",
                                    lambda: self._open_special("is_home"), lambda: self._special("is_home") is None)),
                   self._child(Tile("work", lambda: "Work" if self._special("is_work") else "Set Work",
                                    lambda: self._address("is_work") or "Search for your work address",
                                    lambda: self._open_special("is_work"), lambda: self._special("is_work") is None)),
                   self._child(Tile("plus", lambda: "Add favorite", lambda: "Search for a place", lambda: self._go(SEARCH),
                                    lambda: True))]
    maps = Button("Offline maps", open_maps or (lambda: None), ButtonStyle.NAV, height=T.NAV_BUTTON, font_size=T.font_px(18),
                  radius=T.RADIUS_CARD, padding=T.px(26))
    maps.set_visible(open_maps is not None)
    self._list_footer = self._child(Footer(self._back, lambda: "Turns and speed follow the route automatically while navigating", maps))
    self._list_panel: ListPanel | None = None
    self._list_key: object = None

    # Search
    self._search_back = self._child(nav_button(self._back, T.px(56), T.px(14)))
    self._clear = self._child(Button(on_click=lambda: self._keys.set_text(""), style=ButtonStyle.SECONDARY, height=T.px(36),
                                     width=T.px(36), radius=T.px(18), glyph=lambda r, c, s: draw.icon(r, "close", T.TEXT_SECONDARY, T.px(16))))
    self._cards = [self._child(ResultCard(i, places, self._pick_result)) for i in range(2)]
    self._results_back = self._child(nav_button(self._back, T.px(56), T.px(14)))
    self._results_field = self._child(SearchPill(self._reopen_keyboard, lambda: self._searched))
    self._results_panel: ListPanel | None = None
    self._results_key: object = None

    # Preview
    start = Button("Start", self._start, ButtonStyle.PRIMARY, height=T.NAV_BUTTON, width=T.px(260), font_size=T.font_px(20),
                   radius=T.RADIUS_CARD, weight=T.FONT_EXTRABOLD)
    start.set_enabled(places.can_start)
    self._preview_footer = self._child(Footer(self._back, lambda: "Routes come from Mapbox and need a connection to start"
                                              if places.can_start() else "Routing isn't set up on this device", start))
    flags = places.saved_as
    self._toggles = [self._child(SaveToggle("star", "Favorite", "Save", lambda: flags()[0], lambda: places.toggle("favorite"))),
                     self._child(SaveToggle("home", "Home", "Set as Home", lambda: flags()[1], lambda: places.toggle("home"))),
                     self._child(SaveToggle("work", "Work", "Set as Work", lambda: flags()[2], lambda: places.toggle("work")))]

  # Navigation between views

  def show_event(self):
    super().show_event()
    self._places.refresh()

  def _go(self, view: str) -> None:
    if view == SEARCH:
      self._keys.set_text(self._searched if self._view == RESULTS else "")
    self._history.append(self._view)
    self._view = view

  def _back(self) -> None:
    if self._view == PREVIEW:
      self._places.clear_draft()
    if not self._history:
      self._on_close()
      return
    self._view = self._history.pop()
    if self._view == LIST:
      self._intent = None

  def _address(self, key: str) -> str:
    favorite = self._special(key)
    return (place_line(favorite) or str(favorite.get("place_name") or "")) if favorite else ""

  def _special(self, key: str) -> dict | None:
    return next((f for f in self._places.favorites() if f.get(key)), None)

  def _open_special(self, key: str) -> None:
    favorite = self._special(key)
    if favorite is not None:
      self._places.pick(favorite)
      self._go(PREVIEW)
    else:
      self._intent = "home" if key == "is_home" else "work"
      self._go(SEARCH)

  def _pick(self, place: dict) -> None:
    self._places.pick(place)
    self._go(PREVIEW)

  def _pick_result(self, index: int) -> None:
    self._places.pick_result(index)
    self._awaiting = True

  def _search_now(self) -> None:
    """The Search key: search what's typed and show every result without the keyboard."""
    text = self._keys.text.strip()
    if len(text) < MIN_QUERY:
      return
    if text != self._searched:
      self._places.search(text)
      self._searched = text
    self._go(RESULTS)

  def _reopen_keyboard(self) -> None:
    self._keys.set_text(self._searched)
    self._typed = self._searched
    self._view = SEARCH

  def _start(self) -> None:
    if self._places.start():
      self._on_close()

  def _update_state(self):
    self._places.tick()
    if self._view == SEARCH:
      text = self._keys.text.strip()
      now = time.monotonic()
      if text != self._typed:
        self._typed, self._typed_at = text, now
      elif len(text) >= MIN_QUERY and text != self._searched and now - self._typed_at > SEARCH_PAUSE:
        self._places.search(text)
        self._searched = text
    if self._awaiting and self._places.draft() is not None:
      self._awaiting = False
      if self._intent and not self._places.saved_as()[1 if self._intent == "home" else 2]:
        self._places.toggle(self._intent)       # the tile asked for this place to become Home or Work
      self._go(PREVIEW)

  # Drawing

  def _render(self, rect: rl.Rectangle):
    draw.fill(rect, T.BG)
    {LIST: self._render_list, SEARCH: self._render_search, RESULTS: self._render_results, PREVIEW: self._render_preview}[self._view](rect)

  def _render_list(self, rect: rl.Rectangle) -> None:
    body, footer = column(rect, [FILL, T.NAV_HEIGHT])
    self._list_footer.render(footer)
    body = inset(body, left=T.px(20), right=T.px(20), top=T.px(20), bottom=T.px(14))
    header, tiles, panel = column(body, [T.px(60), T.px(86), FILL], T.px(14))
    chip_w = T.px(200) if self._places.maps_ready() else 0
    title, pill, chip = row(header, [T.px(170), FILL, chip_w], T.px(14))
    draw.text(inset(title, left=T.px(6)), "Where to?", T.font_px(28), T.TEXT, T.FONT_EXTRABOLD)
    self._search_pill.render(pill)
    if chip_w:
      chip = place(chip, chip.width, T.px(44))
      draw.fill(chip, T.SUCCESS_CARD, T.px(12))
      icon, words = row(inset(chip, x=T.px(14)), [T.px(16), FILL], T.px(8))
      draw.icon(icon, "check", T.SUCCESS_TEXT, T.px(16))
      draw.text(words, "Offline maps ready", T.font_px(15), T.SUCCESS_TEXT, T.FONT_SEMIBOLD)
    for tile, cell in zip(self._tiles, row(tiles, [FILL, FILL, FILL], T.px(12)), strict=True):
      tile.render(cell)
    self._list().render(panel)

  def _list(self) -> ListPanel:
    """Favorites other than Home and Work, then recents; rebuilt when they change."""
    places = self._places
    active, favorites, recents = places.active(), places.favorites(), places.recents()
    others = [f for f in favorites if not f.get("is_home") and not f.get("is_work")]
    key = (place_name(active), tuple(place_name(f) for f in others), tuple(place_name(r) for r in recents),
           tuple(places.is_favorite(r) for r in recents))
    if self._list_panel is None or key != self._list_key:
      items: list[Widget] = []
      if active is not None:
        items += [SectionHeader("ON A ROUTE"),
                  SettingRow(f"To {place_name(active)}", place_line(active) or None,
                             Button("End route", places.end_route, ButtonStyle.DANGER_SOFT), leading=Icon("navigate"), height=ROW)]
      if others:
        items.append(SectionHeader("FAVORITES"))
        items += [SettingRow(place_name(f), place_line(f) or None, on_click=lambda f=f: self._pick(f), leading=Icon("star"),
                             chevron=False, height=ROW) for f in others]
      items.append(SectionHeader("RECENT"))
      if recents:
        items += [SettingRow(place_name(r), place_line(r) or None,
                             icon_button("star", lambda r=r: places.toggle_saved(r),
                                         lambda r=r: T.ACCENT_TEXT if places.is_favorite(r) else T.TEXT_TERTIARY),
                             on_click=lambda r=r: self._pick(r), leading=Icon("recent", color=T.TEXT_MUTED), chevron=False, height=ROW)
                  for r in recents]
      else:
        items.append(Text("Places you navigate to show up here."))
      self._list_panel = self._child(ListPanel(items, header_divider=False))
      self._list_key = key
    return self._list_panel

  def _render_field(self, rect: rl.Rectangle) -> None:
    """Search's field while typing: back, then the field with the accent edge, what's typed and a clear button."""
    back, field = row(rect, [T.px(56), FILL], T.px(10))
    self._search_back.render(back)
    draw.fill(field, FIELD_FILL, T.px(14))
    draw.stroke(field, T.ACCENT, T.px(14), T.px(2))
    icon, text, clear = row(inset(field, left=T.px(16), right=T.px(10)), [T.px(20), FILL, T.px(36)], T.px(12))
    draw.icon(icon, "search", T.TEXT_TERTIARY, T.px(20))
    self._keys.render_text(text)
    if self._keys.text:
      self._clear.render(place(clear, T.px(36), T.px(36)))

  def _render_search(self, rect: rl.Rectangle) -> None:
    top, keys = column(rect, [T.px(146), FILL])
    body = inset(top, left=T.px(16), right=T.px(16), top=T.px(14), bottom=T.px(10))
    field, strip = column(body, [T.px(56), FILL], T.px(8))
    self._render_field(field)
    status = self._places.status() if self._searched else None
    if status is not None or not self._places.results():
      title, line = status or ("Type a place or address", f"Results show as you type, from {MIN_QUERY} letters")
      draw.text(inset(strip, left=T.px(6)), f"{title} · {line}", T.font_px(15), T.TEXT_TERTIARY)
    else:
      for card, cell in zip(self._cards, row(strip, [FILL, FILL], T.px(10)), strict=True):
        card.render(cell)
    self._keys.render_keys(keys)

  def _render_results(self, rect: rl.Rectangle) -> None:
    """Every result after Search, without the keyboard; tapping the field brings it back."""
    body = inset(rect, left=T.px(16), right=T.px(16), top=T.px(14), bottom=T.px(14))
    field, panel = column(body, [T.px(56), FILL], T.px(12))
    back, pill = row(field, [T.px(56), FILL], T.px(10))
    self._results_back.render(back)
    self._results_field.render(pill)
    self._results().render(panel)

  def _results(self) -> ListPanel:
    results, status = self._places.results(), self._places.status()
    key = (tuple(results), status)
    if self._results_panel is None or key != self._results_key:
      items: list[Widget] = [Text(f"{status[0]} · {status[1]}")] if status else []
      items += [SettingRow(name, line or None, on_click=lambda i=i: self._pick_result(i), leading=Icon("pin"), chevron=False, height=ROW)
                for i, (name, line) in enumerate(results)]
      self._results_panel = self._child(ListPanel(items, header_divider=False))
      self._results_key = key
    return self._results_panel

  def _render_preview(self, rect: rl.Rectangle) -> None:
    body, footer = column(rect, [FILL, T.NAV_HEIGHT])
    self._preview_footer.render(footer)
    body = inset(body, left=T.px(20), right=T.px(20), top=T.px(20), bottom=T.px(14))
    left, right = row(body, [(body.width - T.px(14)) * 1.25 / 2.25, FILL], T.px(14))
    self._render_place(left)
    draw.fill(right, T.SURFACE_2, T.RADIUS_PANEL)
    inner = inset(right, x=T.px(22), y=T.px(20))
    caption, *toggles = column(inner, [draw.line_height(T.SIZE_CAPTION), T.px(66), T.px(66), T.px(66)], T.px(12))
    draw.caption(caption, "Save this place", T.ACCENT_TEXT)
    for toggle, cell in zip(self._toggles, toggles, strict=True):
      toggle.render(cell)

  def _render_place(self, rect: rl.Rectangle) -> None:
    draft = self._places.draft()
    draw.fill(rect, T.SURFACE_2, T.RADIUS_PANEL)
    inner = inset(rect, T.px(24))
    head, _, caption, *checks = column(inner, [T.px(60), FILL, draw.line_height(T.SIZE_CAPTION)] + [draw.line_height(T.font_px(16))] * 3,
                                       T.px(14))
    well, words = row(head, [T.px(60), FILL], T.px(16))
    draw.fill(well, T.ACCENT_SURFACE, T.px(16))
    draw.icon(well, "pin", T.ACCENT_TEXT, T.px(28))
    name, line = place_name(draft), place_line(draft)
    title_h, line_h = draw.line_height(T.font_px(30)), draw.line_height(T.font_px(16))
    block = place(words, words.width, title_h + (T.px(4) + line_h if line else 0))
    draw.text(rl.Rectangle(block.x, block.y, block.width, title_h), draw.fit(name, T.font_px(30), T.FONT_EXTRABOLD, block.width),
              T.font_px(30), T.TEXT, T.FONT_EXTRABOLD)
    if line:
      draw.text(rl.Rectangle(block.x, block.y + title_h + T.px(4), block.width, line_h), draw.fit(line, T.font_px(16), T.FONT, block.width),
                T.font_px(16), T.TEXT_TERTIARY)
    draw.caption(caption, "On the way")
    for cell, words in zip(checks, ("Slows ahead of turns on the route", "Uses route speed limits when signs are missing",
                                    "Arrival time and what's left show in the bar"), strict=True):
      icon, text = row(cell, [T.px(18), FILL], T.px(10))
      draw.icon(icon, "check", T.SUCCESS_BRIGHT, T.px(18))
      draw.text(text, words, T.font_px(16), T.TEXT_SECONDARY)


def destinations_screen(on_close: Callable[[], None], open_maps: Callable[[], None] | None = None,
                        places: Places | None = None) -> DestinationsScreen:
  return DestinationsScreen(places or UpstreamPlaces(), on_close, open_maps)
