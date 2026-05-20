# Code Review Round 3 — authoring / gateway / commands / cli / mcp_server

**Date:** 2026-05-19  
**Reviewer:** Claude (independent R3 re-audit)  
**Files reviewed:**
- `maglab/authoring/data_vault.py`
- `maglab/authoring/bib_manager.py`
- `maglab/authoring/citation_auditor.py`
- `maglab/authoring/section_drafter.py`
- `maglab/authoring/loop_c.py`
- `maglab/authoring/comms/base.py`
- `maglab/gateway/runner.py`
- `maglab/gateway/session_db.py`
- `maglab/gateway/adapters/base.py`
- `maglab/gateway/adapters/slack.py`
- `maglab/gateway/adapters/telegram.py`
- `maglab/gateway/adapters/discord.py`
- `maglab/commands/p6_authoring.py`
- `maglab/cli.py`
- `maglab/mcp_server.py`

---

## Verdict

**ISSUES FOUND**

---

## Findings

### Finding 1 — HIGH (Research-Integrity): Critic-Revised Drafts Bypass DataVault Injection

**File:** `maglab/authoring/loop_c.py`, lines 241–252

**Defect:**  
When `critic_fn` returns substantive feedback, the loop calls `llm_fn` a second time to produce a revised draft. The revised text is written directly to `draft_result.tex` without re-running `DataVault.inject_into_draft`:

```python
revised_tex = llm_fn(
    "Revise the section per critic feedback.", revision_prompt
)
draft_result.tex = HUMAN_REVIEW_MARKER + revised_tex   # vault injection SKIPPED
```

The revision LLM call uses the minimal system prompt `"Revise the section per critic feedback."`, which does **not** include the invariant rule prohibiting bare numbers and requiring `{{dp:KEY}}` placeholders. Two consequences:

1. **Placeholder leakage:** If the LLM reproduces `{{dp:KEY}}` syntax in the revision, the gate on line 256 (`gate.run`) passes (because `validate_draft` only checks key *existence*, not injection), and the final output file contains raw `{{dp:KEY}}` strings instead of resolved values with provenance comments.

2. **Bare-number fabrication:** The LLM may substitute actual numbers (e.g., `"0.73 A/m"`) for placeholders because the `{{dp:KEY}}` constraint is absent from the revision system prompt. HonestyGate in the reporting pipeline can catch this, but the authoring loop itself has no numerical-value scanner, so the violation persists into the output file.

**Fix:**  
After generating `revised_tex`, re-run vault injection:

```python
revised_tex_with_header = HUMAN_REVIEW_MARKER + revised_tex
try:
    draft_result.tex = self._vault.inject_into_draft(
        revised_tex_with_header, section=section_name
    )
except AuthoringBlockedError:
    ...  # handle normally
```

Also pass the full invariant system prompt (from `_build_system_prompt`) as the revision system prompt instead of the bare one-liner.

---

### Finding 2 — MEDIUM (Security): Channel Allowlist Bypassed When Channel Field Is Empty

**Files:**  
- `maglab/gateway/adapters/slack.py`, line 152  
- `maglab/gateway/adapters/telegram.py`, line 86  
- `maglab/gateway/adapters/discord.py`, line 92

**Defect:**  
All three adapters guard the channel allowlist check with a truthiness test on the channel identifier:

```python
if channel and not self._channel_allowed(channel):
    ...
    return False
```

When the channel field is absent from the raw event dict (e.g., a direct-message delivery path, a malformed payload, or a deliberately omitted field), the channel variable is `""` (falsy) and the entire check is skipped. A user who is in `allowed_users` (or when `allowed_users=None`) can therefore send messages that bypass the `allowed_channels` restriction entirely.

If the operator relies on `allowed_channels` as the primary security boundary (e.g., to restrict the bot to a specific research lab channel), this is a concrete bypass.

**Fix:**  
When `allowed_channels` is configured (non-None) and channel is empty, reject the request:

```python
if self._allowed_channels is not None and (not channel or not self._channel_allowed(channel)):
    log.info("[slack] Channel %r not in allowlist (or missing)", channel)
    return False
```

