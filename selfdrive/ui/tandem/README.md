# Tandem

Tandem is this fork of StarPilot. Its design language is **Essentials**: fewer choices and better defaults, with the car explaining what it's doing. This package holds the Essentials component library. The mocks, screenshots and tokens are in [`design/`](design/). It's built on raylib and the existing `Widget` base class. Screens are put together from these pieces instead of drawing with raylib directly.

| Module | Contents |
| --- | --- |
| `fonts.py` | `font(face)`: the shared `FontWeight` faces from `gui_app`, plus `ExtraFont.EXTRA_BOLD` and `ExtraFont.MONO`, which load on first use. |
| `tokens.py` | Colors, type sizes, radii, layout sizes and timings in device pixels. `px()` converts mock pixels and `font_px()` converts mock font sizes. |
| `layout.py` | Rectangle math: `row`, `column`, `grid` (fixed sizes plus `FILL`), `inset`, `place`, `grow`. It doesn't draw. |
| `draw.py` | Rounded fills, single-line text (aligned and elided), captions, wrapped paragraphs, and `icon()`, which draws the mocks' line icons tinted (chevron, cross, plus and check use them too). |
| `icons/` | The mocks' icons: `svg/` holds each one copied from the mocks, and the PNGs beside it are rasterized from them by `tools/build_icons.js` (`node tools/build_icons.js`, needs Playwright's Chromium). Add an icon by adding its SVG and rerunning the tool. |
| `base.py` | `Component`: a `Widget` with `preferred_size()`, plus a touch area grown to `MIN_TOUCH`. `resolve()` for values that may be getters. |
| `controls.py` | `Button` (primary, secondary, ghost, danger for a confirm, danger soft for every other destructive button, nav), `ButtonRow`, `ValueButton`, `ToggleButton`, `Switch`, `Segmented`, `ChoiceCards`, `Stepper`, `Slider`, `Badge`, `Chip`, `ProgressBar` |
| `rows.py` | `SettingRow`, `SectionHeader`, `Text`, `Banner`, `OptionList` (pick one from a list), `Padded`, and `ListPanel`, which stacks rows with dividers, scrolls when they overflow, and can pin a footer |
| `chrome.py` | `BottomNav`, `Sidebar`, `PageHeader`, `HubTile`, `HubGrid`, and `SettingsPage`, which assembles a full screen |
| `assets/` | `boot_logo.jpg`, Tandem's boot logo (2160×1080, from `boot_logo.html`). Choosing it copies the file into StarPilot's boot logos folder, where StarPilot's theme manager installs it like any other logo; the Essentials defaults choose it. |
| `blocks.py` | Layout blocks for the mocks' card layouts: `Stack` (with `SPACER`s or a growing item), `Card`, `Columns`, `Grid`, `Label`, `ValueLine`, `IconTitle`, `InfoCard`, `Field`, `Icon`, `Inline`, `Sized`, `Surface` |
| `overlays.py` | `Sheet` (slides up), `Dialog` (confirm; `Tone.DANGER` gives a destructive button), `Toast` |

## Building a screen

The param names below are made up to keep the example short; `settings/` has the real screens.

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
- **Upstream integration:**
  - The file names in `FontWeight` (`system/ui/lib/application.py`), which switch the whole UI to Figtree.
  - In `selfdrive/ui/layouts/main.py`: the imports, the calls that create the sidebar, home, settings and onroad screens (`screens.py`), and the left sidebar's width. StarPilot's developer sidebar on the right keeps upstream's width.
  - In the wheel controls daemon and its manager predicate: temporary button testing runs while the Bluetooth screen is open, including onroad, without changing the saved enable setting. Tests cover the service and screen lifecycle.

  If a rebase conflicts in these files, keep upstream's version and reapply the integration.
- **Unchanged:** `Widget`, `process.py`, the installer, the Inter and mono files, `THIRD_PARTY_NOTICES.md`, and the upstream settings panels.
- **New needs go in this package**, not in shared modules. For example, extra font faces live in `fonts.py` rather than in `FontWeight`.

## The settings window

