# Code Review R1-05: authoring / gateway / commands / cli / mcp_server

**Scope:** `maglab/authoring/`, `maglab/gateway/`, `maglab/commands/p6_authoring.py`,
`maglab/cli.py`, `maglab/mcp_server.py`

**Reviewer methodology:** Full adversarial read of every file in scope; targeted runtime
probes for control-flow correctness; no code modifications.

---

## Verdict

**ISSUES FOUND**

---

## Findings

### F1 — HIGH: `comms abstract` CLI silently discards user input (key mismatch)

**File:line:** `maglab/commands/p6_authoring.py:433–441` vs `maglab/authoring/comms/conference_abstract.py:43`

**Defect:** The `comms abstract` CLI command (`comms_abstract()`) builds the input dict
with key `"results"`:

```python
result = agent.draft({
    "conference": conference,
    "char_limit": char_limit,
    "results": results or "[FILL: describe key results]",  # <-- key: "results"
})
```

`ConferenceAbstractAgent._generate_draft()` reads from `"results_context"`:

```python
context = inputs.get("results_context", "[FILL: results summary]")  # <-- different key
```

Because the keys do not match, `context` always falls through to the fallback
`"[FILL: results summary]"`. Every abstract draft is identical regardless of what the
user passes with `--results`. The user's argument is completely and silently discarded.

**Fix:** Align the keys. Either change the CLI to send `"results_context"` or change the
agent to read `"results"`. The agent key should be treated as the authoritative API
since it is also used directly (the CLI is an adapter). Change `p6_authoring.py:440`:
```python
"results_context": results or "[FILL: describe key results]",
```

---

### F2 — MEDIUM: `SessionDB.get_or_create_session` double-hashes the already-hashed user ID

**File:line:** `maglab/gateway/runner.py:243` + `maglab/gateway/session_db.py:183`

**Defect:** `adapter.parse_message()` already stores a SHA-256 hex digest in
`UnifiedMessage.user_id_hash`. The runner then passes this hash to `SessionDB`:

```python
# runner.py:243
session = self._db.get_or_create_session(msg.platform, msg.user_id_hash, msg.channel)
```

`get_or_create_session` is documented to accept the *raw* user identifier and hashes it
internally:

```python
# session_db.py:183
uid_hash = _hash_user_id(user_id)  # hashes the already-hashed value
```

The stored `uid_hash` is therefore `SHA-256(SHA-256(original_user_id))`, not
`SHA-256(original_user_id)` as specified in the §8 security contract. While sessions
remain internally consistent (both create and lookup paths double-hash), the stored value
violates the documented API contract. Any future code path that calls
`get_or_create_session` with a raw user ID (e.g., an admin tool, test fixture, or
migration script) will produce an inconsistent hash, breaking session lookup silently.

**Fix:** Remove the internal hash from `get_or_create_session` (rename the parameter to
`user_id_hash` and skip the `_hash_user_id()` call), and update the docstring. The
adapter is already responsible for hashing.

---

### F3 — MEDIUM: Slack `verify_request` silently disables HMAC verification when `signing_secret` is empty

**File:line:** `maglab/gateway/adapters/slack.py:90–92`

**Defect:** `_verify_slack_signature()` returns `True` unconditionally when
`self._signing_secret` is empty:

```python
if not self._signing_secret:
    # No secret configured — skip (useful in unit tests with mock adapter)
    return True
```

This is a silent no-op. If an operator deploys the gateway without setting
`signing_secret` (e.g., misconfiguration, or leaving the YAML placeholder empty), all
Slack requests pass signature verification regardless of origin. The allowlist provides
a second layer, but the allowlist alone is bypassable if an attacker can forge a Slack
`user_id` header matching an allowlisted user (which is trivial without a signing
secret).

No warning is logged when this path is taken, making the misconfiguration invisible in
operator logs.

**Fix:** Add a `log.warning(...)` inside the `if not self._signing_secret` block so that
every request that bypasses signature verification is logged at WARNING level. Consider
also raising a `RuntimeError` at `SlackAdapter.__init__` time when `signing_secret` is
empty and the adapter is not explicitly constructed in test mode.

---

### F4 — MEDIUM: `DataVault._format_value` silently omits units for list (vector) DataPoints

**File:line:** `maglab/authoring/data_vault.py:176–178`

**Defect:** The scalar branch correctly appends SI units to the injected LaTeX:

```python
return rf"{val:.6g}\,\si{{{dp.units}}}"
```

The list branch does not:

```python
if isinstance(dp.value, list):
    return ", ".join(f"{v:.6g}" for v in dp.value)  # no units
```

A vector DataPoint (e.g., `[B_x, B_y, B_z]` in Tesla) is injected as bare numbers
`1.20, 3.40, 5.60` with no unit annotation. The researcher reviewing the PDF may not
notice the missing units, potentially resulting in a published paper with dimensionless
vector values. This violates the research-integrity goal that every injected value be
traceable and unambiguous.

