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

Holiday themes **on**, rotating wheel **on**, stopped timer **on**, compass off, wheel speed off, reverse cruise increase off, pulse and glide off, map gears off, force stops and force standstill off, model randomizer off. The personality button moves into the onroad bar as the Driving Style selector.

## Navigation changes

- The bottom bar drops the **Toggles** and **Developer** tabs. Metric units and language move to System. SSH, ADB and joystick move under Tuner Mode.
- The hub has six tiles: Driving, Display, Alerts, Driving Model, Vehicle, System. A "Power user" strip below them holds the three bundle switches.
- The onroad bar drops the Experimental flask, because Smart Slowdowns switches modes automatically. A status chip such as "Slowing for curve" shows when it acts.

## Open questions

- **Preset values.** The values each Driving Style and Alert Volume preset writes are placeholders. They need tuning against real drives.
- **Bundle state storage.** When a bundle turns off, the prior values need to be restored. That needs either a saved snapshot per bundle or a rule of "bundle owns these keys while on".
- **Interaction between bundles and Tuner Mode.** If someone overrides one param inside a bundle, is the bundle still "on"? The mocks show it as on, with the override listed under Tuner Mode › Bundle Overrides.
- **Migration.** Existing users have custom values. On first launch, map them to the nearest preset, or show "Custom" until the user picks one.
