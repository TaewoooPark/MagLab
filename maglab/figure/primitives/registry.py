"""Primitive registry — plugin package structure (§12.4-⑤).

``PrimitiveRegistry`` implementation:
- Auto-discovers and loads primitive packages from the ``catalog/`` directory.
- At startup, loads only the index (name, category, tags, description) (3-stage progressive
  loading, analogous to §5.6).
- Loads full body on demand.
- Natural language keyword search.

Primitive package structure:
  ``catalog/<name>/``
  ├── ``PRIMITIVE.md``  — frontmatter (name, category, tags, description)
  └── ``primitive.py``  — Primitive protocol implementation class (returned by ``get_primitive()``)
"""

from __future__ import annotations

import importlib.util
import logging
import sys
from pathlib import Path
from typing import Any

from maglab.figure.primitives.spec import Primitive, PrimitiveRegistry

log = logging.getLogger(__name__)

# Catalog directory (relative to this file)
_CATALOG_DIR = Path(__file__).parent / "catalog"


# ---------------------------------------------------------------------------
# PRIMITIVE.md parser
# ---------------------------------------------------------------------------


def _parse_primitive_md(md_path: Path) -> dict[str, Any]:
    """Parse frontmatter from PRIMITIVE.md.

    YAML frontmatter format:
    ::

        ---
        name: hall-bar
        category: device geometry
        tags: [Hall, bar, measurement]
        description: Hall bar device geometry primitive.
        ---

    Parameters
    ----------
    md_path:
        Path to the PRIMITIVE.md file.

    Returns
    -------
    dict[str, Any]
        Parsed metadata.
    """
    text = md_path.read_text(encoding="utf-8")
    # Extract frontmatter
    parts = text.split("---", 2)
    if len(parts) < 3:
        # No frontmatter — extract name from directory name
        return {"name": md_path.parent.name, "category": "", "tags": [], "description": ""}

    import re

    fm_text = parts[1].strip()
    result: dict[str, Any] = {}

    for line in fm_text.splitlines():
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()

        # List parsing [a, b, c] — ``\w`` is Unicode-aware and already covers
        # any non-ASCII word characters.
        if val.startswith("[") and val.endswith("]"):
            items = re.findall(r"[\w·/\-]+", val[1:-1])
            result[key] = items
        else:
            result[key] = val

    result.setdefault("name", md_path.parent.name)
    result.setdefault("category", "")
    result.setdefault("tags", [])
    result.setdefault("description", "")
    return result


# ---------------------------------------------------------------------------
# Directory-based registry implementation
# ---------------------------------------------------------------------------


class CatalogRegistry(PrimitiveRegistry):
    """Plugin registry based on the ``catalog/`` directory.

    Initialized via the ``load_catalog()`` class method.

    3-stage progressive loading (§5.6):
    - At startup: loads only the name, category, tags, and description index.
    - On ``load(name)`` call: loads the full Primitive object.
    """

    def __init__(self) -> None:
        super().__init__()
        # Catalog package path map: name → Path
        self._catalog_paths: dict[str, Path] = {}

    @classmethod
    def load_catalog(
        cls,
        catalog_dir: Path | None = None,
    ) -> CatalogRegistry:
        """Initialize the registry from the catalog directory.

        Parameters
        ----------
        catalog_dir:
            Catalog directory path. Uses the default ``catalog/`` when None.

        Returns
        -------
        CatalogRegistry
            Registry with index populated.
        """
        reg = cls()
        cat_dir = catalog_dir or _CATALOG_DIR

        if not cat_dir.is_dir():
            log.info("Catalog directory not found: %s", cat_dir)
            return reg

        for pkg_dir in sorted(cat_dir.iterdir()):
            if not pkg_dir.is_dir():
                continue
            md_path = pkg_dir / "PRIMITIVE.md"
            py_path = pkg_dir / "primitive.py"

            if not md_path.is_file():
                log.debug("PRIMITIVE.md not found: %s", pkg_dir)
                continue

            try:
                meta = _parse_primitive_md(md_path)
                name = meta["name"]

                # Register in index (L1 metadata only)
                reg._index[name] = {
                    "name": name,
                    "category": meta.get("category", ""),
                    "tags": meta.get("tags", []),
                    "description": meta.get("description", ""),
                    "journal_styles": meta.get("journal_styles", []),
                }
                # Record package path
                reg._catalog_paths[name] = pkg_dir
                # If py file does not exist, the primitive is index-only
                if py_path.is_file():
                    log.debug("Catalog registered: %s", name)
                else:
                    log.debug("primitive.py not found — index only: %s", name)
            except Exception as exc:  # noqa: BLE001
                log.warning("Catalog load error (%s): %s", pkg_dir, exc)

        log.info("Catalog loaded: %d primitives", len(reg._index))
        return reg

    def load(self, name: str) -> Primitive:
        """Load the full Primitive body by name (L3 — load on demand).

        Returns from cache if already in ``_loaded``.
        Otherwise dynamically imports from ``catalog/<name>/primitive.py``.

        Parameters
        ----------
        name:
            Primitive name.

        Raises
        ------
        KeyError
            Unregistered primitive.
        RuntimeError
            Failed to load ``primitive.py``.
        """
        if name in self._loaded:
            return self._loaded[name]

        if name not in self._index:
            raise KeyError(f"Primitive '{name}' is not in the registry.")

        pkg_dir = self._catalog_paths.get(name)
        if pkg_dir is None:
            raise KeyError(f"No catalog path found for primitive '{name}'.")

        py_path = pkg_dir / "primitive.py"
        if not py_path.is_file():
            raise RuntimeError(f"primitive.py not found for '{name}': {py_path}")

        # Dynamic import
        spec = importlib.util.spec_from_file_location(f"maglab._catalog.{name}", py_path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Failed to import primitive.py: {py_path}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[f"maglab._catalog.{name}"] = module
        try:
            spec.loader.exec_module(module)  # type: ignore[union-attr]
        except Exception as exc:
            raise RuntimeError(f"Error executing primitive.py ({py_path}): {exc}") from exc

        # Obtain instance via ``get_primitive()`` function
        get_fn = getattr(module, "get_primitive", None)
        if get_fn is None:
            raise RuntimeError(f"primitive.py has no ``get_primitive()`` function: {py_path}")
        primitive = get_fn()
        self._loaded[name] = primitive
        return primitive

    def search(self, query: str, max_results: int = 20) -> list[dict[str, Any]]:
        """Search the primitive index by natural language keywords.

        Splits words by whitespace and matches against name, category, tags, and description.
        Results are sorted by number of matching keywords.

        Parameters
        ----------
        query:
            Search string (e.g. "Hall bar measurement geometry").
        max_results:
            Maximum number of results to return.

        Returns
        -------
        list[dict[str, Any]]
            List of matched index entries (sorted by score, descending).
        """
        query_words = [w.lower() for w in query.split() if w.strip()]
        if not query_words:
            return []

        scored: list[tuple[int, dict[str, Any]]] = []
        for item in self._index.values():
            text = " ".join(
                [
                    item["name"],
                    item.get("category", ""),
                    item.get("description", ""),
                ]
                + list(item.get("tags", []))
            ).lower()

            score = sum(1 for word in query_words if word in text)
            if score > 0:
                scored.append((score, item))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored[:max_results]]


# ---------------------------------------------------------------------------
# Default registry factory
# ---------------------------------------------------------------------------


def make_default_registry() -> CatalogRegistry:
    """Create the default catalog registry."""
    return CatalogRegistry.load_catalog()
