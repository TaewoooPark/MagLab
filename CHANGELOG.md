# Changelog

## v0.0.5

A stability, integrity and atomicity hardening pass over the whole codebase.

### Added

- `maglab.core.atomic` — `atomic_write_text`/`atomic_write_bytes` helpers that
  write via a temporary sibling file and `os.replace`, so an interrupted write
  (Ctrl-C, crash, full disk) can never leave a half-written state file behind.

### Fixed

- Stop a broken `config.toml` from locking the user out of every command.
  `load_config` runs on each CLI invocation, so a truncated file or a
  hand-edited typo (`mode = "bogus"`) dumped a raw `tomllib`/pydantic traceback
  from *every* subcommand — including `config restore`/`config reset`, the two
  that repair it. Invalid configs now raise `ConfigError`, which the entry point
  renders as a one-line message naming the file, the offending field, and the
  command that fixes it.
- Write `config.toml` atomically. `save_config` truncated the live config before
  writing, so an interruption mid-save destroyed it; it now replaces the file in
  one step and only serializes through the fallback writer on a *serializer*
  failure, instead of retrying a write against a path that just proved
  unwritable.
- Stop the persona opt-out registry (safeguard ⑥, documented as non-negotiable)
  from failing open. `_load_optout` swallowed every exception and returned an
  empty set, so an unreadable or half-written `optout.json` silently turned
  "these authors opted out" into "nobody opted out" — with only a log line to
  show for it. A *missing* file still means no opt-outs, but a file that exists
  and cannot be parsed now blocks every persona until it is repaired
  (`reload_optout_registry()` clears the block once fixed). The registry is also
  written atomically, and a failed save now raises instead of letting
  `register_optout()` report success for an opt-out that would vanish on
  restart.
- Write the Ralph loop state file atomically. `RalphState.from_markdown`
  deliberately falls back to defaults for fields it cannot parse, so a truncated
  `ralph.local.md` did not fail loudly — it silently resurrected a run stopped at
  iteration 17 as `iteration=0, active=True, stop_reason=None`, handing a halted
  loop a fresh iteration budget. Interrupting a long autonomous loop is exactly
  when that half-written file appeared.
- Write research-pool records and long-term memories atomically.
  `query()`/`semantic_query()` skip records they cannot parse, so a half-written
  record silently vanished from every later search instead of surfacing.
- Stop `maglab gateway stop` from being able to SIGTERM an unrelated process.
  A daemon killed without cleanup (SIGKILL, crash, power loss) leaves its PID
  file behind and the OS eventually reuses that PID; `stop_daemon` signalled it
  blind. The target's command line is now checked first and a confirmed mismatch
  is refused and the stale file cleared. `read_pid` also rejects `0` and negative
  values, which `os.kill` would have broadcast to a whole process group, and the
  PID file is written atomically so a truncated `"12345"` can never be read back
  as a valid-but-wrong PID `12`.
- Bound `git status` in the workspace listing with a timeout, so a huge
  repository or a stalled network mount degrades to "no entries" instead of
  hanging the CLI at startup with no way out.
- Make `CheckpointStore.save` a single atomic upsert. The previous
  SELECT-then-INSERT/UPDATE pair raced: two `maglab` runs resuming the same task
  both saw "no row", both inserted, and the loser died on
  `UNIQUE(task_id, idempotency_key)` — crashing the loop that idempotency keys
  exist to make resumable. `ON CONFLICT DO UPDATE` keeps the original
  `checkpoint_id` and `ts_created`, exactly as the old UPDATE branch did.

### Changed

- Stop rebuilding the whole PROV document on every provenance record.
  `ProvenanceStore._flush_to_db` re-serialised the entire growing document for a
  `prov_graph` snapshot that nothing ever read back, making a session of N
  records cost O(N²): ~0.5 ms/record at 25 records but ~2.8 ms/record at 200.
  The snapshot is export-only, so it is now written on export and on close;
  per-record cost is flat (~0.04 ms), 62× faster at 200 records.

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
- Implement the `prov lineage <id> --db <store>` command. The README listed it
  under the provenance surface and as "Implemented", but only `summary`/`status`
  existed, so `maglab prov lineage` errored with "No such command". It now
  surfaces the existing `ProvenanceStore.get_entity_lineage` records (entity,
  generation, derivation, attribution) as a table or `--json`.

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
