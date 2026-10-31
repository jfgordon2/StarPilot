"""Developer View onroad (design/onroaddev.html).

- A panel on the right: LEAD (distance, gap, relative speed, radar or vision), DEVICE (CPU and temperature, GPU, RAM with
  bars, FPS) and CONTROLS (curve speed, limit source, lane widths). It replaces StarPilot's developer sidebar, which
  still decides when the panel shows (its DeveloperSidebar setting).
- A strip above the bar: accel, want, jerk, lateral accel and steering delay.
- A tag above the lead car: distance, gap and relative speed.

read() gathers every value from openpilot's and StarPilot's messages; the draw functions only draw, so they render
without a car.
"""
from __future__ import annotations

from dataclasses import dataclass

import pyray as rl

from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.layout import FILL, Align, column, inset, row

PANEL_W = T.px(256)                 # the mock's sidebar
WIDTH = PANEL_W + T.px(10)          # with its gap from the road view
STRIP_H = T.px(30)
TILE_FILL = T._hex("1E2227")
LABEL = T._hex("9FAABA")
BAR_INK = T.ACCENT_TEXT
STRIP_FILL = rl.Color(0x0B, 0x0D, 0x10, 0x99)
TAG_FILL = rl.Color(0x0B, 0x0D, 0x10, 0xE6)
MONO, BOLD = T.FONT_MONO, T.FONT_MONO_BOLD   # the mock sets the panel, strip and tag in JetBrains Mono


@dataclass
class Lead:
  distance: str    # "38 m"
  gap: str         # "1.4 s"
  rel_speed: str   # "−2 mph"
  closing: bool    # the lead is slower: rel speed shows amber
  source: str      # "radar" or "vision"


@dataclass
class DevData:
  lead: Lead | None = None
  cpu: float = 0.0          # 0..1
  cpu_temp: str = ""        # "61°C"
  gpu: float = 0.0
  ram: float = 0.0
  ram_text: str = ""        # "3.1 GB"
  fps: str = ""
  curve: str = "idle"
  limit_source: str = "none"
  lanes: str = "—"
  accel: str = "+0.00"
  want: str = "+0.00"
  jerk: str = "0.0"
  lat: str = "0.0 m/s²"
  delay: str = "0.00 s"


# ── Drawing ──

def _section(rect: rl.Rectangle, y: float, title: str) -> float:
  h = draw.line_height(T.SIZE_CAPTION)
  draw.caption(rl.Rectangle(rect.x, y, rect.width, h), title, T.ACCENT_TEXT)
  return y + h + T.px(8)


def _pair(rect: rl.Rectangle, y: float, label: str, value: str) -> float:
  h = draw.line_height(T.font_px(14))
  line = rl.Rectangle(rect.x, y, rect.width, h)
  draw.text(line, label, T.font_px(14), LABEL, MONO)
  draw.text(line, value, T.font_px(14), T.TEXT, MONO, Align.END)
  return y + h + T.px(7)


def _meter(rect: rl.Rectangle, y: float, share: float) -> float:
  track = rl.Rectangle(rect.x, y, rect.width, T.px(5))
  draw.fill(track, T.TRACK, T.px(3))
  if share > 0:
    draw.fill(rl.Rectangle(track.x, y, max(track.height, track.width * min(1.0, share)), track.height), BAR_INK, T.px(3))
  return y + track.height + T.px(7)


