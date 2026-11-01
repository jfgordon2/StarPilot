"""The lead marker over the stand-in road: following, braking for the car ahead, and a car in the next lane."""
import pyray as rl
from openpilot.selfdrive.ui.tandem import draw
from openpilot.selfdrive.ui.tandem.onroad import extras
from openpilot.selfdrive.ui.tandem.onroad.layers import ArcState, BarState
from openpilot.selfdrive.ui.tandem.onroad.status import Snapshot, chip_for
from scene_onroad import scene


def chevron(x, y, d_rel):
  """Upstream's chevron for a lead at screen point (x, y), d_rel meters ahead (ModelRenderer._update_lead_vehicle)."""
  sz = min(max((25 * 30) / (d_rel / 3 + 30), 15.0), 30.0) * 2.35
  return [(x + sz * 1.25, y + sz), (x, y), (x - sz * 1.25, y + sz)]


def car(x, y, w):
  body = rl.Rectangle(x - w / 2, y - w * 0.55, w, w * 0.55)
  draw.fill(body, rl.Color(0x2A, 0x31, 0x38, 255), w * 0.12)
  draw.fill(rl.Rectangle(body.x + w * 0.12, body.y + w * 0.08, w * 0.76, w * 0.15), rl.Color(0x3B, 0x44, 0x4E, 255), 6)
  for lx in (body.x + w * 0.06, body.x + w * 0.78):
    draw.fill(rl.Rectangle(lx, body.y + w * 0.38, w * 0.16, w * 0.08), rl.Color(0xC2, 0x41, 0x4B, 255), 3)


def lead_scene(braking, adjacent=False):
  chip = [(chip_for(Snapshot(slowing_for_lead=True, speed=12.0, accel=-1.0)), 1.0)] if braking else None
  base = scene(BarState(True, True, 48, "mph", "Market Street"), ArcState(0.1, 0.1, True), chip, speed=44)

  def render():
    base()
    x, y = 1080, 560
    car(x, y, 120)
    color = extras.LEAD_BRAKING_INK if braking else extras.LEAD_INK
    extras.draw_lead_bar(extras.lead_bar_rect(chevron(x, y, 30)), color)
    if adjacent:
      car(760, 600, 110)
      extras.draw_lead_bar(extras.lead_bar_rect(chevron(760, 600, 26)), extras.LEAD_INK, extras.LEAD_FAINT, outline=False)
  return render


def main(frame, save, out, tap, gui_app):
  for name, render in (("lead_following", lead_scene(False, adjacent=True)), ("lead_braking", lead_scene(True))):
    for _ in range(3):
      frame(render)
    save(f"{out}/{name}.png")
