# Code Review Round 5 — authoring/gateway domain
**Files reviewed:** `maglab/authoring/`, `maglab/gateway/`, `maglab/commands/`, `maglab/cli.py`, `maglab/mcp_server.py`
**Date:** 2026-05-19
**Reviewer:** Claude Sonnet 4.6 (automated, read-only)

---

## Verdict

**ISSUES FOUND**

---

## Prior Round Patches Verified

All R4 findings were confirmed patched before starting fresh analysis:
- **F1** (theme set config destruction): `cli.py:390–400` now correctly serialises the full `raw` dict in the `tomli_w` fallback. Confirmed clean.
- **F2** (matplotlib figure leak): Both `figure_render` and `figure_export` now use `try/finally` with `contextlib.suppress`. Confirmed clean.
- **F3** (dead `remaining_placeholders`): `section_drafter.py` no longer populates the local `remaining` variable in the except block; the except clause now simply re-raises. Confirmed clean.
- **F4** (docstring inaccuracy): `audit_existence` docstring updated to "Always returned when no exception is raised". Confirmed clean.
- **F5** (abstract word count inflation): Word count now measured on `raw_tex` (pre-disclosure). Confirmed clean.

---

## Findings

### F1 — MEDIUM | `maglab/mcp_server.py:81,497–549,554–622,682–733,750–784,799–831` | `readOnlyHint=True` on tools that write files

**Defect:**
All MCP tools are registered with `_READ_ONLY_ANNOTATIONS = ToolAnnotations(readOnlyHint=True)`, but several tools actively create or modify files on disk:

| Tool | Write side-effect |
|---|---|
| `figure_render` | Writes a figure file to `output_path` (caller-supplied path) |
| `figure_export` | Writes figures to multiple paths under `stem` |
| `instr_ingest_manual` | Builds and writes a RAG SQLite index to `~/.local/share/maglab/` |
| `instr_generate_skill` | Writes a SKILL.md package directory with multiple files |
| `instr_scaffold` | Optionally writes a PyVISA skeleton `.py` file to `output_path` |

The MCP specification states: `readOnlyHint: If true, the tool does not modify its environment.`  MCP clients that rely on this annotation for sandboxing or permission decisions (e.g., confirming write-capable tools before execution) will be misled. The five tools above all clearly modify the filesystem.

**Fix:** Remove `annotations=read_only` (or use `ToolAnnotations(readOnlyHint=False)`) for each of the five tools listed above. The truly read-only tools (`physics_compute`, `physics_check`, `convert_units`, `material_lookup`, `material_search`, `provenance_query`, `sim_validate`, `sim_run`, `sim_parse`, `instr_search_manual`, `instr_safety_check`) correctly carry `readOnlyHint=True` and should keep it.

---

### F2 — LOW | `maglab/commands/p6_authoring.py:643–665`, `maglab/commands/p6_authoring.py:1145–1174` | Foreground gateway start mode has no atomic PID-file claim

**Defect:**
Background mode (`gateway start`, default) correctly uses an atomic `open('x')` exclusive-create to claim the PID file before spawning the daemon subprocess, preventing duplicate instances:
```python
fd = pid_file.open("x")   # atomic — fails with FileExistsError if already exists
```

Foreground mode (`gateway start --foreground`) does not apply the same guard. The execution path is:
1. `is_running()` check — passes if no PID file exists.
2. `_run_gateway_foreground()` called directly.
3. Inside `_run_gateway_foreground()`: `write_pid()` writes `os.getpid()`.

If two terminals simultaneously run `maglab gateway start --foreground`:
- Both pass the `is_running()` check (PID file absent at that instant).
- Both call `write_pid()` concurrently; the second overwrites the first.
- Both gateway event loops run simultaneously (both bind to the asyncio event loop in their respective processes).
- `gateway stop` sends SIGTERM to the PID recorded last, leaving the other instance running and unmanageable.

While foreground mode is primarily for debugging/development, having two gateway instances active simultaneously would silently handle messages inconsistently.

**Fix:** Before calling `_run_gateway_foreground()` (line 665), apply the same atomic claim used in background mode:
```python
pid_file = _pid_path()
try:
    fd = pid_file.open("x")
    fd.close()
except FileExistsError:
    console.print("[yellow]Gateway is already starting or running.[/]")
    return
```
Then have `_run_gateway_foreground()` write the actual PID into the already-claimed file (or use `write_pid()` to overwrite the empty placeholder, as background mode does).

