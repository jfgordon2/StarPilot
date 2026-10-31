"""Bluetooth: wheel-mounted remotes first, then car audio and nearby devices.

Wheel buttons use StarPilot's wheel controls service: a mapping ties a remote's button to a slot, and controller
slots hold the action. While this screen is open the service runs in test mode, so pressing a button highlights
its row instead of running its action. Pairing and audio go through upstream's BluetoothManager and its dialogs.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

import pyray as rl

from openpilot.selfdrive.ui.tandem import tokens as T
from openpilot.selfdrive.ui.tandem.base import Component
from openpilot.selfdrive.ui.tandem.controls import Badge, Button, ButtonStyle, Tone, ValueButton
from openpilot.selfdrive.ui.tandem.layout import FILL, Fill, column, row
from openpilot.selfdrive.ui.tandem.overlays import Sheet
from openpilot.selfdrive.ui.tandem.rows import ListPanel, OptionList, SectionHeader, SettingRow, Text
from openpilot.selfdrive.ui.tandem.settings.model import Pair, Rebuilding
from openpilot.selfdrive.ui.tandem.settings.pages import body_rect

LEARN_SECONDS = 20


class WheelSource(Protocol):
  favorite_slots: int
  def mappings(self) -> list[dict]: ...
  def action(self, slot: int) -> str | None: ...                 # action key in a mapping slot
  def actions(self) -> list[tuple[str, str]]: ...                # (key, name) choices, including favorites
  def status(self) -> dict: ...
  def start_learning(self, slot: int) -> None: ...
  def cancel_learning(self) -> None: ...
  def start_testing(self) -> None: ...
  def stop_testing(self) -> None: ...
  def assign(self, mapping_id: str, key: str) -> None: ...
  def free_slot(self) -> int | None: ...
  def delete(self, mapping_id: str) -> None: ...


class WheelButtons:
  def __init__(self, source: WheelSource):
    self.source = source

  def buttons(self) -> list[dict]:
    return self.source.mappings()

  def action_name(self, mapping: dict) -> str:
    key = self.source.action(mapping["slot"])
    return next((name for k, name in self.source.actions() if k == key), "Not set")

  def pressed(self) -> dict | None:
    status = self.source.status()
    return status.get("last_tested") if status.get("testing") else None

  def is_pressed(self, mapping: dict) -> bool:
    pressed = self.pressed()
    return bool(pressed and pressed.get("mapped") and pressed.get("slot") == mapping["slot"])

  def unassigned_pressed(self) -> bool:
    pressed = self.pressed()
    return bool(pressed and not pressed.get("mapped"))

  def remote_name(self) -> str:
    mappings = self.buttons()
    devices = self.source.status().get("devices") or []
    name = mappings[0]["device_name"] if mappings else (devices[0].get("name") if devices else "")
    return name or "No remote connected"

  def start_testing(self) -> None:
    if self.buttons():
      self.source.start_testing()

  def summary(self) -> str:
    count = len(self.buttons())
    return f"{count} wheel button{'s' if count != 1 else ''}" if count else "No wheel buttons"


class AssignSheet(Component):
  """Step 1: press the button on the remote. Step 2: choose what it does. Save maps it."""
  grow_touch_target = False

  def __init__(self, model: WheelButtons):
    super().__init__()
    self._model = model
    self._slot = model.source.free_slot()
    self._learned: dict | None = None
    self._action = -1
    self._started = False
    self._list = self._child(OptionList([name for _, name in model.source.actions()], lambda: self._action, self._pick, row_height=T.px(50)))

  def _pick(self, index: int) -> None:
    self._action = index

  def show_event(self):
    super().show_event()
    if self._slot is not None and not self._started:
      self._started = True
      self._model.source.start_learning(self._slot)

  def _update_state(self):
    learned = self._model.source.status().get("last_learned")
    if learned and learned.get("slot") == self._slot:
      self._learned = learned

  @property
  def ready(self) -> bool:
    return self._learned is not None and self._action >= 0

  def save(self) -> bool:
    if not self.ready:
      return False
    self._model.source.assign(self._learned["id"], self._model.source.actions()[self._action][0])
    return True

  def cancel(self) -> None:
    self._model.source.cancel_learning()
    if self._learned is not None:
      self._model.source.delete(self._learned["id"])

  def step_one(self) -> tuple[str, str]:
    if self._slot is None:
      return "All button slots are in use", "Remove a button to add another."
    if self._learned is None:
      remaining = self._model.source.status().get("remaining_seconds")
      return "Press the button on your remote", f"Listening{f' for {remaining:.0f} s' if remaining else ''}. It stops after {LEARN_SECONDS} s."
    return f"{self._learned.get('event_name') or 'Button'} detected", "Press a different button on the remote to change it."

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    return max_width, T.px(400)

  def _render(self, rect: rl.Rectangle):
    from openpilot.selfdrive.ui.tandem import draw
    left, right = row(rect, [Fill(0.8), FILL], T.px(22))
    cap1, title, sub, _ = column(left, [T.px(28), draw.line_height(T.font_px(22)), draw.line_height(T.SIZE_SUBTITLE), FILL], T.px(8))
    draw.caption(cap1, "STEP 1 · PRESS IT")
    heading, detail = self.step_one()
    draw.text(title, heading, T.font_px(22), T.SUCCESS_TEXT if self._learned else T.TEXT, T.FONT_BOLD)
    draw.text(sub, detail, T.SIZE_SUBTITLE, T.TEXT_TERTIARY)
    cap2, options = column(right, [T.px(28), FILL], T.px(8))
    draw.caption(cap2, "STEP 2 · CHOOSE WHAT IT DOES")
    self._list.render(options)


def wheel_panel(model: WheelButtons, window) -> Component:
  def change(mapping: dict) -> Callable[[], None]:
    def show():
      actions = model.source.actions()

      def pick(index: int):
        model.source.assign(mapping["id"], actions[index][0])
        window.dismiss()

      def remove():
        model.source.delete(mapping["id"])
        window.dismiss()
      current = model.source.action(mapping["slot"])
      window.present(Sheet(mapping.get("event_name") or "Button", OptionList([name for _, name in actions],
                                                                             lambda: next((i for i, (k, _) in enumerate(actions) if k == current), -1),
                                                                             pick, row_height=T.px(52)),
                           subtitle="What this button does while driving",
                           actions=[Button("Remove", remove, ButtonStyle.DANGER_OUTLINE)], on_dismiss=window.dismiss))
    return show

  def add():
    sheet_body = AssignSheet(model)

    def save():
      if sheet_body.save():
        window.dismiss()
        model.start_testing()

    def cancel():
      sheet_body.cancel()
      window.dismiss()
    window.present(Sheet("Assign a button", sheet_body, actions=[Button("Cancel", cancel), Button("Save", save, ButtonStyle.PRIMARY)],
                         on_dismiss=cancel))

  def button_row(index: int, mapping: dict) -> SettingRow:
    pressed = Badge("Pressed", Tone.SUCCESS)
    pressed.set_visible(lambda: model.is_pressed(mapping))
    value = ValueButton(lambda: model.action_name(mapping), change(mapping))
    value.set_visible(lambda: not model.is_pressed(mapping))
    return SettingRow(f"Button {index + 1}", mapping.get("event_name"), Pair(pressed, value))

  def build() -> ListPanel:
    rows = [button_row(i, m) for i, m in enumerate(model.buttons())]
    add_row = SettingRow("Add a button", lambda: "That button isn't assigned yet. Tap to add it." if model.unassigned_pressed() else None,
                         on_click=add, subtitle_color=T.SUCCESS_TEXT)
    return ListPanel([*rows, add_row], title="Wheel Buttons",
                     subtitle=lambda: f"{model.remote_name()} · press any button to find it",
                     footnote="Buttons don't run their actions while this screen is open.")

  return Rebuilding(lambda: tuple((m["id"], m["slot"]) for m in model.buttons()), build)


class BluetoothDevices(Protocol):
  def tick(self) -> None: ...
  def set_active(self, active: bool) -> None: ...
  def status(self): ...
  def select(self, address: str) -> None: ...
  def test_audio(self, address: str) -> None: ...
  def forget(self, address: str) -> None: ...


def devices_panel(bt: BluetoothDevices) -> Component:
  def audio_row(device) -> SettingRow:
    selected = lambda: bt.status().selected_audio.upper() == device.address.upper()  # noqa: E731
    return SettingRow(device.name, lambda: "Plays alerts and chimes" if selected() else ("Connected" if device.connected else "Paired"),
                      Button("Test sound", lambda: bt.test_audio(device.address)), on_click=lambda: bt.select(device.address),
                      chevron=False)

  def nearby_row(device) -> SettingRow:
    action = Button(lambda: "Connect" if device.paired else "Pair", lambda: bt.select(device.address))
    action.set_enabled(lambda: bt.status().offroad)
    return SettingRow(device.name, lambda: "Paired" if device.paired else None, action)

  def build() -> ListPanel:
    status = bt.status()
    audio = [d for d in status.devices if d.audio and d.paired]
    nearby = [d for d in status.devices if not (d.audio and d.paired) and not d.controller]
    return ListPanel([
      SectionHeader("CAR AUDIO"),
      *([audio_row(d) for d in audio] or [Text("No car audio paired.")]),
      SectionHeader("NEARBY", trailing=None),
      *([nearby_row(d) for d in nearby] or [Text("Scanning…" if status.discovering else "No devices found.")]),
    ], footnote="Pairing waits until you're parked.")

  def key():
    status = bt.status()
    return tuple((d.address, d.paired, d.connected) for d in status.devices), status.discovering

  return Rebuilding(key, build, bt.tick)


class BluetoothPage(Component):
  """Wheel buttons on the left (wider); car audio and nearby devices on the right."""
  grow_touch_target = False

  def __init__(self, wheel: WheelButtons, bt: BluetoothDevices, window):
    super().__init__()
    self._wheel = wheel
    self._bt = bt
    self._left = self._child(wheel_panel(wheel, window))
    self._right = self._child(devices_panel(bt))

  def show_event(self):
    self._bt.set_active(True)
    self._wheel.start_testing()
    super().show_event()

  def hide_event(self):
    super().hide_event()
    self._wheel.source.stop_testing()
    self._bt.set_active(False)

  def _render(self, rect: rl.Rectangle):
    left, right = row(body_rect(rect), [Fill(1.4), FILL], T.px(14))
    self._left.render(left)
    self._right.render(right)


# Action names for the wheel's controller actions, by StarPilot key suffix.
ACTION_NAMES = {"engage_openpilot": "Engage", "disengage_openpilot": "Disengage", "cycle_driving_personality": "Change driving style",
                "toggle_screen_off": "Screen off / on", "bookmark": "Save a clip", "toggle_aol": "Always-on steering", "force_coast": "Coast"}


class UpstreamWheel:
  """WheelSource backed by StarPilot's wheel controls service."""

  def __init__(self):
    from openpilot.common.params import Params
    from openpilot.starpilot.common import controller_actions as ca
    from openpilot.starpilot.system.wheel_controls import wheel_controlsd as wc
    self._wc = wc
    self._ca = ca
    self._params = Params(return_defaults=True)
    self._memory = Params(memory=True)
    self.favorite_slots = wc.FAVORITE_SLOT_COUNT

  def mappings(self) -> list[dict]:
    return self._wc.load_mappings(self._params)

  def _slots(self) -> list[dict]:
    return self._wc.load_controller_action_slots(self._params)

  def action(self, slot: int) -> str | None:
    if slot < self.favorite_slots:
      return f"favorite:{slot}"
    entry = self._slots()[slot - self.favorite_slots]
    return entry.get("key") if entry.get("enabled") else None

  def actions(self) -> list[tuple[str, str]]:
    keys = {o["key"].rsplit(":", 1)[-1]: o["key"] for o in self._ca.CONTROLLER_ACTION_OPTIONS}
    choices = [(keys[suffix], name) for suffix, name in ACTION_NAMES.items() if suffix in keys]
    return choices + [(f"favorite:{i}", f"Navigate to favorite {i + 1}") for i in range(self.favorite_slots)]

  def status(self) -> dict:
    return self._wc.public_status(self._params, self._memory)

  def start_learning(self, slot: int) -> None:
    self._wc.start_learning(slot, self._memory, self._params)

  def cancel_learning(self) -> None:
    self._wc.cancel_learning(self._memory, self._params)

  def start_testing(self) -> None:
    self._wc.start_testing(self._memory, self._params)

  def stop_testing(self) -> None:
    self._wc.stop_testing(self._memory)

  def free_slot(self) -> int | None:
    used = {m["slot"] for m in self.mappings()}
    return next((self.favorite_slots + i for i, s in enumerate(self._slots())
                 if self.favorite_slots + i not in used and not s.get("enabled")), None)

  def assign(self, mapping_id: str, key: str) -> None:
    mappings = self.mappings()
    mapping = next(m for m in mappings if m["id"] == mapping_id)
    if key.startswith("favorite:"):
      mapping["slot"] = int(key.split(":")[1])
    else:
      if mapping["slot"] < self.favorite_slots:
        mapping["slot"] = self.free_slot() or self.favorite_slots
      name = next(n for k, n in self.actions() if k == key)
      self._wc.set_controller_action_slot(mapping["slot"] - self.favorite_slots, key, name, self._params)
    self._wc.save_mappings(mappings, self._params)

  def delete(self, mapping_id: str) -> None:
    self._wc.delete_mapping(mapping_id, self._params)


class UpstreamBluetooth:
  """BluetoothDevices backed by upstream's manager; its own screen handles pairing prompts and the audio test."""

  def __init__(self):
    from openpilot.system.ui.lib.bluetooth_manager import BluetoothManager
    from openpilot.system.ui.widgets.bluetooth import BluetoothManagerUI
    self._manager = BluetoothManager()
    self._manager.set_active(False)
    self._ui = BluetoothManagerUI(self._manager)

  def tick(self) -> None:
    self._ui._handle_prompt(self._manager.status)

  def set_active(self, active: bool) -> None:
    (self._ui.show_event if active else self._ui.hide_event)()
    if active:
      self._ui._scan()

  def status(self):
    return self._manager.status

  def select(self, address: str) -> None:
    self._ui._select_device(address)

  def test_audio(self, address: str) -> None:
    from openpilot.system.ui.lib.application import gui_app
    from openpilot.system.ui.widgets.bluetooth import BluetoothAudioTestDialog
    self._manager.test_audio(address)
    gui_app.push_widget(BluetoothAudioTestDialog(self._manager))

  def forget(self, address: str) -> None:
    self._ui._confirm_forget(address)
