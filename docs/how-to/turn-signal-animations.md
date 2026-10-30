# Turn-signal animations in the raylib UI

The raylib UI supports animated turn signals on comma 3/3X and comma 4. Eight are
bundled, so no download is needed.

**Indicators** follow the on-road widget design language: the Set Speed card's
translucent fill, border and corner radius, with green chevrons pointing towards
the turn. They stay in place level with the current speed (left of centre for
left turns, right of centre for right turns, both for hazards). For blind-spot
warnings the chevrons stop and the card turns traffic red.

- **Sequential**: three chevrons light one after another towards the turn.
- **Flow**: chevrons glide continuously towards the turn inside the card, fading
  in beside the speed and out at the far edge.
- **Open Flow**: the same motion without a card; the floating chevrons have a
  soft shadow so they stay readable over bright scenes.
- **Glide**: a compact card the width of the Set Speed card, where one bold
  chevron slides out and fades while the next fades in behind it.

**Animations** travel across the screen:

- **Frog**: StarPilot's original six-frame jumping frog.
- **Pouncing Cat**: an orange tabby that crouches, leaps and pounces, then
  settles back into a crouch; its blind-spot image is an arched-back red cat.
- **Shooting Star**: a smiling star that arcs across the screen with a sparkling
  gold trail streaming behind it; its blind-spot image is a startled red star.
- **Bouncing Ball**: a white ping-pong ball drops in from the top of the screen,
  touches down four times as it bounces towards the turn, and bounces off the far
  edge; one unhurried pass takes 3 seconds. Its blind-spot image is a red ball
  rolling along the ground.

To choose one:

- **Comma 3/3X:** StarPilot settings → Appearance → Driving Widgets & HUD →
  Turn Signal Animation (listed alphabetically).
- **Comma 4:** Settings → Visuals → Turn Signal Animation (indicators first, then
  animations).
- Select **None** to disable the selected animation.

The comma 3/3X picker also lists downloaded packs containing supported PNG signal
frames; GIF-only and blind-spot-only packs are excluded. The smaller comma 4
picker deliberately offers None and the bundled animations, plus the currently
saved custom pack.

Selecting an animation (or another non-stock signal pack) enables the existing Custom
Themes setting and turns Random Themes off so the selected animation takes
effect. Enabling Custom Themes also reactivates any saved color, icon, distance
icon, and steering-wheel selections; those preferences are not reset.
Automatic holiday themes still override the saved signal selection, including
when Custom Themes is off. Turn off Holiday Themes (next to Turn Signal Animation
on either device, or in The Galaxy) if you want your selected animation
throughout the year. Turning Random Themes back on lets it choose the active
signal pack again. Simple Mode disables custom signal animations.

The animation uses `carState.leftBlinker` and `rightBlinker`; it does not require
openpilot engagement or openpilot longitudinal control, so factory ACC works.
Right turns mirror the animation, hazards draw both directions, and a factory
blind-spot detection uses the theme's warning image on the corresponding side.
Full-screen alerts suppress the animation. Comma 3 alerts reserve space at the
bottom; comma 4 lane-change alerts reserve space at the top, and all other comma
4 alerts use a full-height background and suppress the animation.