---

### Finding 3 — LOW (Correctness/Docstring Contradiction): `remaining_placeholders` in `DraftResult` Is Always Empty

**File:** `maglab/authoring/section_drafter.py`, lines 77–79, 269–274, 286–290

**Defect:**  
The docstring for `DraftResult.remaining_placeholders` states:

> Placeholder keys that were NOT found in the vault (should be empty after successful `DataVault.inject_into_draft`).

However, the code only sets `remaining` to a non-empty list inside the `except AuthoringBlockedError` block (line 272), and then immediately re-raises the exception (line 274). The `DraftResult` constructor on line 286 is therefore unreachable when `remaining` is non-empty. In the success path, `remaining` is always `[]`. The field's diagnostic purpose is never fulfilled.

Additionally, line 272 calls `self._vault.find_placeholders()` which returns **all** `{{dp:KEY}}` keys (found + missing), rather than `self._vault.validate_draft()` which returns only **missing** keys — so even if the return were reachable, it would include false positives.

**Fix:**  
Replace `find_placeholders` with `validate_draft` on line 272 (for correctness if the code path is ever made reachable), and update the docstring to reflect that `remaining_placeholders` is always `[]` in the current implementation.

---

### Finding 4 — LOW (Security / Defence-in-Depth): Slack Replay-Attack Check Silently Skipped on Non-Numeric Timestamp

**File:** `maglab/gateway/adapters/slack.py`, lines 122–129

**Defect:**  
The replay-attack protection converts the `timestamp` header to float and, on `ValueError`/`TypeError`, silently skips the check:

```python
except (ValueError, TypeError):
    pass  # No timestamp provided — skip replay check in mock mode
```

An attacker who knows the `signing_secret` and can intercept a valid Slack request body+signature can replay it indefinitely by substituting `timestamp=""` (causing the float conversion to fail and the 5-minute window check to be skipped). Signature verification still runs, so an attacker **without** the signing secret cannot exploit this. However, with the signing secret exposed (e.g., leaked config), replay-attack protection is fully defeated by this bypass.

The comment `# skip replay check in mock mode` indicates this was intentional for testing, but it weakens defence-in-depth in production where the secret may be at risk.

**Fix:**  
Only skip the replay check when the adapter is operating in explicit mock/test mode (e.g., when `signing_secret` is empty). When `signing_secret` is configured and the timestamp cannot be parsed as a float, reject the request:

```python
except (ValueError, TypeError):
    if self._signing_secret:
        log.warning("[slack] Cannot parse timestamp — rejecting request")
        return False
    # else: no secret configured, already warned globally
```

---

## Items Verified as Not Defective

| Concern | Verdict |
|---|---|
| `DataVault.inject_into_draft` blocking gate — missing key raises `AuthoringBlockedError` | Correct |
| `BibManager.has_key` vs `_verified_keys` consistency — `add_unverified` always raises | Correct |
| `audit_existence` + `audit_semantics` chaining in `PreSectionFinalizeHook.run()` | Correct |
| `HUMAN REVIEW REQUIRED` marker appears in every `DraftResult.tex` | Correct |
| PID file race condition (background mode uses atomic `open("x")`) | Correct — no race |
| `check_credential_permissions` — correctly checks read/write group/other bits | Correct |
| SQLite session_db — all queries use parameterised placeholders | Correct, no SQL injection |
| Gateway foreground `remove_pid()` called in both finally and KeyboardInterrupt paths | Correct |
| `_assemble_full_document` double-inclusion when `dummy_result` is in `completed_sections` | Not an issue — `elif` guards correctly |
| `hmac.new` call — `hmac.new` exists and behaves correctly in Python 3.8+ | Correct |
| MCP tool `readOnlyHint=True` annotations — deterministic tools only | Correct |
| `FILL_MARKER` enforcement in `BaseCommsAgent.draft()` — raises on missing markers | Correct |
| No auto-send path in comms or gateway — all outputs written to files | Correct |
