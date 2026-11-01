"""The Essentials onroad view: StarPilot's view with the Essentials layers on top.

It subclasses StarPilotOnroadView and overrides only the parts Essentials replaces:
- the torque bar becomes the headroom arc, above the bar;
- the road name moves into the bar;
- the paused and weather badges beside the driver monitor become a status chip, bottom left above the bar;
- the current speed, the speed limit sign and the turn card are drawn in the Essentials style, with StarPilot still
  deciding when each shows; the speed pill carries Essentials' turn signal in place of StarPilot's animations;
- the driving personality button, the experimental-mode wheel, the favorites menu, the side-camera bubble and the stopped
  timer are removed;
- the driver monitor icon moves top right, drawn as an Essentials tile from upstream's driver state;
- alerts are drawn in the mock's three levels (info pill, warning card, critical takeover), with upstream still choosing them.
Everything else, from the camera and path to alerts, is upstream's.
"""
from __future__ import annotations

import datetime
from collections.abc import Callable
import time

import pyray as rl

from openpilot.common.constants import CV
from openpilot.common.params import Params
from openpilot.selfdrive.ui.onroad.alert_renderer import AlertRenderer
from openpilot.selfdrive.ui.onroad.augmented_road_view import CAMERA_VIEW_DRIVER
from openpilot.selfdrive.ui.onroad.starpilot.starpilot_onroad_view import StarPilotOnroadView
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.application import MousePos
from openpilot.selfdrive.ui.onroad.starpilot.navigation_card import NavigationCardRenderer
from openpilot.selfdrive.ui.tandem import tokens as T
from openpilot.selfdrive.ui.tandem.onroad import alerts
from openpilot.selfdrive.ui.tandem.onroad.developer import STRIP_H, DevData, developer_view_on, draw_lead_tag, draw_strip, lead_of, read
from openpilot.selfdrive.ui.tandem.onroad.layers import (AT_LIMIT, BAR_HEIGHT, BAR_MARGIN, LIMIT_BORDER_COLOR, LIMIT_LANE_COLOR, ArcState, BarState,
                                                         Headroom, HeadroomArc, HelpSteer, ARC, DEV_ARC, LimitCard, LimitOffer, OnroadBar, StatusChip,
                                                         dm_tile, draw_driver_monitor, draw_speed, draw_speed_limit,
                                                         draw_turn_card, sign_tile, TURN_BELOW_SIGN, TURN_CARD_TOP)
from openpilot.selfdrive.ui.tandem.onroad.status import ChipPicker, snapshot
from openpilot.selfdrive.ui.tandem.onroad.limits import LimitOfferState

CONFIRM_TIMEOUT = 30.0      # StarPilot rejects an unanswered higher limit after 30 s
PREVIEW_SECONDS = 2.5
V_CRUISE_UNSET = 255


class EssentialsTurnCard(NavigationCardRenderer):
  """StarPilot's turn card, keeping its route data, drawn as the mock's card top left, below the speed limit sign or
  the new-limit card when one is showing. Taps do nothing: End route is in the bar."""

  def __init__(self, top: Callable[[], float]):
    super().__init__()
    self._top = top
    self.box: rl.Rectangle | None = None   # where it was drawn this frame, if it was

  def _render(self, rect: rl.Rectangle) -> None:
    self.box = None
    if not self._valid:
      return
    text = " ".join(t for t in (self._primary_text, self._secondary_text) if t)
    self.box = draw_turn_card(rect, self._distance, text, self._maneuver_type, self._modifier, self._top())


