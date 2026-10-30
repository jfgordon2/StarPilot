"""Text-list selections use the same header and commit behavior as visual pickers."""
from collections.abc import Callable

from openpilot.system.ui.lib.application import FontWeight
from openpilot.system.ui.widgets import DialogResult
from openpilot.selfdrive.ui.layouts.settings.starpilot.choice_dialog import AetherChoiceDialog, PreviewChoice


class MultiOptionDialog(AetherChoiceDialog):
  def __init__(self, title, options, current="", option_font_weight=FontWeight.MEDIUM,
               callback: Callable[[DialogResult], None] | None = None, *, subtitle: str = ""):
    super().__init__(title, [PreviewChoice(option, option) for option in options], current,
                     subtitle=subtitle, callback=callback, layout="list", option_font_weight=option_font_weight)
