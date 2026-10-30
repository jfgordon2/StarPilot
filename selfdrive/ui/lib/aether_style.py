"""Aether Cards: one visual language for the comma 3/3X driving screen and settings.

The driving-screen controls (set speed, speed limit, turn-signal indicators) are
translucent black cards with a light outline and a purple accent. Settings use the
same card, outline, radius and accent on an opaque ground, so the two screens read
as one product. Change a value here and both follow.
"""

import pyray as rl

# ── Card (shared) ──
CARD_RADIUS = 31                                  # px corner radius
CARD_BORDER_WIDTH = 6
CARD_FILL = rl.Color(0, 0, 0, 166)                # over the camera image
CARD_BORDER = rl.Color(196, 205, 208, 180)
ACCENT = rl.Color(160, 96, 230, 230)              # purple accent (unified speed card, selection)

# ── Settings ──
# Measurements follow the Aether Cards mockups (drawn at half scale, so 1 mock px = 2 device px).
SETTINGS_BG = rl.Color(5, 7, 11, 255)
SETTINGS_CARD_FILL = rl.Color(2, 3, 4, 255)       # CARD_FILL over SETTINGS_BG: the outline carries the card
SETTINGS_CARD_RADIUS = 40
SETTINGS_TILE_RADIUS = 44
SETTINGS_CARD_BORDER_WIDTH = 6
SETTINGS_CARD_BORDER_IDLE = rl.Color(196, 205, 208, 51)
SETTINGS_TILE_BORDER = rl.Color(196, 205, 208, 82)
SETTINGS_CARD_BORDER_ON = rl.Color(196, 205, 208, 115)   # a row that is on, or opens a picker
SETTINGS_CARD_BORDER_PRESSED = rl.Color(196, 205, 208, 200)
SETTINGS_DIVIDER = rl.Color(196, 205, 208, 40)   # between rows of a grouped list
SETTINGS_DIVIDER_WIDTH = 2
SETTINGS_ROW_CARD_HEIGHT = 184
SETTINGS_ROW_GAP = 24                             # space between row cards
SETTINGS_TILE_GAP = 28

# Layout belongs to the shared components, not to each menu's nesting level.
SETTINGS_PAGE_MARGIN = 48
SETTINGS_PAGE_TOP = 36
SETTINGS_HEADER_HEIGHT = 128
SETTINGS_HEADER_GAP = 36
SETTINGS_CARD_INSET = 44
SETTINGS_CONTROL_GAP = 28
SETTINGS_TEXT_GAP = 8
SETTINGS_TILE_INSET = 44
SETTINGS_HUB_TILE_HEIGHT = 404
SETTINGS_SCROLLBAR_GAP = 16
SETTINGS_GROUP_HEADING_HEIGHT = 48
SETTINGS_GROUP_HEADING_GAP = 16
SETTINGS_GROUP_HEADING_SIZE = 30
SETTINGS_STATUS_ICON_SIZE = 96
SETTINGS_STATUS_ICON_RADIUS = 30
SETTINGS_SEGMENTED_HEIGHT = 128
SETTINGS_SEGMENTED_FONT_SIZE = 40
SETTINGS_SEGMENTED_STATUS_FONT_SIZE = 24
SETTINGS_SEGMENTED_INSET = 8
SETTINGS_SEGMENTED_GAP = 12
SETTINGS_SEGMENTED_TEXT_INSET = 24
SETTINGS_DIALOG_FILL = rl.Color(11, 16, 22, 255)
SETTINGS_DIALOG_MARGIN_X = 96
SETTINGS_DIALOG_MARGIN_Y = 48
SETTINGS_DIALOG_INSET = 48
SETTINGS_DIALOG_RADIUS = 52
SETTINGS_DIALOG_TITLE_SIZE = 56
SETTINGS_DIALOG_DESCRIPTION_SIZE = 28
SETTINGS_DIALOG_ACTION_WIDTH = 216
SETTINGS_CHOICE_FILL = rl.Color(18, 23, 30, 255)
SETTINGS_CHOICE_CARD_HEIGHT = 232
SETTINGS_CHOICE_PREVIEW_WIDTH = 188
SETTINGS_CHOICE_PREVIEW_HEIGHT = 124

ACCENT_SOLID = rl.Color(139, 79, 214, 255)        # switch track when on, primary buttons
ACCENT_TINT = rl.Color(160, 96, 230, 51)          # value pills, icon wells, selected nav
ACCENT_EDGE = rl.Color(160, 96, 230, 204)
ACCENT_TEXT = rl.Color(201, 167, 245, 255)        # breadcrumbs, small labels
ICON_INK = rl.Color(212, 184, 250, 255)
TRACK_OFF = rl.Color(58, 67, 80, 255)

SWITCH_WIDTH = 136
SWITCH_HEIGHT = 76
VALUE_PILL_HEIGHT = 112
ROUND_BUTTON = 128                                # close / back
NAV_ITEM_HEIGHT = 104
NAV_TEXT = rl.Color(195, 202, 210, 255)

TEXT = rl.Color(255, 255, 255, 255)
TEXT_SECONDARY = rl.Color(169, 179, 190, 255)     # 9:1 on SETTINGS_CARD_FILL
TEXT_DISABLED = rl.Color(120, 128, 138, 255)

# Smallest comfortable touch target on the 2160x1080 panel (about 8 mm).
MIN_TOUCH = 112