class EssentialsAlertRenderer(AlertRenderer):
  """StarPilot's alert renderer, keeping its choice of alert, timing and fades, drawn in the mock's three levels."""

  headroom_warning: Callable[[], bool] = staticmethod(lambda: False)   # the view's Help steer warning is up

  def get_alert(self, sm):
    previous = self._prev_alert
    alert = super().get_alert(sm)
    if alert is not None and (alerts.shown_as_chip(alert.alert_type)
                              or (alerts.replaced_by_headroom(alert.alert_type) and self.headroom_warning())):
      self._prev_alert = previous   # not shown, so nothing to fade out either; the status chip says it
      return None
    return alert

  def level(self) -> str | None:
    alert, _ = self.will_render()
    return alerts.level(alert.size, alert.status, alert.alert_type) if alert is not None else None

  def _get_alert_rect(self, rect: rl.Rectangle, size: int) -> rl.Rectangle:
    alert = self._current_alert or self._prev_alert
    kind = alerts.level(alert.size, alert.status, alert.alert_type) if alert is not None else alerts.REVERSE
    if kind == alerts.REVERSE:
      return super()._get_alert_rect(rect, size)
    return alerts.box(rect, kind, alert.text1, alert.text2)

  def _draw_background(self, alert) -> None:
    kind = alerts.level(alert.size, alert.status, alert.alert_type)
    if kind == alerts.REVERSE:
      return super()._draw_background(alert)
    where = rl.Rectangle(self._rect.x, self._alert_y_filter.x, self._rect.width, self._rect.height)   # slides as upstream's does
    alerts.draw_alert(where, kind, alert.text1, alert.text2, self._alpha_filter.x)

  def _draw_text(self, alert) -> None:
    if alerts.level(alert.size, alert.status, alert.alert_type) == alerts.REVERSE:
      super()._draw_text(alert)   # drawn with the background above otherwise


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
    zones = self.layout_manager.zones
    # StarPilot widgets Essentials replaces: the personality button, its driver monitor and steering wheel icons, and the
    # Aether Gauge (Conditional Experimental's "STOPPED"/"SLOW"/curve/light indicator), which the status chip says instead.
    for zone, widget in (("bottom", self._personality_button_widget), ("bottom", self._driver_monitor_widget),
                         ("right", self._steering_wheel_widget), ("left", self._aethergauge_widget)):
      if widget in zones[zone]:
        zones[zone].remove(widget)
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
    self._chip_view = StatusChip(lambda: self._chip)
    self._arc = HeadroomArc(lambda: self._arc_state, lambda: DEV_ARC if self._dev is not None else ARC)   # each mock's curve
    self._help = HelpSteer()
    self._limit = LimitCard(self._offer, self._match_limit, self._ignore_limit)   # in the sign's place, top left
    # StarPilot's HUD keeps deciding when the speed and turn card show; they're drawn in the Essentials style.
    self._turn_card = EssentialsTurnCard(self._turn_top)
    self._hud_renderer._navigation_card = self._turn_card
    self._hud_renderer._draw_current_speed = self._draw_current_speed
    self._favorite_radial_menu = _NoFavorites()
    self._pip_sidecam.set_visible(False)   # the side-camera bubble: a Galaxy developer feature, and it would cover the bar
    self._stopped_timer_widget = _NoStoppedTimer()
    self.alert_renderer = EssentialsAlertRenderer()
    self.alert_renderer.headroom_warning = lambda: self._headroom_warning   # hides steerSaturated while Help steer shows
    self._layers_visible = False
    self._dev: DevData | None = None            # Developer View's readout, while StarPilot's Developer UI is on
    self.model_renderer._draw_lead_metrics = self._lead_tag   # Lead Insights' text becomes the mock's tag
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
    if self._full_alert_showing() or self.alert_renderer.level() == alerts.CRITICAL:
      self._unified_speed_widget.collapse_sources()
      return
    limit = self._posted_limit()
    if limit is not None:
      draw_speed_limit(sign_tile(self._content_rect), limit, ui_state.ui_params.get_bool("UseVienna"), self._sign_note())

  def _turn_top(self) -> float:
    """The turn card stays below whatever holds the top left corner: the new-limit card while it asks, else the sign."""
    if self._offer() is not None:
      box = self._limit.box(self._content_rect)
      return box.y + box.height - self._content_rect.y + T.px(12)
    return TURN_BELOW_SIGN if self._posted_limit() is not None else TURN_CARD_TOP

  def _posted_limit(self) -> str | None:
    """The limit for the sign, or None when it's hidden: no limit known, or the new-limit card is asking."""
    widget = self._unified_speed_widget
    widget._refresh_snapshot()   # cached per frame
    limit = widget._presentation.posted_speed_text
    return None if limit in ("", "–") or self._offer() is not None else limit

  def _render_driver_monitor(self) -> None:
    """Upstream's driver state (its fades already hide it for alerts, stale data and the hide toggle), as our tile."""
    dm = self.driver_state_renderer
    dm._update_state()
    attentive = dm._color_fade_filter.update(0.0 if dm._awareness_unfull else 1.0)
    if not (ui_state.started and self._draw_hud_controls) or self.alert_renderer.will_render()[0] is not None:
      return
    draw_driver_monitor(dm_tile(self._content_rect), dm._fade_filter.x, attentive, dm.is_active)

  def _sign_note(self) -> str:
    """Developer View's line under the sign: where the limit came from and the offset ("MAP · +3")."""
    if self._dev is None or not self._dev.show_source or not ui_state.sm.valid.get("starpilotPlan", False):
      return ""
    plan = ui_state.sm["starpilotPlan"]
    offset = round(plan.slcSpeedLimitOffset * (CV.MS_TO_KPH if ui_state.is_metric else CV.MS_TO_MPH))
    return f"{self._dev.limit_source.upper()} · {offset:+d}".replace("-", "−")

  def _lead_tag(self, adjacent, chevron, lead_data) -> None:
    """Lead Insights for the lead car: our tag above it. Adjacent cars keep only StarPilot's markers, as in the mock."""
    if adjacent:
      return
    car = ui_state.sm["carState"]
    lead = lead_of(lead_data, car.vEgo, bool(ui_state.is_metric))
    if lead is not None:
      draw_lead_tag(chevron[1][0], min(p[1] for p in chevron), lead)

  def _render_developer_metrics(self):
    """Developer View's readout, gathered here; StarPilot's device line moves to our panel and the controls to our strip."""
    self._dev = read(ui_state) if developer_view_on(ui_state, self._params) else None   # drawn as our strip, see _render

  def _render_road_name(self):
    pass

  def _render_bottom_row_widgets(self):
    pass

  def _render_torque_bar(self) -> None:
    self._arc.render(self._content_rect)
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
    if self._headroom_warning:
      return LIMIT_BORDER_COLOR
    return alerts.border(self.alert_renderer.level()) or super()._get_border_color()

  def hide_event(self):
    self._headroom.stage(0.0, time.monotonic(), active=False)
    self._arc_state = ArcState()
    self._headroom_warning = self._headroom_chimed = False
    self.model_renderer.lane_line_color_override = None
    self._memory.put_nonblocking("SteeringHeadroomWarning", 0.0)
    super().hide_event()

  # Our layers

  def _render(self, rect: rl.Rectangle):
    super()._render(rect)
    self._offer()   # observe limit changes even when an alert is covering the card
    alert, _ = self.alert_renderer.will_render()
    self._layers_visible = bool(ui_state.started and self._draw_hud_controls and alert is None)
    self._chip = self._chips.update(snapshot(ui_state, self._navigating()), time.monotonic(), alert is not None)
    self._render_driver_monitor()
    if not self._layers_visible:
      return
    c = self._content_rect
    lift = 0.0
    if self._dev is not None and self._dev.strip:   # the picked metrics, just above the bar; the chip moves up over it
      lift = STRIP_H + T.px(6)
      draw_strip(rl.Rectangle(c.x, c.y + c.height - BAR_MARGIN - BAR_HEIGHT - lift, c.width, STRIP_H), self._dev)
    self._chip_view.render(rl.Rectangle(c.x, c.y, c.width, c.height - lift))
    self._limit.render(c)
    self._bar.render(c)

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
