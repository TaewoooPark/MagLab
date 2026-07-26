# Changelog

## v0.0.5

A stability, integrity and atomicity hardening pass over the whole codebase.

### Added

- `maglab.core.atomic` — `atomic_write_text`/`atomic_write_bytes` helpers that
  write via a temporary sibling file and `os.replace`, so an interrupted write
  (Ctrl-C, crash, full disk) can never leave a half-written state file behind.
- `maglab.ui.json_output` and `maglab.ui.status` — a single place that keeps
  machine-readable payloads on stdout and progress rendering on stderr.

### Tests

- Added a documentation check that fails when a runnable README example names a
  command or install extra that does not exist — the class of defect that hid
  both the missing `prov lineage` and the unimplemented `maglab harness` surface.
- The suite no longer depends on the developer's terminal: `FORCE_COLOR` and
  `CLICOLOR_FORCE` are scrubbed before the CLI modules build their consoles.
  Rich latches those in `Console.__init__`, so a shell exporting them turned
  `assert "0.0.4" in result.output` into a failure against
  `maglab \x1b[1;36m0.0\x1b[0m.\x1b[1;36m4` while CI stayed green — false
  failures that also hide real ones.

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
- Hold channel-qualified SCPI to the hardware safety envelope. SCPI puts a
  numeric suffix on a mnemonic to pick a channel, so a dual-channel supply is
  driven with `:SOUR2:VOLT 250` and `OUTP2 ON`. Prefix matching was literal, so
  none of those were recognised as setters or as output activation — every
  voltage/current/field/temperature limit, the initialise-before-output rule and
  the "no parameter change while output is live" rule were skipped for the whole
  instrument. `:SOUR2:VOLT 250` was reported clean against a 210 V limit. Value
  extraction also read the first number anywhere in the command, so the channel
  digit of `:SOUR2:VOLT 250` was checked as `2` volts; only the parameter list is
  searched now.
- Stop reporting range and compliance nodes as output-limit violations.
  `:SOUR:CURR:COMP 5.0` raises the compliance ceiling — it does not push 5 A
  through the sample — but it matched the `:SOUR:CURR` setter prefix. The
  exclusion existed only for the bare `CURR:COMP` form, not the fully-qualified
  one that real instrument scripts emit.
- Stop both READMEs from documenting a `maglab harness` surface that does not
  exist. The "PI harness mode" section presented `harness doctor|compile|run|
  worker|pi-tool`, a `.[harness]` install extra, `maglab run --harness-workflow`,
  `maglab lit search --harness-plan`, and a copy-pasteable "minimal first
  workflow" — none of which are implemented, in the CLI or anywhere in the git
  history, and the workflow names it used (`literature-review`, `deep-research`)
  are not the ones `harness.manifest.json` declares. The status table also listed
  it as "Implemented". A new user's first copied command failed with
  `No such command`. The design intent is kept, clearly marked as not
  implemented, and the runnable examples and install line are removed.
- Stop silently truncating streamed Codex responses. The live-trace collector
  ended as soon as the child had exited and both queues *looked* empty — but an
  empty queue only means the reader threads have not enqueued the next line yet,
  not that the pipes are drained. With the main thread busy parsing trace
  events, a 5 000-line stream lost up to 87% of its output and a 20 000-line one
  about 29%, cutting off the end of the model's answer with no error. The reader
  threads are now joined (they end at EOF) and the queues drained afterwards, so
  every line is captured and still reaches the trace sink. A timed-out child is
  also reaped instead of being left as a zombie.
- Render progress spinners on stderr instead of stdout. `Console.status` hides
  the cursor, paints a frame, then moves back and erases the line; on stdout
  those control sequences land in the pipe ahead of the payload, so
  `maglab explain --json | jq` and `maglab sim pipeline --json` failed at column
  one whenever Rich rendered live output. stdout now carries only results, as
  curl, pip and docker do.
- Emit `--json` output without Rich formatting. `Console.print_json` always
  highlights, so with `FORCE_COLOR` set — the default on many CI runners —
  `maglab config show > config.json` produced ANSI escape sequences that
  `json.load` rejects. JSON now goes to stdout untouched, which also removes the
  risk of Rich word-wrapping splitting a long string value across lines.
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
- Close the PROV store after `prov lineage`. The command built a
  `ProvenanceStore` inline and never closed it, holding the SQLite connection —
  and the database file — open past the query.
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
