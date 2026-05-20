# Code Review R2-05: authoring / gateway / commands / cli / mcp_server

**Scope:** `maglab/authoring/`, `maglab/gateway/`, `maglab/commands/p6_authoring.py`,
`maglab/cli.py`, `maglab/mcp_server.py`

**Reviewer methodology:** Full adversarial re-read of all files in scope; targeted
runtime probes for control-flow and security correctness; independent of R1 — prior
findings used only for confirmation, not direction.

---

## Verdict

**ISSUES FOUND**

---

## Findings

### F1 — HIGH: Slack HMAC verification silently bypassed when `signing_secret` is set but request carries no `signature` field

**File:line:** `maglab/gateway/adapters/slack.py:141`

**Defect:** `verify_request` was patched in R1 to always log a warning when
`signing_secret` is empty (F3 fix). The resulting code is:

```python
if not self._signing_secret:
    log.warning("[gateway] Slack HMAC signature verification SKIPPED …")
elif signature and not self._verify_slack_signature(body, timestamp, signature):
    log.warning("[slack] Signature verification failed")
    return False
```

The `elif` branch has the form `signature and (not verify(...))`. When
`self._signing_secret` **is** configured but the incoming request carries no
`signature` header (i.e., `raw.get("signature", "")` returns an empty string),
`signature` is falsy and the entire `elif` condition evaluates to **False**. No
return-False executes, so the request silently passes signature verification and
proceeds to the allowlist check.

**Impact:** An attacker who knows any allowlisted Slack user ID can forge a raw
request dict with no `signature` field and bypass HMAC verification entirely,
regardless of the configured `signing_secret`. The signing secret, which is
supposed to be the cryptographic proof of Slack origin, is useless unless the
attacker happens to supply a *wrong* signature. The F3 fix (warning on no secret)
does not apply here — no warning is emitted when the secret is set and the
signature is absent, so the bypass is also invisible in operator logs.

**Fix:** When `signing_secret` is configured, a missing or empty signature must
also be rejected:

```python
if not self._signing_secret:
    log.warning("[gateway] Slack HMAC signature verification SKIPPED …")
elif not signature or not self._verify_slack_signature(body, timestamp, signature):
    log.warning("[slack] Missing or invalid signature")
    return False
```

The `not signature` guard ensures that an absent signature is treated as a
verification failure, not a silent pass.

---

### F2 — LOW: `gateway setup` chmod hint prints literal `{cfg}` instead of the actual path

**File:line:** `maglab/commands/p6_authoring.py:608–610`

**Defect:** In the `gateway_setup` command, when the config file exists with
non-0600 permissions, the code prints a remediation hint:

```python
console.print(
    f"[yellow]Warning:[/] Config file {cfg} has permissions {mode} "
    "(expected 600).  Fix with:  chmod 600 {cfg}"   # ← no f-prefix
)
```

Python concatenates adjacent string literals at compile time. The second string
`"(expected 600).  Fix with:  chmod 600 {cfg}"` has no `f` prefix, so `{cfg}`
is never interpolated — the user sees the literal text `chmod 600 {cfg}` rather
than the actual path (e.g., `chmod 600 /Users/alice/.maglab/gateway.yaml`).

The cosmetic impact is a misleading help message in a security-critical context
(operators fixing unsafe credential permissions). A copy-paste of the printed
command would run `chmod 600 {cfg}` on the shell, which would fail or apply
permissions to a file named literally `{cfg}`.

**Fix:**

```python
console.print(
    f"[yellow]Warning:[/] Config file {cfg} has permissions {mode} "
    f"(expected 600).  Fix with:  chmod 600 {cfg}"   # ← add f-prefix
)
```

---

## Confirmed fixes from R1 (no longer defects)

| R1 ID | Description | Status |
|-------|-------------|--------|
| F1 | `comms abstract` key mismatch (`results` vs `results_context`) | **FIXED** — CLI now passes `"results_context"`. |
| F2 | `get_or_create_session` double-hashes user ID | **FIXED** — parameter is now treated as pre-hashed; no internal `_hash_user_id()` call. |
| F3 | Slack `verify_request` silently skips HMAC when `signing_secret` is empty | **FIXED** — per-request `log.warning(...)` emitted on every bypass. |
| F4 | `DataVault._format_value` omits SI units for vector DataPoints | **FIXED** — list branch now returns `r"({values})\,\si{{{dp.units}}}"`. |
| F5 | `LoopCResult` did not expose temp-dir path to caller | **FIXED** — `output_dir` field added to `LoopCResult`; set to `effective_dir`. |
| F6 | `BibManager.add_verified` could produce duplicate `author` fields | **FIXED** — `"author"` now has explicit priority over `"authors"` via `if/elif`. |
| F7 | PID-file TOCTOU race on concurrent `gateway start` | **FIXED** — atomic `open(pid_file, "x")` claim before subprocess spawn; `FileExistsError` handled cleanly. |

## Non-findings investigated this round

- **Loop C human-gate rejection / infinite loop:** When `human_gate_fn` returns
  `False`, the code calls `engine.stop(StopReason.EXTERNAL)` then `break`,
  correctly exiting the inner `while` loop. The outer `for` checks
  `engine.is_active()` on the next iteration and exits. No infinite-loop risk.

- **Loop C section-save ordering:** `section_drafts[section_name] = draft_result`
  is executed at line 305 *before* `engine.step(...)` at line 306. If `engine.step`
  returns a stop reason, the `break` exits with the section already saved. Correct.

- **`_write_output_files` with dummy `DraftResult`:** When
  `section_drafts` is fully populated, the `dummy_result` passed to
  `_assemble_full_document` is never used by the `elif name ==
  current_draft.section.value` branch (because all sections match the `if name in
  completed_sections` branch first). No spurious double-rendering.

- **SessionDB thread safety in asyncio:** `sqlite3.connect(check_same_thread=False)`
  is shared across coroutines but asyncio is single-threaded; the DB is never
  accessed from `asyncio.to_thread` worker threads. Safe.

- **Double `remove_pid()` in `_run_gateway_foreground`:** The inner `finally`
  (inside `_main`) and outer `finally` both call `remove_pid()`. The second call
  is a no-op because `remove_pid()` uses `contextlib.suppress(OSError)` and
  `unlink(missing_ok=True)`. Harmless.

- **PID file double-write (parent + child):** In background mode, both the parent
  process (`pid_file.write_text(str(proc.pid))`) and the child process
  (`write_pid()` → `os.getpid()`) write the same numeric value because
  `proc.pid == os.getpid()` in the child. No corruption regardless of ordering.

- **`DataVault.inject_into_draft` recursive substitution:** `re.sub` is a
  single-pass operation; substituted text is never re-scanned. No recursive
  placeholder expansion risk.

- **Research integrity gates:** `AuthoringBlockedError` is raised before any draft
  proceeds when citation or vault gates fail. `HUMAN_REVIEW_REQUIRED` markers are
  appended to every output path. `LoopCResult.human_review_required` is hard-coded
  `True`. No auto-send path exists.

- **`ConferenceAbstractAgent` char-limit check timing:** The length check fires
  after `DataVault.inject_into_draft`, correctly measuring the final injected text.
