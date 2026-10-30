from __future__ import annotations

import json
import math
import queue
import threading
import uuid
from dataclasses import dataclass, replace
from typing import Any
from urllib.parse import quote

import pyray as rl
import requests

from openpilot.common.params import Params
from openpilot.selfdrive.ui.lib import aether_style as AS
from openpilot.selfdrive.ui.layouts.settings.starpilot.aethergrid import (
  AETHER_LIST_METRICS,
  AetherListColors,
  PanelManagerView,
  DEFAULT_PANEL_STYLE,
  GROUP_OVERHEAD,
  SECTION_GAP,
  SETTINGS_ROW_VALUE_FONT_SIZE,
  build_settings_group_frame,
  draw_action_pill,
  draw_section_header,
  draw_settings_card_row,
  draw_settings_empty_state,
  draw_settings_group,
  draw_settings_group_heading,
  settings_empty_state_height,
  with_alpha,
)
from openpilot.selfdrive.ui.layouts.settings.starpilot.panel import FrameCachedParams, _SettingsPage
from openpilot.starpilot.navigation import destination_store as _destination_store
from openpilot.starpilot.navigation.destination_store import (
  NavigationDestinationStore,
  add_favorite_destination,
  favorite_destination_id,
  favorite_matches_target,
  favorite_payload_for_galaxy,
  load_favorite_destinations,
  normalize_destination_payload,
  normalize_favorite_destination,
  ordered_favorite_destinations,
  remove_favorite_destination,
  routing_configured,
  same_destination,
  update_favorite_destination,
)
from openpilot.system.ui.lib.application import gui_app
from openpilot.system.ui.lib.multilang import tr
from openpilot.system.ui.widgets import DialogResult
from openpilot.system.ui.widgets.confirm_dialog import ConfirmDialog
from openpilot.system.ui.widgets.keyboard import Keyboard


FAVORITE_DESTINATIONS_KEY = _destination_store.FAVORITE_DESTINATIONS_KEY
NAVIGATION_DESTINATION_KEY = _destination_store.NAVIGATION_DESTINATION_KEY
NAV_INSTRUCTION_COLLAPSED_KEY = _destination_store.NAV_INSTRUCTION_COLLAPSED_KEY
NAV_INSTRUCTION_STATE_KEY = _destination_store.NAV_INSTRUCTION_STATE_KEY
RECENT_DESTINATIONS_KEY = _destination_store.RECENT_DESTINATIONS_KEY

_NavigationParams = NavigationDestinationStore
_add_favorite_destination = add_favorite_destination
_favorite_destination_id = favorite_destination_id
_favorite_matches_target = favorite_matches_target
_favorite_payload_for_galaxy = favorite_payload_for_galaxy
_load_favorite_destinations = load_favorite_destinations
_normalize_favorite_payload = normalize_favorite_destination
_remove_favorite_destination = remove_favorite_destination
_update_favorite_destination = update_favorite_destination


class MapboxSearchError(RuntimeError):
  pass


@dataclass(frozen=True, slots=True)
class SearchResult:
  name: str
  subtitle: str = ""
  latitude: float | None = None
  longitude: float | None = None
  mapbox_id: str = ""
  route_id: str | None = None

  @property
  def has_coordinates(self) -> bool:
    return self.latitude is not None and self.longitude is not None

  def to_destination(self) -> dict[str, Any]:
    if not self.has_coordinates:
      raise ValueError("Search result has no coordinates")
    return {
      "name": self.name,
      "place_name": self.name,
      "latitude": self.latitude,
      "longitude": self.longitude,
    }


