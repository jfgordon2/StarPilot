"""Shared visual tokens for the StarPilot on-road control widgets.

Colours, outline and radius come from selfdrive/ui/lib/aether_style.py, which the
comma 3/3X settings use too.
"""

import pyray as rl

from openpilot.selfdrive.ui.lib import aether_style


# The two left-hand control cards share a visible frame.  Keeping these values
# here prevents the Set Speed and SLC implementations from drifting apart.
CONTROL_WIDTH = 176
SET_SPEED_HEIGHT = 196
SLC_HEIGHT = SET_SPEED_HEIGHT
# Stable Raylib shape settings for scaled rendering.
CONTROL_RADIUS = aether_style.CARD_RADIUS
CONTROL_ROUNDNESS = 0.35
CONTROL_SEGMENTS = 10
CONTROL_BORDER_WIDTH = aether_style.CARD_BORDER_WIDTH
CONTROL_BG = aether_style.CARD_FILL
CONTROL_BORDER = aether_style.CARD_BORDER
UNIFIED_ACCENT = aether_style.ACCENT
# The layout manager has historically anchored the left controls at x + 146.
# Keep that placement stable while making the width explicit and shared.
WIDGET_ANCHOR_OFFSET = 146


def roundness_for(rect: rl.Rectangle, radius: float = CONTROL_RADIUS) -> float:
  """Convert a pixel corner radius to Raylib's normalized roundness value."""
  return min(1.0, radius / max(1.0, min(rect.width, rect.height) / 2.0))


def draw_control_card(rect: rl.Rectangle, *, fill: rl.Color = CONTROL_BG,
                      border: rl.Color = CONTROL_BORDER,
                      border_width: float = CONTROL_BORDER_WIDTH) -> None:
  """Draw the common translucent rounded card used by left-hand controls."""
  roundness = roundness_for(rect)
  rl.draw_rectangle_rounded(rect, roundness, CONTROL_SEGMENTS, fill)
  rl.draw_rectangle_rounded_lines_ex(rect, roundness, CONTROL_SEGMENTS, border_width, border)
