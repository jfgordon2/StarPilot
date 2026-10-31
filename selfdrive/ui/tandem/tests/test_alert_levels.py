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
