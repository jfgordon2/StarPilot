"""Street names as the bar shows them: directions and street types shortened the way signs and the USPS write them.

"North Main Street" is "N Main St", "Martin Luther King Junior Boulevard Northwest" is "Martin Luther King Junior Blvd NW".
A direction that is the name itself stays whole ("North Ave"), and a type that isn't last does too ("Avenue of the Americas").
"""
from __future__ import annotations

DIRECTIONS = {"north": "N", "south": "S", "east": "E", "west": "W", "northeast": "NE", "northwest": "NW", "southeast": "SE",
              "southwest": "SW"}
TYPES = {
  "street": "St", "avenue": "Ave", "road": "Rd", "boulevard": "Blvd", "drive": "Dr", "lane": "Ln", "court": "Ct", "place": "Pl",
  "terrace": "Ter", "parkway": "Pkwy", "highway": "Hwy", "expressway": "Expy", "freeway": "Fwy", "circle": "Cir", "trail": "Trl",
  "square": "Sq", "crossing": "Xing", "turnpike": "Tpke", "heights": "Hts", "center": "Ctr", "plaza": "Plz", "point": "Pt",
  "mountain": "Mtn", "junction": "Jct", "crescent": "Cres", "alley": "Aly", "causeway": "Cswy", "bypass": "Byp",
}


def short_street(name: str) -> str:
  words = name.split()
  if len(words) < 2:
    return name
  start, end = 0, len(words)
  # A trailing direction ("... Street Northwest"), when something other than a type comes before it.
  if DIRECTIONS.get(words[-1].lower()) and len(words) >= 3:
    words[-1], end = DIRECTIONS[words[-1].lower()], end - 1
  # A leading direction, when at least a name and maybe a type follow ("North Main Street", not "North Avenue").
  rest = words[1:end]
  if DIRECTIONS.get(words[0].lower()) and any(w.lower() not in TYPES for w in rest):
    words[0], start = DIRECTIONS[words[0].lower()], 1
  # The street type: the last word before any trailing direction, after a name.
  last = end - 1
  if last > start and words[last].lower() in TYPES:
    words[last] = TYPES[words[last].lower()]
  return " ".join(words)
