from openpilot.selfdrive.ui.tandem.onroad import alerts

SMALL, MID, FULL = 1, 2, 3
NORMAL, PROMPT, CRITICAL, STARPILOT = 0, 1, 2, 3


def test_levels_follow_status_and_size():
  assert alerts.level(SMALL, STARPILOT, "greenLight/permanent") == alerts.INFO       # Light Turned Green
  assert alerts.level(MID, NORMAL, "buttonCancel/noEntry") == alerts.INFO            # openpilot Unavailable
  assert alerts.level(SMALL, NORMAL) == alerts.INFO                                  # Pay Attention, early
  assert alerts.level(MID, PROMPT, "promptDriverDistracted/permanent") == alerts.WARNING
  assert alerts.level(SMALL, PROMPT) == alerts.WARNING
  assert alerts.level(FULL, PROMPT, "steerTempUnavailable/softDisable") == alerts.CRITICAL
  assert alerts.level(FULL, CRITICAL, "fcw/permanent") == alerts.CRITICAL
  assert alerts.level(MID, CRITICAL) == alerts.CRITICAL                              # openpilot crashed


def test_reverse_gear_keeps_upstream_drawing():
  assert alerts.level(FULL, NORMAL, "reverseGear/permanent") == alerts.REVERSE


def test_border_only_for_warning_and_critical():
  assert alerts.border(alerts.INFO) is None
  assert alerts.border(None) is None
  assert alerts.border(alerts.WARNING) == alerts.WARNING_BORDER
  assert alerts.border(alerts.CRITICAL) == alerts.CRITICAL_BORDER


def test_routine_status_banners_go_to_chips():
  assert alerts.shown_as_chip("greenLight/permanent")
  assert alerts.shown_as_chip("leadDeparting/permanent")
  assert alerts.shown_as_chip("laneChange/warning")
  assert alerts.shown_as_chip("turningLeft/warning")
  assert alerts.shown_as_chip("turningRight/warning")
  assert alerts.shown_as_chip("laneChangeBlocked/warning")       # Lane change blocked; the chime still plays
  assert alerts.shown_as_chip("laneChangeBlockedLoud/warning")
  assert not alerts.shown_as_chip("preLaneChangeLeft/warning")
  assert not alerts.shown_as_chip("preLaneChangeRight/warning")
  assert not alerts.shown_as_chip("personalityChanged/warning")
  assert not alerts.shown_as_chip("speedLimitChanged/permanent")   # hidden only while the new-limit card asks (view.py)
  assert not alerts.shown_as_chip("promptDriverDistracted/permanent")
  assert not alerts.shown_as_chip("")
