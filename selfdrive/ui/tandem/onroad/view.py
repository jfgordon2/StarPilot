"""The Essentials onroad view: StarPilot's view with the Essentials layers on top.

It subclasses StarPilotOnroadView and overrides only the parts Essentials replaces:
- the torque bar becomes the headroom arc, above the bar;
- the road name moves into the bar;
- the paused and weather badges beside the driver monitor become status chips;
- the current speed, the speed limit sign and the turn card are drawn in the Essentials style, with StarPilot still
  deciding when each shows; the speed pill carries Essentials' turn signal in place of StarPilot's animations;
- the driving personality button, the experimental-mode wheel, the favorites menu, the side-camera bubble and the stopped
  timer are removed;
- the bottom widgets (the driver monitor icon) sit above the bar.
Everything else, from the camera and path to alerts, is upstream's.
"""
from __future__ import annotations

import datetime
import time

import pyray as rl

from openpilot.common.constants import CV
from openpilot.common.params import Params
from openpilot.selfdrive.ui.onroad.augmented_road_view import CAMERA_VIEW_DRIVER
from openpilot.selfdrive.ui.onroad.starpilot.starpilot_onroad_view import StarPilotOnroadView
from openpilot.selfdrive.ui.onroad.starpilot.widget_layout_manager import WidgetLayoutManager
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.application import MousePos
from openpilot.selfdrive.ui.onroad.starpilot.navigation_card import NavigationCardRenderer
from openpilot.selfdrive.ui.tandem import tokens as T
from openpilot.selfdrive.ui.tandem.onroad.layers import (AT_LIMIT, BAR_ZONE, LIMIT_BORDER_COLOR, LIMIT_LANE_COLOR, SIGN_MARGIN, SIGN_TILE,
                                                         ArcState, BarState, Headroom, HeadroomArc, HelpSteer,
                                                         LimitCard, LimitOffer, OnroadBar, StatusChip, draw_speed, draw_speed_limit,
                                                         draw_turn_card, sign_tile)
from openpilot.selfdrive.ui.tandem.onroad.status import ChipPicker, snapshot
from openpilot.selfdrive.ui.tandem.onroad.limits import LimitOfferState

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


class EssentialsTurnCard(NavigationCardRenderer):
  """StarPilot's turn card, keeping its route data, drawn as the mock's card top left. Taps do nothing: End route is in the bar."""

  def __init__(self):
    super().__init__()
    self.box: rl.Rectangle | None = None   # where it was drawn this frame, if it was

  def _render(self, rect: rl.Rectangle) -> None:
    self.box = None
    if not self._valid:
      return
    text = " ".join(t for t in (self._primary_text, self._secondary_text) if t)
    self.box = draw_turn_card(rect, self._distance, text, self._maneuver_type, self._modifier)


class _NoFavorites:
  """Stands in for StarPilot's favorites menu (the lower-left gesture), which Essentials doesn't show."""

  def process_mouse_events(self, events, rect) -> bool:
    return False

  def blocks_pointer(self, mouse_pos) -> bool:
    return False

  def render(self, rect) -> None:
    pass

  def render_corner_hint(self, rect) -> None:
    pass

  def collapse(self) -> None:
    pass