`settings/` is the Essentials settings window. `selfdrive/ui/layouts/main.py` creates it through `settings_window()` instead of upstream's `SettingsLayout`. Set `TANDEM_SETTINGS=0` to get the upstream window back.

### How it's built

- **Window:** `window.py` has five tabs, each with its own page stack, and the close/back button. It also takes upstream `PanelType`s, so the home screen and sidebar open the right tab. Sheets and dialogs are drawn over the page by the window itself (`present`/`dismiss`), because the app draws only the top widget of its own stack.
- **Models and panels:** each screen is a small model class that reads and writes params through `SettingsStore`, plus a function that builds its panel. One control usually writes several params, and the model owns that mapping. Tests drive the models with a fake param cache.
- **Upstream logic:** anything with real logic behind it goes through an adapter class named `Upstream…` that calls upstream code. That covers downloads, Wi-Fi, Bluetooth, wheel remotes, the updater, the car list, and calibration and power. Upstream keeps its checks, threads and confirmations, and we only draw. The window takes each adapter as a constructor argument, so tests and headless renders pass fakes (`tests/fakes.py`).
- **Signalling:** `SettingsStore.write` signals the driving processes once per call. `SettingsStore.batch()` groups many writes into one signal; Reset Settings uses it.

| Tab | Screens | Files | Upstream code it drives |
| --- | --- | --- | --- |
| Driving | Hub with the power-user switches | `driving_tab.py`, `bundles.py` | |
| | Speed & Steering: Everyday, Vehicle Profile, Weather, Navigation, Assistance | `speed_steering.py` | |
| | Display: Driving Screen, Theme & Startup, Map | `display.py` | |
| | Alerts, with the volume sheet | `alerts.py` | Sounds screen's sample player |
| | Driving Model and its catalog | `model.py` | Driving model screen controller |
| | Vehicle and the car picker | `vehicle.py` | Fingerprint catalog, button actions |
| | Offline Maps and the region picker | `maps.py` | Maps screen controller |
| | Tuner Mode: Steering, Gas & Brake, Following & Stops, Bundle Overrides | `tuner.py`, `editors.py` | |
| Device | This Device | `device.py` | `DeviceLayout` handlers |
| | General, Backups, Storage & Data, Report a Problem | `device_sections.py` | Same folders and report as StarPilot's System screen |
| Network | Wi-Fi, Cellular, and Roaming, APN and IP address | `network_tab.py` | `WifiManager` |
| Bluetooth | Wheel Buttons, car audio, nearby devices | `bluetooth_tab.py` | Wheel controls service, `BluetoothManager` |
| Software | Updates, release channel, Reset Settings, Uninstall | `software_tab.py`, `defaults.py` | `SoftwareLayout` actions |

### Upstream screens still shown, one tap away

These are reached from a row or button, never as a tab:

- **Destination search**, from Navigation's Set or Change. In the mocks it belongs on the parked home screen, which isn't built yet.
- **"More for your car"** under Vehicle. It holds car-specific toggles (Toyota, Subaru, Bolt, Jeep) and panda flashing.
- **openpilot's Developer panel**, under Device, only while Tuner Mode is on.

`upstream.py` hosts them. `StarPilotPage` opens one StarPilot panel directly, without going through StarPilot's own hub.

### Where the code differs from the mocks

- **Alerts:** the volume preset adds **Auto**, upstream's default, where the level follows cabin noise.
- **Uploads:** offers Off, **Parked** and Always. Upstream can hold uploads while driving, but it has no Wi-Fi-only switch.
- **Things upstream has no support for:**
  - Automatic weekly backups.
  - "Attach last drive" in Report a Problem.
  - Automatic matching of the speed limit sign style to your region, so the choice is US or Vienna.
- **Wheel remotes** don't come with four preset buttons. A button has to be pressed before it can be mapped.
- **Wheel-button testing** captures remote presses while the Bluetooth tab is shown, including onroad and with no mappings yet. Leaving the tab or closing settings ends testing and cancels pending learning. Testing does not change the saved enable setting for normal remote actions.
- **Button favorites** run the existing settings/action favorites. Car and remote pickers show each saved action's name; these are separate from saved destinations. Removing or moving a remote mapping frees its controller action slot once no other button uses it.
- **openpilot's core switches** live in Speed & Steering › Assistance. Upstream's "Experimental mode" switch is gone; Smart Slowdowns switches modes automatically.

