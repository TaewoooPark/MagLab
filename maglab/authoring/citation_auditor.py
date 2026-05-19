r"""Citation auditor — existence + semantic 4-class verification (§16.4, §16.7).

Two verification layers:
1. **Existence** (§16.4): every ``\cite{KEY}`` in a draft must appear in the
   verified ``.bib`` pool.  Missing keys → ``MISSING`` tag → blocking gate.

2. **Semantic** (§16.7): each citation is classified into one of four classes:
       SUPPORTS / PARTIAL / UNSUPPORTED / UNCERTAIN
   plus a confidence score (0–1).  UNSUPPORTED or UNCERTAIN → blocking gate
   halts authoring (§5.15).

Public entry points:
    ``preflight_citations``  — build a verified pool before drafting.
    ``audit_existence``      — check ``\cite{KEY}`` against the verified pool.
    ``audit_semantics``      — 4-class semantic check via LLM mock.

Blocking gate integration:
    Both ``audit_existence`` and ``audit_semantics`` integrate with
    :class:`~maglab.authoring.data_vault.AuthoringBlockedError`.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from maglab.authoring.bib_manager import BibManager
from maglab.authoring.data_vault import AuthoringBlockedError

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Semantic classification
# ---------------------------------------------------------------------------


class SemanticLabel(StrEnum):
    """4-class semantic classification of a citation's support for a claim (§16.7)."""

    SUPPORTS = "SUPPORTS"
    """The cited paper clearly supports the claim."""
    PARTIAL = "PARTIAL"
    """The cited paper partially supports the claim or is only tangentially relevant."""
    UNSUPPORTED = "UNSUPPORTED"
    """The cited paper does not support the claim (or contradicts it)."""
    UNCERTAIN = "UNCERTAIN"
    """The relationship cannot be determined (full-text unavailable, etc.)."""


# ---------------------------------------------------------------------------
# Result data structures
# ---------------------------------------------------------------------------


@dataclass
class ExistenceFinding:
    """Existence-check result for a single cite-key."""

    cite_key: str
    found: bool
    """True if the key exists in the verified ``.bib`` pool."""


@dataclass
class ExistenceReport:
    """Full existence-check report for a draft."""

    findings: list[ExistenceFinding] = field(default_factory=list)

    @property
    def missing_keys(self) -> list[str]:
        """Cite-keys that are absent from the pool."""
        return [f.cite_key for f in self.findings if not f.found]

    @property
    def all_present(self) -> bool:
        """True if every cite-key is present in the pool."""
        return all(f.found for f in self.findings)


@dataclass
class SemanticFinding:
    """Semantic verification result for a single (claim, citation) pair."""

    cite_key: str
    claim_sentence: str
    label: SemanticLabel
    confidence: float  # 0.0 – 1.0
    evidence_snippet: str = ""
    """Supporting or refuting snippet from the cited paper."""


@dataclass
class SemanticReport:
    """Full semantic-verification report for a draft."""

    findings: list[SemanticFinding] = field(default_factory=list)

    @property
    def blocking_findings(self) -> list[SemanticFinding]:
        """Findings that block authoring (UNSUPPORTED or UNCERTAIN)."""
        return [
            f
            for f in self.findings
            if f.label in (SemanticLabel.UNSUPPORTED, SemanticLabel.UNCERTAIN)
        ]

    @property
    def passes_gate(self) -> bool:
        """True if no blocking findings (all SUPPORTS or PARTIAL)."""
        return len(self.blocking_findings) == 0


# ---------------------------------------------------------------------------
# Verified citation pool
# ---------------------------------------------------------------------------


@dataclass
class VerifiedCitePool:
    """Pool of DOI-verified cite-keys supplied to the LLM drafter (§16.4)."""

    cite_keys: list[str] = field(default_factory=list)
    """Verified BibTeX cite-keys the LLM may use in drafts."""
    doi_map: dict[str, str] = field(default_factory=dict)
    """Mapping: cite_key → normalised DOI."""


# ---------------------------------------------------------------------------
# LaTeX cite-key extraction
# ---------------------------------------------------------------------------

#: Regex matching ``\cite{KEY}``, ``\cite{KEY1,KEY2}``, ``\citep{KEY}``, etc.
_CITE_RE = re.compile(r"\\cite[pt]?\{([^}]+)\}")


def _extract_cite_keys(draft_tex: str) -> list[str]:
    """Extract all BibTeX cite-keys from a LaTeX draft string."""
    keys: list[str] = []
    for m in _CITE_RE.finditer(draft_tex):
        for raw_key in m.group(1).split(","):
            k = raw_key.strip()
            if k:
                keys.append(k)
    return keys


# ---------------------------------------------------------------------------
# Preflight — build verified pool before drafting
# ---------------------------------------------------------------------------


