import datetime
import threading

import pyray as rl

from openpilot.selfdrive.ui.tandem import routemap as M

PLAN = M.RoutePlan(((45.50, -122.70), (45.52, -122.64)), 5310.0, 1080.0)


def test_arrival_words():
  assert M.arrive_text(PLAN, datetime.datetime(2026, 10, 31, 17, 47)) == "6:05 PM"
  assert M.time_text(PLAN) == "18 min"
  assert M.time_text(M.RoutePlan((), 0, 3900)) == "1 h 5 min"
  assert M.distance_text(PLAN, False) == "3.3 mi" and M.distance_text(PLAN, True) == "5.3 km"
  assert M.arrive_text(None) == M.time_text(None) == M.distance_text(None, True) == M.EMPTY


def test_project_fits_the_route_inside_the_padding_north_up():
  rect = rl.Rectangle(100, 50, 800, 600)
  points = M.project(PLAN.path, rect, 40)
  for p in points:
    assert 140 - 1e-6 <= p.x <= 860 + 1e-6 and 90 - 1e-6 <= p.y <= 610 + 1e-6
  start, end = points
  assert end.x > start.x and end.y < start.y          # east and north of the start


def test_gps_fix_reads_last_gps_position():
  assert M.gps_fix('{"hasFix": true, "latitude": 45.5, "longitude": -122.6, "bearing": 90}') == (45.5, -122.6, 90.0)
  assert M.gps_fix('{"hasFix": false, "latitude": 45.5, "longitude": -122.6}') is None
  assert M.gps_fix('{"hasFix": true, "latitude": 0, "longitude": 0}') is None
  assert M.gps_fix("") is None and M.gps_fix("{") is None


def test_fetcher_asks_once_per_place_and_keeps_only_the_latest():
  gate, asked = threading.Event(), []

  def fetch(place):
    asked.append(place["name"])
    if place["name"] == "slow":
      gate.wait(2)
      return PLAN
    return M.NO_FIX

  fetcher = M.RouteFetcher(fetch)
  slow = {"name": "slow", "latitude": 1, "longitude": 1}
  assert fetcher.route(slow) == (None, M.FINDING)
  fetcher.route(slow)
  other = {"name": "other", "latitude": 2, "longitude": 2}
  fetcher.route(other)
  for _ in range(200):
    if fetcher.route(other) == (None, M.NO_FIX):
      break
    threading.Event().wait(0.01)
  gate.set()
  threading.Event().wait(0.05)
  assert fetcher.route(other) == (None, M.NO_FIX)    # the slow, older answer doesn't land
  assert asked.count("slow") == 1
  assert fetcher.route(None) == (None, "")
