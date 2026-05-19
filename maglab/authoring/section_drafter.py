"""Section drafter — ordered manuscript section drafting (§16.5).

Drafting order (§16.5): Methods → Results → Discussion → Conclusion →
    Introduction → Abstract → Title.

Every section draft enforces:
    - LLM receives only verified cite-keys (no key invention).
    - Numerical values enter only as ``{{dp:KEY}}`` placeholders.
    - The ``DataVault`` substitutes placeholders with real DataPoint values.
    - The pre-section gate (citation_auditor) fires before finalisation.

The ``compile_draft`` function wraps ``tectonic`` for LaTeX compilation.
``readback_pdf`` provides a vision-model stub for PDF layout review.
"""

from __future__ import annotations

import logging
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from maglab.authoring.bib_manager import BibManager
from maglab.authoring.citation_auditor import VerifiedCitePool
from maglab.authoring.data_vault import AuthoringBlockedError, DataVault

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Section type enum
# ---------------------------------------------------------------------------


class SectionType(StrEnum):
    """Ordered manuscript sections (§16.5)."""

    METHODS = "methods"
    RESULTS = "results"
    DISCUSSION = "discussion"
    CONCLUSION = "conclusion"
    INTRO = "intro"
    ABSTRACT = "abstract"
    TITLE = "title"


#: Canonical drafting order (§16.5)
DRAFTING_ORDER: list[SectionType] = [
    SectionType.METHODS,
    SectionType.RESULTS,
    SectionType.DISCUSSION,
    SectionType.CONCLUSION,
    SectionType.INTRO,
    SectionType.ABSTRACT,
    SectionType.TITLE,
]

# ---------------------------------------------------------------------------
# Draft result
# ---------------------------------------------------------------------------


@dataclass
class DraftResult:
    """Output of a single section draft call.

    Attributes
    ----------
    section:
        Section type.
    tex:
        LaTeX source with placeholders already substituted by the data vault.
    used_cite_keys:
        Cite-keys referenced in the draft.
    remaining_placeholders:
        Placeholder keys whose vault lookup failed.  Always ``[]`` — a
        ``DraftResult`` is only returned when the ``DataVault`` injection
        succeeds (all placeholders resolved).  When injection fails,
        ``SectionDrafter.draft_section`` raises ``AuthoringBlockedError``
        instead of returning a ``DraftResult``.
    human_review_required:
        Always ``True`` — AI drafts, human is the author.
    """

    section: SectionType
    tex: str
    used_cite_keys: list[str] = field(default_factory=list)
    remaining_placeholders: list[str] = field(default_factory=list)
    human_review_required: bool = True


# ---------------------------------------------------------------------------
# Compile result
# ---------------------------------------------------------------------------


@dataclass
class CompileResult:
    """Result of a ``tectonic`` LaTeX compilation."""

    success: bool
    pdf_path: Path | None
    log: str


# ---------------------------------------------------------------------------
# PDF readback feedback
# ---------------------------------------------------------------------------


@dataclass
class ReadbackFeedback:
    """Feedback from a PDF readback (vision model or text heuristic, §16.5)."""

    layout_ok: bool
    issues: list[str] = field(default_factory=list)
    raw_response: str = ""


# ---------------------------------------------------------------------------
# Section system prompts
# ---------------------------------------------------------------------------

#: Per-section LLM system-prompt suffixes
_SECTION_PROMPTS: dict[SectionType, str] = {
    SectionType.METHODS: (
        "Draft the Methods section.  "
        "Describe experimental or simulation procedures precisely. "
        "Use {{dp:KEY}} placeholders for all numerical parameters. "
        "Cite only keys from the provided verified cite-key list."
    ),
    SectionType.RESULTS: (
        "Draft the Results section.  "
        "Present findings objectively.  "
        "All measurements and computed values must use {{dp:KEY}} placeholders. "
        "Do not interpret data — interpretation belongs in Discussion."
    ),
    SectionType.DISCUSSION: (
        "Draft the Discussion section.  "
        "Interpret the results and compare with prior work. "
        "Ground every comparison in {{dp:KEY}} placeholders and verified citations."
    ),
    SectionType.CONCLUSION: (
        "Draft the Conclusion section.  "
        "Summarise key findings concisely (typically ≤200 words). "
        "Reference results via {{dp:KEY}} and verified cite-keys only."
    ),
    SectionType.INTRO: (
        "Draft the Introduction section.  "
        "Motivate the work and place it in context. "
        "Cite only from the verified cite-key list. "
        "Do not invent data or citations."
    ),
    SectionType.ABSTRACT: (
        "Draft the Abstract section.  "
        "Respect the word limit supplied in `abstract_word_limit`. "
        "Summarise background, methods, key result ({{dp:KEY}}), and conclusion."
    ),
    SectionType.TITLE: (
        "Propose a concise manuscript title (≤15 words). "
        "The title must reflect the main scientific finding. "
        "Return only the title string — no LaTeX markup."
    ),
}

