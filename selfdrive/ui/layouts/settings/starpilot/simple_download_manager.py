from __future__ import annotations
import re
import time
from pathlib import Path
from collections.abc import Callable

import pyray as rl
from openpilot.system.ui.lib.application import gui_app, FontWeight, MousePos, FONT_SCALE
from openpilot.system.ui.lib.multilang import tr
from openpilot.system.ui.lib.scroll_panel2 import GuiScrollPanel2
from openpilot.system.ui.widgets import Widget, DialogResult
from openpilot.system.ui.widgets.confirm_dialog import ConfirmDialog
from openpilot.system.ui.widgets.label import gui_label
from openpilot.selfdrive.ui.lib import aether_style as AS
from openpilot.selfdrive.ui.layouts.settings.starpilot.aethergrid import (
    AetherButton, AetherListColors, AetherScrollbar, AetherSegmentedControl, DEFAULT_PANEL_STYLE,
    draw_list_group_shell, draw_list_scroll_fades, draw_settings_card, draw_settings_card_row,
    draw_settings_empty_state, settings_empty_state_height, with_alpha, snap_rect, point_hits, wrap_text,
    aether_begin_scissor_mode, aether_end_scissor_mode, SETTINGS_ROW_VALUE_FONT_SIZE,
)


# ── Helpers ──

def _theme_display_name(value: str) -> str:
  if not value:
    return "Stock"
  if value.lower() == "stock":
    return "Stock"
  if value.lower() == "none":
    return "None"
  base, creator = (value.split("~", 1) + [""])[:2] if "~" in value else (value, "")
  user_created = False
  for suffix in ("-user_created", "_user_created", "-user-created", "_user-created"):
    if base.endswith(suffix):
      base = base[: -len(suffix)]
      user_created = True
      break
  parts = [part for part in re.split(r"[-_]+", base) if part]
  display = " ".join(part[:1].upper() + part[1:] for part in parts) if parts else value
  if user_created:
    display += " (User Created)"
  if creator:
    display += f" - by: {creator}"
  return display


def _display_to_slug(display: str) -> str:
  slug = display.lower().strip()
  slug = slug.replace("(user created)", "").strip()
  if " - by: " in slug:
    slug = slug.split(" - by: ")[0].strip()
  slug = slug.replace("(", "").replace(")", "").replace("'", "").replace(".", "").replace("\u2728", "").strip()
  slug = slug.replace(" ", "_")
  slug = re.sub(r"_+", "_", slug)
  slug = slug.strip("_")
  return slug


def _delete_asset_file(directory: Path, display_name: str) -> bool:
  base = display_name.lower()
  base = base.replace("(", "-").replace(")", "").replace(" ", "-")
  base = re.sub(r"[^a-z0-9\-]", "", base)
  while base.endswith("-"):
    base = base[:-1]
  base_underscore = base.replace("-", "_")
  candidates = {base, base + "-user-created", base_underscore, base_underscore + "-user_created"}

  for f in sorted(directory.iterdir()):
    if f.is_file():
      normalized = f.stem.lower().replace("_", "-")
      normalized = re.sub(r"[^a-z0-9\-~]", "", normalized)
      if normalized in candidates:
        f.unlink()
        return True
  return False


def _add_to_downloadable_list(params, param_key: str, display_name: str):
  current = params.get(param_key, encoding="utf-8") or ""
  assets = [a.strip() for a in current.split(",") if a.strip()]
  slug = _display_to_slug(display_name)
  if slug and slug not in assets:
    assets.append(slug)
    assets.sort()
    params.put(param_key, ",".join(assets))


def _is_online() -> bool:
  try:
    from openpilot.selfdrive.ui.ui_state import ui_state
    from cereal import log
    nt = ui_state.sm["deviceState"].networkType if ui_state.sm.valid.get("deviceState", False) else log.NetworkType.none
    return nt != log.NetworkType.none
  except Exception:
    return True


def _is_parked() -> bool:
  try:
    from openpilot.selfdrive.ui.ui_state import ui_state
    if ui_state.is_offroad():
      return True
    if ui_state.sm.valid.get("starpilotCarState", False):
      return bool(ui_state.sm["starpilotCarState"].isParked)
  except Exception:
    pass
  return True


