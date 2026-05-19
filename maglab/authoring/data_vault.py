"""Data vault — every quantitative claim sourced from locked provenance DataPoints (§16.4).

The data vault acts as the single authoritative source for all numerical values
in authored text.  Draft sections reference values via ``{{dp:KEY}}``
placeholders; this module resolves them to the actual value string **only** when
a matching ``DataPoint`` exists in the vault registry.

Research integrity rule (§3.3, §16.4):
    - DataPoint-absent placeholders are **never** resolved — the pipeline is blocked.
    - The LLM must not invent numbers.  Numbers enter text only through this
      module after being sourced from a ``DataPoint``.
"""

from __future__ import annotations

import re
from typing import Any

from maglab.provenance.datapoint import DataPoint

# ---------------------------------------------------------------------------
# Sentinel error
# ---------------------------------------------------------------------------


class AuthoringBlockedError(Exception):
    """Raised when the data vault blocks authoring (missing DataPoint, §5.15).

    Halts the authoring pipeline; the researcher must supply a DataPoint for
    every quantitative claim before proceeding.
    """


# ---------------------------------------------------------------------------
# Placeholder pattern
# ---------------------------------------------------------------------------

#: Regex for data-vault placeholders: ``{{dp:KEY}}``
_PLACEHOLDER_RE = re.compile(r"\{\{dp:([A-Za-z0-9_.-]+)\}\}")


# ---------------------------------------------------------------------------
# DataVault
# ---------------------------------------------------------------------------


class DataVault:
    """Registry of locked ``DataPoint`` instances available to the authoring pipeline.

    Parameters
    ----------
    datapoints:
        Initial mapping of vault key → ``DataPoint``.  Keys are arbitrary
        identifiers chosen by the researcher (e.g. ``"AHE_rho_xy"``).
    """

    def __init__(self, datapoints: dict[str, DataPoint] | None = None) -> None:
        self._vault: dict[str, DataPoint] = dict(datapoints or {})

    # ------------------------------------------------------------------
    # Registry management
    # ------------------------------------------------------------------

    def register(self, key: str, dp: DataPoint) -> None:
        """Add a ``DataPoint`` to the vault under ``key``.

        Parameters
        ----------
        key:
            Vault key (used in ``{{dp:KEY}}`` placeholders).
        dp:
            Locked ``DataPoint`` instance from ``maglab.provenance``.
        """
        self._vault[key] = dp

    def get(self, key: str) -> DataPoint | None:
        """Return the ``DataPoint`` for ``key``, or ``None`` if absent."""
        return self._vault.get(key)

    def keys(self) -> list[str]:
        """Return all registered vault keys."""
        return list(self._vault.keys())

    def ids(self) -> set[str]:
        """Return the set of DataPoint UUIDs in the vault."""
        return {dp.id for dp in self._vault.values()}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_locked_value(self, key: str) -> DataPoint | None:
        """Return the locked ``DataPoint`` for ``key`` (§16.4).

        Parameters
        ----------
        key:
            Vault key registered via :meth:`register`.

        Returns
        -------
        ``DataPoint`` if found, ``None`` otherwise.
        """
        return self._vault.get(key)

    def inject_into_draft(self, draft_tex: str, *, section: str = "") -> str:
        """Replace ``{{dp:KEY}}`` placeholders in a LaTeX draft with actual values.

        For each placeholder ``{{dp:KEY}}``:
        - If the key is in the vault: replaces with the value string and appends
          a LaTeX comment tagging the provenance ID.
        - If the key is **absent**: raises :exc:`AuthoringBlockedError`.

        Parameters
        ----------
        draft_tex:
            LaTeX source containing ``{{dp:KEY}}`` placeholders.
        section:
            Human-readable section name for error messages.

        Returns
        -------
        LaTeX source with placeholders resolved.

        Raises
        ------
        AuthoringBlockedError
            If any placeholder key is not in the vault.
        """
        missing: list[str] = []
        result = draft_tex

        def _replace(m: re.Match[str]) -> str:
            key = m.group(1)
            dp = self._vault.get(key)
            if dp is None:
                missing.append(key)
                return m.group(0)  # leave placeholder unchanged for error reporting
            value_str = self._format_value(dp)
            provenance_comment = f"% [prov:{dp.id}]"
            return f"{value_str} {provenance_comment}"

        result = _PLACEHOLDER_RE.sub(_replace, result)

        if missing:
            sec_hint = f" in section '{section}'" if section else ""
            raise AuthoringBlockedError(
                f"Data vault blocked authoring{sec_hint}: "
                f"no DataPoint found for placeholder(s): {missing}.  "
                f"Register a DataPoint before authoring."
            )
        return result

    def find_placeholders(self, draft_tex: str) -> list[str]:
        """Return all ``{{dp:KEY}}`` keys found in *draft_tex* (for pre-flight checks)."""
        return _PLACEHOLDER_RE.findall(draft_tex)

    def validate_draft(self, draft_tex: str, *, section: str = "") -> list[str]:
        """Return a list of missing vault keys without raising an exception.

        Useful for reporting all missing keys at once before blocking.
        """
        missing: list[str] = []
        for key in self.find_placeholders(draft_tex):
            if key not in self._vault:
                missing.append(key)
        return missing

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _format_value(dp: DataPoint) -> str:
        """Format a DataPoint's value as a string for LaTeX insertion."""
        if isinstance(dp.value, list):
            # Array — format as comma-separated list with SI unit annotation
            values = ", ".join(f"{v:.6g}" for v in dp.value)
            return rf"({values})\,\si{{{dp.units}}}"
        val = dp.scalar()
        if dp.uncertainty is not None:
            return rf"{val:.6g}\,\pm\,{dp.uncertainty:.6g}\,\si{{{dp.units}}}"
        return rf"{val:.6g}\,\si{{{dp.units}}}"


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------


def make_vault(entries: dict[str, Any] | None = None) -> DataVault:
    """Create a ``DataVault`` from a mapping of key → ``DataPoint`` dicts.

    Parameters
    ----------
    entries:
        Mapping of vault key → ``DataPoint`` or dict serialisation of one.

    Returns
    -------
    Populated ``DataVault``.
    """
    vault = DataVault()
    for k, v in (entries or {}).items():
        if isinstance(v, DataPoint):
            vault.register(k, v)
        elif isinstance(v, dict):
            vault.register(k, DataPoint.from_dict(v))
        else:
            raise TypeError(f"Expected DataPoint or dict for key {k!r}, got {type(v)}")
    return vault