def draw_panel(rect: rl.Rectangle, data: DevData) -> None:
  """The right-hand panel: rect is the strip beside the road view (WIDTH wide)."""
  draw.fill(rect, T.BG)
  panel = rl.Rectangle(rect.x, rect.y + T.px(10), PANEL_W, rect.height - T.px(20))
  draw.fill(panel, T._hex("13161A"), T.px(18))
  body = inset(panel, T.px(14))
  y = _section(body, body.y, "Lead")
  tile_h = T.px(52)
  lead = data.lead
  tiles = [("distance", lead.distance if lead else "—", None), ("gap", lead.gap if lead else "—", None),
           ("rel speed", lead.rel_speed if lead else "—", T.WARNING if lead and lead.closing else None),
           ("source", lead.source if lead else "none", None)]
  for i in range(0, 4, 2):
    for (label, value, ink), cell in zip(tiles[i:i + 2], row(rl.Rectangle(body.x, y, body.width, tile_h), [FILL, FILL], T.px(6)), strict=True):
      draw.fill(cell, TILE_FILL, T.px(10))
      inner = inset(cell, x=T.px(10), y=T.px(7))
      top, bottom = column(inner, [draw.line_height(T.font_px(11)), FILL], T.px(3))
      draw.text(top, label, T.font_px(11), LABEL, MONO)
      draw.text(bottom, draw.fit(value, T.font_px(18), BOLD, bottom.width), T.font_px(18), ink or T.TEXT, BOLD)
    y += tile_h + T.px(6)
  y = _section(body, y + T.px(6), "Device")
  cpu = f"{round(data.cpu * 100)}%" + (f" · {data.cpu_temp}" if data.cpu_temp else "")
  y = _meter(body, _pair(body, y, "CPU", cpu), data.cpu)
  y = _meter(body, _pair(body, y, "GPU", f"{round(data.gpu * 100)}%"), data.gpu)
  y = _meter(body, _pair(body, y, "RAM", data.ram_text), data.ram)
  y = _pair(body, y, "FPS", data.fps)
  y = _section(body, y + T.px(6), "Controls")
  y = _pair(body, y, "curve spd", data.curve)
  y = _pair(body, y, "limit src", data.limit_source)
  _pair(body, y, "lanes L/R", data.lanes)


def draw_strip(rect: rl.Rectangle, data: DevData) -> None:
  """accel, want, jerk, lat and delay in one dark band, spread evenly."""
  draw.fill(rect, STRIP_FILL)
  parts = [("accel", data.accel), ("want", data.want), ("jerk", data.jerk), ("lat", data.lat), ("delay", data.delay)]
  for (label, value), cell in zip(parts, row(inset(rect, x=T.px(20)), [FILL] * len(parts), T.px(12)), strict=True):
    lw = draw.text_width(label + " ", T.font_px(13), MONO)
    vw = draw.text_width(value, T.font_px(13), BOLD)
    x = cell.x + (cell.width - lw - vw) / 2
    draw.text(rl.Rectangle(x, cell.y, lw, cell.height), label + " ", T.font_px(13), T.TEXT_SECONDARY, MONO)
    draw.text(rl.Rectangle(x + lw, cell.y, vw, cell.height), value, T.font_px(13), T.TEXT, BOLD)


def draw_lead_tag(center_x: float, top_y: float, lead: Lead) -> None:
  """The tag above the lead car: distance, gap, then relative speed in amber when closing."""
  parts = [(lead.distance, T.TEXT, BOLD), (lead.gap, LABEL, BOLD),
           (lead.rel_speed, T.WARNING if lead.closing else T.TEXT_SECONDARY, BOLD)]
  size, gap, pad = T.font_px(14), T.px(12), T.px(12)
  widths = [draw.text_width(text, size, weight) for text, _, weight in parts]
  w = sum(widths) + gap * 2 + pad * 2
  h = T.px(30)
  box = rl.Rectangle(center_x - w / 2, top_y - h - T.px(14), w, h)
  draw.fill(box, TAG_FILL, T.px(10))
  draw.stroke(box, T.TRACK, T.px(10), T.px(1))
  x = box.x + pad
  for (text, ink, weight), width in zip(parts, widths, strict=True):
    draw.text(rl.Rectangle(x, box.y, width, box.height), text, size, ink, weight)
    x += width + gap


# ── Reading ──

def _signed(value: float, digits: int = 2) -> str:
  return f"{value:+.{digits}f}".replace("-", "−")


