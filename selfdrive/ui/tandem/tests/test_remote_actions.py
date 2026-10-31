from types import SimpleNamespace
from copy import deepcopy

from openpilot.selfdrive.ui.tandem.settings.bluetooth_tab import UpstreamWheel
from openpilot.selfdrive.ui.tandem.settings.vehicle import UpstreamCars, WheelButton
from openpilot.starpilot.common import controller_actions as ca
from openpilot.starpilot.system.wheel_controls import wheel_controlsd as wc
from openpilot.starpilot.system.wheel_controls.tests.test_wheel_controlsd import FakeParams, source


def wheel_source():
  wheel = UpstreamWheel.__new__(UpstreamWheel)
  wheel._params, wheel._memory = FakeParams(), FakeParams()
  wheel._wc, wheel._ca = wc, ca
  wheel.favorite_slots = wc.FAVORITE_SLOT_COUNT
  return wheel


def map_button(wheel, code, slot=None):
  return wc.upsert_mapping(source(), code, wheel.free_slot() if slot is None else slot, wheel._params)


def test_favorite_choices_name_the_saved_action_and_dispatch_it():
  wheel = wheel_source()
  wheel._params.put("StarPilotFavoriteSlots", [{"enabled": True, "key": ca.CONTROLLER_ACTION_BOOKMARK, "label": "Save a clip"}])
  assert dict(wheel.actions())["favorite:0"] == "Favorite 1 · Save a clip"
  assert dict(wheel.actions())["favorite:1"] == "Favorite 2 · Not set"

  mapping = map_button(wheel, 30)
  assert wheel.assign(mapping["id"], "favorite:0")
  assert wc.execute_mapping_slot(wheel.mappings()[0]["slot"], wheel._params, wheel._memory)
  assert wheel._memory.get_int("WheelButtonBookmarkCounter") == 1
  assert wheel._params.get("NavDestination") is None

  cars = UpstreamCars.__new__(UpstreamCars)
  cars._state = SimpleNamespace(params=wheel._params, car_state=SimpleNamespace(hasOpenpilotLongitudinal=True))
  cars._v = SimpleNamespace(ACTION_OPTIONS=[{"id": 11, "name": "Favorite #1"}, {"id": 12, "name": "Favorite #2"}])
  button = WheelButton("Distance", "Press", "DistanceButtonControl")
  assert dict(cars.actions(button))[11] == "Favorite 1 · Save a clip"

  wheel._params.put("StarPilotFavoriteSlots", [{"enabled": True, "key": ca.CONTROLLER_ACTION_SCREEN_OFF, "label": "Screen off / on"}])
  assert dict(wheel.actions())["favorite:0"] == "Favorite 1 · Screen off / on"
  assert dict(cars.actions(button))[11] == "Favorite 1 · Screen off / on"


def test_repeated_add_assign_remove_reuses_action_slots():
  wheel = wheel_source()
  for i in range(wc.CONTROLLER_ACTION_SLOT_COUNT * 3):
    mapping = map_button(wheel, 100 + i)
    assert wheel.assign(mapping["id"], ca.CONTROLLER_ACTION_BOOKMARK)
    wheel.delete(mapping["id"])
    assert wheel.mappings() == []
    assert wheel.free_slot() == wc.FAVORITE_SLOT_COUNT
    assert not any(s["enabled"] for s in wheel._slots())


def test_reassigning_to_a_favorite_releases_the_previous_action_slot():
  wheel = wheel_source()
  mapping = map_button(wheel, 30)
  assert wheel.assign(mapping["id"], ca.CONTROLLER_ACTION_BOOKMARK)
  assert wheel.assign(mapping["id"], "favorite:0")
  assert wheel.mappings()[0]["slot"] == 0
  assert wheel.free_slot() == wc.FAVORITE_SLOT_COUNT
  assert wheel.assign(mapping["id"], ca.CONTROLLER_ACTION_DISENGAGE)
  assert wheel.mappings()[0]["slot"] == wc.FAVORITE_SLOT_COUNT


def test_removing_a_shared_mapping_keeps_the_other_button_working():
  wheel = wheel_source()
  first = map_button(wheel, 30)
  assert wheel.assign(first["id"], ca.CONTROLLER_ACTION_BOOKMARK)
  second = map_button(wheel, 31, first["slot"])
  wheel.delete(first["id"])
  assert wc.execute_mapping_slot(second["slot"], wheel._params, wheel._memory)
  assert wheel._memory.get_int("WheelButtonBookmarkCounter") == 1
  wheel.delete(second["id"])
  assert wheel.free_slot() == wc.FAVORITE_SLOT_COUNT
  assert not any(s["enabled"] for s in wheel._slots())


def test_reassigning_a_shared_mapping_does_not_change_the_other_action():
  wheel = wheel_source()
  first = map_button(wheel, 30)
  assert wheel.assign(first["id"], ca.CONTROLLER_ACTION_BOOKMARK)
  second = map_button(wheel, 31, first["slot"])
  assert wheel.assign(first["id"], ca.CONTROLLER_ACTION_SCREEN_OFF)
  assert wheel.action(second["slot"]) == ca.CONTROLLER_ACTION_BOOKMARK
  assert wc.execute_mapping_slot(second["slot"], wheel._params, wheel._memory)
  assert wheel._memory.get_int("WheelButtonBookmarkCounter") == 1


def test_full_action_slots_do_not_overwrite_an_existing_button():
  wheel = wheel_source()
  for i in range(wc.CONTROLLER_ACTION_SLOT_COUNT):
    mapping = map_button(wheel, 30 + i)
    assert wheel.assign(mapping["id"], ca.CONTROLLER_ACTION_BOOKMARK)
  favorite = map_button(wheel, 100, 0)
  before = deepcopy(wheel._params.values)
  assert wheel.free_slot() is None
  assert not wheel.assign(favorite["id"], ca.CONTROLLER_ACTION_SCREEN_OFF)
  assert wheel._params.values == before


def test_deleting_a_mapping_preserves_unrelated_configured_actions():
  wheel = wheel_source()
  wc.set_controller_action_slot(1, ca.CONTROLLER_ACTION_SCREEN_OFF, "Screen off / on", wheel._params)
  mapping = map_button(wheel, 30)
  assert wheel.assign(mapping["id"], ca.CONTROLLER_ACTION_BOOKMARK)
  wheel.delete(mapping["id"])
  assert wheel._slots()[1]["key"] == ca.CONTROLLER_ACTION_SCREEN_OFF
