# Code Review R2-04 — literature / reviewer / lab domains

**Reviewer**: Claude Sonnet 4.6 (automated adversarial audit)
**Date**: 2026-05-19
**Scope**: `maglab/literature/`, `maglab/reviewer/`, `maglab/lab/`
**Method**: Read-only static analysis + targeted `python -c` probes via project `.venv`
**Basis**: Fresh audit of current (patched) code; R1 findings used for context only.

---

## Verdict

**ISSUES FOUND**

---

## R1 Patch Verification

All ten R1 findings were confirmed fixed in the current code:

| R1 finding | Status |
|---|---|
| F-01 `@_with_backoff` dead code | **Fixed** — inner handlers now call `raise` on retriable errors; backoff retries confirmed via probe. |
| F-02 DOI case-sensitive set lookup | **Fixed** — `verified_lower = {d.lower() for d in verified_dois}`; probe passes. |
| F-03 LanceDB write-only / no reload | **Fixed** — `_load_from_db()` added, called in `__init__`, BM25 rebuilt from DB rows. |
| F-04 Dummy score always returned | **Fixed** — `score = llm_score if llm_score is not None else self._make_dummy_score(...)`, `(str, ReviewScore)` tuple accepted; probe confirms 9.0 scores propagated. |
| F-05 Duplicate `WeightedKeyword` for same-normalized keyword | **Fixed** — `norm_to_scores` dict keyed by normalized form; probe produces single entry. |
| F-06 arXiv IDs never validated against `verified_dois` | **Partially fixed** — `check_fabricated_citations()` now accepts `verified_arxivs`; see N-01. |
| F-07 `conditions_array` freezes column set to first point's keys | **Fixed** — `keys = sorted(set().union(*(p.conditions.keys() for p in self.measured_points)))`; probe confirms (2,3) shape. |
| F-08 Stale cache rows accumulate unboundedly | **Fixed** — `DELETE FROM literature_cache WHERE key = ?` added to TTL-expiry branch. |
| F-09 `_name_similar` matches any empty author name | **Fixed** — `if not a_parts or not b_parts: return False` guard added. |
| F-10 `get_by_doi` fails on URL-prefixed DOIs | **Fixed** — SQL uses `LOWER(REPLACE(REPLACE(doi, 'https://doi.org/', ''), 'http://doi.org/', '')) = ?`. |

---

## Findings

### N-01 — MEDIUM | `reviewer/disclosure.py:532`, `reviewer/panel.py:206–209` | F-06 arXiv-validation fix is unreachable via `PersonaGuard.guard()`

**Defect**: The R1 F-06 fix added a `verified_arxivs` parameter to `check_fabricated_citations()` and implemented arXiv ID validation against a supplied set. However, the fix was not propagated to the `PersonaGuard` class — the primary enforcement path used by all pipeline calls.

Specifically:
- `PersonaGuard.__init__` (line 490–499) accepts only `verified_dois`; there is no `verified_arxivs` parameter.
- `PersonaGuard.guard()` (line 532) calls `check_fabricated_citations(text, self._verified_dois)` — `verified_arxivs` is never passed.
- `PersonaSpec` (the per-persona data struct in `panel.py`) likewise has no `verified_arxivs` field.
- `_review_single` constructs a `PersonaGuard` from `persona.verified_dois` only.

**Proven** by probe: a fabricated arXiv ID (`arXiv:9999.99999`) present in a review text is correctly detected when calling `check_fabricated_citations(..., verified_arxivs={'2305.12345'})` directly, but passes through `PersonaGuard.guard(raise_on_violation=False)` without any violation, even when a verified set is available.

**Impact**: Integrity violation — arXiv ID fabrication bypasses safeguard ③ in all production pipeline paths. The only way to enforce arXiv validation is to call `check_fabricated_citations()` outside of `PersonaGuard`, which no production code does.

**Fix**: Add `verified_arxivs: set[str] | None = None` to `PersonaGuard.__init__`, store as `self._verified_arxivs`, and pass it to `check_fabricated_citations` in `guard()`:
```python
# disclosure.py PersonaGuard.__init__:
self._verified_arxivs = verified_arxivs

# disclosure.py PersonaGuard.guard():
violations.extend(check_fabricated_citations(text, self._verified_dois, self._verified_arxivs))
```
Also add `verified_arxivs: set[str] = field(default_factory=set)` to `PersonaSpec` and propagate to `PersonaGuard` in `_review_single`.

---

### N-02 — LOW | `literature/connectors.py:118–143, 146–157` | SQLite connection leaked when any operation after `_get_cache_conn()` raises

