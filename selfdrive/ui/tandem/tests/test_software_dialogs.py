from openpilot.system.ui.widgets import DialogResult
from openpilot.selfdrive.ui.tandem.settings import software_tab as S
from openpilot.selfdrive.ui.tandem.tests.fakes import FakeUpdates


class Window:
  def __init__(self):
    self.shown = []

  def present(self, overlay):
    self.shown.append(overlay)

  def dismiss(self):
    pass

  @property
  def top(self):
    return self.shown[-1]


class Model:
  def __init__(self):
    self.actions = FakeUpdates()

  def version_parts(self):
    return "0.10.1", "release"


def test_uninstall_asks_three_times_like_upstream():
  for answers, expected in [((DialogResult.CANCEL,), []),
                            ((DialogResult.CONFIRM, DialogResult.CANCEL), [("uninstall", False)]),          # Skip keeps data
                            ((DialogResult.CONFIRM, DialogResult.CONFIRM, DialogResult.CONFIRM), [("uninstall", True)]),
                            ((DialogResult.CONFIRM, DialogResult.CONFIRM, DialogResult.CANCEL), [("uninstall", False)])]:
    model, window = Model(), Window()
    S.uninstall(model, window)
    for answer in answers:
      window.top._finish(answer)
    assert model.actions.calls == expected, answers


def test_branch_sheet_sets_the_target():
  model, window = Model(), Window()
  S.choose_branch(model, window)
  window.top._body._on_change(1)
  assert model.actions.calls == [("branch", "staging")]


def test_release_notes_become_plain_text():
  html = "<h1>Version 0.10.1</h1><ul><li>Smoother &amp; calmer</li><li>Fixes</li></ul><p>Thanks!</p>"
  assert S.notes_text(html) == "Version 0.10.1\n• Smoother & calmer\n• Fixes\nThanks!"
  assert S.notes_text("") == "No release notes for this version."


def test_sound_test_counts_down_in_our_dialog():
  from openpilot.selfdrive.ui.tandem.settings.bluetooth_tab import sound_test
  from openpilot.selfdrive.ui.tandem.tests.fakes import FakeBluetooth
  bt, window = FakeBluetooth(), Window()
  sound_test(bt, "AA", window)
  assert bt.calls == [("test", "AA")]
  assert not window.top._cancel.is_visible           # a notice with one button
  from openpilot.selfdrive.ui.tandem.base import resolve
  assert resolve(window.top._message) == "A sound plays in 3…"


def test_face_box_follows_upstreams_mapping():
  import pyray as rl
  from openpilot.selfdrive.ui.tandem.drivercamera import face_box
  box = face_box(0.0, 0.109, rl.Rectangle(0, 0, 2160, 1080))
  assert (round(box.x), round(box.y), box.width) == (970, 390, 220)   # centered at upstream's (1080, 500)
  half = face_box(0.0, 0.109, rl.Rectangle(0, 0, 1080, 540))
  assert half.width == 110                                              # scales with the view
