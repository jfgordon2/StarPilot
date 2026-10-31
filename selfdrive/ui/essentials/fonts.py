"""Fonts for Essentials components.

FontWeight (system/ui/lib/application.py) covers the shared Figtree weights, which load at startup.
The design's extra faces live here instead, so upstream's enum only differs by file names, and they
load on first use: ExtraBold for titles and big numbers, JetBrains Mono for Developer View and Tuner Mode.
"""
from __future__ import annotations

from enum import StrEnum
from importlib.resources import as_file

import pyray as rl

from openpilot.system.ui.lib.application import FONT_DIR, FontWeight, gui_app


class ExtraFont(StrEnum):
  EXTRA_BOLD = "Figtree-ExtraBold.fnt"
  MONO = "JetBrainsMono-Medium.fnt"


Face = FontWeight | ExtraFont

_loaded: dict[ExtraFont, rl.Font] = {}


def font(face: Face) -> rl.Font:
  if not isinstance(face, ExtraFont):
    return gui_app.font(face)
  if face not in _loaded:
    with as_file(FONT_DIR) as path:
      loaded = rl.load_font((path / face).as_posix())
    rl.gen_texture_mipmaps(loaded.texture)
    rl.set_texture_filter(loaded.texture, rl.TextureFilter.TEXTURE_FILTER_TRILINEAR)
    _loaded[face] = loaded
  return _loaded[face]
