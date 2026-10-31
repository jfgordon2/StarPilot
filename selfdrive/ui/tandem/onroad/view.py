"""The Essentials onroad view: StarPilot's view with the bar, status chip, headroom arc and new-limit card on top.

It subclasses StarPilotOnroadView and overrides only the parts Essentials replaces:
- the torque bar becomes the headroom arc, above the bar;
- the road name moves into the bar;
- the paused and weather badges beside the driver monitor become status chips;
- the driving personality button and the experimental-mode wheel are removed;
- the bottom widgets (the driver monitor icon) sit above the bar.
Everything else, from the camera and path to the speed, alerts, turn signals and navigation card, is upstream's.
"""
from __future__ import annotations

import datetime
import math
import time

import pyray as rl

from openpilot.common.constants import CV
from openpilot.common.params import Params
from openpilot.selfdrive.ui.onroad.starpilot.starpilot_onroad_view import StarPilotOnroadView
from openpilot.selfdrive.ui.onroad.starpilot.widget_layout_manager import WidgetLayoutManager
from openpilot.selfdrive.ui.ui_state import UIStatus, ui_state
from openpilot.system.ui.lib.application import MousePos
from openpilot.selfdrive.ui.tandem.onroad.layers import (AT_LIMIT, BAR_ZONE, ArcState, BarState, Headroom, HeadroomArc, HelpSteer,
                                                         LimitCard, LimitOffer, OnroadBar, StatusChip)
from openpilot.selfdrive.ui.tandem.onroad.status import ChipPicker, snapshot

CONFIRM_TIMEOUT = 30.0      # StarPilot rejects an unanswered higher limit after 30 s
PREVIEW_SECONDS = 2.5
V_CRUISE_UNSET = 255


class BarAwareLayout(WidgetLayoutManager):
  """Upstream's layout, with the bottom zone lifted above the bar."""

  def _layout_bottom(self, is_rhd: bool):
    full = self.content_rect
    self.content_rect = rl.Rectangle(full.x, full.y, full.width, full.height - BAR_ZONE + 40)
    try:
      super()._layout_bottom(is_rhd)
    finally:
      self.content_rect = full


