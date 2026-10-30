# Turn-signal animations in the raylib UI

The raylib UI supports animated turn signals on comma 3/3X and comma 4. Three are
bundled, so no download is needed:

- **Frog**: StarPilot's original six-frame jumping frog.
- **Pouncing Cat**: an orange tabby that crouches, leaps and pounces, then
  settles back into a crouch; its blind-spot image is an arched-back red cat.
- **Shooting Star**: a smiling star that arcs across the screen with a sparkling
  gold trail streaming behind it; its blind-spot image is a startled red star.

To choose one:

- **Comma 3/3X:** StarPilot settings → Appearance → Driving Widgets & HUD →
  Turn Signal Animation → Frog, Pouncing Cat or Shooting Star.
- **Comma 4:** Settings → Visuals → Turn Signal Animation → Frog, Pouncing Cat or
  Shooting Star.
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
`shooting_star`). At boot the theme manager copies them into
`theme_packs/<slug>/signals`, and the installed copy takes precedence, so
edits there are used once the theme manager activates that pack. When switching
animations, the bundled frames appear immediately if the active link still points
at another pack, then the installed copy loads at the next signal after relinking.
To add another bundled animation, put its `signals` folder under
`starpilot/assets/signal_packs/<slug>/` and add the slug to `BUNDLED_SIGNAL_PATHS`
in `turn_signals.py` and to both pickers. The cat and star frames are drawn by
`starpilot/tools/make_pouncing_cat_signals.py` and
`starpilot/tools/make_shooting_star_signals.py` (dev-only: `pip install cairosvg`).
Unlike the frog and cat, the star's six frames form one continuous arc, so each
loop starts as a new star rather than cutting off a second hop.
Static signal themes do not yet reproduce Qt's stopped-timer suppression; all
bundled animations use the traditional style and are unaffected by that difference.

Host regression tests (no vehicle or graphics window required):

```sh
PYTHONPATH=. pytest -q -c /dev/null --confcutdir=selfdrive/ui/tests selfdrive/ui/tests/test_turn_signals.py
PYTHONPATH=. pytest -q -c /dev/null --confcutdir=starpilot/assets/tests starpilot/assets/tests/test_theme_catalog_refresh.py
```

After installing the change, check left, right, and hazard signals while parked,
with ACC disengaged and engaged. This change only draws UI overlays.
