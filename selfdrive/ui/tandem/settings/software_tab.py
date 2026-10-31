"""Software: version and update status, automatic updates, release channel, Reset Settings, and Uninstall.

Checking, downloading, installing, choosing a branch and uninstalling are upstream's SoftwareLayout actions,
so they keep its signals to the updater and its confirmations. Reset Settings applies the Essentials defaults.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

import pyray as rl

from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.base import Component
from openpilot.selfdrive.ui.tandem.controls import Badge, Button, ButtonStyle, Switch, Tone, ValueButton
from openpilot.selfdrive.ui.tandem.layout import FILL, column, inset, row
from openpilot.selfdrive.ui.tandem.rows import ListPanel, SettingRow
from openpilot.selfdrive.ui.tandem.settings.bundles import TUNER_MODE
from openpilot.selfdrive.ui.tandem.settings.pages import body_rect
from openpilot.selfdrive.ui.tandem.settings.store import SettingsStore


class UpdateActions(Protocol):
  def tick(self) -> None: ...
  def check_or_download(self) -> None: ...
  def install(self) -> None: ...
  def choose_branch(self) -> None: ...
  def uninstall(self) -> None: ...
  def release_notes(self) -> None: ...


UPDATER_STATES = {"checking": "Checking for an update", "downloading": "Downloading the update", "finalizing": "Getting the update ready"}


class Software:
  def __init__(self, store: SettingsStore, actions: UpdateActions, reset: Callable[[], None]):
    self._store = store
    self.actions = actions
    self._reset = reset

  def version(self) -> str:
    return self._store.get_str("UpdaterCurrentDescription") or "Unknown version"

  def state(self) -> str:
    """One of: busy, failed, available (to download), ready (to install), current."""
    if (self._store.get_str("UpdaterState") or "idle") != "idle":
      return "busy"
    if self._store.get_bool("UpdateAvailable"):
      return "ready"
    if self._store.get_int("UpdateFailedCount") > 0:
      return "failed"
    return "available" if self._store.get_bool("UpdaterFetchAvailable") else "current"

  def status_badge(self) -> tuple[str, Tone]:
    return {"busy": ("Updating", Tone.ACCENT), "ready": ("Ready to install", Tone.SUCCESS), "failed": ("Check failed", Tone.WARNING),
            "available": ("Update available", Tone.ACCENT), "current": ("Up to date", Tone.SUCCESS)}[self.state()]

  def status_line(self) -> str:
    state = self.state()
    if state == "busy":
      return UPDATER_STATES.get(self._store.get_str("UpdaterState"), "Updating")
    if state == "ready":
      return f"{self._store.get_str('UpdaterNewDescription') or 'A new version'} installs when you turn off the car or restart"
    if state == "failed":
      return "Couldn't check for updates. Check the connection and try again."
    if state == "available":
      return "A new version is available to download"
    return "You have the latest version"

  def action_label(self) -> str:
    return {"busy": "Working…", "ready": "Restart to install", "failed": "Try again", "available": "Download"}.get(self.state(), "Check now")

  def act(self) -> None:
    if self.state() == "ready":
      self.actions.install()
    elif self.state() != "busy":
      self.actions.check_or_download()

  @property
  def automatic(self) -> bool:
    return self._store.get_bool("AutomaticUpdates")

  def set_automatic(self, on: bool) -> None:
    self._store.write({"AutomaticUpdates": on})

  def channel(self) -> str:
    branch = self._store.get_str("UpdaterTargetBranch") or self._store.get_str("GitBranch")
    return {"release": "Stable", "release3": "Stable", "master": "Stable", "staging": "Beta"}.get(branch, branch or "Stable")

  def tuner(self) -> bool:
    return TUNER_MODE.is_on(self._store)

  def reset_settings(self) -> None:
    self._reset()


class VersionCard(Component):
  """The status badge, version, status line and the main action, as one card."""
  grow_touch_target = False

  def __init__(self, model: Software):
    super().__init__()
    self._model = model
    self._badge = self._child(Badge(lambda: model.status_badge()[0], lambda: model.status_badge()[1]))
    self._action = self._child(Button(model.action_label, model.act, ButtonStyle.PRIMARY))
    self._action.set_enabled(lambda: model.state() != "busy")
    self._notes = self._child(Button("What's new", model.actions.release_notes))

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    return max_width, T.px(150)

  def set_parent_rect(self, parent_rect: rl.Rectangle) -> None:
    super().set_parent_rect(parent_rect)
    for w in (self._action, self._notes):
      w.set_parent_rect(parent_rect)

  def _render(self, rect: rl.Rectangle):
    body = inset(rect, x=T.PANEL_HEADER_INSET, y=T.px(16))
    text, buttons = row(body, [FILL, T.px(330)], T.px(16))
    badge, version, line, _ = column(text, [T.px(26), draw.line_height(T.font_px(26)), draw.line_height(T.SIZE_SUBTITLE), FILL], T.px(8))
    w, h = self._badge.preferred_size(text.width)
    self._badge.render(rl.Rectangle(badge.x, badge.y, w, h))
    draw.text(version, f"Version {self._model.version()}", T.font_px(26), T.TEXT, T.FONT_EXTRABOLD)
    draw.text(line, self._model.status_line(), T.SIZE_SUBTITLE, T.TEXT_TERTIARY)
    top, bottom = column(buttons, [T.BUTTON_HEIGHT, T.BUTTON_HEIGHT], T.px(10))
    self._action.render(top)
    self._notes.render(bottom)


def software_panel(model: Software, confirm) -> ListPanel:
  channel = SettingRow("Release Channel", lambda: "Choose another branch" if model.tuner() else "Other branches are in Tuner Mode",
                       ValueButton(model.channel, model.actions.choose_branch))
  channel.set_enabled(model.tuner)
  return ListPanel([
    VersionCard(model),
    SettingRow("Automatic Updates", "Download while parked, install when you turn off the car",
               Switch(lambda: model.automatic, model.set_automatic)),
    channel,
    SettingRow("Reset Settings", "Back to the Essentials defaults. Backups are kept.",
               Button("Reset", lambda: confirm("Reset settings?", "Every setting goes back to the Essentials default. Your backups are kept.",
                                               "Reset", model.reset_settings), ButtonStyle.DANGER_OUTLINE)),
    SettingRow("Uninstall", "Removes this software from the device", Button("Uninstall", model.actions.uninstall, ButtonStyle.DANGER_OUTLINE)),
  ], title="Software")


class SoftwarePage(Component):
  grow_touch_target = False

  def __init__(self, model: Software, confirm):
    super().__init__()
    self._model = model
    self._panel = self._child(software_panel(model, confirm))

  def _update_state(self):
    self._model.actions.tick()

  def _render(self, rect: rl.Rectangle):
    self._panel.render(body_rect(rect))


class UpstreamUpdates:
  """UpdateActions backed by upstream's SoftwareLayout, whose state machine tracks the updater."""

  def __init__(self):
    from openpilot.selfdrive.ui.layouts.settings.software import SoftwareLayout
    self._layout = SoftwareLayout()

  def tick(self) -> None:
    self._layout._update_state()

  def check_or_download(self) -> None:
    self._layout._on_download_update()

  def install(self) -> None:
    self._layout._on_install_update()

  def choose_branch(self) -> None:
    self._layout._on_select_branch()

  def uninstall(self) -> None:
    self._layout._on_uninstall()

  def release_notes(self) -> None:
    from openpilot.system.ui.lib.application import gui_app
    from openpilot.system.ui.widgets.confirm_dialog import ConfirmDialog
    notes = self._layout._version_item.description or "No release notes for this version."
    gui_app.push_widget(ConfirmDialog(notes if isinstance(notes, str) else notes(), "OK", rich=True))