# AI usage disclosure appended to every draft (§16.5)
_AI_DISCLOSURE = (
    "\n\n% --- AI usage disclosure (§16.5) ---\n"
    "% This section was drafted with MagLab AI assistance.\n"
    "% HUMAN REVIEW REQUIRED — the named authors bear full responsibility\n"
    "% for all content, data, and citations.\n"
    "% --- end disclosure ---\n"
)

# HUMAN REVIEW REQUIRED header marker
HUMAN_REVIEW_MARKER = "% HUMAN REVIEW REQUIRED\n"


# ---------------------------------------------------------------------------
# Section drafter
# ---------------------------------------------------------------------------


class SectionDrafter:
    """Draft manuscript sections according to the cite-then-write protocol (§16.5).

    Parameters
    ----------
    vault:
        ``DataVault`` with locked ``DataPoint`` values.
    bib_manager:
        ``BibManager`` with the verified ``.bib`` pool.
    llm_fn:
        Callable ``(system_prompt: str, user_prompt: str) → str``.
        Wraps the LLM backend.  In tests, inject a deterministic mock.
    abstract_word_limit:
        Word limit for the abstract (from the journal style profile).
    """

    def __init__(
        self,
        vault: DataVault,
        bib_manager: BibManager,
        llm_fn: Callable[[str, str], str],
        abstract_word_limit: int | None = None,
    ) -> None:
        self._vault = vault
        self._bib = bib_manager
        self._llm = llm_fn
        self._abstract_word_limit = abstract_word_limit

    def draft_section(
        self,
        section_type: SectionType | str,
        context: str,
        verified_cite_pool: VerifiedCitePool | None = None,
        *,
        extra_system: str = "",
    ) -> DraftResult:
        """Draft a single manuscript section.

        The LLM receives:
        - The section-specific system prompt.
        - The verified cite-key list (the only keys it may use).
        - The context/results summary provided by the researcher.

        All numerical values in the draft must be expressed as ``{{dp:KEY}}``
        placeholders; the vault then substitutes them.

        Parameters
        ----------
        section_type:
            One of the ``SectionType`` values.
        context:
            Researcher-provided context, results summary, and instructions.
        verified_cite_pool:
            Pre-flight citation pool (§16.4).  ``None`` means no citations
            are allowed in this section.
        extra_system:
            Additional system prompt text (e.g. journal-specific constraints).

        Returns
        -------
        ``DraftResult`` with vault-substituted LaTeX source.
        """
        if isinstance(section_type, str):
            section_type = SectionType(section_type)

        # Build system prompt
        cite_key_list = verified_cite_pool.cite_keys if verified_cite_pool else []
        system_prompt = self._build_system_prompt(section_type, cite_key_list, extra_system)

        # Build user prompt
        user_prompt = self._build_user_prompt(section_type, context)

        # Call LLM
        raw_tex = self._llm(system_prompt, user_prompt)

        # Add disclosure
        raw_tex_with_disclosure = HUMAN_REVIEW_MARKER + raw_tex + _AI_DISCLOSURE

        # Extract used cite-keys from raw draft (before vault injection)
        used_keys = _extract_cite_keys_from_tex(raw_tex_with_disclosure)

        # Inject DataPoint values
        try:
            final_tex = self._vault.inject_into_draft(
                raw_tex_with_disclosure, section=section_type.value
            )
        except AuthoringBlockedError:
            raise

        # Abstract word limit check — count only the raw LLM output before the
        # HUMAN_REVIEW_MARKER and _AI_DISCLOSURE boilerplate are prepended/appended,
        # so that the ~40-word footer does not trigger spurious over-limit warnings.
        if section_type == SectionType.ABSTRACT and self._abstract_word_limit is not None:
            word_count = len(raw_tex.split())
            if word_count > self._abstract_word_limit:
                log.warning(
                    "Abstract word count %d exceeds limit %d.",
                    word_count,
                    self._abstract_word_limit,
                )

        return DraftResult(
            section=section_type,
            tex=final_tex,
            used_cite_keys=used_keys,
            remaining_placeholders=[],
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_system_prompt(
        self,
        section_type: SectionType,
        cite_keys: list[str],
        extra_system: str,
    ) -> str:
        """Build the section-specific LLM system prompt."""
        base = (
            "You are MagLab — an academic writing assistant for "
            "magnetism and spintronics research.\n\n"
            "INVARIANT RULES:\n"
            "1. Do NOT invent numbers.  All values must be expressed as "
            "{{dp:KEY}} placeholders.\n"
            "2. Do NOT invent citations.  Only cite keys from the verified "
            "list below.\n"
            "3. Do NOT use first-person attribution (no 'I calculated', "
            "'I found', etc.).\n"
            "4. Every output carries HUMAN REVIEW REQUIRED — the researcher "
            "bears full responsibility.\n\n"
        )
        cite_block = (
            f"Verified cite-keys (use ONLY these):\n  {', '.join(cite_keys)}\n\n"
            if cite_keys
            else "No citations allowed in this section.\n\n"
        )
        section_instruction = _SECTION_PROMPTS.get(section_type, "Draft this section.")
        return (
            base
            + cite_block
            + section_instruction
            + ("\n\n" + extra_system if extra_system else "")
        )

    def _build_user_prompt(self, section_type: SectionType, context: str) -> str:
        """Build the section-specific LLM user prompt."""
        header = f"[Section: {section_type.value.upper()}]\n\n"
        if section_type == SectionType.ABSTRACT and self._abstract_word_limit:
            header += f"Word limit: {self._abstract_word_limit} words.\n\n"
        return header + context


# ---------------------------------------------------------------------------
# LaTeX cite-key extraction helper
# ---------------------------------------------------------------------------

_CITE_RE = re.compile(r"\\cite[pt]?\{([^}]+)\}")


def _extract_cite_keys_from_tex(tex: str) -> list[str]:
    """Extract all BibTeX cite-keys from a LaTeX string."""
    keys: list[str] = []
    for m in _CITE_RE.finditer(tex):
        for raw_key in m.group(1).split(","):
            k = raw_key.strip()
            if k:
                keys.append(k)
    return list(dict.fromkeys(keys))  # deduplicate preserving order


# ---------------------------------------------------------------------------
# tectonic compilation
# ---------------------------------------------------------------------------


def compile_draft(
    tex_dir: Path,
    *,
    main_tex: str = "main.tex",
    tectonic_bin: str = "tectonic",
) -> CompileResult:
    """Compile a LaTeX draft with ``tectonic``.

    Parameters
    ----------
    tex_dir:
        Directory containing the ``.tex`` source files.
    main_tex:
        Entry-point LaTeX file (relative to *tex_dir*).
    tectonic_bin:
        Path/name of the ``tectonic`` binary.

    Returns
    -------
    ``CompileResult`` with ``success``, ``pdf_path``, and ``log``.
    """
    tex_path = tex_dir / main_tex
    if not tex_path.is_file():
        return CompileResult(
            success=False,
            pdf_path=None,
            log=f"Entry-point file not found: {tex_path}",
        )

    cmd = [tectonic_bin, str(tex_path)]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(tex_dir),
            timeout=120,
        )
        log_output = proc.stdout + proc.stderr
        if proc.returncode == 0:
            pdf_path = tex_path.with_suffix(".pdf")
            return CompileResult(
                success=pdf_path.is_file(),
                pdf_path=pdf_path if pdf_path.is_file() else None,
                log=log_output,
            )
        return CompileResult(success=False, pdf_path=None, log=log_output)
    except FileNotFoundError:
        return CompileResult(
            success=False,
            pdf_path=None,
            log=f"tectonic binary not found: {tectonic_bin!r}.  Install tectonic first.",
        )
    except subprocess.TimeoutExpired:
        return CompileResult(
            success=False,
            pdf_path=None,
            log="tectonic compilation timed out after 120 seconds.",
        )


