"""Installed manual discovery for MagLab's bilingual CLI help surface."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ManualEntry:
    """One installed manual page."""

    lang: str
    topic: str
    title: str
    path: Path


def _manual_roots() -> tuple[Path, ...]:
    """Candidate locations for bundled manuals in source trees and wheels."""
    package_root = Path(__file__).resolve().parents[1]
    return (
        Path.cwd() / "docs" / "manuals",
        package_root / "docs" / "manuals",
    )


def manuals_root() -> Path:
    """Return the first installed manuals root."""
    for root in _manual_roots():
        if root.is_dir():
            return root
    raise FileNotFoundError("MagLab manuals are not installed with this package.")


def available_languages() -> tuple[str, ...]:
    """Return language codes with installed manuals."""
    root = manuals_root()
    langs = sorted(path.name for path in root.iterdir() if path.is_dir())
    return tuple(langs)


def _read_title(path: Path) -> str:
    """Return the first Markdown H1 title, falling back to the file stem."""
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("# "):
                return line.removeprefix("# ").strip()
    except OSError:
        pass
    return path.stem.replace("-", " ").title()


def list_manuals(lang: str = "en") -> list[ManualEntry]:
    """List installed manuals for one language."""
    root = manuals_root() / lang
    if not root.is_dir():
        raise FileNotFoundError(
            f"Manual language {lang!r} is not installed. Available: {', '.join(available_languages())}"
        )
    entries = [
        ManualEntry(lang=lang, topic=path.stem, title=_read_title(path), path=path)
        for path in sorted(root.glob("*.md"), key=lambda p: (p.stem != "index", p.stem))
    ]
    return entries


def resolve_manual(topic: str, lang: str = "en") -> ManualEntry:
    """Resolve a manual topic by exact stem or simple normalized alias."""
    normalized = topic.strip().lower().replace("_", "-")
    aliases = {
        "analysis": "analysis-fitting",
        "fit": "analysis-fitting",
        "fitting": "analysis-fitting",
        "authoring": "authoring-comms",
        "comms": "authoring-comms",
        "writing": "authoring-comms",
        "fig": "figures",
        "figure": "figures",
        "instrument": "instruments",
        "instr": "instruments",
        "lab": "lab-planning",
        "planning": "lab-planning",
        "materials": "materials-physics",
        "physics": "materials-physics",
        "review": "review-explain",
        "explain": "review-explain",
        "sim": "simulation",
    }
    target = aliases.get(normalized, normalized)
    for entry in list_manuals(lang):
        if entry.topic == target:
            return entry
    topics = ", ".join(entry.topic for entry in list_manuals(lang))
    raise FileNotFoundError(f"Manual topic {topic!r} not found for {lang}. Available: {topics}")
