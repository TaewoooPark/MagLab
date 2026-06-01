# Changelog

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