The renderer also reads installed PNG signal themes from `active_theme/signals`,
including numbered frames, `turn_signal_blindspot.png`, and the existing
`traditional_<milliseconds>` / `static_<milliseconds>` timing markers. GIF signal
themes are not supported by this renderer.
Bundled assets live in `starpilot/assets/holiday_themes/world_frog_day/signals`
(Frog) and `starpilot/assets/signal_packs/<slug>/signals` (`pouncing_cat`,
`shooting_star`, `sequential`, `flow`, `open_flow`, `glide`, `bouncing_ball`). At boot the theme manager copies them into
`theme_packs/<slug>/signals`, and the installed copy takes precedence, so
edits there are used once the theme manager activates that pack. When switching
animations, the bundled frames appear immediately if the active link still points
at another pack, then the installed copy loads at the next signal after relinking.
To add another bundled animation, put its `signals` folder under
`starpilot/assets/signal_packs/<slug>/` and add the slug to `BUNDLED_SIGNAL_PATHS`
in `turn_signals.py` and to both pickers (a test checks every bundled pack is
offered on both devices). The bundled frames are drawn by scripts in
`starpilot/tools/`: `make_pouncing_cat_signals.py`, `make_shooting_star_signals.py`,
`make_sequential_signals.py`, `make_motion_signals.py` (Flow, Open Flow and
Glide) and `make_bouncing_ball_signals.py`; dev-only: `pip install cairosvg`. The indicator cards mirror
`widget_style.py`; a test fails if the two drift apart, so regenerate the frames
after changing those values.
Unlike the frog and cat, the star's six frames form one continuous arc, so each
loop starts as a new star rather than cutting off a second hop.
The indicators use the `static` style, so they animate in place rather than
moving across the screen: Sequential with six frames at 125 ms (`static_125`),
Flow, Open Flow and Glide with twelve frames at 62 ms (`static_62`) for smooth
motion. The static style places a frame half its height below the top of the
view, so the indicators use a short 350x170 canvas that keeps them level with the
speed digits (and uses about a third of the texture memory of a 350x500 frame).
Unlike Qt, static signals are not hidden while the car is stopped, which suits an
indicator; the travelling animations use the traditional style. Bouncing Ball's
frames are the full screen height (64x1080) so the ball can fall from the top;
its 40 frames at 75 ms use about 11 MB of texture memory while it is selected.
Like the other full-width animations, it briefly passes over the top-corner
controls as it drops in, and a bottom alert scales the pass down to fit above it.

## Speed at Bottom (comma 3/3X)

The `SpeedAtBottom` toggle (Appearance on the device, Visual (Display & UI) in
Galaxy) moves the current speed, its unit and the compass to the bottom of the
screen, leaving the same gap between the unit label and the idle torque bar as
between the bar and the bottom of the view (derived from the torque bar's geometry,
so it scales with the view). `StarPilotOnroadView` computes one
vertical offset and hands it to `HudRenderer.speed_offset_y`, the stopped timer and
`TurnSignalRenderer.render(static_offset=...)`, so static indicators (Sequential,
Flow, Open Flow, Glide) stay level with the speed. Travelling animations (Frog,
Cat, Shooting Star, Bouncing Ball) get a larger `bottom_margin` instead, so they
pass above the speed rather than over it. While a small or mid alert shows, the
block rises to sit `SPEED_ALERT_GAP` above it, eased with the same filter as the
alert margin; full-screen alerts hide the indicators as before. A gradient
behind the bottom speed keeps it readable over the camera image. The comma 4 UI is
unchanged.

The torque bar thickens past 50% torque, so in a hard turn its top edge can
approach the unit text.

## Previewing on the real driving screen

`starpilot/tools/render_onroad_preview.py` renders StarPilot's actual comma 3X
on-road view (`StarPilotOnroadView`, including the real `TurnSignalRenderer`) to
PNG frames or a GIF, so you can check a pack against the real layout: speed,
unified speed card, steering-wheel widget, torque bar and bottom row. Only the
inputs are faked: there is no camera (the road area is the camera-off
background), car data comes from stubbed messaging (speed, cruise, blinkers,
blind spot), settings use an isolated params store, and the turn-signal renderer
gets a controlled clock so frame N is exactly animation frame N.

```sh
python starpilot/tools/render_onroad_preview.py --pack sequential --out /tmp/preview
python starpilot/tools/render_onroad_preview.py --pack bouncing_ball --right --gif /tmp/ball.gif
python starpilot/tools/render_onroad_preview.py --pack flow --hazards --blindspot --frames 1
python starpilot/tools/render_onroad_preview.py --pack sequential --speed-at-bottom --alert small
```

By default it captures one full animation cycle at the pack's own timing. On
Linux without a display, run it under `xvfb-run -a`; on macOS a window may
flash briefly. `--gif` needs Pillow. `--speed-at-bottom` turns on Speed at
Bottom, and `--alert small|mid` shows a sample lane-change or "Take Control"
alert; other alerts, the speed-limit card and the sources drawer aren't simulated.

Host regression tests (no vehicle or graphics window required):

```sh
PYTHONPATH=. pytest -q -c /dev/null --confcutdir=selfdrive/ui/tests selfdrive/ui/tests/test_turn_signals.py
PYTHONPATH=. pytest -q -c /dev/null --confcutdir=starpilot/assets/tests starpilot/assets/tests/test_theme_catalog_refresh.py
```

After installing the change, check left, right, and hazard signals while parked,
with ACC disengaged and engaged. This change only draws UI overlays.
