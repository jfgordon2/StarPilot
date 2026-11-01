# AGENTS.md

Tandem is a fork of StarPilot (which sits on openpilot). Its UI design language is **Essentials**. These rules hold for any change in this repo.

## Keep unowned code untouched

Everything outside Tandem's own files belongs to StarPilot or openpilot and changes with every upstream merge. The less of it we edit, the easier merges are.

- **Ours:** `selfdrive/ui/tandem/` (code, `design/`, `tools/`, `tests/`), `starpilot/tandem/`, the Figtree and JetBrains Mono font files in `selfdrive/assets/fonts/`, `RELEASES.md`'s top entry, and this file (with `CLAUDE.md`, which imports it for Claude Code).
- **Everything else is unowned.** Put new behavior in our files: subclass, wrap or call upstream code instead of editing it. Read upstream's state rather than adding fields to it.
- **When an upstream edit can't be avoided,** make it the smallest hook that works: a flag that defaults to upstream's behavior, an overridable method, or one line. Don't reformat or reorganize around it.
- **List every upstream edit** in `selfdrive/ui/tandem/README.md` under "Keeping rebases easy" › Upstream integration, so a merge knows what to reapply.
- **Never change upstream's behavior for its own UI.** The `TANDEM_*=0` environment switches bring back upstream's screens, and they must still work as upstream intended.

## Merging upstream

- Upstream is the `StarPilot` branch of `StarPilotHQ/StarPilot`. Tandem merges it; it doesn't rebase, so pushes never need force.
- In a conflict on an unowned file, keep upstream's version and make our edit again.
- After a merge, check what Tandem reads from StarPilot that can change without a conflict. The README's "Branches and merging upstream" section lists it.

## Design

- **Mock first.** A new or changed screen gets its HTML mock in `selfdrive/ui/tandem/design/` (with a screenshot in `design/screenshots/`) before the code, and the code then matches the mock.
- **Don't change an approved mock without asking the owner.** If the code has to differ, say where and why in the README's "Where the code differs from the mocks".
- **Build screens from the component library** (`tokens.py`, `layout.py`, `draw.py`, `controls.py`, `rows.py`, `blocks.py`, `chrome.py`, `overlays.py`), not with raw raylib calls. Sizes come from the mocks through `T.px()` and `T.font_px()`.
- **Keep StarPilot's logic.** Essentials redraws StarPilot's settings, alerts and onroad state; StarPilot still decides what's true, what's allowed and when. Settings write StarPilot's own params.
- **Wording:** plain words about what the car does, sentence case, and no em dashes (Figtree has none in the atlases).

## Settings search

Every settings row is indexed in `selfdrive/ui/tandem/settings/search.py`. When you add, rename or move a setting, update its entry; `tests/test_settings.py` checks the index against every screen.

## Tests

- Run `pytest selfdrive/ui/tandem/tests` before pushing, and add tests for new behavior. `ruff check selfdrive/ui/tandem` must pass.
- Some tests import `cereal` and need a full openpilot build. Where that isn't available, say which tests didn't run.
- Don't skip or weaken a test to get green.

## Release notes

A device's "What's new" is the top entry of `RELEASES.md`, up to its first blank line; GitHub releases aren't read. Before a release, add a new top entry: a `Tandem <date>` heading, its `===` line, then `* ` bullets with no blank lines inside.
