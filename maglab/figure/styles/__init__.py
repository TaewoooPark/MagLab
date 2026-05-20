"""Journal style profile loader (§12.3-⑤).

``StyleProfile`` parses YAML files and provides matplotlib ``rcParams``
and figure dimensions.

Appendix G canonical dimensions:
- Nature     : 89 / 183 mm
- APS        : 86 / 178 mm
- IEEE       : 88.9 / 182 mm
- Elsevier   : 90 / 190 mm
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_STYLES_DIR = Path(__file__).parent

# mm → inch conversion factor
_MM_TO_INCH = 1 / 25.4


class StyleProfile:
    """Journal style profile.

    Parameters
    ----------
    journal:
        Journal key (e.g. ``"nature"``, ``"aps"``, ``"ieee"``, ``"elsevier"``).
    data:
        Parsed YAML dictionary.
    """

    def __init__(self, journal: str, data: dict[str, Any]) -> None:
        self.journal = journal
        self._data = data

    # ------------------------------------------------------------------
    # Dimension accessors
    # ------------------------------------------------------------------

    def column_width_mm(self, column: str = "single") -> float:
        """Return column width in mm.

        Parameters
        ----------
        column:
            ``"single"`` or ``"double"``.
        """
        return float(self._data["column_width_mm"][column])

    def column_width_inch(self, column: str = "single") -> float:
        """Return column width in inches."""
        return self.column_width_mm(column) * _MM_TO_INCH

    def figure_size(
        self,
        column: str = "single",
        aspect_ratio: float = 0.75,
    ) -> tuple[float, float]:
        """Return figure size (width_inch, height_inch) for matplotlib.

        Parameters
        ----------
        column:
            ``"single"`` or ``"double"``.
        aspect_ratio:
            height / width ratio (default 0.75 = 3:4).
        """
        w = self.column_width_inch(column)
        return (w, w * aspect_ratio)

    # ------------------------------------------------------------------
    # Font accessors
    # ------------------------------------------------------------------

    @property
    def font_family(self) -> str:
        """Font family string."""
        return str(self._data.get("font_family", "sans-serif"))

    def font_size(self, key: str = "label") -> float:
        """Font size in pt for the specified use."""
        return float(self._data["font_size_pt"].get(key, 8))

    # ------------------------------------------------------------------
    # Line width accessors
    # ------------------------------------------------------------------

    def line_width(self, key: str = "data") -> float:
        """Line width in pt for the specified use."""
        return float(self._data["line_width_pt"].get(key, 1.0))

    # ------------------------------------------------------------------
    # Palette
    # ------------------------------------------------------------------

    @property
    def palette(self) -> list[str]:
        """Colorblind-safe palette hex color list."""
        return list(self._data.get("palette", []))

    # ------------------------------------------------------------------
    # DPI
    # ------------------------------------------------------------------

    @property
    def dpi(self) -> int:
        """Raster export DPI."""
        return int(self._data.get("dpi", 300))

    # ------------------------------------------------------------------
    # rcParams construction
    # ------------------------------------------------------------------

    def rcparams(self, column: str = "single") -> dict[str, Any]:
        """Build a matplotlib ``rcParams`` dictionary.

        Combines values defined in the journal style profile with figure size.

        Parameters
        ----------
        column:
            ``"single"`` or ``"double"``.
        """
        w, h = self.figure_size(column)
        base: dict[str, Any] = {
            "figure.figsize": [w, h],
            "figure.dpi": self.dpi,
            "font.family": self.font_family,
            "font.size": self.font_size("label"),
            "axes.labelsize": self.font_size("label"),
            "xtick.labelsize": self.font_size("tick"),
            "ytick.labelsize": self.font_size("tick"),
            "axes.titlesize": self.font_size("title"),
            "lines.linewidth": self.line_width("data"),
            "axes.prop_cycle": _make_prop_cycle(self.palette),
            # Font embedding (§12.3-⑥)
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "svg.fonttype": "none",
        }
        # Apply YAML rcparams overrides
        base.update(self._data.get("rcparams", {}))
        return base


def _make_prop_cycle(palette: list[str]) -> Any:
    """Create a matplotlib cycler object."""
    from matplotlib.pyplot import cycler  # type: ignore[attr-defined]

    return cycler("color", palette)


_JOURNAL_ALIASES: dict[str, str] = {
    "physical-review-letters": "aps",
    "phys-rev-lett": "aps",
    "prl": "aps",
    "physical-review-b": "aps",
    "phys-rev-b": "aps",
    "prb": "aps",
    "physical-review-x": "aps",
    "prx": "aps",
    "nature-communications": "nature",
    "nat-commun": "nature",
    "npj": "nature",
    "nature-family": "nature",
    "jmmm": "elsevier",
    "journal-of-magnetism-and-magnetic-materials": "elsevier",
    "ieee-magnetics": "ieee",
    "ieee-transactions-on-magnetics": "ieee",
}


def normalize_journal_key(journal: str) -> str:
    """Normalize common journal aliases to installed figure style keys."""
    key = journal.strip().lower().replace("_", "-").replace(" ", "-")
    return _JOURNAL_ALIASES.get(key, key)


def load_style(journal: str) -> StyleProfile:
    """Load a ``StyleProfile`` by journal key.

    Parameters
    ----------
    journal:
        Journal key — ``"nature"``, ``"aps"``, ``"ieee"``, ``"elsevier"``.

    Returns
    -------
    StyleProfile

    Raises
    ------
    FileNotFoundError
        When no YAML file exists for the given journal.
    ValueError
        When an unknown journal key is given.
    """
    journal = normalize_journal_key(journal)
    yaml_path = _STYLES_DIR / f"{journal}.yaml"
    if not yaml_path.exists():
        raise FileNotFoundError(f"Style YAML not found for journal '{journal}': {yaml_path}")
    with yaml_path.open("r", encoding="utf-8") as fh:
        data: dict[str, Any] = yaml.safe_load(fh)
    return StyleProfile(journal=journal, data=data)


def available_journals() -> list[str]:
    """Return the list of available journal keys."""
    return [p.stem for p in sorted(_STYLES_DIR.glob("*.yaml"))]


__all__ = ["StyleProfile", "available_journals", "load_style", "normalize_journal_key"]
