"""MagLab authoring suite — academic writing and communication (§16).

Sub-modules:
    templates         — LaTeX preambles and style profiles (§16.2, Appendix G).
    data_vault        — DataPoint-sourced numerical claims (§16.4).
    bib_manager       — DOI-verified BibTeX management (§16.4).
    citation_auditor  — Existence + semantic 4-class citation verification (§16.4, §16.7).
    section_drafter   — Ordered section drafting with vault injection (§16.5).
    loop_c            — Loop C Ralph loop: draft → critic → revise → compile (§16.5).
    comms/            — 6 communication agents (§16.3).
    present/          — Slide and poster drafters (§16.6).

Research integrity invariants (§3.3, §16.1):
    - Every quantitative claim originates from a locked DataPoint.
    - Every citation is DOI-verified before the LLM sees the cite-key.
    - All outputs carry HUMAN REVIEW REQUIRED.
    - No auto-submission pathway exists.
"""

from __future__ import annotations

from maglab.authoring.bib_manager import BibManager, UnverifiedCitationError
from maglab.authoring.citation_auditor import (
    PreSectionFinalizeHook,
    SemanticLabel,
    VerifiedCitePool,
    audit_existence,
    audit_semantics,
    preflight_citations,
)
from maglab.authoring.data_vault import AuthoringBlockedError, DataVault, make_vault
from maglab.authoring.loop_c import LoopCResult, run_loop_c
from maglab.authoring.section_drafter import (
    DRAFTING_ORDER,
    CompileResult,
    DraftResult,
    ReadbackFeedback,
    SectionDrafter,
    SectionType,
    compile_draft,
    readback_pdf,
)
from maglab.authoring.templates import JournalTemplate, list_journals, load_template

__all__ = [
    # templates
    "JournalTemplate",
    "load_template",
    "list_journals",
    # data vault
    "DataVault",
    "make_vault",
    "AuthoringBlockedError",
    # bib manager
    "BibManager",
    "UnverifiedCitationError",
    # citation auditor
    "preflight_citations",
    "audit_existence",
    "audit_semantics",
    "VerifiedCitePool",
    "SemanticLabel",
    "PreSectionFinalizeHook",
    # section drafter
    "SectionDrafter",
    "SectionType",
    "DRAFTING_ORDER",
    "DraftResult",
    "CompileResult",
    "ReadbackFeedback",
    "compile_draft",
    "readback_pdf",
    # loop C
    "run_loop_c",
    "LoopCResult",
]