class MapboxSearchClient:
  SUGGEST_URL = "https://api.mapbox.com/search/searchbox/v1/suggest"
  RETRIEVE_URL = "https://api.mapbox.com/search/searchbox/v1/retrieve"

  def __init__(self, session: Any = requests, timeout: float = 5.0):
    self._session = session
    self._timeout = timeout

  @staticmethod
  def _coordinates(payload: dict[str, Any]) -> tuple[float | None, float | None]:
    geometry = payload.get("geometry") or {}
    coordinates = geometry.get("coordinates") if isinstance(geometry, dict) else None
    if isinstance(coordinates, (list, tuple)) and len(coordinates) >= 2:
      try:
        return float(coordinates[1]), float(coordinates[0])
      except (TypeError, ValueError):
        pass
    try:
      return float(payload["latitude"]), float(payload["longitude"])
    except (KeyError, TypeError, ValueError):
      return None, None

  @classmethod
  def _normalize_result(cls, payload: dict[str, Any]) -> SearchResult | None:
    properties = payload.get("properties") or {}
    if not isinstance(properties, dict):
      properties = {}
    name = str(
      payload.get("name") or
      properties.get("name") or
      payload.get("full_address") or
      properties.get("full_address") or
      payload.get("place_formatted") or
      properties.get("place_formatted") or
      ""
    ).strip()
    if not name:
      return None

    full_address = str(payload.get("full_address") or properties.get("full_address") or "").strip()
    place_formatted = str(payload.get("place_formatted") or properties.get("place_formatted") or "").strip()
    subtitle = place_formatted or full_address
    if subtitle.casefold() == name.casefold():
      subtitle = ""
    latitude, longitude = cls._coordinates(payload)
    return SearchResult(
      name=name,
      subtitle=subtitle,
      latitude=latitude,
      longitude=longitude,
      mapbox_id=str(payload.get("mapbox_id") or properties.get("mapbox_id") or ""),
      route_id=payload.get("routeId") or properties.get("routeId"),
    )

  def _get_json(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
    try:
      response = self._session.get(url, params=params, timeout=self._timeout)
      response.raise_for_status()
      payload = response.json()
    except (requests.RequestException, ValueError, TypeError, RuntimeError) as error:
      raise MapboxSearchError("Mapbox search request failed") from error
    if not isinstance(payload, dict):
      raise MapboxSearchError("Mapbox returned an invalid response")
    return payload

  def search(
    self,
    query: str,
    public_token: str,
    session_token: str,
    *,
    proximity: tuple[float, float] | None = None,
    language: str = "",
    limit: int = 4,
  ) -> list[SearchResult]:
    normalized_query = query.strip()
    if len(normalized_query) < 3 or not public_token:
      return []
    params: dict[str, Any] = {
      "access_token": public_token,
      "session_token": session_token,
      "q": normalized_query,
      "limit": max(1, min(limit, 10)),
    }
    if proximity is not None:
      params["proximity"] = f"{proximity[0]},{proximity[1]}"
    if language.strip():
      params["language"] = language.strip()
    payload = self._get_json(self.SUGGEST_URL, params)
    suggestions = payload.get("suggestions") or []
    if not isinstance(suggestions, list):
      return []
    return [
      result
      for item in suggestions
      if isinstance(item, dict) and (result := self._normalize_result(item)) is not None
    ]

  def resolve(self, result: SearchResult, public_token: str, session_token: str) -> SearchResult:
    if result.has_coordinates:
      return result
    if not result.mapbox_id or not public_token:
      raise MapboxSearchError("Search result has no location")
    payload = self._get_json(
      f"{self.RETRIEVE_URL}/{quote(result.mapbox_id, safe='')}",
      {"access_token": public_token, "session_token": session_token},
    )
    features = payload.get("features") or []
    if not isinstance(features, list) or not features:
      raise MapboxSearchError("Mapbox returned no location")
    feature = features[0]
    if not isinstance(feature, dict):
      raise MapboxSearchError("Mapbox returned an invalid location")
    resolved = self._normalize_result(feature)
    if resolved is None or not resolved.has_coordinates:
      raise MapboxSearchError("Mapbox returned no coordinates")
    return SearchResult(
      name=result.name or resolved.name,
      subtitle=result.subtitle or resolved.subtitle,
      latitude=resolved.latitude,
      longitude=resolved.longitude,
      mapbox_id=result.mapbox_id,
      route_id=result.route_id,
    )


PANEL_STYLE = DEFAULT_PANEL_STYLE
NAVIGATION_METRICS = replace(AETHER_LIST_METRICS, header_height=0)

NAV_ROW_HEIGHT = 160.0  # same grouped row as Map Data's regions and Driving Model's models
NAV_ACTION_COLUMNS = 3


class NavigationManagerView(PanelManagerView):
  METRICS = NAVIGATION_METRICS
  PANEL_STYLE = PANEL_STYLE

  def __init__(self, controller: StarPilotNavigationLayout):
    super().__init__()
    self._controller = controller

  def _draw_header(self, rect: rl.Rectangle):
    del rect

  def _measure_content_height(self, content_width: float) -> float:
    return self._controller._measure_navigation_content_height(content_width)

  def _draw_scroll_content(self, scroll_rect: rl.Rectangle, content_width: float):
    self._controller._draw_navigation_content(scroll_rect, content_width, self._scroll_offset, self)

  def _activate_target(self, target_id: str | None):
    self._controller._activate_navigation_target(target_id)


class StarPilotNavigationLayout(_SettingsPage):
  """On-device destination search and navigation management panel."""

  def __init__(self):
    super().__init__()
    self._params = FrameCachedParams()
    self._params_memory = Params(memory=True)
    self._store = _NavigationParams(self._params, self._params_memory)
    self._search_client = MapboxSearchClient()
    self._keyboard = Keyboard(min_text_size=3)

    self._pending: queue.Queue[tuple[str, int, Any]] = queue.Queue()
    self._search_generation = 0
    self._session_token = str(uuid.uuid4())
    self._last_state_refresh = -1.0

    self._query = ""
    self._search_results: list[SearchResult] = []
    self._search_loading = False
    self._search_error = ""
    self._active_destination: dict[str, Any] | None = None
    self._favorites: list[dict[str, Any]] = []
    self._recent_destinations: list[dict[str, Any]] = []
    self._draft_destination: dict[str, Any] | None = None
    self._selected_favorite: dict[str, Any] | None = None

    self._manager_view = NavigationManagerView(self)

  def show_event(self):
    self._session_token = str(uuid.uuid4())
    self._search_generation += 1
    self._query = ""
    self._search_results = []
    self._search_loading = False
    self._search_error = ""
    self._draft_destination = None
    self._selected_favorite = None
    self._refresh_navigation_state(force=True)
    super().show_event()

  def hide_event(self):
    self._search_generation += 1
    self._search_loading = False
    super().hide_event()

  def _update_state(self):
    self._consume_pending_results()
    now = rl.get_time()
    if self._last_state_refresh < 0 or now - self._last_state_refresh >= 0.5:
      self._refresh_navigation_state()

  def _refresh_navigation_state(self, force: bool = False):
    now = rl.get_time()
    if not force and self._last_state_refresh >= 0 and now - self._last_state_refresh < 0.5:
      return
    self._last_state_refresh = now
    self._active_destination = self._store.active_destination()
    self._favorites = self._store.favorite_destinations()
    self._recent_destinations = self._store.recent_destinations()

    if self._selected_favorite is not None:
      selected_id = self._selected_favorite.get("id")
      self._selected_favorite = next((fav for fav in self._favorites if fav.get("id") == selected_id), None)

  def _consume_pending_results(self):
    while True:
      try:
        kind, generation, payload = self._pending.get_nowait()
      except queue.Empty:
        return

      if generation != self._search_generation:
        continue

      self._search_loading = False
      if kind == "search":
        if isinstance(payload, Exception):
          self._search_results = []
          self._search_error = tr("Search is unavailable. Check your connection and try again.")
        else:
          self._search_results = payload
          self._search_error = ""
      elif kind == "resolve":
        if isinstance(payload, Exception):
          self._search_error = tr("Could not determine that location. Try another result.")
        elif isinstance(payload, SearchResult):
          self._select_search_result(payload)

  def _public_mapbox_key(self) -> str:
    return str(self._params.get("MapboxPublicKey", encoding="utf-8") or "").strip()

  def _routing_available(self) -> bool:
    return routing_configured(self._params)

  def _language_code(self) -> str:
    language = str(self._params.get("LanguageSetting", encoding="utf-8") or "").strip()
    if language.lower().startswith("main_"):
      language = language[5:]
    return language.replace("_", "-")

  def _last_position(self) -> tuple[float, float] | None:
    raw = self._params.get("LastGPSPosition", encoding="utf-8") or ""
    if isinstance(raw, str):
      try:
        raw = json.loads(raw)
      except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
      return None
    if "hasFix" in raw and str(raw["hasFix"]).strip().lower() in ("0", "false", "no", "off"):
      return None
    try:
      longitude = float(raw["longitude"])
      latitude = float(raw["latitude"])
    except (KeyError, TypeError, ValueError):
      return None
    if not math.isfinite(latitude) or not math.isfinite(longitude):
      return None
    return longitude, latitude

  def _open_search_keyboard(self):
    self._keyboard.reset(min_text_size=3)
    self._keyboard.set_title(tr("Search destination"), tr("Enter a place or address"))
    self._keyboard.set_text(self._query)
    self._keyboard.set_callback(self._on_search_keyboard_result)
    gui_app.push_widget(self._keyboard)

  def _on_search_keyboard_result(self, result: DialogResult):
    if result != DialogResult.CONFIRM:
      return
    self._start_search(self._keyboard.text)

  def _start_search(self, query: str):
    self._search_generation += 1
    self._query = query.strip()
    self._search_results = []
    self._search_error = ""
    self._draft_destination = None
    self._selected_favorite = None
    if len(self._query) < 3:
      self._search_error = tr("Enter at least 3 characters to search.")
      return

    public_key = self._public_mapbox_key()
    if not public_key:
      self._search_error = tr("Mapbox search is not configured on this device.")
      return

    generation = self._search_generation
    self._search_loading = True
    proximity = self._last_position()
    language = self._language_code()
    query = self._query

    def worker():
      try:
        results = self._search_client.search(
          query,
          public_key,
          self._session_token,
          proximity=proximity,
          language=language,
        )
        self._pending.put(("search", generation, results))
      except Exception as error:
        self._pending.put(("search", generation, error))

    threading.Thread(target=worker, daemon=True, name="navigation-search").start()

  def _select_search_result(self, result: SearchResult):
    if result.has_coordinates:
      self._select_destination(result.to_destination())
      return

    if not result.mapbox_id or not self._public_mapbox_key():
      self._search_error = tr("That result did not include a usable location.")
      return

    self._search_generation += 1
    generation = self._search_generation
    self._search_loading = True
    public_key = self._public_mapbox_key()

    def worker():
      try:
        resolved = self._search_client.resolve(result, public_key, self._session_token)
        self._pending.put(("resolve", generation, resolved))
      except Exception as error:
        self._pending.put(("resolve", generation, error))

    threading.Thread(target=worker, daemon=True, name="navigation-search-resolve").start()

  @staticmethod
  def _same_destination(left: dict[str, Any] | None, right: dict[str, Any] | None) -> bool:
    return same_destination(left, right)

  def _favorite_for_destination(self, destination: dict[str, Any] | None) -> dict[str, Any] | None:
    return next((favorite for favorite in self._favorites if self._same_destination(favorite, destination)), None)

  def _select_destination(self, payload: dict[str, Any], favorite: dict[str, Any] | None = None):
    destination = normalize_destination_payload(payload)
    if destination is None:
      self._search_error = tr("That destination is missing a valid location.")
      return
    if payload.get("routeId"):
      destination["routeId"] = payload["routeId"]
    self._draft_destination = destination
    self._selected_favorite = favorite or self._favorite_for_destination(destination)
    self._search_error = ""

  def _ensure_favorite(self) -> dict[str, Any] | None:
    if self._draft_destination is None:
      return None
    favorite = self._selected_favorite or self._favorite_for_destination(self._draft_destination)
    if favorite is None:
      self._store.add_favorite(_favorite_payload_for_galaxy(self._draft_destination))
      self._refresh_navigation_state(force=True)
      favorite = self._favorite_for_destination(self._draft_destination)
    self._selected_favorite = favorite
    return favorite

  def _toggle_favorite(self):
    if self._draft_destination is None:
      return
    favorite = self._selected_favorite or self._favorite_for_destination(self._draft_destination)
    if favorite is None:
      self._ensure_favorite()
    else:
      self._store.remove_favorite(favorite)
      self._selected_favorite = None
      self._refresh_navigation_state(force=True)

  def _toggle_special(self, key: str):
    favorite = self._ensure_favorite()
    if favorite is None:
      return
    self._store.update_favorite(favorite, **{key: not bool(favorite.get(key))})
    self._refresh_navigation_state(force=True)

  def _open_rename_keyboard(self):
    favorite = self._selected_favorite
    if favorite is None:
      return
    favorite_id = favorite.get("id")
    self._keyboard.reset(min_text_size=1)
    self._keyboard.set_title(tr("Rename favorite"), tr("Choose a short name"))
    self._keyboard.set_text(str(favorite.get("name") or ""))

    def on_result(result: DialogResult):
      if result == DialogResult.CONFIRM and self._keyboard.text.strip():
        target = next((item for item in self._favorites if item.get("id") == favorite_id), None)
        if target is not None:
          self._store.update_favorite(target, name=self._keyboard.text.strip())
          self._refresh_navigation_state(force=True)

    self._keyboard.set_callback(on_result)
    gui_app.push_widget(self._keyboard)

  def _remove_favorite(self):
    favorite = self._selected_favorite
    if favorite is None:
      return

    def on_result(result: DialogResult):
      if result == DialogResult.CONFIRM:
        self._store.remove_favorite(favorite)
        self._selected_favorite = None
        self._refresh_navigation_state(force=True)

    gui_app.push_widget(
      ConfirmDialog(
        tr("Remove {} from favorites?").format(favorite.get("name") or tr("this destination")),
        tr("Remove"),
        callback=on_result,
      )
    )

  def _start_navigation(self):
    if self._draft_destination is None or not self._routing_available():
      return
    if self._store.set_destination(self._draft_destination) is None:
      self._search_error = tr("That destination is not valid.")
      return
    self._draft_destination = None
    self._selected_favorite = None
    self._refresh_navigation_state(force=True)

  def _cancel_navigation(self):
    self._store.clear_navigation()
    self._draft_destination = None
    self._selected_favorite = None
    self._refresh_navigation_state(force=True)

  def _activate_navigation_target(self, target_id: str | None):
    if not target_id:
      return
    if target_id == "action:search":
      self._open_search_keyboard()
    elif target_id == "action:start":
      self._start_navigation()
    elif target_id == "action:cancel":
      self._cancel_navigation()
    elif target_id == "action:favorite":
      self._toggle_favorite()
    elif target_id == "action:home":
      self._toggle_special("is_home")
    elif target_id == "action:work":
      self._toggle_special("is_work")
    elif target_id == "action:rename":
      self._open_rename_keyboard()
    elif target_id == "action:remove":
      self._remove_favorite()
    elif target_id.startswith("result:"):
      try:
        result = self._search_results[int(target_id.split(":", 1)[1])]
      except (IndexError, ValueError):
        return
      self._select_search_result(result)
    elif target_id.startswith("favorite:"):
      favorite_id = target_id.split(":", 1)[1]
      favorite = next((item for item in self._favorites if str(item.get("id")) == favorite_id), None)
      if favorite is None:
        return
      self._select_destination(favorite, favorite)
    elif target_id.startswith("recent:"):
      try:
        recent = self._recent_destinations[int(target_id.split(":", 1)[1])]
      except (IndexError, ValueError):
        return
      if normalize_destination_payload(recent) is None:
        self._start_search(str(recent.get("place_name") or recent.get("name") or ""))
      else:
        self._select_destination(recent)

  def _action_definitions(self) -> list[tuple[str, str, bool, bool]]:
    if self._draft_destination is None:
      return []
    favorite = self._selected_favorite or self._favorite_for_destination(self._draft_destination)
    definitions = [
      ("action:favorite", tr("Unfavorite" if favorite else "Favorite"), True, False),
      ("action:home", tr("Unset Home" if favorite and favorite.get("is_home") else "Set Home"), True, False),
      ("action:work", tr("Unset Work" if favorite and favorite.get("is_work") else "Set Work"), True, False),
    ]
    if favorite:
      definitions.extend([
        ("action:rename", tr("Rename"), True, False),
        ("action:remove", tr("Remove"), True, True),
      ])
    return definitions

  def _action_buttons_height(self) -> float:
    count = len(self._action_definitions())
    rows = (count + NAV_ACTION_COLUMNS - 1) // NAV_ACTION_COLUMNS
    return rows * AS.MIN_TOUCH + max(0, rows - 1) * AS.SETTINGS_TILE_GAP

  def _draw_action_buttons(self, rect: rl.Rectangle, manager: NavigationManagerView) -> None:
    """Favorite / Home / Work / Rename / Remove as the shared 112 px pills, three to a row."""
    gap = AS.SETTINGS_TILE_GAP
    button_width = (rect.width - gap * (NAV_ACTION_COLUMNS - 1)) / NAV_ACTION_COLUMNS
    for index, (target_id, label, enabled, danger) in enumerate(self._action_definitions()):
      row, column = divmod(index, NAV_ACTION_COLUMNS)
      button = rl.Rectangle(rect.x + column * (button_width + gap), rect.y + row * (AS.MIN_TOUCH + gap), button_width, AS.MIN_TOUCH)
      hovered, pressed = manager._interactive_state(target_id, button)
      if danger:
        fill, border = AetherListColors.DANGER_SOFT, with_alpha(AetherListColors.DANGER, 140)
      else:
        fill, border = (with_alpha(AS.ACCENT, 110) if pressed else AS.ACCENT_TINT), AS.ACCENT_EDGE
      if not enabled:
        fill, border = with_alpha(AS.TRACK_OFF, 120), AS.SETTINGS_TILE_BORDER
      draw_action_pill(button, label, fill, border, AS.TEXT if enabled else AS.TEXT_DISABLED,
                       font_size=SETTINGS_ROW_VALUE_FONT_SIZE)

  def _draw_destination_row(self, rect: rl.Rectangle, manager: NavigationManagerView) -> None:
    if self._draft_destination is not None:
      title = tr("Ready to navigate")
      subtitle = str(self._draft_destination.get("place_name") or self._draft_destination.get("name") or "")
      enabled = self._routing_available()
      action_text = tr("Start") if enabled else tr("Unavailable")
      target_id, tone, current = "action:start", AetherListColors.SUCCESS, False
    else:
      title = tr("Navigation active")
      subtitle = str(self._active_destination.get("place_name") or self._active_destination.get("name") or "")
      enabled, action_text = True, tr("Cancel")
      target_id, tone, current = "action:cancel", AetherListColors.DANGER, True
    hovered, pressed = manager._interactive_state(target_id, rect)
    draw_settings_card_row(
      rect, title=title, subtitle=subtitle, action_text=action_text, hovered=hovered and enabled, pressed=pressed and enabled,
      current=current, grouped=True, is_last=True, style=PANEL_STYLE,
      action_text_size=SETTINGS_ROW_VALUE_FONT_SIZE, action_height=AS.VALUE_PILL_HEIGHT,
      action_fill=with_alpha(tone, 60 if enabled else 16), action_border=with_alpha(tone, 170 if enabled else 50),
      action_text_color=AS.TEXT if enabled else AS.TEXT_DISABLED,
    )

  def _destination_rows(self) -> list[tuple[str, list[tuple[str, str, str, bool]]]]:
    """(heading, rows) for results, favorites and recents; each row is (target, title, subtitle, current)."""
    groups = []
    if self._search_results:
      groups.append((tr("Search results"), [
        (f"result:{index}", result.name, result.subtitle or tr("Destination"),
         self._same_destination(self._draft_destination, result.to_destination()) if result.has_coordinates else False)
        for index, result in enumerate(self._search_results)
      ]))
    if self._favorites:
      rows = []
      for index, favorite in enumerate(ordered_favorite_destinations(self._favorites)):
        badges = [label for key, label in (("is_home", tr("Home")), ("is_work", tr("Work"))) if favorite.get(key)]
        rows.append((f"favorite:{favorite.get('id') or index}", str(favorite.get("name") or tr("Unnamed favorite")),
                     " • ".join(badges) or tr("Favorite destination"), self._same_destination(self._draft_destination, favorite)))
      groups.append((tr("Favorite destinations"), rows))
    if self._recent_destinations:
      groups.append((tr("Recent destinations"), [
        (f"recent:{index}", str(recent.get("place_name") or recent.get("name") or tr("Recent destination")),
         tr("Recent destination"), self._same_destination(self._draft_destination, recent))
        for index, recent in enumerate(self._recent_destinations)
      ]))
    return groups

  def _status_message(self) -> tuple[str, str] | None:
    """Loading, error or empty state shown in place of destination lists."""
    if self._search_loading:
      return tr("Searching..."), tr("Looking up destinations")
    if self._search_error:
      return tr("Search unavailable"), self._search_error
    if not self._search_results and not self._favorites and not self._recent_destinations:
      if self._query:
        return tr("No matching destinations"), tr("Try a different place or address.")
      return tr("No destinations yet"), tr("Search for a place or address to begin.")
    return None

  def _navigation_blocks(self) -> list[tuple[float, Any]]:
    """(height, draw(rect, manager)) for each block on the page, top to bottom."""
    blocks: list[tuple[float, Any]] = []

    def search(rect, manager):
      body = draw_settings_group(rect, tr("Destination"), style=PANEL_STYLE)
      hovered, pressed = manager._interactive_state("action:search", body)
      draw_settings_card_row(body, title=self._query or tr("Search for a destination"),
                             subtitle=tr("Use the on-device keyboard to search Mapbox locations"), action_text=tr("Search"),
                             hovered=hovered, pressed=pressed, grouped=True, is_last=True, style=PANEL_STYLE,
                             action_text_size=SETTINGS_ROW_VALUE_FONT_SIZE, action_height=AS.VALUE_PILL_HEIGHT)
    blocks.append((GROUP_OVERHEAD + NAV_ROW_HEIGHT, search))

    if self._draft_destination is not None or self._active_destination is not None:
      def destination(rect, manager):
        body = draw_settings_group(rl.Rectangle(rect.x, rect.y, rect.width, GROUP_OVERHEAD + NAV_ROW_HEIGHT),
                                   tr("Route"), style=PANEL_STYLE)
        self._draw_destination_row(body, manager)
        if self._action_definitions():
          self._draw_action_buttons(rl.Rectangle(rect.x, body.y + body.height + AS.SETTINGS_ROW_GAP, rect.width,
                                                 self._action_buttons_height()), manager)
      actions_h = self._action_buttons_height()
      blocks.append((GROUP_OVERHEAD + NAV_ROW_HEIGHT + (AS.SETTINGS_ROW_GAP + actions_h if actions_h else 0), destination))

    status = self._status_message()
    if status is not None:
      def message(rect, manager, status=status):
        body = draw_settings_group_heading(rect, tr("Destinations"), style=PANEL_STYLE)
        draw_settings_empty_state(body, status[0], status[1], style=PANEL_STYLE)
      blocks.append((GROUP_OVERHEAD + settings_empty_state_height(), message))

    if not self._search_loading and not self._search_error:
      for heading, rows in self._destination_rows():
        def group(rect, manager, heading=heading, rows=rows):
          body = draw_settings_group(rect, heading, style=PANEL_STYLE)
          draw_section_header(build_settings_group_frame(rect).heading, "", trailing_text=str(len(rows)),
                              trailing_size=AS.SETTINGS_GROUP_HEADING_SIZE - 4, style=PANEL_STYLE)
          for index, (target_id, title, subtitle, current) in enumerate(rows):
            row = rl.Rectangle(body.x, body.y + index * NAV_ROW_HEIGHT, body.width, NAV_ROW_HEIGHT)
            hovered, pressed = manager._interactive_state(target_id, row)
            draw_settings_card_row(row, title=title, subtitle=subtitle, action_text=tr("Select"), hovered=hovered,
                                   pressed=pressed, current=current, grouped=True, is_last=index == len(rows) - 1,
                                   style=PANEL_STYLE, action_text_size=SETTINGS_ROW_VALUE_FONT_SIZE,
                                   action_height=AS.VALUE_PILL_HEIGHT)
        blocks.append((GROUP_OVERHEAD + len(rows) * NAV_ROW_HEIGHT, group))
    return blocks

  def _draw_navigation_content(self, scroll_rect: rl.Rectangle, content_width: float, scroll_offset: float, manager: NavigationManagerView):
    y = scroll_rect.y + scroll_offset
    for index, (height, draw) in enumerate(self._navigation_blocks()):
      if index:
        y += SECTION_GAP
      draw(rl.Rectangle(scroll_rect.x, y, content_width, height), manager)
      y += height

  def _measure_navigation_content_height(self, content_width: float) -> float:
    del content_width
    blocks = self._navigation_blocks()
    return sum(height for height, _draw in blocks) + SECTION_GAP * max(0, len(blocks) - 1)