def lead_of(lead, v_ego: float, metric: bool) -> Lead | None:
  """radarState's lead, in the driver's units."""
  if lead is None or not lead.status:
    return None
  from openpilot.common.constants import CV
  distance = f"{round(lead.dRel)} m" if metric else f"{round(lead.dRel * CV.METER_TO_FOOT)} ft"
  rel = lead.vRel * (CV.MS_TO_KPH if metric else CV.MS_TO_MPH)
  return Lead(distance, f"{lead.dRel / max(v_ego, 1.0):.1f} s", f"{round(rel):+d} {'km/h' if metric else 'mph'}".replace("-", "−"),
              rel < -0.5, "radar" if getattr(lead, "radar", False) else "vision")


def read(ui_state) -> DevData:
  """Every value the Developer View shows, from the messages the UI already receives."""
  from openpilot.common.constants import CV
  sm = ui_state.sm
  get = lambda name: sm[name] if sm.valid.get(name, False) else None  # noqa: E731
  car, control, plan, device, delay = get("carState"), get("carControl"), get("starpilotPlan"), get("deviceState"), get("liveDelay")
  controls, radar = get("controlsState"), get("radarState")
  metric = bool(ui_state.is_metric)
  v_ego = car.vEgo if car else 0.0
  data = DevData()
  data.lead = lead_of(radar.leadOne if radar else None, v_ego, metric)
  if device:
    cpus = list(device.cpuUsagePercent)
    data.cpu = (sum(cpus) / len(cpus) / 100.0) if cpus else 0.0
    data.cpu_temp = f"{round(device.maxTempC)}°C"
    data.gpu = device.gpuUsagePercent / 100.0
    data.ram = device.memoryUsagePercent / 100.0
    data.ram_text = f"{8.0 * data.ram:.1f} GB"     # as StarPilot reckons it
  data.fps = f"{round(rl.get_fps())}"
  if plan:
    speed = plan.cscSpeed * (CV.MS_TO_KPH if metric else CV.MS_TO_MPH)
    data.curve = f"active · {round(speed)} {'km/h' if metric else 'mph'}" if plan.cscControllingSpeed else "idle"
    data.limit_source = (plan.slcPresentedSpeedLimitSource or plan.slcSpeedLimitSource or "none").lower()
    unit, scale = ("m", 1.0) if metric else ("ft", CV.METER_TO_FOOT)
    data.lanes = f"{plan.laneWidthLeft * scale:.1f} / {plan.laneWidthRight * scale:.1f} {unit}"
    data.jerk = f"{plan.accelerationJerk:.1f}"
  if car:
    data.accel = _signed(car.aEgo)
  if control:
    data.want = _signed(control.actuators.accel)
  if controls and car:
    data.lat = f"{abs(car.vEgo ** 2 * controls.curvature):.1f} m/s²"
  if delay:
    data.delay = f"{delay.lateralDelay:.2f} s"
  return data


def developer_ui_on(ui_state, params) -> bool:
  """StarPilot's Developer UI switch (the Developer View bundle turns it on)."""
  return bool(ui_state.starpilot_toggles.get("developer_ui", params.get_bool("DeveloperUI")))


def developer_sidebar():
  """The right panel, shown when StarPilot's developer sidebar would be. Made on the device only."""
  from openpilot.selfdrive.ui.onroad.starpilot.developer_sidebar import DeveloperSidebar
  from openpilot.selfdrive.ui.ui_state import ui_state

  class EssentialsDeveloperSidebar(DeveloperSidebar):
    def update(self):
      super().update()   # StarPilot decides whether the sidebar shows
      self._data = read(ui_state) if self._visible else None

    def render(self, sidebar_rect: rl.Rectangle):
      if self._visible and getattr(self, "_data", None) is not None:
        draw_panel(sidebar_rect, self._data)

  return EssentialsDeveloperSidebar()