class _NoStoppedTimer:
  """Stands in for StarPilot's stopped timer, which Essentials doesn't show: the speed always stays."""
  replaces_current_speed = False
  is_visible = False

  def render(self, rect=None) -> None:
    pass


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
    self._memory.put_nonblocking("SteeringHeadroomWarning", 0.0)
    self._chips = ChipPicker()
    self._chip = None
    self._headroom = Headroom()
    self._arc_state = ArcState()
    self._headroom_warning = False
    self._headroom_chimed = False
    self._limit_offer = LimitOfferState()
    self._bar = OnroadBar(self._bar_state, self._open_menu, self._step_speed, self._toggle_engaged, self._end_route)
    self._chip_view = StatusChip(lambda: self._chip, lambda: SIGN_MARGIN + SIGN_TILE[1] + T.px(12) if self._sign_right else T.px(22))
    self._arc = HeadroomArc(lambda: self._arc_state)
    self._help = HelpSteer()
    self._limit = LimitCard(self._offer, self._match_limit, self._ignore_limit,
                            lambda: (self._turn_card.box.y + self._turn_card.box.height - self._content_rect.y + T.px(12))
                            if self._turn_card.box is not None else T.px(16))
    # StarPilot's HUD keeps deciding when the speed and turn card show; they're drawn in the Essentials style.
    self._turn_card = EssentialsTurnCard()
    self._hud_renderer._navigation_card = self._turn_card
    self._hud_renderer._draw_current_speed = self._draw_current_speed
    self._favorite_radial_menu = _NoFavorites()
    self._pip_sidecam.set_visible(False)   # the side-camera bubble: a Galaxy developer feature, and it would cover the bar
    self._stopped_timer_widget = _NoStoppedTimer()
    self._sign_right = False
    self._layers_visible = False
    self._nav_sm = None

  # Upstream pieces replaced here

  def _draw_current_speed(self, rect: rl.Rectangle) -> None:
    sm = ui_state.sm
    car = sm["carState"] if sm.valid.get("carState", False) and sm.recv_frame["carState"] >= ui_state.started_frame else None
    left, right = (bool(car.leftBlinker), bool(car.rightBlinker)) if car is not None else (False, False)
    draw_speed(rect, self._hud_renderer.speed, "km/h" if ui_state.is_metric else "mph", self._hud_renderer.speed_offset_y,
               left, right, time.monotonic())

  def _render_turn_signals(self) -> None:
    pass   # Essentials' turn signal is in the speed pill

  def _render_speed_card(self):
    """The posted limit StarPilot's speed card would show, as the mock's sign; hidden while the new-limit card asks."""
    self._sign_right = False
    widget = self._unified_speed_widget
    if self._full_alert_showing():
      widget.collapse_sources()
      return
    widget._refresh_snapshot()
    limit = widget._presentation.posted_speed_text
    if limit in ("", "–") or self._offer() is not None:
      return
    self._sign_right = self._turn_card.box is not None
    draw_speed_limit(sign_tile(self._content_rect, self._sign_right), limit, ui_state.ui_params.get_bool("UseVienna"))

  def _render_road_name(self):
    pass

  def _render_bottom_row_widgets(self):
    pass

  def _render_torque_bar(self) -> None:
    self._arc.render(self._above_bar())
    if self._headroom_warning:
      self._help.render(self._content_rect)

  def _update_state(self) -> None:
    super()._update_state()
    self._update_headroom()

  def _update_headroom(self) -> None:
    # Compute before the model and border draw, so all warning layers share this frame's state.
    sm = ui_state.sm
    fresh = all(sm.valid.get(service, False) and sm.alive.get(service, False)
                and sm.recv_frame[service] >= ui_state.started_frame
                for service in ("carControl", "carOutput", "controlsState", "carState", "selfdriveState"))
    active = bool(ui_state.started and fresh and sm["carControl"].latActive and not sm["carState"].steeringPressed
                  and not self.is_in_reverse() and self._camera_view() != CAMERA_VIEW_DRIVER)
    if active:
      self._torque_bar._update_state()   # upstream's estimate, including angle-controlled cars
    usage = float(self._torque_bar._torque_filter.x) if active else 0.0
    now = time.monotonic()
    stage = self._headroom.stage(usage, now, active)
    self._arc_state = ArcState(usage, self._preview() if active else 0.0, active, stage)
    # Stock/custom alerts, including their exit animation, retain visual priority.
    clear = self.alert_renderer.get_alert(sm) is None and self.alert_renderer.will_render()[0] is None
    warning = active and stage == AT_LIMIT and clear
    self.model_renderer.lane_line_color_override = LIMIT_LANE_COLOR if warning else None
    if warning and not self._headroom_chimed:
      self._memory.put_nonblocking("SteeringHeadroomWarning", now)
      self._headroom_chimed = True
    elif self._headroom_warning and not warning:
      self._memory.put_nonblocking("SteeringHeadroomWarning", 0.0)
    if stage != AT_LIMIT:
      self._headroom_chimed = False
    self._headroom_warning = warning

  def _get_border_color(self):
    return LIMIT_BORDER_COLOR if self._headroom_warning else super()._get_border_color()

  def hide_event(self):
    self._headroom.stage(0.0, time.monotonic(), active=False)
    self._arc_state = ArcState()
    self._headroom_warning = self._headroom_chimed = False
    self.model_renderer.lane_line_color_override = None
    self._memory.put_nonblocking("SteeringHeadroomWarning", 0.0)
    super().hide_event()

  # Our layers

  def _above_bar(self) -> rl.Rectangle:
    c = self._content_rect
    return rl.Rectangle(c.x, c.y, c.width, c.height - BAR_ZONE)

  def _render(self, rect: rl.Rectangle):
    super()._render(rect)
    self._offer()   # observe limit changes even when an alert is covering the card
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
    now = time.monotonic()
    pending_ms = float(plan.unconfirmedSlcSpeedLimit) if plan.speedLimitChanged else 0.0
    self._limit_offer.observe(pending_ms, float(plan.slcSpeedLimit), str(plan.slcSpeedLimitSource), now)
    conversion = CV.MS_TO_KPH if ui_state.is_metric else CV.MS_TO_MPH
    pending = pending_ms * conversion
    current = float(plan.slcSpeedLimit) * conversion
    since = self._limit_offer.since
    if since is None or not (plan.speedLimitChanged and pending > current + 0.5) or self._limit_offer.ignored:
      return None
    offset = float(plan.slcSpeedLimitOffset) * conversion
    return LimitOffer(pending, pending + offset, "km/h" if ui_state.is_metric else "mph",
                      str(plan.slcPresentedSpeedLimitSource or plan.slcSpeedLimitSource or "map"),
                      CONFIRM_TIMEOUT - (now - since), CONFIRM_TIMEOUT, ui_state.ui_params.get_bool("UseVienna"))

  def _offroad_transition(self) -> None:
    super()._offroad_transition()
    self._limit_offer = LimitOfferState()

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
      self._limit_offer.ignore()
