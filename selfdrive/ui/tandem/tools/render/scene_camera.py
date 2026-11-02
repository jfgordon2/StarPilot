import pyray as rl
from openpilot.selfdrive.ui.tandem import draw
from openpilot.selfdrive.ui.tandem.drivercamera import draw_overlay, face_box


def main(frame, save, out, tap, gui_app):
  rect = rl.Rectangle(0, 0, 2160, 1080)

  def scene():
    draw.fill(rect, rl.Color(30, 34, 39, 255))
    rl.draw_ellipse(1080, 500, 165, 205, rl.Color(58, 64, 72, 255))
    rl.draw_ellipse(1080, 1080, 370, 330, rl.Color(48, 53, 60, 255))
    draw_overlay(rect, False, face_box(0.0, 0.109, rect), 1.0, True, 1.0)
  for _ in range(4):
    frame(scene)
  save(f"{out}/drivercamera.png")