## Onroad, home and first-run setup

`screens.py` creates the screens MainLayout shows. Setting `TANDEM_SIDEBAR=0`, `TANDEM_HOME=0`, `TANDEM_SETTINGS=0` or `TANDEM_ONROAD=0` brings back upstream's version of that screen.

- **Onroad** (`onroad/`): `EssentialsOnroadView` subclasses StarPilot's onroad view and keeps its camera, path, lane lines and alerts. It replaces the following:
  - **Bottom bar:** a scrim, not a panel. It holds menu (the sidebar), MAX − / + (StarPilot's `SLCForceCruiseSpeed`, only while engaged), the street name, and engage.
    - Engage and disengage go through the wheel controls' action counters.
    - While a route is active, the street name gives way to arrival time, what's left and End route. That reads `navInstruction` through the view's own subscriber, since `ui_state` doesn't subscribe to it.
  - **Status chip** (top right): one at a time, held 2 s, hidden during alerts. The rules are in `onroad/status.py`, pure and tested.
  - **Steering headroom arc:** replaces the torque bar and uses its estimate. It has three stages (under 60%, 60–85%, over 85% held for 0.5 s) and a faint preview of what the path needs 2.5 s ahead.
    - At limit, the lane lines turn orange, the border turns amber, and Help steer plays one soft warning chime through soundd. It uses the warning volume and steering-limit mute-speed settings. The warning clears below 80%, or when steering becomes inactive; existing alerts take priority. The small release margin prevents repeated chimes around 85%.
  - **New-limit card:** asks before matching a higher limit. Match sends StarPilot's `SpeedLimitAccepted`. Ignore suppresses consecutive offers for that same limit, including after an offer expires or its source briefly disappears. An intervening higher or lower posted limit, or a new drive, allows it again.
  - **Speed, sign and turn card:** StarPilot still decides when each shows (its HUD's speed with the hide-speed rule, its speed card's posted limit, its turn card's route data); they're drawn as in the mocks. The sign sits top left, moves top right while navigating and hides while the new-limit card asks. The compass above the speed isn't drawn.
  - **Turn signal:** two green chevrons in the speed pill on the signalling side, the brighter one stepping outward. It replaces StarPilot's signal animations, so Display has no animation picker.
  - **Removed:** the driving personality button, the experimental-mode wheel, the favorites menu (the lower-left gesture), the picture-in-picture side camera (a Galaxy developer feature), the stopped timer, and the paused and weather badges, which the chips replace. The driver monitor icon sits above the bar.
- **Home** (`home.py`): upstream's HomeLayout with new home content: readiness and the current setup, Where to? (StarPilot's destination search), and update status. The home cards use the full content height without the legacy header or its tap targets. Offroad alerts and update details retain upstream's header and navigation.
- **Sidebar** (`sidebar.py`): subclasses upstream's Sidebar, which still tracks device state and owns the callbacks. It has a Settings button and a status card with Network, comma connect, Temperature, Vehicle and Maps, each with a colored dot. Onroad it adds Save a clip (upstream's flag button), and it shows a recording indicator while cabin audio is recorded.
- **First-run setup** (`setup.py`): three questions, or Use defaults. Either way it applies the Essentials defaults first. Home shows it once, as soon as onboarding has closed; a marker file beside the params folder records that it's done, so no new param key is needed.

What these don't do yet:
- **Developer View metrics** keep upstream's layout.

## Third-party

Figtree is © 2022 The Figtree Project Authors (<https://github.com/erikdkennedy/figtree>), used under the SIL Open Font License 1.1. The license text is in `selfdrive/assets/fonts/Figtree-OFL.txt`. The `.ttf` files are unmodified; the `.fnt`/`.png` atlases are generated from them by `tools/build_figtree_fonts.py`.

Tests: `tests/test_tandem.py` (components) and `tests/test_settings.py` (window navigation and param mapping).
