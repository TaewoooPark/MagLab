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

from typing import TYPE_CHECKING

# Lazy public API (PEP 562). Importing this package must NOT eagerly pull the
# heavy authoring stack (bibtexparser, pylatex, python-pptx, python-docx). That
# eager chain meant even a deterministic, dependency-free command like
# `maglab present templates` crashed with a ModuleNotFoundError when the
# optional [authoring] extra was absent. Each public name is resolved to its
# submodule on first access instead.
if TYPE_CHECKING:
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

_LAZY_IMPORTS: dict[str, str] = {
    "BibManager": "bib_manager",
    "UnverifiedCitationError": "bib_manager",
    "PreSectionFinalizeHook": "citation_auditor",
    "SemanticLabel": "citation_auditor",
    "VerifiedCitePool": "citation_auditor",
    "audit_existence": "citation_auditor",
    "audit_semantics": "citation_auditor",
    "preflight_citations": "citation_auditor",
    "DataVault": "data_vault",
    "make_vault": "data_vault",
    "AuthoringBlockedError": "data_vault",
    "LoopCResult": "loop_c",
    "run_loop_c": "loop_c",
    "DRAFTING_ORDER": "section_drafter",
    "CompileResult": "section_drafter",
    "DraftResult": "section_drafter",
    "ReadbackFeedback": "section_drafter",
    "SectionDrafter": "section_drafter",
    "SectionType": "section_drafter",
    "compile_draft": "section_drafter",
    "readback_pdf": "section_drafter",
    "JournalTemplate": "templates",
    "list_journals": "templates",
    "load_template": "templates",
}


def __getattr__(name: str):  # noqa: N807 - PEP 562 module-level hook
    submodule = _LAZY_IMPORTS.get(name)
    if submodule is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    module = importlib.import_module(f"{__name__}.{submodule}")
    return getattr(module, name)


def __dir__() -> list[str]:
    return sorted(__all__)


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
