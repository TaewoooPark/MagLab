"""Presentation template catalog for MagLab authoring outputs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

_TEMPLATES_DIR = Path(__file__).parent / "templates"


@dataclass(frozen=True)
class PresentationTemplate:
    """One installed slide or poster template profile."""

    name: str
    kind: str
    formats: tuple[str, ...]
    use_case: str
    command: str
    source_paths: tuple[Path, ...]
    constraints: tuple[str, ...]
    reference_urls: tuple[str, ...]
    notes: str


def list_presentation_templates(kind: str = "all") -> tuple[PresentationTemplate, ...]:
    """Return installed presentation template profiles.

    Parameters
    ----------
    kind:
        ``all``, ``slides``, or ``poster``.
    """
    normalized = kind.strip().lower()
    if normalized not in {"all", "slides", "poster"}:
        raise ValueError("kind must be one of: all, slides, poster")
    entries = _catalog()
    if normalized == "all":
        return entries
    return tuple(entry for entry in entries if entry.kind == normalized)


def get_presentation_template(name: str) -> PresentationTemplate:
    """Resolve a presentation template profile by name."""
    normalized = name.strip().lower()
    aliases = {
        "aps": "aps-12min",
        "aps-march": "aps-12min",
        "march-meeting": "aps-12min",
        "talk": "aps-12min",
        "slides": "aps-12min",
        "seminar-talk": "seminar",
        "poster": "a0-poster",
        "a0": "a0-poster",
        "beamerposter": "beamerposter-a0",
    }
    target = aliases.get(normalized, normalized)
    for entry in _catalog():
        if entry.name == target:
            return entry
    available = ", ".join(entry.name for entry in _catalog())
    raise ValueError(f"Unknown presentation template {name!r}. Available: {available}")


def template_guidance(name: str) -> str:
    """Return prompt guidance for a slide/poster template profile."""
    entry = get_presentation_template(name)
    lines = [
        f"Template profile: {entry.name}",
        f"Use case: {entry.use_case}",
        "Constraints:",
    ]
    lines.extend(f"- {item}" for item in entry.constraints)
    lines.append(f"Notes: {entry.notes}")
    return "\n".join(lines)


def _catalog() -> tuple[PresentationTemplate, ...]:
    return (
        PresentationTemplate(
            name="aps-12min",
            kind="slides",
            formats=("beamer", "pptx", "marp"),
            use_case=(
                "APS March Meeting / April Meeting contributed oral slot: 10 min talk + 2 min Q&A."
            ),
            command=(
                'maglab present slides "<verified results>" '
                "--template aps-12min --format beamer --n-slides 10"
            ),
            source_paths=(
                _TEMPLATES_DIR / "beamer" / "template.tex",
                _TEMPLATES_DIR / "marp" / "template.md",
                _TEMPLATES_DIR / "pptx" / "README.txt",
            ),
            constraints=(
                "Timebox: 10 minutes presentation, 2 minutes questions.",
                "Recommended deck: 8-10 content slides plus title/backup.",
                "Default screen format: widescreen 16:9 for beamer, Marp, and pptx outputs.",
            ),
            reference_urls=(
                "https://www.aps.org/about/governance/policies-procedures/contributed-abstract-guidelines",
                "https://support.microsoft.com/en-gb/office/change-the-size-of-your-powerpoint-slides-040a811c-be43-40b9-8d04-0de5ed79987e",
                "https://marpit.marp.app/directives",
            ),
            notes="Compact physics story: motivation, method, two to three verified results, takeaway.",
        ),
        PresentationTemplate(
            name="seminar",
            kind="slides",
            formats=("beamer", "pptx", "marp"),
            use_case="Longer group seminar or invited talk.",
            command=(
                'maglab present slides "<verified results plus context>" '
                "--template seminar --format beamer --n-slides 24"
            ),
            source_paths=(
                _TEMPLATES_DIR / "beamer" / "template.tex",
                _TEMPLATES_DIR / "marp" / "template.md",
                _TEMPLATES_DIR / "pptx" / "README.txt",
            ),
            constraints=(
                "Venue-specific timing is not standardized; set --n-slides to match the invitation.",
                "Default screen format: widescreen 16:9 for beamer, Marp, and pptx outputs.",
                "Use more methods, controls, limitations, and backup slides than aps-12min.",
            ),
            reference_urls=(
                "https://support.microsoft.com/en-gb/office/change-the-size-of-your-powerpoint-slides-040a811c-be43-40b9-8d04-0de5ed79987e",
                "https://marp.app/",
            ),
            notes="Adds background, methods detail, controls, limitations, and backup slides.",
        ),
        PresentationTemplate(
            name="internal-update",
            kind="slides",
            formats=("beamer", "pptx", "marp"),
            use_case="Lab meeting or collaborator progress update.",
            command=(
                'maglab present slides "<latest verified results and blockers>" '
                "--template internal-update --format marp --n-slides 8"
            ),
            source_paths=(
                _TEMPLATES_DIR / "marp" / "template.md",
                _TEMPLATES_DIR / "pptx" / "README.txt",
            ),
            constraints=(
                "MagLab profile, not a venue rule: decision-first progress update.",
                "Default screen format: widescreen 16:9 for Marp and pptx outputs.",
                "Include provenance IDs, blockers, and next experiment decisions.",
            ),
            reference_urls=(
                "https://support.microsoft.com/en-gb/office/change-the-size-of-your-powerpoint-slides-040a811c-be43-40b9-8d04-0de5ed79987e",
                "https://marp.app/",
            ),
            notes="Emphasizes decisions, next experiments, open risks, and provenance IDs.",
        ),
        PresentationTemplate(
            name="aps-march-poster",
            kind="poster",
            formats=("svg", "pdf"),
            use_case="APS March/April printed poster board profile.",
            command=(
                'maglab present poster "<verified results and figure refs>" '
                '--template aps-march-poster --format svg --title "Poster title"'
            ),
            source_paths=(_TEMPLATES_DIR / "svg" / "aps_march_template.svg",),
            constraints=(
                "Must fit the provided board; APS notes 8 ft wide x 4 ft high is common for March/April.",
                "No audiovisuals in APS March/April poster sessions; use printed visuals.",
                "Put the poster up at least 30 minutes before the session and stay for the session.",
            ),
            reference_urls=("https://www.aps.org/meetings/policies/posters.cfm",),
            notes="Landscape 96 x 48 in SVG/PDF layout for APS March/April poster boards.",
        ),
        PresentationTemplate(
            name="a0-poster",
            kind="poster",
            formats=("svg", "pdf"),
            use_case="A0 conference poster with vector layout.",
            command=(
                'maglab present poster "<verified results and figure refs>" '
                '--size A0 --format svg --title "Poster title"'
            ),
            source_paths=(_TEMPLATES_DIR / "svg" / "template.svg",),
            constraints=(
                "ISO A0 portrait canvas: 841 x 1189 mm.",
                "Use when the venue asks for A0, not as a substitute for APS March board sizing.",
            ),
            reference_urls=("https://www.ctan.org/pkg/a0poster",),
            notes="Single-panel SVG/PDF poster with placeholders for verified MagLab figures.",
        ),
        PresentationTemplate(
            name="beamerposter-a0",
            kind="poster",
            formats=("beamerposter", "tex"),
            use_case="A0 LaTeX poster for beamerposter-based conference workflows.",
            command=(
                'maglab present poster "<verified results and figure refs>" '
                '--size A0 --format beamerposter --title "Poster title"'
            ),
            source_paths=(_TEMPLATES_DIR / "beamerposter" / "template.tex",),
            constraints=(
                "Uses beamerposter on an a0poster-backed A-series poster canvas.",
                "Supports scalable fonts, A-series sizes, and portrait or landscape orientation.",
            ),
            reference_urls=(
                "https://ctan.org/pkg/beamerposter?lang=en",
                "https://www.ctan.org/pkg/a0poster",
            ),
            notes="Writes poster.tex; compile with a TeX toolchain after replacing [FILL] fields.",
        ),
    )