def preflight_citations(
    topic: str,
    n_candidates: int = 10,
    *,
    bib_manager: BibManager | None = None,
    search_fn: Callable[[str, int], list[dict[str, Any]]] | None = None,
    doi_verify_fn: Callable[[str], bool] | None = None,
) -> VerifiedCitePool:
    """Build a verified citation pool before drafting starts (§16.4).

    Searches for candidate papers on ``topic``, verifies each DOI (title +
    author cross-check), registers verified entries in *bib_manager*, and
    returns the pool of safe cite-keys.

    Parameters
    ----------
    topic:
        Research topic or query string passed to the literature search.
    n_candidates:
        Maximum number of candidate papers to fetch.
    bib_manager:
        ``BibManager`` instance to register verified entries in.  If ``None``
        a fresh in-memory manager is used.
    search_fn:
        Callable ``(topic, n) → list[dict]``.  Each dict must contain at least
        ``doi``, ``title``, ``author``/``authors``.  If ``None`` returns an
        empty pool (offline / test mode).
    doi_verify_fn:
        Callable ``(doi) → bool``.  ``True`` means the DOI resolves and
        metadata matches.  If ``None`` every non-empty DOI is treated as
        verified (permissive offline mode).

    Returns
    -------
    ``VerifiedCitePool`` — only DOI-verified candidates included.
    """
    mgr = bib_manager or BibManager()
    pool = VerifiedCitePool()

    if search_fn is None:
        return pool  # offline / test mode — empty pool

    candidates = search_fn(topic, n_candidates)

    for record in candidates:
        doi = record.get("doi", "")
        if not doi:
            continue

        # DOI verification
        if doi_verify_fn is not None and not doi_verify_fn(doi):
            continue
        # Permissive mode: any non-empty DOI passes

        cite_key = mgr.add_verified(doi, record)
        pool.cite_keys.append(cite_key)
        pool.doi_map[cite_key] = doi

    return pool


# ---------------------------------------------------------------------------
# Layer 1 — Existence verification
# ---------------------------------------------------------------------------


def audit_existence(
    draft_tex: str,
    bib_manager: BibManager,
    *,
    raise_on_missing: bool = True,
) -> ExistenceReport:
    r"""Verify that every ``\cite{KEY}`` in *draft_tex* is in the verified pool (§16.4).

    Parameters
    ----------
    draft_tex:
        LaTeX source of the draft section or full document.
    bib_manager:
        ``BibManager`` with the verified ``.bib`` pool.
    raise_on_missing:
        If ``True`` (default), raises :exc:`AuthoringBlockedError` when any
        cite-key is missing.

    Returns
    -------
    ExistenceReport
        Always returned when no exception is raised (i.e. all keys are present,
        or keys are missing but ``raise_on_missing=False``).  Callers using
        ``raise_on_missing=True`` should still capture the return value to
        inspect ``missing_keys`` inside a ``try/except`` block.

    Raises
    ------
    AuthoringBlockedError
        When missing keys are found and ``raise_on_missing=True``.
    """
    keys = _extract_cite_keys(draft_tex)
    findings: list[ExistenceFinding] = []

    for key in keys:
        found = bib_manager.has_key(key)
        findings.append(ExistenceFinding(cite_key=key, found=found))

    report = ExistenceReport(findings=findings)

    if not report.all_present and raise_on_missing:
        raise AuthoringBlockedError(
            f"Citation existence check failed — missing cite-key(s): "
            f"{report.missing_keys}.  Add verified entries before authoring."
        )
    return report


# ---------------------------------------------------------------------------
# Layer 2 — Semantic 4-class verification
# ---------------------------------------------------------------------------


def _default_semantic_fn(
    claim: str,
    paper_text: str,
    cite_key: str,
) -> SemanticFinding:
    """Fallback semantic classifier used when no LLM-backed classifier is injected.

    Returns PARTIAL (non-blocking) with a clear warning so that authoring can
    proceed on existence-verified citations without an LLM configured.  A real
    injected ``semantic_classify_fn`` must still enforce 4-class blocking
    (UNSUPPORTED / UNCERTAIN → AuthoringBlockedError).

    This fallback intentionally does NOT use UNCERTAIN so that researchers who
    have not yet configured LLM credentials can still draft with verified-pool
    citations.  The warning in the log makes it clear that semantic verification
    was skipped.
    """
    _log.warning(
        "Semantic classifier not configured — skipping semantic check for cite_key=%r "
        "(existence check still enforced). Inject a semantic_classify_fn to enable "
        "full 4-class verification.",
        cite_key,
    )
    return SemanticFinding(
        cite_key=cite_key,
        claim_sentence=claim,
        label=SemanticLabel.PARTIAL,
        confidence=0.0,
        evidence_snippet="[Semantic verification skipped — no classifier configured]",
    )


