"""MAX follows the speed limit: only a change StarPilot has adopted moves MAX, toward the limit plus the offset."""
from openpilot.common.constants import CV
from openpilot.selfdrive.ui.tandem.onroad.limits import LimitFollower

MPH = CV.MPH_TO_MS
OFFSET = 3 * MPH


def _follow(follower, limit_mph, max_mph, engaged=True, source="Map Data"):
  target = follower.update(limit_mph * MPH, source, OFFSET, max_mph * MPH, engaged)
  return None if target is None else round(target / MPH)


def test_a_lower_limit_brings_max_down():
  f = LimitFollower()
  assert _follow(f, 65, 68) is None              # the first limit seen only sets the baseline
  assert _follow(f, 55, 68) == 58
  assert _follow(f, 55, 68) is None              # the same limit again: nothing more
  assert _follow(f, 45, 58) == 48


def test_a_higher_limit_raises_max_but_never_lowers_a_higher_one():
  f = LimitFollower()
  _follow(f, 45, 48)
  assert _follow(f, 55, 48) == 58                # adopted on its own, or after Match
  _follow(f, 45, 58)
  assert _follow(f, 65, 75) is None              # the driver's higher MAX stays
  assert _follow(f, 65, 68) is None


def test_a_max_the_driver_sets_stays_until_the_next_limit():
  f = LimitFollower()
  _follow(f, 65, 68)
  assert _follow(f, 55, 68) == 58
  assert _follow(f, 55, 62) is None              # the driver raised it within the zone
  assert _follow(f, 45, 62) == 48                # the next lower limit follows again


def test_disengaged_or_fallback_limits_do_not_move_max():
  f = LimitFollower()
  _follow(f, 65, 68)
  assert _follow(f, 55, 68, engaged=False) is None
  assert _follow(f, 55, 68) is None              # the change happened while disengaged; engaging starts at the limit
  assert _follow(f, 45, 58, source="None") is None
  assert _follow(f, 0, 58) is None
  assert _follow(f, 45, 58) == 48
