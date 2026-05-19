"""Journal LaTeX template loader — minimal working preambles (§16.2, Appendix G).

Supported journal classes:
    sn-jnl             — Nature Portfolio, npj Spintronics
    scifile            — Science, Science Advances
    revtex4-2          — APS (PRL, PRB, PRX, PR Applied, PR Materials)
    revtex4-2-aip      — AIP (APL, JAP, APL Materials)
    IEEEtran           — IEEE Magnetics Letters, Trans. Magnetics
    elsarticle         — Elsevier (JMMM, Acta Materialia)
    advanced-materials — Wiley-VCH (Advanced Materials, Small, Adv. Functional Mater.)
"""

from __future__ import annotations

from pathlib import Path

import yaml

_TEMPLATE_DIR = Path(__file__).parent

# Map public journal names → template subdirectory names.
JOURNAL_ALIASES: dict[str, str] = {
    # Nature Portfolio
    "nature": "sn-jnl",
    "nature-physics": "sn-jnl",
    "nature-materials": "sn-jnl",
    "nature-nanotechnology": "sn-jnl",
    "nature-electronics": "sn-jnl",
    "nature-communications": "sn-jnl",
    "npj-spintronics": "sn-jnl",
    "npj": "sn-jnl",
    "sn-jnl": "sn-jnl",
    # Science/AAAS
    "science": "scifile",
    "science-advances": "scifile",
    "scifile": "scifile",
    # APS
    "prl": "revtex4-2",
    "prb": "revtex4-2",
    "prx": "revtex4-2",
    "pr-applied": "revtex4-2",
    "pr-materials": "revtex4-2",
    "revtex4-2": "revtex4-2",
    # AIP
    "apl": "revtex4-2-aip",
    "jap": "revtex4-2-aip",
    "apl-materials": "revtex4-2-aip",
    "revtex4-2-aip": "revtex4-2-aip",
    # IEEE
    "ieee-magnetics": "IEEEtran",
    "ieee-trans-magnetics": "IEEEtran",
    "IEEEtran": "IEEEtran",
    "ieeetran": "IEEEtran",
    # Elsevier
    "jmmm": "elsarticle",
    "acta-materialia": "elsarticle",
    "elsarticle": "elsarticle",
    # Wiley Advanced Materials
    "advanced-materials": "advanced-materials",
    "advanced-functional-materials": "advanced-materials",
    "advanced-science": "advanced-materials",
    "small": "advanced-materials",
    "wiley": "advanced-materials",
    "word": "advanced-materials",
}


class JournalTemplate:
    """Loaded journal template — preamble text and style profile.

    Parameters
    ----------
    journal:
        Journal name or alias (case-insensitive).
    """

    def __init__(self, journal: str) -> None:
        key = journal.lower()
        subdir = JOURNAL_ALIASES.get(key) or JOURNAL_ALIASES.get(journal)
        if subdir is None:
            raise ValueError(
                f"Unknown journal: {journal!r}. Valid aliases: {sorted(JOURNAL_ALIASES)}"
            )
        self._subdir: str = subdir
        self._dir = _TEMPLATE_DIR / self._subdir

    @property
    def journal_class(self) -> str:
        """LaTeX document class name."""
        return self._subdir

    @property
    def preamble(self) -> str:
        """LaTeX preamble text."""
        path = self._dir / "preamble.tex"
        if not path.is_file():
            raise FileNotFoundError(f"Preamble not found: {path}")
        return path.read_text(encoding="utf-8")

    @property
    def style_profile(self) -> dict:
        """Style profile dictionary (figure dimensions, word limits, etc.)."""
        path = self._dir / "style_profile.yaml"
        if not path.is_file():
            raise FileNotFoundError(f"Style profile not found: {path}")
        with path.open(encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}

    @property
    def figure_width_single_mm(self) -> float:
        """Single-column figure width in millimetres."""
        return float(self.style_profile.get("figure_width_single_mm", 86.0))

    @property
    def figure_width_double_mm(self) -> float:
        """Double-column (full-width) figure width in millimetres."""
        return float(self.style_profile.get("figure_width_double_mm", 178.0))

    @property
    def abstract_word_limit(self) -> int | None:
        """Abstract word limit (None if uncapped)."""
        v = self.style_profile.get("abstract_word_limit")
        return int(v) if v is not None else None

    @property
    def figure_spec(self) -> dict:
        """Figure style constraints (column widths, DPI, colour palette, etc.).

        Returns the parsed ``figure_spec.yaml`` from the template directory.
        Returns an empty dict if the file is absent (backward-compatible).
        """
        path = self._dir / "figure_spec.yaml"
        if not path.is_file():
            return {}
        with path.open(encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}

    @property
    def word_template_path(self) -> Path | None:
        """Path to the Word (.dotx) template for this journal, or ``None``.

        Word templates live under ``templates/word/<name>.dotx``.  Returns
        ``None`` if no Word template is available for this journal class.
        """
        word_dir = _TEMPLATE_DIR / "word"
        # Derive a candidate filename: replace hyphens with underscores.
        candidate = word_dir / f"{self._subdir.replace('-', '_')}.dotx"
        return candidate if candidate.is_file() else None


def load_template(journal: str) -> JournalTemplate:
    """Load and return the ``JournalTemplate`` for the given journal name.

    Parameters
    ----------
    journal:
        Journal name or alias (e.g. ``"prl"``, ``"nature"``, ``"jmmm"``).

    Raises
    ------
    ValueError
        If the journal alias is not recognised.
    FileNotFoundError
        If the template files are missing.
    """
    return JournalTemplate(journal)


def list_journals() -> list[str]:
    """Return a sorted list of all supported journal aliases."""
    return sorted(JOURNAL_ALIASES)
