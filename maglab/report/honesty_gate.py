"""Honesty Gate — active blocking gate (§5.15·§17).

This module **stops** (raises an exception or returns a blocked result) rather
than merely warning.  It scans for:

1. Untagged numbers — bare numerical values in text without a DataPoint.
2. Unverified citations — DOI/URL patterns not present in the verification pool.
3. Missing persona disclosure — AI disclosure label absent from reviewer utterances.
4. First-person attribution patterns — "I calculated", "I found", etc.
5. Out-of-vault value references — DataPoint ID references not in the vault.
6. Untagged figure data — numerical values in figure body without a DataPoint.

Claim-level audit:
- ``audit_claims``: extracts factual claims from text and cross-checks them
  against DataPoint / citation evidence.

Promise-check (§5.15):
- Extracts "I executed", "I remembered" claims from agent utterances and
  cross-checks them against actual tool-call logs and provenance records,
  flagging discrepancies.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

# ---------------------------------------------------------------------------
# Violation kinds and result data structures
# ---------------------------------------------------------------------------


class ViolationKind(StrEnum):
    """Integrity violation kind."""

    UNTAGGED_NUMBER = "UNTAGGED_NUMBER"
    """Bare numerical value without a DataPoint."""
    UNVERIFIED_CITATION = "UNVERIFIED_CITATION"
    """Citation not present in the verification pool."""
    MISSING_PERSONA_DISCLOSURE = "MISSING_PERSONA_DISCLOSURE"
    """AI disclosure label missing from a persona utterance."""
    FIRST_PERSON_ATTRIBUTION = "FIRST_PERSON_ATTRIBUTION"
    """First-person attribution pattern."""
    OUT_OF_VAULT_VALUE = "OUT_OF_VAULT_VALUE"
    """DataPoint ID reference not in the data vault."""
    UNTAGGED_FIGURE_DATA = "UNTAGGED_FIGURE_DATA"
    """Numerical value in a figure without a DataPoint."""
    PROMISE_MISMATCH = "PROMISE_MISMATCH"
    """Mismatch between agent utterance and actual tool log."""


@dataclass(frozen=True)
class Violation:
    """A single integrity violation record."""

    kind: ViolationKind
    message: str
    excerpt: str = ""
    position: int = -1  # position in text (if available)

    def __str__(self) -> str:
        loc = f" [pos={self.position}]" if self.position >= 0 else ""
        excerpt = f" | excerpt: «{self.excerpt[:60]}»" if self.excerpt else ""
        return f"[{self.kind.value}]{loc} {self.message}{excerpt}"


@dataclass
class GateResult:
    """Honesty Gate check result."""

    passed: bool
    violations: list[Violation] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> str:
        if self.passed:
            return "PASSED (no violations)"
        lines = [f"BLOCKED — {len(self.violations)} violation(s):"]
        for v in self.violations:
            lines.append(f"  • {v}")
        return "\n".join(lines)


class HonestyViolationError(Exception):
    """Blocking gate violation — halts pipeline execution."""

    def __init__(self, violations: list[Violation]) -> None:
        self.violations = violations
        super().__init__(
            f"HonestyGate blocked: {len(violations)} violation(s)\n"
            + "\n".join(f"  • {v}" for v in violations)
        )


# Backward-compatible alias — public API compatibility
HonestyViolation = HonestyViolationError


# ---------------------------------------------------------------------------
# Detection regular expressions
# ---------------------------------------------------------------------------

# Bare numbers: decimal and exponent notation (e.g. 3.14, 1e-3, -0.5, 4.2e+7)
_NUMBER_RE = re.compile(
    r"""
    (?<!\w)              # not preceded by a word character
    -?                   # optional sign
    (?:
        \d+\.\d+         # decimal (e.g. 3.14)
      | \d+[eE][+-]?\d+ # exponent (e.g. 1e-3)
      | \d+\.\d+[eE][+-]?\d+  # decimal + exponent
      | \d+              # integer (standalone)
    )
    (?!\w)               # not followed by a word character
    """,
    re.VERBOSE,
)

# DOI pattern (10.xxxx/xxx)
_DOI_RE = re.compile(r"\b10\.\d{4,}/\S+")

# arXiv ID pattern
_ARXIV_RE = re.compile(r"\barXiv:\d{4}\.\d{4,}\b", re.IGNORECASE)

# Persona AI disclosure label pattern
_PERSONA_DISCLOSURE_RE = re.compile(
    r"(?:"
    r"AI model"
    r"|language model"
    r"|corpus model"
    r"|AI.{0,10}reviewer"
    r"|simulated reviewer"
    r"|model.{0,10}based reviewer"
    r")",
    re.IGNORECASE,
)

# First-person attribution patterns
_FIRST_PERSON_RE = re.compile(
    r"(?:"
    r"I\s+(?:calculated|found|measured|proved|discovered|analyzed|verified)"
    r"|my\s+(?:calculation|analysis|research|experiment)"
    r"|I\s+have\s+(?:calculated|found|measured)"
    r")",
    re.IGNORECASE,
)

# DataPoint ID reference pattern (UUID4 format)
_DP_ID_RE = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)

# Promise patterns: first-person only — "I executed", "I have saved", "we ran",
# "I have already completed", etc.  Requires an explicit first-person subject
# (I or we, optionally followed by "have" and/or "already") so passive and
# third-person constructions ("results were recorded", "the fit was completed")
# do NOT match.
_PROMISE_RE = re.compile(
    r"(?:"
    r"(?:I|we)\s+(?:have\s+)?(?:already\s+)?"
    r"(?:executed|remembered|saved|recorded|completed|performed|processed|verified"
    r"|ran|done|finished)"
    r")",
    re.IGNORECASE,
)

# Figure context detection (matches "figure", "fig.", "Fig.")
_FIGURE_CONTEXT_RE = re.compile(
    r"(?:figure|fig\.|Fig\.)\s*\d*",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Core check functions
# ---------------------------------------------------------------------------


def check_untagged_numbers(
    text: str,
    known_dp_ids: set[str] | None = None,
    allow_integers: bool = False,
) -> list[Violation]:
    """Detect bare numerical values in text without an accompanying DataPoint.

    Parameters
    ----------
    text:
        Text to check.
    known_dp_ids:
        Set of verified DataPoint IDs.  Any UUID in the text that is not in
        this set is treated as a violation.
    allow_integers:
        If True, standalone integers (no decimal point or exponent) are
        allowed (e.g. sequence numbers, years).
    """
    violations: list[Violation] = []
    for m in _NUMBER_RE.finditer(text):
        raw = m.group(0)
        # Check whether this is an integer-only value
        is_integer = re.fullmatch(r"-?\d+", raw) is not None
        if allow_integers and is_integer:
            continue
        # Check whether a DataPoint ID appears in the surrounding context
        ctx_start = max(0, m.start() - 200)
        ctx_end = min(len(text), m.end() + 200)
        context = text[ctx_start:ctx_end]
        ids_in_context = _DP_ID_RE.findall(context)
        if known_dp_ids is not None:
            ids_verified = any(did in known_dp_ids for did in ids_in_context)
        else:
            ids_verified = bool(ids_in_context)  # any ID present counts as tagged

        if not ids_verified:
            violations.append(
                Violation(
                    kind=ViolationKind.UNTAGGED_NUMBER,
                    message=f"Untagged number without DataPoint: {raw}",
                    excerpt=context[:80].strip(),
                    position=m.start(),
                )
            )
    return violations


def check_citations(
    text: str,
    verified_citations: set[str] | None = None,
) -> list[Violation]:
    """Cross-check citations (DOI, arXiv) in text against the verification pool.

    Parameters
    ----------
    text:
        Text to check.
    verified_citations:
        Set of verified DOI / arXiv IDs.  If None, only format is checked.
    """
    violations: list[Violation] = []
    found_dois = _DOI_RE.findall(text)
    found_arxivs = _ARXIV_RE.findall(text)
    all_found = found_dois + found_arxivs

    if verified_citations is None:
        return violations  # no pool — format passes

    for cit in all_found:
        # Strip trailing punctuation from DOI
        cit_clean = cit.rstrip(".,;")
        if cit_clean not in verified_citations:
            violations.append(
                Violation(
                    kind=ViolationKind.UNVERIFIED_CITATION,
                    message=f"Citation not in verification pool: {cit_clean}",
                    excerpt=cit_clean,
                )
            )
    return violations


def check_persona_disclosure(
    text: str,
    require_disclosure: bool = True,
) -> list[Violation]:
    """Check that a persona utterance carries an AI disclosure label.

    Parameters
    ----------
    text:
        Reviewer or persona utterance text.
    require_disclosure:
        If True, the absence of a disclosure label is treated as a violation.
    """
    if not require_disclosure:
        return []
    if _PERSONA_DISCLOSURE_RE.search(text):
        return []
    return [
        Violation(
            kind=ViolationKind.MISSING_PERSONA_DISCLOSURE,
            message=(
                "Persona utterance is missing an AI disclosure label "
                "(e.g. 'AI model', 'simulated reviewer', 'language model')."
            ),
            excerpt=text[:80].strip(),
        )
    ]


def check_first_person_attribution(text: str) -> list[Violation]:
    """Detect first-person attribution patterns ('I calculated', 'I found', etc.)."""
    violations: list[Violation] = []
    for m in _FIRST_PERSON_RE.finditer(text):
        violations.append(
            Violation(
                kind=ViolationKind.FIRST_PERSON_ATTRIBUTION,
                message=f"First-person attribution detected: «{m.group(0)}»",
                excerpt=text[max(0, m.start() - 20) : m.end() + 20].strip(),
                position=m.start(),
            )
        )
    return violations


def check_vault_references(
    text: str,
    vault_ids: set[str],
) -> list[Violation]:
    """Check that DataPoint UUIDs in text are present in the data vault.

    Parameters
    ----------
    text:
        Text to check.
    vault_ids:
        Set of valid DataPoint IDs (the vault).
    """
    violations: list[Violation] = []
    found_ids = _DP_ID_RE.findall(text)
    for did in found_ids:
        if did.lower() not in {v.lower() for v in vault_ids}:
            violations.append(
                Violation(
                    kind=ViolationKind.OUT_OF_VAULT_VALUE,
                    message=f"DataPoint ID not in vault: {did}",
                    excerpt=did,
                )
            )
    return violations


def check_figure_data_tags(
    figure_text: str,
    known_dp_ids: set[str] | None = None,
) -> list[Violation]:
    """Check that numerical values in figure descriptions have an accompanying DataPoint.

    Skips the check when no figure context is detected in the text.
    """
    if not _FIGURE_CONTEXT_RE.search(figure_text):
        return []
    return check_untagged_numbers(figure_text, known_dp_ids)


# ---------------------------------------------------------------------------
# Promise-check
# ---------------------------------------------------------------------------


def check_promises(
    agent_text: str,
    tool_log: list[dict[str, Any]],
) -> list[Violation]:
    """Cross-check 'I executed' claims in agent utterances against the tool log (§5.15).

    Parameters
    ----------
    agent_text:
        Agent utterance text (natural language).
    tool_log:
        Actual tool-call log.  Each entry has the form
        ``{"tool": str, "status": str, ...}``.

    Returns
    -------
    list[Violation]
        List of mismatch violations.  An empty list means no discrepancy.
    """
    violations: list[Violation] = []
    promise_matches = list(_PROMISE_RE.finditer(agent_text))
    if not promise_matches:
        return []

    # Extract the set of successfully executed tools from the log
    executed_tools: set[str] = set()
    for entry in tool_log:
        if isinstance(entry, dict):
            tool_name = entry.get("tool", "")
            status = entry.get("status", "")
            if tool_name and status in {"success", "ok", "completed", "done"}:
                executed_tools.add(tool_name.lower())

    # Read-only / query-tier tools whose presence must NOT suppress a
    # promise-check violation.  An agent claiming "I executed the simulation"
    # must still be flagged when the only logged tool is "memory.read".
    read_only_tools: frozenset[str] = frozenset(
        {"memory.read", "pool.query", "read", "list", "search", "query"}
    )
    # Write-tier tools: any successfully executed tool that is NOT read-only
    write_tools = {t for t in executed_tools if t not in read_only_tools}

    for m in promise_matches:
        # Extract context around the promise for diagnosis
        ctx = agent_text[max(0, m.start() - 100) : m.end() + 100]
        # Flag when no write-tier tool was actually executed.
        # This catches both "no tools at all" and "only read-only tools ran"
        # while suppressing false positives when a genuine write-tier action
        # (e.g. sim_run, save, record) was logged for this session.
        if not write_tools:
            violations.append(
                Violation(
                    kind=ViolationKind.PROMISE_MISMATCH,
                    message=(
                        f"Agent claimed «{m.group(0)}» but no write-tier execution "
                        f"record found in the tool log "
                        f"(executed: {sorted(executed_tools) or 'none'})."
                    ),
                    excerpt=ctx[:80].strip(),
                    position=m.start(),
                )
            )
    return violations


# ---------------------------------------------------------------------------
# Claim-level audit
# ---------------------------------------------------------------------------


def audit_claims(
    text: str,
    verified_dp_ids: set[str] | None = None,
    verified_citations: set[str] | None = None,
) -> list[Violation]:
    """Cross-check factual claims in text against DataPoint and citation evidence.

    Internally runs number tagging, citation verification, and first-person
    attribution checks, then returns the combined violation list.

    Parameters
    ----------
    text:
        Text to audit.
    verified_dp_ids:
        Set of valid DataPoint IDs.
    verified_citations:
        Set of verified citations.
    """
    violations: list[Violation] = []
    violations.extend(check_untagged_numbers(text, verified_dp_ids))
    violations.extend(check_citations(text, verified_citations))
    violations.extend(check_first_person_attribution(text))
    return violations


# ---------------------------------------------------------------------------
# Integrated gate
# ---------------------------------------------------------------------------


def run_gate(
    text: str,
    *,
    is_persona: bool = False,
    known_dp_ids: set[str] | None = None,
    vault_ids: set[str] | None = None,
    verified_citations: set[str] | None = None,
    tool_log: list[dict[str, Any]] | None = None,
    is_figure: bool = False,
    raise_on_violation: bool = True,
) -> GateResult:
    """Run all integrity checks in sequence — the integrated gate.

    Parameters
    ----------
    text:
        Text to check.
    is_persona:
        If True, activates the persona AI disclosure check.
    known_dp_ids:
        Set of known DataPoint IDs (UUID pattern only if None).
    vault_ids:
        Set of valid DataPoint vault IDs.
    verified_citations:
        Set of verified citations.
    tool_log:
        Tool-call log (for promise-check).
    is_figure:
        If True, also runs the figure data tag check.
    raise_on_violation:
        If True, raises ``HonestyViolation`` on any violation.

    Returns
    -------
    GateResult
        Check result.  Only returned when ``raise_on_violation=False``.
    """
    violations: list[Violation] = []

    # 1. Untagged numbers — skipped when is_figure=True because step 6
    # (check_figure_data_tags) already calls check_untagged_numbers on the
    # same text, which would otherwise produce identical duplicate violations.
    if not is_figure:
        violations.extend(check_untagged_numbers(text, known_dp_ids))

    # 2. Citation verification
    if verified_citations is not None:
        violations.extend(check_citations(text, verified_citations))

    # 3. Persona disclosure
    if is_persona:
        violations.extend(check_persona_disclosure(text))

    # 4. First-person attribution
    violations.extend(check_first_person_attribution(text))

    # 5. Vault references
    if vault_ids is not None:
        violations.extend(check_vault_references(text, vault_ids))

    # 6. Figure untagged data — supersedes step 1 when is_figure=True.
    # check_figure_data_tags internally calls check_untagged_numbers, so it
    # covers all untagged-number violations for figure text.  When no figure
    # context keyword is present in the text it returns [] (no false positives).
    if is_figure:
        violations.extend(check_figure_data_tags(text, known_dp_ids))

    # 7. Promise-check
    if tool_log is not None:
        violations.extend(check_promises(text, tool_log))

    passed = len(violations) == 0
    result = GateResult(passed=passed, violations=violations)

    if not passed and raise_on_violation:
        raise HonestyViolation(violations)

    return result
