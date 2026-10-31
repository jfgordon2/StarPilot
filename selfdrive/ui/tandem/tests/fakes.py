"""Stand-ins for StarPilot's model controller and car catalog, for tests and headless renders."""
from openpilot.selfdrive.ui.tandem.settings.model import ModelInfo
from openpilot.selfdrive.ui.tandem.settings.vehicle import CarOption, WheelButton


class FakeModels:
  def __init__(self):
    self.items = [ModelInfo("rdf43", "Recommended Model", True), ModelInfo("vtx", "Vortex", True, community_pick=True),
                  ModelInfo("nlp", "North Loop", False, community_pick=True), ModelInfo("big", "Big Model", False, needs_egpu=True)]
    self.current = "rdf43"
    self.downloading = None
    self.calls = []

  def refresh(self):
    self.calls.append("refresh")

  def tick(self):
    pass

  def models(self):
    return self.items

  def current_key(self):
    return self.current

  def recommended_key(self):
    return "rdf43"

  def downloading_key(self):
    return self.downloading

  def progress(self):
    return "45% · about 3 min left"

  def egpu_available(self):
    return False

  def free_space(self):
    return "12.4 GB free"

  def use(self, key):
    self.current = key

  def download(self, key):
    self.downloading = key

  def cancel(self):
    self.downloading = None

  def remove(self, key):
    self.items = [m for m in self.items if m.key != key]


class FakeCars:
  def makes(self):
    return ["Chevrolet", "Honda", "Toyota"]

  def models(self, make):
    return {"Toyota": [CarOption("TOYOTA_RAV4_TSS2", "RAV4 2019-21"), CarOption("TOYOTA_RAV4H_TSS2", "RAV4 Hybrid 2019-21")],
            "Honda": [CarOption("HONDA_CIVIC", "Civic 2016-21")], "Chevrolet": [CarOption("CHEVROLET_BOLT_EUV", "Bolt EUV 2022-23")]}[make]

  def actions(self, button):
    return [(0, "Car default"), (1, "Change driving style"), (3, "Pause steering"), (9, "Always-on steering")]

  def buttons(self):
    return [WheelButton("Distance", "Press", "DistanceButtonControl"), WheelButton("Distance", "Long press", "LongDistanceButtonControl"),
            WheelButton("LKAS", "Press", "LKASButtonControl"), WheelButton("Cruise main", "Press", "MainCruiseButtonControl", True)]

  def has_auto_lock(self):
    return True
