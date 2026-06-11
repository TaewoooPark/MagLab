# Changelog

## v0.0.4

A UX hardening pass driven by exercising the CLI/REPL as a real user end to end.

### Fixed

- Report the installed package version and accept the conventional
  `--version`/`-V` flag (previously only a `version` subcommand existed and it
  printed a stale hardcoded `0.0.1`); `__version__` now derives from package
  metadata so it can never drift again.
- Let the Codex delegated backend run outside a Git repository by passing
  `--skip-git-repo-check`; `maglab auth test` and every Codex-backed call failed
  in a plain (non-Git) research folder before this.
- Give `physics units`/`physics compute` actionable errors instead of leaking
  internals — no more `tesla_to_meter` function names or raw Python
  `TypeError`s; missing/misspelled parameters and unsupported conversions are
  named with usage hints.
- Trim floating-point noise from `physics` output (`0.10000000005443757 tesla`
  → `0.1 tesla`) via a shared `g`-format helper.
- Render reduced χ² with significant figures in fit/analyze/consistency output
  instead of collapsing small values to `0.0000`.
- Make `figure render|compose|export` degrade gracefully with an install hint
  when the optional `[figure]` extra is absent, instead of dumping a raw
  `ModuleNotFoundError` traceback.
- Produce publication-style axis labels in `sim plot` (`H`, `V_mix`, `ρ_xy`)
  instead of lowercased raw CSV headers (`h`, `v_mix`).
- Resolve the authoring package lazily so `present templates` — a deterministic
  listing — works without the heavy `[authoring]` extra; previously even listing
  templates crashed importing bibtexparser/pylatex/python-pptx.
- Restore every REPL CLI slash command (`/physics`, `/mat`, `/doctor`, `/fit`,
  …) under typer ≥ 0.26, which vendors click as `typer._click` and no longer
  ships a standalone `click` that `_run_cli_slash` imported.
- Differentiate `sim validate` failures: a non-JSON file (e.g. a CSV) now points
  to `sim plot`, a malformed JSON string and a wrong-schema document each get
  their own message, instead of one opaque `JSON parse failed`.
- Pin KeyBERT's embedding model to CPU for `lit keywords`/`lit search`. On Apple
  Silicon the default device auto-selection put SPECTER2 on MPS, where it OOM'd
  mid-inference, spewed raw Metal command-buffer errors to stderr, and silently
  contributed nothing (KeyBERT column all zeros). It now runs cleanly and adds
  real semantic scores.
- Stop duplicating the "Did you mean ...?" hint on a mistyped command. Under
  typer ≥ 0.26 a typo printed it twice (`Did you mean 'set'? Did you mean
  'set'?`); a single suggestion now shows for both root- and subcommand typos.

### Changed

- Bumped the package version to `0.0.4`.

### Tests

- Added regression coverage for the Codex `--skip-git-repo-check` flag,
  publication-style `sim plot` axis labels, and real (un-mocked) REPL CLI
  slash-command dispatch.

## v0.0.3

### Changed

- Reworked `sot-device-scene` as a Nature-style browser/SVG figure instead of a
  rough schematic demo: 183 mm editable vector canvas, three-panel stack to
  patterned-device to qualitative-readout story, lowercase panel labels, compact
  5-7 pt-equivalent text, black annotation labels/keylines, no raster images,
  no decorative effects, and tighter publication-oriented whitespace.
- Added `backend="html"` support for `sot-device-scene`, returning a
  self-contained HTML preview document with the editable SVG inline.
- Updated figure documentation to describe the browser-first SVG workflow.
- Bumped the package version to `0.0.3`.

### Tests

- Added regression checks for the Nature-style SVG canvas and inline HTML
  backend.

## v0.0.2

### Added

- Added shared SVG primitive helpers for schematic style tokens, safe SVG text
  and attribute escaping, color validation, compact number formatting, and
  reusable tag generation.
- Added reusable schematic frame and anchor helpers so publication figures can
  be authored layout-first, with named regions and compass anchors instead of
  ad-hoc coordinate-only drawings.
- Added explicit scene-frame composition for schematic panels via
  `panel.extra["primitives"]`, allowing deterministic placement of catalog
  primitives inside publication-oriented SVG layouts.
- Added publication-oriented multilayer stack rendering with bounded thickness
  scaling, role-aware material colors, callout labels for thin layers, and a
  growth-direction cue.
- Added Hall bar voltage and out-of-plane field annotations so transport
  schematics carry measurement semantics by default.
- Added `sot-device-scene`, a layout-first composite primitive for SOT stack to
  Hall-bar device schematics with process, transport, voltage, field, and axes
  annotations in one editable SVG.

### Changed

- Bumped the package version to `0.0.2`.
- Documented the schematic primitive workflow in the README and figure manual.

### Tests

- Added regression coverage for explicit schematic scene frames.
- Added XML/quality checks for bounded multilayer layouts, role-aware labels,
  Hall bar measurement annotations, and the composite SOT device scene.