---

### F3 — LOW | `maglab/authoring/loop_c.py:254–261` | Critic-revised section drafts are missing the per-section `_AI_DISCLOSURE` comment

**Defect:**
In `section_drafter.py`, `draft_section` always appends `_AI_DISCLOSURE` to every LLM output before vault injection:
```python
raw_tex_with_disclosure = HUMAN_REVIEW_MARKER + raw_tex + _AI_DISCLOSURE
```

In `loop_c.py`, when the domain critic provides substantive feedback and the draft is revised (step 2), the revision is assembled without `_AI_DISCLOSURE`:
```python
revised_tex_with_header = HUMAN_REVIEW_MARKER + revised_tex   # no _AI_DISCLOSURE
draft_result.tex = vault.inject_into_draft(revised_tex_with_header, ...)
```

`draft_result.tex` — which is the final value stored in `section_drafts[section_name]` and written to individual `{section_name}.tex` files by `_write_section_tex` — is therefore missing the per-section AI-usage disclosure comment block when a critic revision occurs.

The document-level `_AI_DISCLOSURE_FOOTER` added by `_assemble_full_document` is present in the compiled `main.tex`, so the assembled manuscript has the disclosure. However, individual section `.tex` files written to disk (e.g., `methods.tex`) lack the disclosure if they went through critic revision, creating an inconsistency with the protocol requirement (§16.5) that every AI-drafted output carry the disclosure.

This is not a research-integrity bypass (the disclosure is present in the final assembled document), but it is an internal inconsistency that could confuse a researcher inspecting individual section files.

**Fix:** In `loop_c.py` around line 255, append `_AI_DISCLOSURE` to the revised text:
```python
from maglab.authoring.section_drafter import _AI_DISCLOSURE   # already imported indirectly
revised_tex_with_header = HUMAN_REVIEW_MARKER + revised_tex + _AI_DISCLOSURE
```

---

## Summary Table

| # | Severity | File | Issue |
|---|----------|------|-------|
| F1 | MEDIUM | `mcp_server.py:81` | `readOnlyHint=True` on five tools that write files to disk — violates MCP spec contract |
| F2 | LOW | `p6_authoring.py:643,1145` | Foreground gateway mode has no atomic PID claim — two concurrent starts both succeed |
| F3 | LOW | `loop_c.py:255` | Critic-revised section drafts missing `_AI_DISCLOSURE` per-section footer — inconsistent with §16.5 protocol |

## Integrity Invariants — No Bypass Found

All research-integrity blocking gates were re-verified:
- **`AuthoringBlockedError` / citation existence gate** (`PreSectionFinalizeHook.run`): enforced unconditionally before any section is accepted. Non-bypassable.
- **Semantic citation gate** (`audit_semantics`): correctly passes vacuously for citation-free sections (by design); correctly blocks UNSUPPORTED/UNCERTAIN citations when semantic_classify_fn is provided.
- **`DataVault` injection guard**: `inject_into_draft` raises `AuthoringBlockedError` for any unregistered `{{dp:KEY}}` placeholder. The gate fires on both initial drafts and critic-revised drafts.
- **HUMAN REVIEW REQUIRED marker**: present in all outputs — initial drafts, revised drafts, and final `main.tex`. `HUMAN_REVIEW_REQUIRED.txt` always written to the output directory.
- **No auto-send path**: all comms outputs are written to files only; no API call or subprocess invocation sends content. Confirmed in `comms/base.py`, all six comms agents, and all CLI commands.
- **Gateway allowlist enforcement**: user_id and channel checks are applied before any command dispatch in all three adapters (Slack, Telegram, Discord). Slack HMAC signature verification is correctly implemented with `hmac.new` + `hmac.compare_digest`; missing `signing_secret` is logged as a warning on every request but does not suppress the allowlist check.
- **PID file security**: PID file is stored in the platform data directory (via `platformdirs`), not in a world-writable temp directory.
- **Credential permissions**: `check_credential_permissions` correctly checks `stat.S_IRGRP | stat.S_IWGRP | stat.S_IROTH | stat.S_IWOTH` and raises `PermissionError` for insecure modes on all non-Windows platforms.
