# StarPilot Essentials: design direction

An opinionated take on the StarPilot 3X settings UI. Instead of exposing a control for every param, StarPilot ships good defaults and offers a small number of controls. Each control writes several existing params at once. Detail that most drivers never need sits behind one-switch bundles.

This builds on the visual direction in *StarPilot 3X UI Directions*, pages 6–9: the hub, the sidebar panel, the option sheet and the onroad bar. The look stays the same. The number of choices goes down.

Open any `.html` file in this folder in a browser. Each screen is 1125×563, the same frame as the PDF. Screenshots are in `screenshots/`.

| Screen | File |
| --- | --- |
| Hub | [hub.html](hub.html) |
| Driving | [driving.html](driving.html) |
| Display and bundles | [display.html](display.html) |
| What a bundle sets | [bundlesheet.html](bundlesheet.html) |
| Onroad, default | [onroad.html](onroad.html) |
| Onroad, Developer View + Lead Insights | [onroaddev.html](onroaddev.html) |
| Alerts | [alerts.html](alerts.html) |
| Tuner Mode | [tuner.html](tuner.html) |
| Defaults map | [defaults.html](defaults.html) |
| Destinations | [destinations.html](destinations.html) |
| Search with keyboard | [navsearch.html](navsearch.html) |
| Route preview | [routepreview.html](routepreview.html) |
| Onroad, navigating | [onroadnav.html](onroadnav.html) |
| Offline maps | [mapdata.html](mapdata.html) |
| Onroad alert levels | [alertstyles.html](alertstyles.html) |
| Confirm new speed limit | [confirmlimit.html](confirmlimit.html) |
| Confirm dialogs | [confirmdialog.html](confirmdialog.html) |
| Progress, blocked, done, empty | [feedback.html](feedback.html) |
| Parked home | [home.html](home.html) |
| First-run setup | [setup.html](setup.html) |
| Driving Model | [model.html](model.html) |
| System | [system.html](system.html) |
| Vehicle | [vehicle.html](vehicle.html) |
| Steering headroom | [steeringheadroom.html](steeringheadroom.html) |

## Principles

1. **One control per decision a driver actually makes.** About 190 rows in `selfdrive/ui/layouts/settings/starpilot/` become 14 controls.
2. **Presets over sliders.** A segmented choice, such as Relaxed / Standard / Sport, writes a coherent set of values. Raw numbers live only in Tuner Mode.
3. **Bundles for power users.** Developer View, Lead Insights and Tuner Mode are each one switch. Turning a bundle off restores the values it replaced.
4. **Safety info is never hidden.** The Hide* toggles for speed, max speed, alerts, steering wheel, driver monitoring icon and lead marker are removed.
5. **Show state, not descriptions.** Hub tiles show current values ("Standard · Auto lane change") so a driver can check their setup at a glance.

## Controls and the params they write

Defaults are in **bold**.

### Driving

| Control | Choices | Params |
| --- | --- | --- |
| Driving Style | Relaxed · **Standard** · Sport | `LongitudinalPersonality` `AccelProfile` `DecelProfile` `HumanLaneChanges` |
| Speed Limits | Off · Show · **Match** (offset **+3**) | `ShowSpeedLimits` `SetSpeedLimit` `SLCConfirmation` `SLCFallback` `SLCPriority` `SLCMapboxFiller` `VisionSpeedLimit` `ConfigureOffsets` `UseVienna` (from region) |
| Lane Changes | Nudge · **Auto** | `NudgelessLaneChange` `OneLaneChange` `LaneChangeTime` `MinimumLaneChangeSpeed` `LaneDetectionWidth` `LaneChangeSmoothing` |
| Smart Slowdowns | **On** · Off | `ConditionalExperimental` `CECurves` `CEStopLights` `CEStoppedLead` `CESlowerLead` `CurveSpeedController` `MapDecel` |
| Always-On Steering | **On** · Off | `AlwaysOnLateral` `PauseAOLOnBrake` `TeslaAOLDisengageOnBrake` |
| Vehicle Profile | **Car** · EV · Truck · Towing | `EVTuning` `TruckTuning` `TrailerLoad` |
| Weather | **Auto** · Off | `WeatherPresets` `LowVisibility` `Rain` `RainStorm` `Snow` |