class SimpleDownloadManager(Widget):
  """Fullscreen manager for downloadable assets, in the shared settings dialog shell.

  Same header as the pickers (title, current selection, Close), a segmented Select / Delete /
  Download control, then a grouped list whose rows carry the shared 112 px action pills.
  """

  MODE_SELECT = 0
  MODE_DELETE = 1
  MODE_DOWNLOAD = 2

  MODE_LABELS = ["Select", "Delete", "Download"]
  ITEM_HEIGHT = 160  # the grouped row used by Map Data, Driving Model and Navigation

  def __init__(
    self,
    title: str,
    asset_type: str,
    directory: str | Path,
    asset_param: str,
    download_param: str,
    downloadable_list_param: str,
    params,
    params_memory,
    on_close: Callable,
    *,
    get_is_online: Callable[[], bool] | None = None,
    get_is_parked: Callable[[], bool] | None = None,
  ):
    super().__init__()
    self.title = title
    self.asset_type = asset_type
    self.directory = Path(directory)
    self.asset_param = asset_param
    self.download_param = download_param
    self.downloadable_list_param = downloadable_list_param
    self.params = params
    self.params_memory = params_memory
    self._on_close = on_close

    self._get_is_online = get_is_online or (lambda: True)
    self._get_is_parked = get_is_parked or (lambda: True)

    self._active_mode = self.MODE_SELECT
    self._downloading = False
    self.refresh_thread = None
    self._download_progress = ""
    self._finalizing_until = 0.0
    self._pressed_target: str | None = None
    self._pressed_time = 0.0

    self._scroll_panel = GuiScrollPanel2(horizontal=False)
    self._scrollbar = AetherScrollbar()
    self._scroll_offset = 0.0
    self._content_height = 0.0

    self._list_items: list[str] = []
    self._slug_map: dict[str, str] = {}
    self._item_rects: dict[str, rl.Rectangle] = {}
    self._cancel_rect = rl.Rectangle(0, 0, 0, 0)
    self._scroll_rect = rl.Rectangle(0, 0, 0, 0)
    self._info_message = ""
    self._info_message_until = 0.0

    self._close_button = self._child(AetherButton(tr("Close"), lambda: self._close(DialogResult.CANCEL), neutral=True))
    self._mode_control = self._child(AetherSegmentedControl(
      [tr(label) for label in self.MODE_LABELS], lambda: self._active_mode, self._set_mode, style=DEFAULT_PANEL_STYLE))

    self._refresh_list()
    self.set_touch_valid_callback(lambda: self._scroll_panel.is_touch_valid())

  def _set_mode(self, mode: int):
    if mode != self._active_mode:
      self._active_mode = mode
      self._scroll_offset = 0.0
      self._scroll_panel.set_offset(0.0)
      self._refresh_list()

  # ── List data ──

  def _refresh_list(self):
    if self._active_mode in (self.MODE_SELECT, self.MODE_DELETE):
      self._list_items = self._list_downloaded()
    elif self._active_mode == self.MODE_DOWNLOAD:
      downloadable = self._list_downloadable()
      downloaded_stems = set(s.lower() for s in self._list_downloaded_stems())
      self._list_items = [
        item for item in downloadable
        if _display_to_slug(item).lower() not in downloaded_stems
      ]

  def _list_downloaded(self) -> list[str]:
    if not self.directory.is_dir():
      return []
    items: list[str] = []
    for f in sorted(self.directory.iterdir()):
      if f.is_file():
        items.append(_theme_display_name(f.stem))
    return items

  def _list_downloaded_stems(self) -> list[str]:
    if not self.directory.is_dir():
      return []
    return [f.stem for f in self.directory.iterdir() if f.is_file()]

  def _list_downloadable(self) -> list[str]:
    raw = self.params.get(self.downloadable_list_param, encoding="utf-8") or ""
    if not raw.strip():
      return []
    names = [s.strip() for s in raw.split(",") if s.strip()]
    self._slug_map = {}
    result = []
    for n in names:
      display = _theme_display_name(n)
      self._slug_map[display] = n
      result.append(display)
    return result

  def _current_value(self) -> str:
    return self.params.get(self.asset_param, encoding="utf-8") or ""

  # ── Actions ──

  def _select_asset(self, display_name: str):
    slug = _display_to_slug(display_name)
    if slug:
      self.params.put(self.asset_param, slug)
    self._close(DialogResult.CONFIRM, slug)

  def _delete_asset(self, display_name: str):
    _delete_asset_file(self.directory, display_name)
    _add_to_downloadable_list(self.params, self.downloadable_list_param, display_name)
    self._info_message = f"Deleted \"{display_name}\""
    self._info_message_until = time.monotonic() + 2.5
    self._refresh_list()

  def _start_download(self, display_name: str):
    if self._downloading:
      return
    slug = self._slug_map.get(display_name) or _display_to_slug(display_name)
    if not slug:
      return
    self._downloading = True
    self._download_progress = "Downloading..."
    # A cancel left over from an earlier download (e.g. tapped after it had
    # already finished) must not abort this one.
    self.params_memory.remove("CancelThemeDownload")
    self.params_memory.put("ThemeDownloadProgress", "Downloading...")
    self.params_memory.put(self.download_param, slug)

  def _cancel_download(self):
    self.params_memory.put_bool("CancelThemeDownload", True)
    self._info_message = tr("Cancelling...")
    self._info_message_until = time.monotonic() + 5.0

  def _close(self, result: DialogResult, value=None):
    gui_app.pop_widget()
    if self._on_close:
      self._on_close(result, value)

  # ── Mouse handling ──

  def _hit_target(self, pos: MousePos) -> str | None:
    # Close and the mode control are AetherButton / AetherSegmentedControl children; rows are clipped
    # to the scrolling list so a row scrolled under the header can't be tapped.
    if self._downloading:
      return "cancel_download" if point_hits(pos, self._cancel_rect, self._scroll_rect, pad_x=0, pad_y=0) else None
    for key, irect in self._item_rects.items():
      if point_hits(pos, irect, self._scroll_rect, pad_x=0, pad_y=0):
        return key
    return None

  def _handle_mouse_press(self, pos: MousePos):
    target = self._hit_target(pos)
    if target:
      self._pressed_target = target
      self._pressed_time = rl.get_time()

  def _handle_mouse_release(self, pos: MousePos):
    target = self._hit_target(pos)
    if target and target == self._pressed_target:
      self._on_target(target)
    self._pressed_target = None

  def _on_target(self, target: str):
    if target == "close":
      self._close(DialogResult.CANCEL)
    elif target.startswith("mode:"):
      self._set_mode(int(target.split(":")[1]))
    elif target.startswith("item:"):
      idx = int(target.split(":")[1])
      if 0 <= idx < len(self._list_items):
        item = self._list_items[idx]
        if self._active_mode == self.MODE_SELECT:
          self._select_asset(item)
        elif self._active_mode == self.MODE_DELETE:
          def on_result(result: DialogResult):
            if result == DialogResult.CONFIRM:
              self._delete_asset(item)

          gui_app.push_widget(ConfirmDialog(
            tr("Delete \"{name}\"?").format(name=item), tr("Delete"), callback=on_result,
          ))
        elif self._active_mode == self.MODE_DOWNLOAD:
          self._start_download(item)
    elif target == "cancel_download":
      self._cancel_download()

  # ── State update ──

  def _update_state(self):
    now = time.monotonic()
    if self.refresh_thread is not None and not self.refresh_thread.is_alive():
      self.params.invalidate(self.downloadable_list_param)
      self._refresh_list()
      self.refresh_thread = None
    if self._pressed_target is not None and not self.is_pressed:
      self._pressed_target = None
    if self._info_message_until > 0 and now >= self._info_message_until:
      self._info_message = ""
      self._info_message_until = 0.0
    if self._finalizing_until > 0 and now >= self._finalizing_until:
      self._finalizing_until = 0.0
      self._downloading = False
      self._download_progress = ""
      self._refresh_list()
    if self._downloading:
      progress = self.params_memory.get("ThemeDownloadProgress", encoding="utf-8") or ""
      if progress != self._download_progress:
        self._download_progress = progress
        if progress == "Downloaded!" or ("cancelled" in progress.lower() or "failed" in progress.lower() or "offline" in progress.lower() or "unavailable" in progress.lower()):
          self._finalizing_until = now + 2.5

  # ── keepScreenOn support ──

  @property
  def should_keep_screen_on(self) -> bool:
    return self._downloading

  # ── Rendering ──

  def _render(self, rect: rl.Rectangle) -> bool | int | None:
    self.set_rect(rect)
    rl.draw_rectangle_rec(rect, AS.SETTINGS_BG)
    margin_x = min(AS.SETTINGS_DIALOG_MARGIN_X, rect.width * 0.05)
    margin_y = min(AS.SETTINGS_DIALOG_MARGIN_Y, rect.height * 0.05)
    shell = snap_rect(rl.Rectangle(rect.x + margin_x, rect.y + margin_y, rect.width - margin_x * 2, rect.height - margin_y * 2))
    draw_settings_card(shell, fill=AS.SETTINGS_DIALOG_FILL, border=AS.SETTINGS_TILE_BORDER, radius_px=AS.SETTINGS_DIALOG_RADIUS)
    inset = min(AS.SETTINGS_DIALOG_INSET, shell.width * 0.05)
    x, y, width = shell.x + inset, shell.y + inset, shell.width - inset * 2

    # Header: title and current selection beside Close, as in the shared pickers.
    close_w = max(AS.SETTINGS_DIALOG_ACTION_WIDTH, self._close_button.measure_width())
    close_rect = rl.Rectangle(x + width - close_w, y, close_w, self._close_button.measure_height())
    text_w = max(1.0, close_rect.x - AS.SETTINGS_CARD_INSET - x)
    title_size, description_size = AS.SETTINGS_DIALOG_TITLE_SIZE, AS.SETTINGS_DIALOG_DESCRIPTION_SIZE
    title_h = max(70.0, title_size * FONT_SCALE)
    description_h = max(36.0, description_size * FONT_SCALE)
    title_line = (wrap_text(gui_app.font(FontWeight.BOLD), tr(self.title), text_w, title_size, max_lines=1, spacing=0) or [""])[0]
    gui_label(rl.Rectangle(x, y, text_w, title_h), title_line, title_size, AS.TEXT, FontWeight.BOLD)
    if self._info_message and time.monotonic() < self._info_message_until:
      description, color = self._info_message, AetherListColors.SUCCESS
    else:
      current_val = self._current_value()
      description = f"{tr('Current')}: {_theme_display_name(current_val) if current_val else 'Stock'}"
      color = AS.TEXT_SECONDARY
    gui_label(rl.Rectangle(x, y + title_h + 4, text_w, description_h), description, description_size, color)
    self._close_button.render(close_rect)
    y += max(close_rect.height, title_h + 4 + description_h) + AS.SETTINGS_TILE_GAP

    mode_h = self._mode_control.measure_height(width)
    self._mode_control.render(rl.Rectangle(x, y, width, mode_h))
    y += mode_h + AS.SETTINGS_ROW_GAP

    scroll_rect = rl.Rectangle(x, y, width, max(0.0, shell.y + shell.height - inset - y))
    self._scroll_rect = scroll_rect
    if scroll_rect.height < 40:
      return True

    n_items = len(self._list_items)
    progress_h = self.ITEM_HEIGHT if self._downloading else 0.0
    list_h = n_items * self.ITEM_HEIGHT
    if n_items == 0 and not self._downloading:
      content_height = settings_empty_state_height()
    else:
      content_height = progress_h + (AS.SETTINGS_ROW_GAP if progress_h and n_items else 0.0) + list_h

    self._scroll_panel.set_enabled(True)
    self._scroll_offset = self._scroll_panel.update(scroll_rect, max(content_height, scroll_rect.height))
    self._item_rects.clear()
    self._cancel_rect = rl.Rectangle(0, 0, 0, 0)

    aether_begin_scissor_mode(int(scroll_rect.x), int(scroll_rect.y), int(scroll_rect.width), int(scroll_rect.height))
    item_y = scroll_rect.y + self._scroll_offset
    if n_items == 0 and not self._downloading:
      empty_msg = self._empty_state_text()
      draw_settings_empty_state(rl.Rectangle(scroll_rect.x, item_y, scroll_rect.width, content_height),
                                tr(empty_msg["title"]), tr(empty_msg["body"]))
    else:
      if self._downloading:
        progress_rect = rl.Rectangle(scroll_rect.x, item_y, scroll_rect.width, progress_h)
        draw_list_group_shell(progress_rect)
        self._cancel_rect = draw_settings_card_row(
          progress_rect, title=self._download_progress or tr("Downloading..."),
          subtitle=tr("Keep the device on until the download finishes."), action_text=tr("Cancel"),
          pressed=self._pressed_target == "cancel_download", grouped=True, is_last=True,
          action_text_size=SETTINGS_ROW_VALUE_FONT_SIZE, action_height=AS.VALUE_PILL_HEIGHT,
          action_fill=AetherListColors.DANGER_SOFT, action_border=with_alpha(AetherListColors.DANGER, 140),
        )
        item_y += progress_h + (AS.SETTINGS_ROW_GAP if n_items else 0.0)
      if n_items:
        draw_list_group_shell(rl.Rectangle(scroll_rect.x, item_y, scroll_rect.width, list_h))
      for idx, item in enumerate(self._list_items):
        row = rl.Rectangle(scroll_rect.x, item_y + idx * self.ITEM_HEIGHT, scroll_rect.width, float(self.ITEM_HEIGHT))
        key = f"item:{idx}"
        self._item_rects[key] = row
        if row.y + row.height < scroll_rect.y or row.y > scroll_rect.y + scroll_rect.height:
          continue
        self._draw_item(row, item, key, is_last=idx == n_items - 1)
    aether_end_scissor_mode()

    if content_height > scroll_rect.height:
      self._scrollbar.render(scroll_rect, content_height, self._scroll_offset)
    draw_list_scroll_fades(scroll_rect, content_height, self._scroll_offset, AS.SETTINGS_DIALOG_FILL)
    return True

  def _draw_item(self, row: rl.Rectangle, item: str, key: str, *, is_last: bool):
    is_current = self._active_mode == self.MODE_SELECT and _display_to_slug(item) == self._current_value()
    pressed = self._pressed_target == key and not self._downloading
    kwargs: dict = {}
    if self._active_mode == self.MODE_SELECT:
      action_text = tr("Current") if is_current else tr("Select")
      if is_current:
        kwargs = {"action_fill": with_alpha(AetherListColors.SUCCESS_SOFT, 60), "action_border": AetherListColors.SUCCESS}
    elif self._active_mode == self.MODE_DELETE:
      action_text = tr("Delete")
      kwargs = {"action_fill": AetherListColors.DANGER_SOFT, "action_border": with_alpha(AetherListColors.DANGER, 140)}
    else:
      action_text = tr("Download")
    if self._downloading:
      # One download at a time: the other rows wait, pills included.
      kwargs = {"action_fill": with_alpha(AS.TRACK_OFF, 120), "action_border": AS.SETTINGS_TILE_BORDER,
                "action_text_color": AS.TEXT_DISABLED}
    draw_settings_card_row(row, title=item, action_text=action_text, pressed=pressed, current=is_current,
                           enabled=not self._downloading, grouped=True, is_last=is_last,
                           action_text_size=SETTINGS_ROW_VALUE_FONT_SIZE, action_height=AS.VALUE_PILL_HEIGHT, **kwargs)

  def _empty_state_text(self) -> dict:
    at = self.asset_type
    if self._active_mode == self.MODE_SELECT:
      return {"title": tr("No {name}s").format(name=at.title()), "body": tr("Download {name}s to see them here.").format(name=at)}
    if self._active_mode == self.MODE_DELETE:
      return {"title": tr("Nothing to Delete"), "body": tr("No {name}s are currently downloaded.").format(name=at)}
    if self._active_mode == self.MODE_DOWNLOAD:
      if self._downloading:
        return {"title": "", "body": ""}
      return {"title": tr("All Available"), "body": tr("You have all available {name}s.").format(name=at)}
    return {"title": "", "body": ""}
