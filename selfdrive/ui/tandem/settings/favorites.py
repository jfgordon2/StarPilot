"""Names of the existing settings/action favorites used by car buttons and remotes."""
from openpilot.starpilot.common.favorite_slots import load_favorite_slots


def favorite_action_names(params) -> list[str]:
  names = []
  for i, slot in enumerate(load_favorite_slots(params)):
    name = f"Favorite {i + 1}"
    if not slot.get("enabled") or not slot.get("key"):
      name += " · Not set"
    elif slot.get("label"):
      name += f" · {slot['label']}"
    names.append(name)
  return names