class EssentialsOnroadView(StarPilotOnroadView):
  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    layout = BarAwareLayout(self._content_rect)
    layout.zones = self.layout_manager.zones
    self.layout_manager = layout
    for zone, widget in (("bottom", self._personality_button_widget), ("right", self._steering_wheel_widget)):
      if widget in layout.zones[zone]:
        layout.zones[zone].remove(widget)
      widget.set_visible(False)

    self._memory = Params(memory=True)
    self._chips = ChipPicker()
    self._chip = None
    self._headroom = Headroom()
    self._arc_state = ArcState()
    self._ignored_limit = 0.0
    self._offer_since: float | None = None
    self._bar = OnroadBar(self._bar_state, self._open_menu, self._step_speed, self._toggle_engaged, self._end_route)
    self._chip_view = StatusChip(lambda: self._chip)
    self._arc = HeadroomArc(lambda: self._arc_state)
    self._help = HelpSteer()
    self._limit = LimitCard(self._offer, self._match_limit, self._ignore_limit)
    self._layers_visible = False
    self._nav_sm = None

  # Upstream pieces replaced here

  def _render_road_name(self):
    pass

  def _render_bottom_row_widgets(self):
    pass

  def _render_torque_bar(self) -> None:
    self._torque_bar._update_state()   # upstream's estimate: lateral accel, path error and road roll over the car's maximum
    now = time.monotonic()
    usage = float(self._torque_bar._torque_filter.x)
    active = ui_state.status == UIStatus.ENGAGED or ui_state.always_on_lateral_active
    self._arc_state = ArcState(usage, self._preview(), active, self._headroom.stage(usage, now) if active else "comfortable")
    self._arc.render(self._above_bar())
    if self._arc_state.stage == AT_LIMIT:
      self._help.render(self._content_rect)

  # Our layers

  def _above_bar(self) -> rl.Rectangle:
    c = self._content_rect
    return rl.Rectangle(c.x, c.y, c.width, c.height - BAR_ZONE)

  def _render(self, rect: rl.Rectangle):
    super()._render(rect)
    alert, _ = self.alert_renderer.will_render()
    self._layers_visible = bool(ui_state.started and self._draw_hud_controls and alert is None)
    self._chip = self._chips.update(snapshot(ui_state, self._navigating()), time.monotonic(), alert is not None)
    if not self._layers_visible:
      return
    self._chip_view.render(self._content_rect)
    self._limit.render(self._content_rect)
    self._bar.render(self._content_rect)

  def _handle_mouse_press(self, mouse_pos: MousePos):
    # Taps on our layers stay ours; anywhere else keeps upstream's behavior (toggling the sidebar).
    if self._layers_visible:
      hits = self._bar.hit_rects(self._content_rect)
      if self._offer() is not None:
        hits.append(self._limit.box(self._content_rect))
      if any(rl.check_collision_point_rec(mouse_pos, r) for r in hits):
        return
    super()._handle_mouse_press(mouse_pos)

  # State

  def _navigating(self) -> bool:
    return bool(self._params.get("NavDestination"))

  def _bar_state(self) -> BarState:
    metric = bool(ui_state.is_metric)
    conversion = 1.0 if metric else CV.KPH_TO_MPH
    set_speed = 0.0
    if ui_state.sm.valid.get("carState", False):
      v_cruise = float(ui_state.sm["carState"].vCruiseCluster)
      if 0 < v_cruise < V_CRUISE_UNSET:
        set_speed = v_cruise * conversion
    street = ""
    if ui_state.sm.valid.get("mapdOut", False):
      street = str(ui_state.sm["mapdOut"].roadName or "")
    navigating = self._navigating()
    arrive, left = self._route_progress(metric) if navigating else ("", "")
    return BarState(engaged=bool(ui_state.engaged), can_engage=bool(ui_state.started), set_speed=set_speed,
                    unit="km/h" if metric else "mph", street=street, navigating=navigating, arrive=arrive, left=left)

  def _route_progress(self, metric: bool) -> tuple[str, str]:
    """Arrival time and what's left, from navInstruction. ui_state doesn't subscribe to it, so this view does."""
    if self._nav_sm is None:
      import cereal.messaging as messaging
      self._nav_sm = messaging.SubMaster(["navInstruction"])
    self._nav_sm.update(0)
    if not self._nav_sm.valid.get("navInstruction", False):
      return "", ""
    nav = self._nav_sm["navInstruction"]
    seconds, meters = float(nav.timeRemaining), float(nav.distanceRemaining)
    arrive = (datetime.datetime.now() + datetime.timedelta(seconds=seconds)).strftime("%-I:%M %p")
    distance = f"{meters / 1000:.1f} km" if metric else f"{meters / 1609.344:.1f} mi"
    return arrive, f"{max(1, round(seconds / 60))} min · {distance}"

  def _preview(self) -> float:
    """Lateral acceleration the planned path needs PREVIEW_SECONDS ahead, as a share of the car's maximum."""
    if not ui_state.sm.valid.get("modelV2", False) or not ui_state.sm.valid.get("carState", False):
      return 0.0
    model = ui_state.sm["modelV2"]
    times, yaw_rates = list(model.orientationRate.t), list(model.orientationRate.z)
    if not times:
      return 0.0
    index = min(range(len(times)), key=lambda i: abs(times[i] - PREVIEW_SECONDS))
    max_lat = ui_state.CP.maxLateralAccel if ui_state.CP and ui_state.CP.maxLateralAccel else 3.0
    return float(yaw_rates[index]) * float(ui_state.sm["carState"].vEgo) / max_lat

  def _offer(self) -> LimitOffer | None:
    if not ui_state.sm.valid.get("starpilotPlan", False):
      return None
    plan = ui_state.sm["starpilotPlan"]
    conversion = CV.MS_TO_KPH if ui_state.is_metric else CV.MS_TO_MPH
    pending = float(plan.unconfirmedSlcSpeedLimit) * conversion
    current = float(plan.slcSpeedLimit) * conversion
    if not (plan.speedLimitChanged and pending > 1 and pending > current + 0.5) or math.isclose(pending, self._ignored_limit):
      self._offer_since = None
      return None
    self._offer_since = self._offer_since or time.monotonic()
    offset = float(plan.slcSpeedLimitOffset) * conversion
    return LimitOffer(pending, pending + offset, "km/h" if ui_state.is_metric else "mph",
                      str(plan.slcPresentedSpeedLimitSource or plan.slcSpeedLimitSource or "map"),
                      CONFIRM_TIMEOUT - (time.monotonic() - self._offer_since))

  # Actions

  def _open_menu(self) -> None:
    if self._click_callback is not None:
      self._click_callback()

  def _step_speed(self, direction: int) -> None:
    from openpilot.starpilot.system.wheel_controls.wheel_controlsd import set_controller_cruise_speed
    state = self._bar_state()
    step = max(1.0, self._params.get_float("CustomCruise") or 1.0)
    target = (round(state.set_speed / step) + direction) * step
    set_controller_cruise_speed(target, self._params, self._memory)

  def _toggle_engaged(self) -> None:
    from openpilot.starpilot.common.controller_actions import CONTROLLER_ACTION_DISENGAGE, CONTROLLER_ACTION_ENGAGE
    from openpilot.starpilot.system.wheel_controls.wheel_controlsd import trigger_controller_action
    trigger_controller_action(CONTROLLER_ACTION_DISENGAGE if ui_state.engaged else CONTROLLER_ACTION_ENGAGE, self._memory)

  def _end_route(self) -> None:
    self._params.remove("NavDestination")
    self._memory.remove("NavInstructionState")

  def _match_limit(self) -> None:
    self._memory.put_bool("SpeedLimitAccepted", True)

  def _ignore_limit(self) -> None:
    offer = self._offer()
    if offer is not None:
      self._ignored_limit = offer.limit