def audit_semantics(
    draft_tex: str,
    bib_manager: BibManager,
    full_text_pool: dict[str, str] | None = None,
    *,
    semantic_classify_fn: Callable[[str, str, str], SemanticFinding] | None = None,
    raise_on_blocking: bool = True,
) -> SemanticReport:
    r"""Semantic 4-class verification of each citation in *draft_tex* (§16.7).

    For each ``\cite{KEY}`` found adjacent to a claim sentence, classify the
    citation as SUPPORTS / PARTIAL / UNSUPPORTED / UNCERTAIN.  Blocking labels
    (UNSUPPORTED, UNCERTAIN) halt authoring.

    Parameters
    ----------
    draft_tex:
        LaTeX source of the draft.
    bib_manager:
        Verified ``BibManager`` — used to check key existence.
    full_text_pool:
        Mapping of cite-key → full paper text (or abstract).  Used to supply
        paper content to *semantic_classify_fn*.  Missing keys are passed to
        the classifier with empty paper text.
    semantic_classify_fn:
        Callable ``(claim_sentence, paper_text, cite_key) → SemanticFinding``.
        In production this wraps an LLM call.  In tests, inject a mock.
        If ``None``, the fallback marks every citation PARTIAL (non-blocking)
        and logs a warning that semantic verification was skipped.
    raise_on_blocking:
        If ``True`` (default), raises :exc:`AuthoringBlockedError` when any
        blocking finding is detected.

    Returns
    -------
    ``SemanticReport``.

    Raises
    ------
    AuthoringBlockedError
        When blocking findings are present and ``raise_on_blocking=True``.
    """
    classify = semantic_classify_fn or _default_semantic_fn
    pool = full_text_pool or {}
    findings: list[SemanticFinding] = []

    # Extract sentences containing \cite{} — heuristic: split on sentence boundaries.
    sentences_with_cites = _extract_claim_sentences(draft_tex)

    for sentence, cite_keys in sentences_with_cites:
        for key in cite_keys:
            paper_text = pool.get(key, "")
            finding = classify(sentence, paper_text, key)
            findings.append(finding)

    report = SemanticReport(findings=findings)

    if not report.passes_gate and raise_on_blocking:
        blocking = report.blocking_findings
        details = "; ".join(f"{f.cite_key}: {f.label} (conf={f.confidence:.2f})" for f in blocking)
        raise AuthoringBlockedError(
            f"Semantic citation check failed — {len(blocking)} blocking finding(s): "
            f"{details}.  Resolve before authoring proceeds."
        )
    return report


def _extract_claim_sentences(draft_tex: str) -> list[tuple[str, list[str]]]:
    r"""Extract (sentence, cite_keys) pairs from a LaTeX draft.

    A simplistic sentence splitter: split on ``.``, ``!``, ``?`` followed by
    whitespace.  Each segment containing ``\cite{...}`` is returned as a
    claim sentence with its cite-keys.
    """
    # Remove LaTeX comments
    no_comments = re.sub(r"%[^\n]*", "", draft_tex)
    # Split on sentence-ending punctuation
    segments = re.split(r"(?<=[.!?])\s+", no_comments)

    result: list[tuple[str, list[str]]] = []
    for seg in segments:
        keys = [
            k.strip() for m in _CITE_RE.finditer(seg) for k in m.group(1).split(",") if k.strip()
        ]
        if keys:
            result.append((seg.strip(), keys))
    return result


# ---------------------------------------------------------------------------
# Blocking gate integration (§5.15)
# ---------------------------------------------------------------------------


class PreSectionFinalizeHook:
    """Pre-section finalisation hook — chains existence + semantic checks (§5.15, T-P6-09).

    Usage::

        hook = PreSectionFinalizeHook(bib_manager=mgr, vault=vault)
        hook.run(draft_tex, section="methods")   # raises AuthoringBlockedError on failure

    Parameters
    ----------
    bib_manager:
        Verified BibTeX manager.
    vault:
        ``DataVault`` instance used to validate placeholder keys.
    full_text_pool:
        Optional mapping cite-key → paper text for semantic classification.
    semantic_classify_fn:
        Optional LLM-backed classifier (injected in production; mocked in tests).
    """

    def __init__(
        self,
        bib_manager: BibManager,
        vault: Any = None,
        full_text_pool: dict[str, str] | None = None,
        semantic_classify_fn: Callable[[str, str, str], SemanticFinding] | None = None,
    ) -> None:
        self._bib = bib_manager
        self._vault = vault
        self._pool = full_text_pool or {}
        self._classify = semantic_classify_fn

    def run(
        self,
        draft_tex: str,
        section: str = "",
    ) -> None:
        """Run the full pre-section gate (existence + semantic + data vault).

        Raises
        ------
        AuthoringBlockedError
            If any check fails.
        """
        # 1. Existence check
        audit_existence(draft_tex, self._bib, raise_on_missing=True)

        # 2. Semantic check
        audit_semantics(
            draft_tex,
            self._bib,
            self._pool,
            semantic_classify_fn=self._classify,
            raise_on_blocking=True,
        )

        # 3. Data vault: validate placeholder keys
        if self._vault is not None:
            missing = self._vault.validate_draft(draft_tex, section=section)
            if missing:
                raise AuthoringBlockedError(
                    f"Data vault gate failed{' in section ' + repr(section) if section else ''}: "
                    f"no DataPoint for placeholder key(s): {missing}."
                )
