"""Track consecutive posted limits and the driver's dismissal in native m/s, independent of display units."""
import math
from dataclasses import dataclass

LIVE_SOURCES = {"Dashboard", "Map Data", "Vision", "Mapbox"}


@dataclass
class LimitOfferState:
  last_limit: float = 0.0
  ignored_limit: float = 0.0
  pending_limit: float = 0.0
  since: float | None = None

  @staticmethod
  def same(a: float, b: float) -> bool:
    return math.isclose(a, b, rel_tol=0.0, abs_tol=0.1)

  def observe(self, pending: float, current: float, current_source: str, now: float) -> None:
    # A rejected/expired offer can leave the old accepted target in the plan. Only a live source counts as a change.
    observed = pending if pending > 1 else current if current_source in LIVE_SOURCES else 0.0
    if observed > 1:
      if self.last_limit > 1 and not self.same(observed, self.last_limit):
        self.ignored_limit = 0.0
      self.last_limit = observed
    if pending <= 1:
      self.since = None
    elif self.since is None or not self.same(pending, self.pending_limit):
      self.since = now
    self.pending_limit = pending

  @property
  def ignored(self) -> bool:
    return self.pending_limit > 1 and self.same(self.pending_limit, self.ignored_limit)

  def ignore(self) -> None:
    self.ignored_limit = self.pending_limit
