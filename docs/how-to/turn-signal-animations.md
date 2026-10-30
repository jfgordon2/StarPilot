# Turn-signal frogs in the raylib UI

The raylib UI supports StarPilot's original six-frame jumping-frog turn signals
on comma 3/3X and comma 4. The frog assets are bundled; no download is needed.

- **Comma 3/3X:** StarPilot settings → Appearance → Driving Widgets & HUD →
  Turn Signal Animation → Frog.
- **Comma 4:** Settings → Visuals → Turn Signal Animation → Frog.
- Select **None** to disable the selected animation.

The comma 3/3X picker also lists downloaded packs containing supported PNG signal
frames; GIF-only and blind-spot-only packs are excluded. The smaller comma 4
picker deliberately offers None and Frog, plus the currently saved custom pack.

Selecting Frog (or another non-stock signal pack) enables the existing Custom
Themes setting and turns Random Themes off so the selected animation takes
effect. Enabling Custom Themes also reactivates any saved color, icon, distance
icon, and steering-wheel selections; those preferences are not reset.
Automatic holiday themes still override the saved signal selection, including
when Custom Themes is off. Turn off Holiday Themes (next to Turn Signal Animation on either device, or in
The Galaxy) if you want the selected frogs
throughout the year. Turning Random Themes back on lets it choose the active
signal pack again. Simple Mode disables custom signal animations.

The animation uses `carState.leftBlinker` and `rightBlinker`; it does not require
openpilot engagement or openpilot longitudinal control, so factory ACC works.
Right turns mirror the frog, hazards draw both directions, and a factory
blind-spot detection uses the theme's warning image on the corresponding side.
Full-screen alerts suppress the animation. Comma 3 alerts reserve space at the
bottom; comma 4 lane-change alerts reserve space at the top, and all other comma
4 alerts use a full-height background and suppress the animation.

The renderer also reads installed PNG signal themes from `active_theme/signals`,
including numbered frames, `turn_signal_blindspot.png`, and the existing
`traditional_<milliseconds>` / `static_<milliseconds>` timing markers. GIF signal
themes are not supported by this renderer.
The active frog pack takes precedence over the bundled fallback, so edits to
`theme_packs/frog/signals` are used when the theme manager activates that pack.
When switching to Frog, bundled frogs appear immediately if the active link
still points at another pack, then the installed frog assets load after relinking.
Static signal themes do not yet reproduce Qt's stopped-timer suppression;
jumping frogs use the traditional style and are unaffected by that difference.

Host regression tests (no vehicle or graphics window required):

```sh
PYTHONPATH=. pytest -q -c /dev/null --confcutdir=selfdrive/ui/tests selfdrive/ui/tests/test_turn_signals.py
```

After installing the change, check left, right, and hazard signals while parked,
with ACC disengaged and engaged. This change only draws UI overlays.
