import pytest

from openpilot.selfdrive.ui.tandem.onroad.streets import short_street


@pytest.mark.parametrize("name, short", [
  ("North Main Street", "N Main St"),
  ("Southwest Broadway", "SW Broadway"),
  ("Martin Luther King Junior Boulevard Northwest", "Martin Luther King Junior Blvd NW"),
  ("Park Avenue South", "Park Ave S"),
  ("East 14th Street", "E 14th St"),
  ("Pacific Coast Highway", "Pacific Coast Hwy"),
  ("North Avenue", "North Ave"),                 # the direction is the name
  ("East Street", "East St"),
  ("Avenue of the Americas", "Avenue of the Americas"),   # the type isn't last
  ("Broadway", "Broadway"),
  ("Interstate 5", "Interstate 5"),
  ("", ""),
])
def test_directions_and_types_are_shortened(name, short):
  assert short_street(name) == short