### Display and alerts

| Control | Choices | Params |
| --- | --- | --- |
| Path Style | **Standard** · Thin · Rainbow · Acceleration | `PathColor` `PathWidth` `PathEdgeWidth` `PathEdgesColor` `LaneLinesColor` `LaneLinesWidth` `RoadEdgesWidth` `RainbowPath` `AccelerationPath` `DynamicPathWidth` |
| Clean Screen | **On** · Off | `HideChangingLanesBanner` `HideTurningBanner` `HideDistanceProfileBanner` `QOLVisuals` |
| Blind Spot Highlights | **On** · Off | `BlindSpotPath` `BlindSpotMetrics` `SignalMetrics` `BorderWidth` |
| Alert Volume | Quiet · **Normal** · Loud | `EngageVolume` `DisengageVolume` `PromptVolume` `PromptDistractedVolume` `RefuseVolume` `WarningSoftVolume` `WarningImmediateVolume` `BelowSteerSpeedVolume` |

The four chime switches stay as they are: Green Light (**on**), Lead Departure (**on**), Speed Limit Change (off) and Loud Blind Spot (off). Warning volumes keep their existing 25% floor.

### Power user

| Control | Default | Params |
| --- | --- | --- |
| Developer View | **Off** | `DeveloperSidebar` `DeveloperSidebarMetrics` `DeveloperMetrics` `FPSCounter` `ShowCPU` `ShowGPU` `NumericalTemp` `ShowMemoryUsage` `AdjacentPathMetrics` `ShowCSCStatus` `ShowSLCOffset` `SpeedLimitSources` |
| Lead Insights | **Off** | `LeadInfo` `RadarTracksUI` `ShowStoppingPoint` `ShowStoppingPointMetrics` `AdjacentPath` `PedalsOnUI` |
| Tuner Mode | **Off** | Writes nothing. It unhides `SteerDelay` `UseAutoSteerDelay` `SteerFriction` `SteerKP` `NNFF` `NNFFLite` `ForceTorqueController` `ForceAutoTune` `ActuatorDelay` `MaxAccel` `StartAccel` `StopAccel` `StoppingRate` `StartSpeed` `StopSpeed` `LeadDetection` `CustomCruise`, plus per-item overrides inside bundles |

## Fixed values, no longer shown

Holiday themes **on**, rotating wheel **on**, stopped timer **on**, compass off, wheel speed off, reverse cruise increase off, pulse and glide off, map gears off, force stops and force standstill off, model randomizer off. The onroad personality button (`OnroadDistanceButton`) is removed.

## Navigation changes

- The bottom bar drops the **Toggles** and **Developer** tabs. Metric units and language move to System. SSH, ADB and joystick move under Tuner Mode.
- The hub has six tiles: Driving, Display, Alerts, Driving Model, Vehicle, System. A "Power user" strip below them holds the three bundle switches.
- The onroad bar drops the Experimental flask, because Smart Slowdowns switches modes automatically. A status chip such as "Slowing for curve" shows when it acts.
- **The onroad bar holds four things:** menu, MAX −/+, the current street name, and the engage button.
  - Driving Style is set in Settings › Driving and with the wheel's distance button. There is no onroad toggle for it.
  - The street name is always on, which retires the `RoadNameUI` toggle. While navigating, arrival time, distance left and End route take its slot, and the street name moves to a chip above the steering headroom arc.

## Steering headroom

