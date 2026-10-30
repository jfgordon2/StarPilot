"""Read-only thumbnails from the same PNG packs used by the driving screen."""
from __future__ import annotations

from pathlib import Path

import pyray as rl

from openpilot.selfdrive.ui.onroad.starpilot.turn_signals import FRAME_PATTERN, BUNDLED_SIGNAL_PATHS
from openpilot.selfdrive.ui.lib import aether_style as AS
from openpilot.system.ui.lib.multilang import tr
from openpilot.system.ui.widgets.label import gui_label


SIGNAL_PICKER_ORDER = ("stock", "sequential", "flow", "open_flow", "glide", "frog", "pouncing_cat", "shooting_star", "bouncing_ball")


class SignalPreview:
  def __init__(self, slug: str, themes_path: Path):
    installed = themes_path / "theme_packs" / slug / "signals"
    self._path = None
    for directory in (installed, BUNDLED_SIGNAL_PATHS.get(slug)):
      if directory is None:
        continue
      frames = sorted((path for path in directory.glob("*") if path.is_file() and FRAME_PATTERN.fullmatch(path.name)),
                      key=lambda path: int(FRAME_PATTERN.fullmatch(path.name)[1] or 0))
      if frames:
        self._path = frames[len(frames) // 2]
        break
    self._texture = None
    self._loaded = False

  def __call__(self, rect: rl.Rectangle):
    if not self._loaded:
      self._loaded = True
      if self._path is not None:
        image = rl.load_image(str(self._path))
        if image.width > 0 and image.height > 0:
          try:
            # Ignore faint motion trails when fitting a representative thumbnail.
            rl.image_alpha_crop(image, 0.3)
            if image.width > 0 and image.height > 0:
              texture = rl.load_texture_from_image(image)
              if texture.id:
                rl.set_texture_filter(texture, rl.TextureFilter.TEXTURE_FILTER_BILINEAR)
                self._texture = texture
          finally:
            rl.unload_image(image)
    if self._texture is None:
      gui_label(rect, tr("No preview"), 22, AS.TEXT_SECONDARY)
      return
    scale = min(rect.width / self._texture.width, rect.height / self._texture.height)
    width, height = self._texture.width * scale, self._texture.height * scale
    destination = rl.Rectangle(rect.x + (rect.width - width) / 2, rect.y + (rect.height - height) / 2, width, height)
    rl.draw_texture_pro(self._texture, rl.Rectangle(0, 0, self._texture.width, self._texture.height), destination, rl.Vector2(), 0, rl.WHITE)

  def close(self):
    if self._texture is not None:
      rl.unload_texture(self._texture)
      self._texture = None