**Fix:** Append the `\si{}` unit to the list output:

```python
values = ", ".join(f"{v:.6g}" for v in dp.value)
return rf"{values}\,\si{{{dp.units}}}"
```

---

### F5 — LOW: `run_loop_c` tempdir path not communicated to caller

**File:line:** `maglab/authoring/loop_c.py:196–202, 319–323`

**Defect:** When `output_dir=None`, a `tempfile.mkdtemp()` directory is created and
used for all written output files (assembled `main.tex`, `HUMAN_REVIEW_REQUIRED.txt`,
per-section `.tex` files). The path is stored in the local variable `_tmp_dir` but is
never included in the returned `LoopCResult`. The comment explicitly says *"user can
find artifacts"* but there is no mechanism to communicate the path to the caller.

The CLI always passes an explicit `output_dir`, so CLI users are not affected. However,
any direct library caller using `run_loop_c(..., output_dir=None)` loses access to the
file artifacts. Only the in-memory `DraftResult.tex` strings (in `section_drafts`) are
recoverable.

**Fix:** Add an `output_dir: Path | None` field to `LoopCResult` and set it to
`effective_dir` before returning, so callers can always find the written artifacts.

---

### F6 — LOW: `BibManager.add_verified` can create duplicate `author` fields

**File:line:** `maglab/authoring/bib_manager.py:128–148`

**Defect:** `_field_map` maps both `"author"` and `"authors"` to the BibTeX field
`"author"`. If a metadata dict contains both keys (common when APIs return both a
pre-formatted author string and an author list), the loop appends two `Field("author",
...)` objects to the entry's fields list. Some BibTeX parsers silently take the last
value; others raise a warning or produce garbled bibliography entries.

**Fix:** Prioritise `"author"` over `"authors"` — check `metadata.get("author")` first,
and only fall back to joining `metadata.get("authors")` when `"author"` is absent. An
`elif` structure or a de-duplication step on the fields list before constructing the
`Entry` would fix this.

---

### F7 — LOW: PID-file daemon manager has no atomic write (TOCTOU race)

**File:line:** `maglab/commands/p6_authoring.py:659–679` / `maglab/gateway/runner.py:342–344`

**Defect:** `gateway start` checks `is_running()` (reads PID file + `os.kill`), then
unconditionally launches a subprocess and writes its PID. If two `gateway start`
commands execute concurrently, both can pass the `is_running()` check before either
writes a PID file, resulting in two daemon processes. Only the second process's PID is
recorded; the first becomes an unmanaged orphan that `gateway stop` cannot reach.

This is a low-severity operational issue (the gateway is unlikely to be started
concurrently in practice), but the absence of a lock makes it non-robust.

**Fix:** Use an atomic file-creation pattern (e.g., `open(pid_file, 'x')` which raises
`FileExistsError` if the file already exists) for the PID file write, combined with a
stale-PID cleanup on startup.

---

## Non-findings (investigated, dismissed)

- **Citation regex (`_CITE_RE`):** The raw string `r"\\cite[pt]?\{([^}]+)\}"` correctly
  uses two backslashes to produce the regex pattern `\\cite` which matches a single
  literal backslash followed by `cite`. Verified against raw file bytes; the regex
  compiles and matches LaTeX `\cite{...}` and `\citep{...}` correctly on Python 3.14.

- **`hmac.new()` in `SlackAdapter`:** `hmac.new()` is a valid (if deprecated) alias for
  `hmac.HMAC()`. The HMAC-SHA256 computation, constant-time comparison via
  `hmac.compare_digest`, and replay-attack window (±300 s) are all correct.

- **Loop C control flow / infinite loop:** The inner `while engine.is_active() and not
  approved` loop correctly exits on: `AuthoringBlockedError` (via `engine.step`
  circuit-break check), gate failure (human rejection + `engine.stop`), and section
  approval. The outer `for section_type in DRAFTING_ORDER` loop is guarded by
  `if not engine.is_active(): break`. No infinite-loop risk found.

- **`check_credential_permissions` symlink/setuid handling:** `path.stat()` follows
  symlinks by default, so the permission check correctly reflects the target file. Setuid
  bits on a data file are irrelevant.

- **`DataVault._format_value` type safety:** `DataPoint.value` is typed `float |
  list[float]` and enforced by Pydantic at construction time, so `{v:.6g}` in the list
  branch is always safe.

- **Research integrity gates (no-bypass):** `audit_existence` and `audit_semantics` both
  raise `AuthoringBlockedError` before any drafting proceeds when gate conditions fail.
  `DataVault.inject_into_draft` raises on missing placeholders. `run_loop_c` re-raises
  all `AuthoringBlockedError` from the inner draft/gate steps. The `HUMAN_REVIEW_REQUIRED`
  marker is appended to every output regardless of code path. No auto-send pathway exists.
