import time
from types import SimpleNamespace

import pytest
import pyray as rl

from openpilot.selfdrive.ui.layouts.home import CONTENT_MARGIN, HEADER_HEIGHT, SPACING, HomeLayout, HomeLayoutState
from openpilot.selfdrive.ui.tandem.home import essentials_home
from openpilot.system.ui.lib.application import MousePos, gui_app
from openpilot.system.ui.widgets import Widget


class DetailPanel(Widget):
  def __init__(self):
    super().__init__()
    self.rendered = []
    self.dismiss_callback = None

  def set_dismiss_callback(self, callback):
    self.dismiss_callback = callback

  def _render(self, rect):
    self.rendered.append(rect)


@pytest.fixture
def home_layout(monkeypatch):
  # Keep the actual layout, state transitions, content and tap handling. Replace device-only panels and drawing.
  def init(self):
    Widget.__init__(self)
    self.current_state = HomeLayoutState.HOME
    self.last_refresh = time.monotonic()
    self.update_available, self.alert_count = True, 1
    self._version_text = "StarPilot test"
    self.settings_callback = None
    self.update_alert, self.offroad_alert = DetailPanel(), DetailPanel()
    self._layout_widgets = {HomeLayoutState.UPDATE: self.update_alert, HomeLayoutState.ALERTS: self.offroad_alert}
    self._exp_mode_button = DetailPanel()
    self.header_rect = self.content_rect = rl.Rectangle(0, 0, 0, 0)
    self.update_notif_rect = rl.Rectangle(0, 0, 200, HEADER_HEIGHT - 10)
    self.alert_notif_rect = rl.Rectangle(0, 0, 220, HEADER_HEIGHT - 10)
    self._setup_callbacks()

  monkeypatch.setattr(HomeLayout, "__init__", init)
  headers = []
  monkeypatch.setattr(HomeLayout, "_render_header", lambda self: headers.append(self.current_state))
  monkeypatch.setattr(gui_app, "_mouse_events", [])
  home = essentials_home()
  home._setup_checked = True
  cards = {}
  for name in ("hero", "where", "update"):
    monkeypatch.setattr(getattr(home._content, f"_{name}"), "_render", lambda rect, name=name: cards.update({name: rect}))
  return SimpleNamespace(home=home, headers=headers, cards=cards)


@pytest.mark.parametrize("rect", [(0, 0, 2160, 1080), (554, 30, 1606, 1050), (400, 10, 1200, 800)])
def test_home_cards_reclaim_header_and_gap_with_sidebar_offsets(home_layout, rect):
  f, rect = home_layout, rl.Rectangle(*rect)
  f.home.render(rect)
  assert not f.headers
  assert f.home.header_rect.height == 0
  assert f.cards["hero"].x == rect.x + CONTENT_MARGIN
  assert f.cards["hero"].y == rect.y + CONTENT_MARGIN
  assert f.cards["hero"].width == rect.width - 2 * CONTENT_MARGIN
  assert f.home.content_rect.height == rect.height - 2 * CONTENT_MARGIN
  for name in ("where", "update"):
    card = f.cards[name]
    assert card.y + card.height == rect.y + rect.height - CONTENT_MARGIN


def test_invisible_header_buttons_do_not_intercept_home_card_taps(home_layout):
  home = home_layout.home
  home.render(rl.Rectangle(554, 0, 1606, 1080))
  for rect in (home.update_notif_rect, home.alert_notif_rect):
    home._handle_mouse_release(MousePos(rect.x + rect.width / 2, rect.y + rect.height / 2))
    assert home.current_state == HomeLayoutState.HOME


@pytest.mark.parametrize("state", [HomeLayoutState.ALERTS, HomeLayoutState.UPDATE])
def test_home_card_opens_detail_view_and_close_restores_full_height(home_layout, state):
  f, home = home_layout, home_layout.home
  rect = rl.Rectangle(554, 0, 1606, 1080)
  home.render(rect)
  if state == HomeLayoutState.ALERTS:
    home._content._hero._click_callback()
  else:
    home._content._update._button._click_callback()
  assert home.current_state == state
  home.render(rect)
  assert f.headers == [state]
  panel = home._layout_widgets[state]
  assert panel.rendered[-1].y == rect.y + CONTENT_MARGIN + HEADER_HEIGHT + SPACING
  panel.dismiss_callback()
  assert home.current_state == HomeLayoutState.HOME
  home.render(rect)
  assert f.headers == [state]
  assert f.cards["hero"].y == rect.y + CONTENT_MARGIN


def test_upstream_home_keeps_header_geometry_and_notification_buttons(home_layout):
  home = HomeLayout()
  home._render_home_content = lambda: None
  home.render(rl.Rectangle(554, 0, 1606, 1080))
  assert home_layout.headers == [HomeLayoutState.HOME]
  assert home.header_rect.height == HEADER_HEIGHT
  assert home.content_rect.y == CONTENT_MARGIN + HEADER_HEIGHT + SPACING
  button = home.update_notif_rect
  home._handle_mouse_release(MousePos(button.x + 10, button.y + 10))
  assert home.current_state == HomeLayoutState.UPDATE


def test_refresh_returning_home_reclaims_header_in_the_same_frame(home_layout):
  home = home_layout.home
  home._set_state(HomeLayoutState.UPDATE)
  home.last_refresh = 0
  home._refresh = lambda: home._set_state(HomeLayoutState.HOME)
  home.render(rl.Rectangle(554, 30, 1606, 1050))
  assert home.current_state == HomeLayoutState.HOME
  assert not home_layout.headers
  assert home_layout.cards["hero"].y == 30 + CONTENT_MARGIN