**Defect**: `_cache_get` and `_cache_put` open a fresh `sqlite3.Connection` per call via `_get_cache_conn()`. Each function has a single broad `except Exception` block that logs and returns. When `_get_cache_conn()` succeeds (connection opened) but a subsequent operation raises, the connection is never closed:

`_cache_get` vulnerable paths:
- `conn.execute("SELECT ...")` raises `OperationalError` (DB locked)
- `conn.execute("DELETE ...")` raises in the TTL-expiry branch
- `json.loads(payload)` raises `JSONDecodeError` (malformed cached entry)

`_cache_put` vulnerable path:
- `conn.execute("INSERT OR REPLACE ...")` raises (e.g., disk full, `IntegrityError`)

In all these cases, `conn` is in scope in the `except` block (Python function-level scoping) but `conn.close()` is never called. Python's garbage collector will eventually finalize the connection, but under high-throughput calls or long-running processes, open file descriptors can accumulate until OS limits are hit.

**Fix**: Use `contextlib.closing` or a `try/finally` pattern:
```python
def _cache_get(key: str, ttl_s: float = 86400.0) -> Any:
    try:
        conn = _get_cache_conn()
        try:
            row = conn.execute(...).fetchone()
            ...
            return json.loads(payload)
        finally:
            conn.close()
    except Exception as exc:
        log.debug("Cache read error (key=%s): %s", key, exc)
        return None
```

---

### N-03 — LOW | `literature/rag.py:50–58` | `chunk_text()` hangs forever when `overlap >= chunk_size`

**Defect**: `chunk_text` advances by `step = chunk_size - overlap` per iteration. When `overlap >= chunk_size`, `step <= 0`, so `start` never advances and the loop runs forever:

```python
while start < len(words):
    end = min(start + chunk_size, len(words))
    chunks.append(" ".join(words[start:end]))
    if end == len(words):
        break          # only exits when end reaches the exact end
    start += chunk_size - overlap  # step=0 or negative → start unchanged → infinite loop
```

There is no guard, assertion, or `ValueError` to catch this. The function is exposed in the public API of `add_document()` with `chunk_size` and `overlap` as caller-supplied parameters; `LiteratureRAG.add_document` passes them through without validation.

**Impact**: A caller who accidentally passes `chunk_size <= overlap` (e.g., a small test chunk with `chunk_size=32, overlap=64`) will hang the process indefinitely with no error or timeout.

**Fix**: Add an early guard in `chunk_text`:
```python
step = chunk_size - overlap
if step <= 0:
    raise ValueError(
        f"chunk_size ({chunk_size}) must be greater than overlap ({overlap})"
    )
```

---

## Non-Issues (investigated and cleared in R2)

- **`update_retraction_status` DOI normalization**: Only applies `.lower()`, not prefix-stripping. Inconsistent with `get_by_doi`'s SQL expression fix (F-10), but all connectors store bare lowercase DOIs, so records with URL-prefixed DOIs only arise via direct `LiteratureRecord` construction — an unlikely misuse pattern. Acceptable as-is.
- **`_load_from_db` year=0 round-trip**: `c.year or 0` stores `None` as `0`; restored as `None` via `int(row['year']) if row.get('year') else None` (since `bool(0)` is `False`). Year=0 CE is not a valid publication year in this domain; the round-trip is semantically correct.
- **`_with_backoff` wraps non-network errors**: The decorator retries ALL exceptions from the decorated function. Non-retriable exceptions are swallowed inside the function (not re-raised), so they never reach the wrapper. Retriable exceptions that do reach the wrapper are correctly retried. The behavior is as intended.
- **`_CorpusBM25Index._pending` memory growth**: Never cleared after rebuild; O(n) memory. Intentional design — all pending chunks are needed for full TF-IDF rebuild. Not a correctness defect.
- **`_CITATION_PATTERN_RE` false positives on year-in-parentheses**: `\(\d{4}\)` matches e.g. `(2023)` in flowing prose. Triggers FABRICATED_CITATION if no DOI is present. This is a pre-existing design limitation present before R1; it is not introduced by the R1 patches. The system's intent is that all year-referencing in reviews must be backed by a DOI — an intentional strictness choice.
- **`loop_a.py` `if not engine.is_active(): break` (line 230)**: Checks engine state before `engine.step()` is called for the current round. Only catches externally-triggered deactivation between rounds. Not a logic error; `engine.step()` at line 273 correctly terminates the loop after the last round.
- **`PersonaGuard` thread safety**: Global `_OPTOUT_REGISTRY` has no lock. Single-threaded CLI design; not a current concern.
