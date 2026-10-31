"""Developer View onroad (design/onroaddev.html): StarPilot's developer sidebar and device stats in our style.

The sidebar keeps StarPilot's DeveloperSidebar: which metrics the driver picked, how each is computed, and its tuning
colors. We draw them as tiles on our panel. The device stats (CPU, GPU, temperature, memory, FPS) follow StarPilot's
toggles too, as a strip above the bar instead of text in the border.
"""
from __future__ import annotations

import pyray as rl

from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.layout import FILL, column, inset, row

TILE_H = T.px(64)
STRIP_H = T.px(34)
STRIP_FILL = rl.Color(0x0B, 0x0D, 0x10, 200)


def draw_metric_tiles(rect: rl.Rectangle, metrics: list[tuple[str, str, rl.Color | None]]) -> None:
  """The sidebar: a panel of tiles (two to a row when there is room), each a small label over its value. A value keeps StarPilot's color when
  it marks a tuning source (live or changed); otherwise it's our text color."""
  draw.fill(rect, T.BG)
  panel = inset(rect, x=T.px(10), y=T.px(10))
  draw.fill(panel, T.SURFACE_2, T.RADIUS_PANEL)
  body = inset(panel, x=T.px(14), y=T.px(14))
  caption, grid = column(body, [draw.line_height(T.SIZE_CAPTION), FILL], T.px(10))
  draw.caption(caption, "Developer", T.ACCENT_TEXT)
  per_row = 2 if grid.width >= T.px(260) else 1   # StarPilot's sidebar is narrow (300 px): one tile per row there
  y = grid.y
  for i in range(0, len(metrics), per_row):
    group = metrics[i:i + per_row]
    cells = row(rl.Rectangle(grid.x, y, grid.width, TILE_H), [FILL] * per_row, T.px(10))
    for (label, value, color), cell in zip(group, cells, strict=False):
      draw.fill(cell, T.CONTROL, T.px(12))
      text = inset(cell, x=T.px(12), y=T.px(8))
      top, bottom = column(text, [draw.line_height(T.font_px(12)), FILL], T.px(2))
      draw.text(top, draw.fit(label.lower(), T.font_px(12), T.FONT, top.width), T.font_px(12), T.TEXT_MUTED)
      draw.text(bottom, draw.fit(value or "—", T.font_px(18), T.FONT_BOLD, bottom.width), T.font_px(18), color or T.TEXT, T.FONT_BOLD)
    y += TILE_H + T.px(10)
    if y + TILE_H > grid.y + grid.height:
      break


def draw_strip(rect: rl.Rectangle, parts: list[tuple[str, str]]) -> None:
  """Device stats in one dark band: each a muted label and a bold value, spread evenly."""
  draw.fill(rect, STRIP_FILL)
  if not parts:
    return
  for (label, value), cell in zip(parts, row(inset(rect, x=T.px(20)), [FILL] * len(parts), T.px(12)), strict=True):
    lw = draw.text_width(label + " ", T.font_px(14))
    vw = draw.text_width(value, T.font_px(14), T.FONT_BOLD)
    x = cell.x + (cell.width - lw - vw) / 2
    draw.text(rl.Rectangle(x, cell.y, lw, cell.height), label + " ", T.font_px(14), T.TEXT_TERTIARY)
    draw.text(rl.Rectangle(x + lw, cell.y, vw, cell.height), value, T.font_px(14), T.TEXT, T.FONT_BOLD)


class DeviceStats:
  """StarPilot's developer metrics line, as label and value pairs: the same toggles, the same FPS min/max/average."""

  def __init__(self):
    self._min_fps, self._max_fps, self._avg_fps = 99.0, 0.0, 0.0

  def parts(self, params) -> list[tuple[str, str]]:
    from openpilot.selfdrive.ui.ui_state import ui_state
    toggles = ui_state.starpilot_toggles
    debug_mode = bool(toggles.get("debug_mode", params.get_bool("DebugMode")))
    developer = (bool(toggles.get("developer_ui", params.get_bool("DeveloperUI"))) and params.get_bool("DeveloperMetrics")) or debug_mode

    def on(toggle_key: str, param_key: str, debug_override: bool = False) -> bool:
      if debug_mode and debug_override:
        return True
      if developer and toggle_key in toggles:
        return bool(toggles.get(toggle_key))
      return bool(developer and params.get_bool(param_key))

    show = {"fps": on("show_fps", "FPSCounter", True), "cpu": on("cpu_metrics", "ShowCPU", True), "gpu": on("gpu_metrics", "ShowGPU"),
            "temp": on("numerical_temp", "NumericalTemp", True), "ram": on("memory_metrics", "ShowMemoryUsage", True)}
    if not any(show.values()):
      return []
    fps = rl.get_fps()
    if fps > 0:
      self._min_fps, self._max_fps = min(self._min_fps, fps), max(self._max_fps, fps)
      self._avg_fps = fps if self._avg_fps == 0.0 else self._avg_fps + (fps - self._avg_fps) / 300.0
    sm = ui_state.sm
    state = sm["deviceState"] if sm.valid.get("deviceState", False) else None
    cpus = list(state.cpuUsagePercent) if state else []
    out = []
    if show["cpu"]:
      out.append(("CPU", f"{int(sum(cpus) / len(cpus)) if cpus else 0}%"))
    if show["gpu"]:
      out.append(("GPU", f"{int(state.gpuUsagePercent) if state else 0}%"))
    if show["temp"]:
      out.append(("Temp", f"{int(state.maxTempC) if state else 0}°C"))
    if show["ram"]:
      mem = int(state.memoryUsagePercent) if state else 0
      out.append(("RAM", f"{8.0 * mem / 100.0:.1f} GB"))
    if show["fps"]:
      out.append(("FPS", f"{round(fps)} · {round(self._min_fps)}–{round(self._max_fps)}"))
    return out


def developer_sidebar():
  """StarPilot's developer sidebar, drawn as our tiles. Made on the device only (it reads the car's messages)."""
  from openpilot.selfdrive.ui.onroad.starpilot.developer_sidebar import DeveloperSidebar

  class EssentialsDeveloperSidebar(DeveloperSidebar):
    def render(self, sidebar_rect: rl.Rectangle):
      if not self._visible or not self._active_ids:
        return
      default = self._metric_color
      metrics = []
      for metric_id in self._active_ids:
        if metric_id not in self._metrics:
          continue
        label, value = self._metrics[metric_id]
        if not value:                      # the model name metric: its name is the value
          label, value = "Model", label
        color = self._metric_colors.get(metric_id)
        metrics.append((label, value, color if color is not None and (color.r, color.g, color.b) != (default.r, default.g, default.b)
                        else None))
      draw_metric_tiles(sidebar_rect, metrics)

  return EssentialsDeveloperSidebar()

