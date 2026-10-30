# Consistent comma 3/3X settings

The shared settings primitives live in `selfdrive/ui/layouts/settings/starpilot/aethergrid.py`.
Spacing, radii and colors live in `selfdrive/ui/lib/aether_style.py`.

- `build_settings_page_frame` owns the outer gutter, header and header-to-content gap.
  `StarPilotLayout` applies it once, for both the main hub and nested pages. A child
  panel receives the content rectangle and should not add another page margin.
- Use `CardHubManagerView`, `HubGrid` and `HubTile` for category pages. `HubGrid`
  keeps small folders top-aligned with the same card-height limit as the main hub.
- Use `AetherSettingsView`, `SettingSection` and `SettingRow` for settings. Supply
  labels, values, callbacks and visibility rules instead of drawing a new row.
- Toggle, value, action and navigation cards use `draw_settings_card_row` and
  `build_settings_row_layout`. Grid toggle tiles use the same component. Their
  text and trailing controls share insets, spacing and vertical alignment.
- Use `draw_settings_group` for a named group of controls. Its heading sits above
  the outline, with a font-safe text height and a fixed gap to the body. The
  heading, row labels and adjustors all use `SETTINGS_CARD_INSET`. Render controls
  into the returned body rectangle and include `GROUP_OVERHEAD` when measuring
  scroll content. `AetherSettingsView` uses the same heading spacing for sections
  made up of individual cards.
- A list row's slot includes its trailing gap. `row_card_rect` returns only the
  visible card; use that rectangle for hit testing. Shared card outlines stay
  inside those bounds, and scrollbars sit in the page gutter.
- A `ParentToggle` is presented in the shared page header by `_SettingsPage`.
  A standalone view retains its own master-toggle row. Both use the original
  getter and setter.
- Use `AetherButton` for actions instead of clickable text. Its measured height
  meets the shared touch minimum, and it uses the same pill drawing as row actions.
  Set `confirmation` and `confirm_label` for reset or destructive actions; their
  callback runs only after confirmation. A view can return the button from
  `use_page_header` to keep the action visible while its content scrolls.
- Use `AetherSegmentedControl` for mutually exclusive modes. Its selection uses
  the shared card radius and stays inset inside the border, including when pressed.
  It owns its shell, 128-pixel height, 40-pixel label font, insets and segment gaps.
  Give it the full page content width, reserve `measure_height(width)` and use
  `AetherSegmentedControl.GAP` around the bar. Do not add a separate shell or
  derive font size from a page-specific height. Long labels elide at the same
  font size. System, Conditional Drive Mode and Map Data all use this component.
- All selection dialogs inherit `AetherSelectionDialog`. It owns the outlined
  shell, left-aligned title and description, fixed Cancel/Apply pills and the
  content rectangle below them. Titles and descriptions wrap when needed; narrow
  panels put the actions below the copy. Subclasses supply `_render_content`,
  `_can_apply` and `_on_result` instead of drawing another header or footer.
- Use `AetherChoiceDialog` with `PreviewChoice` for visual or text choices. Choose
  `layout="grid"` for thumbnails or `layout="list"` for full-width text rows.
  It owns selection checkmarks, vertical scrolling and clipped touch targets.
  The saved choice is initially visible. Selection stays local until Apply;
  Cancel discards it. Supply preview drawing and cleanup callbacks when needed.
  `SignalPreview` supplies read-only thumbnails from installed or bundled signal
  packs, loads each texture once and releases it when the dialog closes.
- `MultiOptionDialog` adapts string options to that shared scrolling list. Use
  `subtitle` for context and retain `option_font_weight` for language pickers.
  `AetherMultiSelectDialog` uses the same rows with several selections; applying
  an empty selection is valid. Numeric choices use `AetherSliderDialog`, sharing
  the header while retaining the value, presets and slider. Settings helpers reuse
  the originating row's title and description. Live audio/brightness previews
  restore their original value on Cancel or Escape. Button press assignments stay
  local to their parent dialog until its Apply action.