This builds on the existing torque bar in `selfdrive/ui/onroad/starpilot/torque_bar.py`. That bar is the clearest early signal that the car is running out of steering on a curve, so it is always on. The `EnableTorqueBarWidget` and `ShowSteering` toggles go away.

- It keeps the current arc at the bottom of the road view and the current estimate (lateral acceleration plus path error plus road tilt, divided by the car's maximum).
- **Three stages instead of a gradual fade:**
  - **Comfortable (under 60%):** a thin white arc and no sound.
  - **Working (60–85%):** the arc turns amber and gets thicker.
  - **At limit (over 85%, held for about half a second):** the arc turns orange-red, the lane lines tint, and the Warning alert "Help steer" plays one chime.
- **Preview of the curve ahead.** A faint extension of the arc shows the steering the planned path will need 2–3 seconds out, based on the model's desired curvature at the current speed. The driver sees trouble before the car reaches it.
- The arc sits on the road view just above the onroad bar, where the driver is already looking. It replaces the flat "STEERING" bar from the earlier mocks.

Open: the 60% and 85% thresholds, and whether the preview should use the model's plan or map curvature when a route is active.

## Navigation

- **Destinations are one tap from the parked home screen** ("Where to?"), not buried under Driving Controls › Navigation & Maps.
- Destinations shows Home, Work, up to 3 more favorites and recent places. Search uses the on-device keyboard.
- **The route preview has no toggles.** While a route is active, `NavDesiresAllowed` and `NavLongitudinalAllowed` are always on: the car slows for turns and uses route speed limits where signs are missing.
- Onroad, the turn instruction sits top-left and the speed limit sign moves top-right. Arrival time, remaining distance and End route replace the steering bar.
- **Offline maps start from one detected region**, with weekly updates by default (only while parked on Wi-Fi). The full state and region picker stays behind "Add another region".

## Alerts and dialogs

- **Three onroad alert levels.** Info is a small banner and the border stays green. Warning has an amber border and a two-line banner. Critical is a full-screen red takeover. Clean Screen never hides any of them.
- **Speed limit confirmation** appears as a card on the speed sign, with Ignore and Match buttons and an 8 second timeout. Pressing Resume on the wheel also matches. This is the Match default with `SLCConfirmation` on.
- **Confirm dialogs come in two kinds.** Destructive actions get a red button and a "can't be undone" line. Actions that need a restart get a blue "Restart now" button and a Later option.
- **Every long-running job uses the same four states:** in progress (bar and cancel), blocked (lock icon and the reason, e.g. "park to download"), done (a 4 second toast, never shown while driving) and empty (a short explanation and the next action).

## Remaining screens

- **Parked home** shows readiness and the current setup, plus Where to? and update status. Detailed device stats move to Developer View.
- **First-run setup** asks three questions: driving style, then speed limits, then lane changes. "Use defaults" skips all three.
- **Driving Model** defaults to the recommended model for the car, which updates automatically. Picking another model means turning Use recommended off. The randomizer and blacklist move to Tuner Mode.
- **System** keeps units, language, brightness (Dimmer / Auto / Brighter), Standby, uploads and weekly backups.
- **Vehicle** shows the detected car with a "Wrong car?" link, which covers `CarMake`, `CarModel` and `ForceFingerprint`. Steering wheel buttons come preset for each car, and Auto-Lock Doors is a single switch.

## Open questions

- **Preset values.** The values each Driving Style and Alert Volume preset writes are placeholders. They need tuning against real drives.
- **Bundle state storage.** When a bundle turns off, the prior values need to be restored. That needs either a saved snapshot per bundle or a rule of "bundle owns these keys while on".
- **Interaction between bundles and Tuner Mode.** If someone overrides one param inside a bundle, is the bundle still "on"? The mocks show it as on, with the override listed under Tuner Mode › Bundle Overrides.
- **Migration.** Existing users have custom values. On first launch, map them to the nearest preset, or show "Custom" until the user picks one.
