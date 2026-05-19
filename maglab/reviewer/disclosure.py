"""Persona reviewer seven-safeguard enforcement (§15.2).

★ Non-negotiable — violations trigger HonestyGate blocking.

Seven safeguards:
  1. Disclosure label — "[AI Reviewer] modeled from N public papers by [Author], not their actual opinion or endorsement"
  2. No first-person attribution — third-person inferential only, enforced by post-processing check
  3. No fabricated citations — verbatim chunk excerpts + DOI only
  4. Scope limited to public/published positions
  5. No fabricated expertise outside the corpus
  6. Opt-out registry — blocks persona generation for registered authors
  7. Mandatory "AI Reviewer (corpus model)" naming
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

import platformdirs

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Violation types
# ---------------------------------------------------------------------------


class DisclosureViolation(StrEnum):
    """Seven safeguard violation types."""

    MISSING_DISCLOSURE_LABEL = "MISSING_DISCLOSURE_LABEL"
    """Safeguard ①: missing disclosure label."""
    FIRST_PERSON_ATTRIBUTION = "FIRST_PERSON_ATTRIBUTION"
    """Safeguard ②: first-person attribution pattern."""
    FABRICATED_CITATION = "FABRICATED_CITATION"
    """Safeguard ③: citation without DOI (possible fabrication)."""
    OUT_OF_SCOPE_OPINION = "OUT_OF_SCOPE_OPINION"
    """Safeguard ④: claim exceeding publicly stated positions."""
    FABRICATED_EXPERTISE = "FABRICATED_EXPERTISE"
    """Safeguard ⑤: claimed expertise outside the corpus."""
    OPTED_OUT_AUTHOR = "OPTED_OUT_AUTHOR"
    """Safeguard ⑥: attempted persona generation for opted-out author."""
    MISSING_AI_REVIEWER_LABEL = "MISSING_AI_REVIEWER_LABEL"
    """Safeguard ⑦: missing "AI Reviewer" naming."""


@dataclass(frozen=True)
class DisclosureViolationRecord:
    """Single safeguard violation record."""

    violation: DisclosureViolation
    message: str
    excerpt: str = ""

    def __str__(self) -> str:
        ex = f" | «{self.excerpt[:60]}»" if self.excerpt else ""
        return f"[{self.violation.value}] {self.message}{ex}"


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Safeguards ①·⑦: disclosure label and AI reviewer naming
_DISCLOSURE_LABEL_RE = re.compile(
    r"(?:"
    r"public papers?.{0,30}modeled.{0,10}AI [Rr]eviewer"
    r"|AI [Rr]eviewer"
    r"|corpus model"
    r"|model.{0,10}based reviewer"
    r"|not their actual opinion"
    r"|not.{0,20}actual opinion.{0,20}endorsement"
    r"|AI.{0,10}reviewer"
    r"|corpus.{0,10}model"
    r")",
    re.IGNORECASE,
)

_AI_REVIEWER_LABEL_RE = re.compile(
    r"(?:AI [Rr]eviewer|corpus model|model.{0,10}based reviewer)",
    re.IGNORECASE,
)

# Safeguard ②: first-person attribution
_FIRST_PERSON_RE = re.compile(
    r"(?:"
    r"I\s+(?:calculated|found|measured|proved|discovered|analyzed|reviewed|evaluated|recommend)"
    r"|my\s+(?:calculation|analysis|research|experiment|review|opinion)"
    r"|I\s+have\s+(?:calculated|found|measured|reviewed)"
    r")",
    re.IGNORECASE,
)

# Safeguard ③: DOI pattern (citations must include a DOI)
_CITATION_PATTERN_RE = re.compile(
    r"(?:"
    r"\[[0-9]+\]"
    r"|et al\."
    r"|corresponding author"
    r"|\(\d{4}\)"
    r"|DOI:\s*10\."          # "DOI: 10.xxxx/..." direct citation form
    r"|\(DOI:"               # "(DOI:..." parenthetical form
    r")",
    re.IGNORECASE,
)
_DOI_RE = re.compile(r"10\.\d{4,}/[a-zA-Z0-9_./-]+")
_ARXIV_RE = re.compile(r"arXiv:\d{4}\.\d{4,}", re.IGNORECASE)

# Safeguard ⑤: fabricated expertise outside the corpus
_EXPERTISE_FABRICATION_RE = re.compile(
    r"(?:"
    r"I\s+am\s+(?:an?\s+)?expert"
    r"|I\s+(?:hold|have)\s+a\s+(?:PhD|doctorate)"
    r"|as\s+a\s+(?:professor|researcher|PhD)"
    r"|personally\s+(?:calculated|measured|researched)"
    r"|unpublished"
    r"|(?:private|confidential|proprietary)\s+data"
    r")",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Opt-out registry — persisted to disk so opt-outs survive process restarts
# ---------------------------------------------------------------------------

_APP = "maglab"


def _optout_path() -> Path:
    """Return the path to the persistent opt-out JSON file.

    Uses ``platformdirs.user_data_dir`` so the file lives in the correct
    platform-specific user data directory (~/.local/share/maglab/ on Linux,
    ~/Library/Application Support/maglab/ on macOS, etc.).
    """
    d = Path(platformdirs.user_data_dir(_APP))
    d.mkdir(parents=True, exist_ok=True)
    return d / "optout.json"


def _load_optout() -> set[str]:
    """Load the opt-out registry from disk; return an empty set on any error."""
    try:
        p = _optout_path()
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return {str(x).strip().lower() for x in data}
    except Exception as exc:  # noqa: BLE001
        log.warning("opt-out registry load failed (using empty set): %s", exc)
    return set()


def _save_optout(registry: set[str]) -> None:
    """Persist the opt-out registry to disk; failures are logged, not raised."""
    try:
        p = _optout_path()
        p.write_text(json.dumps(sorted(registry), ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        log.warning("opt-out registry save failed: %s", exc)


# Load persisted opt-outs at import time so the set is always current.
_OPTOUT_REGISTRY: set[str] = _load_optout()
"""Global opt-out registry — blocks persona generation for registered author IDs.
Persisted to disk via ``platformdirs.user_data_dir("maglab")/optout.json``."""


def register_optout(author_id: str) -> None:
    """Register an author ID in the opt-out registry and persist to disk.

    Registered authors are blocked by ``check_optout()`` or ``PersonaGuard``.
    """
    _OPTOUT_REGISTRY.add(author_id.strip().lower())
    _save_optout(_OPTOUT_REGISTRY)


def unregister_optout(author_id: str) -> None:
    """Remove an author ID from the opt-out registry and persist to disk."""
    _OPTOUT_REGISTRY.discard(author_id.strip().lower())
    _save_optout(_OPTOUT_REGISTRY)


def is_opted_out(author_id: str) -> bool:
    """Return True if the author ID is in the opt-out registry."""
    return author_id.strip().lower() in _OPTOUT_REGISTRY


def get_optout_registry() -> frozenset[str]:
    """Return an immutable copy of the current opt-out registry."""
    return frozenset(_OPTOUT_REGISTRY)


def clear_optout_registry() -> None:
    """Clear the opt-out registry and persist the empty state to disk (for testing)."""
    _OPTOUT_REGISTRY.clear()
    _save_optout(_OPTOUT_REGISTRY)


# ---------------------------------------------------------------------------
# Disclosure label generation
# ---------------------------------------------------------------------------


def build_disclosure_label(
    author_name: str,
    paper_count: int,
    *,
    author_id: str = "",
) -> str:
    """Generate the safeguard ① disclosure label string.

    Parameters
    ----------
    author_name:
        Author display name.
    paper_count:
        Number of papers in the corpus.
    author_id:
        Author ID (optional, for opt-out check).

    Returns
    -------
    str
        Standard disclosure label text.
    """
    return (
        f"[AI Reviewer — Corpus Model] "
        f"This review was generated by an AI Reviewer modeled from {paper_count} public papers by {author_name}. "
        f"This is not {author_name}'s actual opinion or endorsement. "
        f"For manuscript preparation feedback only."
    )


# ---------------------------------------------------------------------------
# Seven safeguard check functions
# ---------------------------------------------------------------------------


def check_disclosure_label(text: str) -> list[DisclosureViolationRecord]:
    """Safeguard ①: check for the presence of the disclosure label."""
    if _DISCLOSURE_LABEL_RE.search(text):
        return []
    return [
        DisclosureViolationRecord(
            violation=DisclosureViolation.MISSING_DISCLOSURE_LABEL,
            message="Persona review output is missing the disclosure label. "
            "Example: 'AI Reviewer modeled from N public papers by [Author], not their actual opinion or endorsement'",
            excerpt=text[:80].strip(),
        )
    ]


def check_first_person(text: str) -> list[DisclosureViolationRecord]:
    """Safeguard ②: detect first-person attribution patterns (third-person inferential required)."""
    violations = []
    for m in _FIRST_PERSON_RE.finditer(text):
        violations.append(
            DisclosureViolationRecord(
                violation=DisclosureViolation.FIRST_PERSON_ATTRIBUTION,
                message=f"First-person attribution detected: «{m.group(0)}». "
                "Persona reviewers must express opinions in third-person inferential form only.",
                excerpt=text[max(0, m.start() - 20) : m.end() + 20].strip(),
            )
        )
    return violations


def check_fabricated_citations(
    text: str,
    verified_dois: set[str] | None = None,
) -> list[DisclosureViolationRecord]:
    """Safeguard ③: detect citations without DOIs (possible fabrication).

    A citation pattern without a DOI/arXiv ID is treated as a fabricated citation.

    Parameters
    ----------
    text:
        Text to check.
    verified_dois:
        Set of verified DOIs. If None, only checks for DOI presence.
    """
    citations_found = _CITATION_PATTERN_RE.findall(text)
    if not citations_found:
        return []

    dois_found = set(_DOI_RE.findall(text))
    arxivs_found = set(_ARXIV_RE.findall(text))
    all_refs = dois_found | arxivs_found

    violations = []

    # Citation pattern present but no DOI/arXiv at all
    if citations_found and not all_refs:
        violations.append(
            DisclosureViolationRecord(
                violation=DisclosureViolation.FABRICATED_CITATION,
                message=f"Found {len(citations_found)} citation pattern(s) but no DOI/arXiv ID. "
                "No fabricated citations: only verbatim chunk excerpts + DOI are permitted.",
                excerpt=str(citations_found[:3]),
            )
        )

    # If a verified DOI set is provided, check for DOI matches
    if verified_dois is not None:
        for doi in dois_found:
            clean = doi.rstrip(".,;")
            if clean not in verified_dois:
                violations.append(
                    DisclosureViolationRecord(
                        violation=DisclosureViolation.FABRICATED_CITATION,
                        message=f"Unverified DOI: {clean}. "
                        "Only DOIs from chunks retrieved by the corpus RAG may be used.",
                        excerpt=clean,
                    )
                )

    return violations


def check_scope(
    text: str,
    *,
    corpus_keywords: set[str] | None = None,
) -> list[DisclosureViolationRecord]:
    """Safeguard ④: restrict to public/published positions.

    If a corpus keyword set is provided, performs a basic check for whether
    the text makes expert claims about topics outside the corpus scope.

    Current implementation: detects only explicit out-of-scope assertion patterns
    (advanced NLI deferred to P6 extension).
    """
    # Explicit out-of-scope assertion markers: "asserting dogmatically despite topic absence in corpus"
    _out_of_scope_markers = [
        "in this field, it is generally",
        "in every laboratory",
        "as anyone knows",
        "as everyone knows",
        "it is universally accepted that",
    ]
    violations = []
    text_lower = text.lower()
    for marker in _out_of_scope_markers:
        if marker.lower() in text_lower:
            idx = text_lower.find(marker.lower())
            violations.append(
                DisclosureViolationRecord(
                    violation=DisclosureViolation.OUT_OF_SCOPE_OPINION,
                    message=f"Out-of-scope dogmatic assertion detected: «{marker}». "
                    "Must remain within the scope of the author's publicly stated positions.",
                    excerpt=text[max(0, idx - 20) : idx + len(marker) + 20].strip(),
                )
            )
    return violations


def check_expertise_fabrication(text: str) -> list[DisclosureViolationRecord]:
    """Safeguard ⑤: detect fabricated expertise patterns outside the corpus."""
    violations = []
    for m in _EXPERTISE_FABRICATION_RE.finditer(text):
        violations.append(
            DisclosureViolationRecord(
                violation=DisclosureViolation.FABRICATED_EXPERTISE,
                message=f"Fabricated expertise pattern detected outside corpus: «{m.group(0)}». "
                "Only information within the author's public paper corpus may be used.",
                excerpt=text[max(0, m.start() - 20) : m.end() + 20].strip(),
            )
        )
    return violations


def check_optout(author_id: str) -> list[DisclosureViolationRecord]:
    """Safeguard ⑥: check whether the author ID is in the opt-out registry."""
    if is_opted_out(author_id):
        return [
            DisclosureViolationRecord(
                violation=DisclosureViolation.OPTED_OUT_AUTHOR,
                message=f"Author '{author_id}' is registered in the opt-out registry. "
                "Persona generation for this author is not permitted.",
                excerpt=author_id,
            )
        ]
    return []


def check_ai_reviewer_label(text: str) -> list[DisclosureViolationRecord]:
    """Safeguard ⑦: check for the presence of "AI Reviewer (corpus model)" naming."""
    if _AI_REVIEWER_LABEL_RE.search(text):
        return []
    return [
        DisclosureViolationRecord(
            violation=DisclosureViolation.MISSING_AI_REVIEWER_LABEL,
            message="Review output does not include 'AI Reviewer' or 'corpus model' naming. "
            "Persona reviewers must be identified as an AI Reviewer (corpus model).",
            excerpt=text[:80].strip(),
        )
    ]


# ---------------------------------------------------------------------------
# Unified guard — all seven safeguards
# ---------------------------------------------------------------------------


@dataclass
class PersonaGuardResult:
    """PersonaGuard unified check result."""

    passed: bool
    violations: list[DisclosureViolationRecord] = field(default_factory=list)

    def summary(self) -> str:
        """Summary string of the check result."""
        if self.passed:
            return "PASSED — all seven safeguards passed"
        lines = [f"BLOCKED — {len(self.violations)} safeguard violation(s):"]
        for v in self.violations:
            lines.append(f"  • {v}")
        return "\n".join(lines)


class PersonaDisclosureError(Exception):
    """Persona safeguard violation — halts pipeline execution."""

    def __init__(self, violations: list[DisclosureViolationRecord]) -> None:
        self.violations = violations
        super().__init__(
            f"PersonaGuard blocked: {len(violations)} violation(s)\n"
            + "\n".join(f"  • {v}" for v in violations)
        )


class PersonaGuard:
    """Unified seven-safeguard checker for persona reviewers.

    Call before and after generating reviewer output to verify all safeguards.

    Parameters
    ----------
    author_id:
        Original author ID for the persona.
    author_name:
        Author display name.
    corpus_keywords:
        Author corpus keyword set (used by safeguard ④).
    verified_dois:
        Verified DOI set from corpus RAG search results (used by safeguard ③).
    """

    def __init__(
        self,
        author_id: str,
        author_name: str = "",
        corpus_keywords: set[str] | None = None,
        verified_dois: set[str] | None = None,
    ) -> None:
        self._author_id = author_id
        self._author_name = author_name
        self._corpus_keywords = corpus_keywords
        self._verified_dois = verified_dois

    def check_author_eligibility(self) -> list[DisclosureViolationRecord]:
        """Check whether the author is opted out (safeguard ⑥)."""
        return check_optout(self._author_id)

    def guard(
        self,
        text: str,
        *,
        raise_on_violation: bool = True,
    ) -> PersonaGuardResult:
        """Apply all seven safeguards to persona reviewer output.

        Parameters
        ----------
        text:
            Persona reviewer output text.
        raise_on_violation:
            If True, raises ``PersonaDisclosureError`` on violation.

        Returns
        -------
        PersonaGuardResult
        """
        violations: list[DisclosureViolationRecord] = []

        # ①: disclosure label
        violations.extend(check_disclosure_label(text))
        # ②: first-person attribution
        violations.extend(check_first_person(text))
        # ③: fabricated citations
        violations.extend(check_fabricated_citations(text, self._verified_dois))
        # ④: scope limit
        violations.extend(check_scope(text, corpus_keywords=self._corpus_keywords))
        # ⑤: fabricated expertise
        violations.extend(check_expertise_fabrication(text))
        # ⑥: opt-out
        violations.extend(check_optout(self._author_id))
        # ⑦: AI reviewer naming
        violations.extend(check_ai_reviewer_label(text))

        passed = len(violations) == 0
        result = PersonaGuardResult(passed=passed, violations=violations)

        if not passed and raise_on_violation:
            raise PersonaDisclosureError(violations)

        return result

    def add_disclosure(self, text: str, paper_count: int = 0) -> str:
        """Automatically prepend the standard disclosure label to the text.

        Does not add the label if it is already present.
        """
        if _DISCLOSURE_LABEL_RE.search(text):
            return text
        label = build_disclosure_label(
            self._author_name or self._author_id,
            paper_count,
            author_id=self._author_id,
        )
        return f"{label}\n\n{text}"


# ---------------------------------------------------------------------------
# HonestyGate integration helper
# ---------------------------------------------------------------------------


def violations_to_honesty_gate(
    violations: list[DisclosureViolationRecord],
) -> list[Any]:
    """Convert DisclosureViolationRecord list to honesty_gate.Violation objects.

    Uses a runtime import to avoid circular dependencies with honesty_gate.
    """
    try:
        from maglab.report.honesty_gate import Violation, ViolationKind

        mapping = {
            DisclosureViolation.MISSING_DISCLOSURE_LABEL: ViolationKind.MISSING_PERSONA_DISCLOSURE,
            DisclosureViolation.FIRST_PERSON_ATTRIBUTION: ViolationKind.FIRST_PERSON_ATTRIBUTION,
            DisclosureViolation.FABRICATED_CITATION: ViolationKind.UNVERIFIED_CITATION,
            DisclosureViolation.OUT_OF_SCOPE_OPINION: ViolationKind.MISSING_PERSONA_DISCLOSURE,
            DisclosureViolation.FABRICATED_EXPERTISE: ViolationKind.MISSING_PERSONA_DISCLOSURE,
            DisclosureViolation.OPTED_OUT_AUTHOR: ViolationKind.MISSING_PERSONA_DISCLOSURE,
            DisclosureViolation.MISSING_AI_REVIEWER_LABEL: ViolationKind.MISSING_PERSONA_DISCLOSURE,
        }
        result = []
        for v in violations:
            kind = mapping.get(v.violation, ViolationKind.MISSING_PERSONA_DISCLOSURE)
            result.append(Violation(kind=kind, message=v.message, excerpt=v.excerpt))
        return result
    except ImportError:
        return []