- `ConfirmDialog` and `alert_dialog` (`system/ui/widgets/confirm_dialog.py`) use the
  same outlined card, dialog fill and `AetherButton` Cancel / confirm pills as the
  selection dialogs. A short message gets a centered card sized to its text; `rich=True`
  uses the full-size shell with scrolling formatted text. `AetherButton(confirmation=...)`
  shows this dialog, so reset and destructive actions match automatically.
- Use `draw_centered_text` for prominent numeric values. It centers visible glyph
  bounds rather than the font's line box. `draw_stepper_symbol` draws centered
  plus/minus strokes, so symbols do not depend on font baselines or glyph support.
- An `AetherAdjustorRow` can accept a `RowStatus` or a status getter for an icon
  well, status subtitle and value/chevron. This replaces the level line, while
  preserving the picker callback and making the entire row tappable. Status
  describes the configured value independently of the row's editing state.
- Settings scroll vertically when content exceeds the viewport. Register toggle
  grids with `register_scroll_grid` and populate them with `set_toggle_items`.
  Pass the complete list of items; the shared base measures their full height.
  Keep card dimensions stable instead of paging or squeezing controls to fit.
- Two-column pages use independent vertical scroll regions. `PanelManagerView`
  owns each column's offset, inertia, clipping, scrollbar and touch rejection.
  A custom layout supplies `SettingsColumn` entries from `_build_scroll_columns`;
  each entry declares a stable key, its natural content height and a draw callback.
  The callback receives a rectangle whose origin includes that column's offset.
  Use `_bind_scroll_widget` or `_render_scroll_grid` to bind child controls to the
  current column. `AetherSettingsView` splits long sections and explicit column
  pairs automatically; two-column category grids use the same scroll handling.
  At narrow widths the content stacks into one scroll region. Call `reset_scroll`
  when switching modes or tabs; full-width mode selectors stay above the columns.

Dense grouped adjustors, such as volume controls with live sound previews, retain
their specialized interaction. They should still use the shared page frame,
group shell, typography and control components. Add a new rendering path only
when the interaction or information structure requires it; a different menu
location alone is not a reason.

## Render and inspect

With the repo's Python UI dependencies installed, run from the repository root:

```sh
PYTHONPATH=. python starpilot/tools/render_settings_preview.py --out /tmp/settings-preview
PYTHONPATH=. python starpilot/tools/render_settings_preview.py --page hub --page hud --out /tmp/settings-preview
PYTHONPATH=. python starpilot/tools/render_settings_preview.py --include-scrolled --out /tmp/settings-preview
```

This captures the real 2160x1080 settings widgets with isolated parameters and
stubbed vehicle inputs. The available pages include the hub, Appearance, Driving
Widgets & HUD, Sounds, System, Vehicle, Driving Controls, Gas / Brake and
Conditional Drive Mode and Map Data. `--include-scrolled` captures each overflowing
column at its bottom independently, then captures both columns at the bottom.
Single-column pages get one bottom capture. On Linux without a display,
prefix the command with `xvfb-run -a`. On macOS, a window may appear briefly.
`sounds-states` includes Auto, custom-volume and muted examples; `sounds-volume`
captures the actual volume picker. These samples only change isolated preview parameters.
`signal-picker` captures the Turn Signal Animation grid from PDF page 4.
`camera-picker`, `metric-picker`, `button-picker` and `maintenance-picker` capture
the same header with a short list, long list, button assignments and maintenance
choices. With `--include-scrolled`, overflowing picker lists also get a bottom
capture while their header remains fixed.
`sounds-reset`, `alert-dialog` and `rich-dialog` capture `ConfirmDialog` as a
confirmation, a one-button alert and long formatted text.

The capture uses device-pixel clipping, independent of desktop window scale.
Inspect page edges, gaps, long labels, disabled controls and scroll clipping.

```sh
PYTHONPATH=. pytest -q -c /dev/null --confcutdir=selfdrive/ui/tests selfdrive/ui/tests/test_aethergrid.py
```
