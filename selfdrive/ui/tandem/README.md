# Tandem

Tandem is this fork of StarPilot. Its design language is **Essentials**: fewer choices and better defaults, with the car explaining what it's doing. This package holds the Essentials component library. The mocks, screenshots and tokens are in [`design/`](design/). It's built on raylib and the existing `Widget` base class. Screens are put together from these pieces instead of drawing with raylib directly.

| Module | Contents |
| --- | --- |
| `fonts.py` | `font(face)`: the shared `FontWeight` faces from `gui_app`, plus `ExtraFont.EXTRA_BOLD` and `ExtraFont.MONO`, which load on first use. |
| `tokens.py` | Colors, type sizes, radii, layout sizes and timings in device pixels. `px()` converts mock pixels and `font_px()` converts mock font sizes. |
| `layout.py` | Rectangle math: `row`, `column`, `grid` (fixed sizes plus `FILL`), `inset`, `place`, `grow`. It doesn't draw. |
| `draw.py` | Rounded fills, single-line text (aligned and elided), captions, wrapped paragraphs, stroke glyphs (chevron, cross, plus, minus, check) and tinted PNG icons. |
| `base.py` | `Component`: a `Widget` with `preferred_size()`, plus a touch area grown to `MIN_TOUCH`. `resolve()` for values that may be getters. |
| `controls.py` | `Button` (primary, secondary, ghost, danger, danger outline, nav), `ValueButton`, `Switch`, `Segmented`, `Stepper`, `Slider`, `Badge`, `Chip`, `ProgressBar` |
| `rows.py` | `SettingRow`, `SectionHeader`, `Text`, `Banner`, and `ListPanel`, which stacks rows with dividers and scrolls when they overflow |
| `chrome.py` | `BottomNav`, `Sidebar`, `PageHeader`, `HubTile`, `HubGrid`, and `SettingsPage`, which assembles a full screen |
| `overlays.py` | `Sheet` (slides up), `Dialog` (confirm; `Tone.DANGER` gives a destructive button), `Toast` |

## Building a screen

```python
from openpilot.selfdrive.ui.tandem import (BottomNav, ListPanel, Segmented, SettingRow, SettingsPage, Sidebar, SidebarItem, Stepper,
                                               Switch)

params = Params()

page = SettingsPage(
  sidebar=Sidebar("Driving", [SidebarItem("Everyday"), SidebarItem("Weather", open_weather, value="Auto")], selected=0),
  content=ListPanel([
    SettingRow("Driving Style", "Sets following gap, acceleration and braking together",
               Segmented(["Relaxed", "Standard", "Sport"], lambda: params.get_int("DrivingStyle"),
                         lambda i: params.put_int("DrivingStyle", i))),
    SettingRow("Offset", "Added to every matched limit",
               Stepper(lambda: params.get_int("SpeedLimitOffset"), lambda v: params.put_int("SpeedLimitOffset", int(v)), -10, 15,
                       fmt=lambda v: f"{v:+g} mph"), indent=True),
    SettingRow("Smart Slowdowns", "Slows for curves and stop lights", Switch(lambda: params.get_bool("SmartSlowdowns"),
                                                                             lambda on: params.put_bool("SmartSlowdowns", on))),
  ], title="Everyday"),
  nav=BottomNav(["Driving", "Device", "Network", "Bluetooth", "Software"], selected=0, on_select=open_tab),
)
```

## Conventions

- **Values may be getters.** Any `Bindable` argument takes either a plain value or a zero-argument callable that is read every frame. That lets a row stay in sync with Params without extra glue. Changes go out through `on_change` / `on_click` callbacks.
- **Containers lay out their children.** A container asks each child for `preferred_size(max_width)` and decides where it goes, so pages never hard-code positions.
- **Touch.** A control smaller than `MIN_TOUCH` (112 px) still responds across a 112 px area. Containers turn that off with `grow_touch_target = False`. Rows inside a `ListPanel` ignore taps that are really scrolls.
- **Color and size only come from `tokens`.** If a screen needs a value that isn't there, add a token rather than a hex code.
- **Text.** Use `draw.text`, `draw.caption` and `draw.paragraph`. They apply `FONT_SCALE` and elide with "…". The font atlases are pre-baked, so a character that isn't baked in draws as "?". Add it to `DESIGN_CHARS` in `tools/build_figtree_fonts.py` and run that script.

## Keeping rebases easy

This fork is rebased onto StarPilot, and everything outside this package belongs to StarPilot or to openpilot underneath it. Our work therefore lives in new files and edits upstream files only when there is no other way.

- **Ours:** everything in `selfdrive/ui/tandem/`, meaning the code, `design/` (mocks and docs), `tools/` and `tests/`. Also the new font files `selfdrive/assets/fonts/Figtree-*` and `Figtree-OFL.txt`, which have to sit where the app loads fonts from.
- **The only upstream edit** is the file names in `FontWeight` (`system/ui/lib/application.py`), which switches the whole UI to Figtree. If a rebase conflicts there, keep upstream's version and change the file names again.
- **Unchanged:** `Widget`, `process.py`, the installer, the Inter and mono files, `THIRD_PARTY_NOTICES.md`, the `starpilot/` tree, and every existing test.
- **New needs go in this package**, not in shared modules. For example, extra font faces live in `fonts.py` rather than in `FontWeight`.

## Taking over the settings window

The settings window and its panels come from upstream: StarPilot's own panel is built on `aethergrid.py` and `aether_style.py`, and Device, Network, Bluetooth, Toggles, Software and Developer come from openpilot. We don't edit or delete any of them.

- Build each replacement screen in this package.
- Tandem's own settings window replaces the whole upstream window. It goes in with one line in `selfdrive/ui/layouts/main.py`, where the window is created. That's the second and last upstream edit.
- Tabs that haven't been rebuilt yet host their upstream panel inside our window.
- The replaced upstream code then stays in the tree unused. It costs nothing at runtime, because it isn't imported, and it never conflicts on a rebase.

## Third-party

Figtree is © 2022 The Figtree Project Authors (<https://github.com/erikdkennedy/figtree>), used under the SIL Open Font License 1.1. The license text is in `selfdrive/assets/fonts/Figtree-OFL.txt`. The `.ttf` files are unmodified; the `.fnt`/`.png` atlases are generated from them by `tools/build_figtree_fonts.py`.

Tests: `tests/test_tandem.py`.