# ---------------------------------------------------------------------------
# PDF readback (vision model stub)
# ---------------------------------------------------------------------------


def readback_pdf(
    pdf_path: Path,
    *,
    vision_fn: Callable[[Path], str] | None = None,
) -> ReadbackFeedback:
    """Read back a compiled PDF with a vision model or heuristic check (§16.5).

    Parameters
    ----------
    pdf_path:
        Path to the compiled PDF.
    vision_fn:
        Callable ``(pdf_path) → str`` — a vision model response.
        If ``None``, a file-existence heuristic is used.

    Returns
    -------
    ``ReadbackFeedback`` with layout issues (if any).
    """
    if not pdf_path.is_file():
        return ReadbackFeedback(
            layout_ok=False,
            issues=["PDF file not found — compilation may have failed."],
        )

    if vision_fn is None:
        # Heuristic: a non-zero PDF file is assumed layout-OK.
        size = pdf_path.stat().st_size
        if size < 100:
            return ReadbackFeedback(
                layout_ok=False,
                issues=["PDF is suspiciously small (<100 bytes)."],
            )
        return ReadbackFeedback(layout_ok=True)

    raw = vision_fn(pdf_path)
    issues: list[str] = []
    # Parse common layout problems from vision-model output
    for keyword in ("overflow", "missing figure", "broken reference", "undefined", "error"):
        if keyword.lower() in raw.lower():
            issues.append(f"Vision model flagged: {keyword}")

    return ReadbackFeedback(layout_ok=len(issues) == 0, issues=issues, raw_response=raw)
