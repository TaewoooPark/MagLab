"""Primitive contract and registry interface (§12.4-①).

In P1, only the contract (protocol) and registry interface are established.
The primitive bodies (schematic vector templates) and registry implementation
are added in P4.

``Primitive`` protocol:
- The single contract implemented by all magnetic schematic primitives.
- The figure-designer agent searches via ``PrimitiveRegistry.search()`` using
  natural language, fills in parameters, then calls ``render()``.

``PrimitiveRegistry`` interface:
- Designed so that P4 can implement this interface without breaking changes.
"""

from __future__ import annotations

from abc import abstractmethod
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable


class Category(StrEnum):
    """Primitive taxonomy categories (plan §12.4-②).

    Using ``StrEnum`` so that ``Category.DEVICE_GEOMETRY == "device geometry"``
    and existing free-form strings in the catalog remain valid.
    """

    DEVICE_GEOMETRY = "device geometry"
    SPIN_TEXTURE = "spin/magnetic texture"
    SAMPLE_STRUCTURE = "sample/thin film structure"
    MEASUREMENT_GEOMETRY = "measurement geometry"
    ANNOTATION = "annotation"
    DYNAMICS = "dynamics"
    CRYSTAL_LATTICE = "crystal/lattice"
    ENERGY_BAND = "energy/band"
    CIRCUIT_MEASUREMENT = "circuit/measurement"
    CONCEPT_PROCESS = "concept/process"


@runtime_checkable
class Primitive(Protocol):
    """Single contract for magnetic schematic primitives (§12.4-①).

    Attributes
    ----------
    name:
        Unique primitive name (registry key).
    category:
        Classification taxonomy (one of the §12.4-② categories).
    tags:
        List of search keywords.
    description:
        Natural language description — used by the figure-designer agent for matching.
    parameters:
        List of parameter schemas. Each entry contains name, type, default, and description.
    physics_convention:
        Physics convention description (e.g. "Néel wall, right-hand coordinate system").
    references:
        List of source DOIs / URLs.
    provenance:
        Primitive source metadata (sourcing information).
    preview:
        SVG/PNG preview path or Base64 string. None if unavailable.
    journal_styles:
        List of supported journal style keys.
    """

    name: str
    category: str
    tags: list[str]
    description: str
    parameters: list[dict[str, Any]]
    physics_convention: str
    references: list[str]
    provenance: dict[str, Any]
    preview: str | None
    journal_styles: list[str]

    @abstractmethod
    def render(
        self,
        params: dict[str, Any],
        backend: str = "svg",
        style: str = "nature",
    ) -> str:
        """Generate a vector representation from parameters.

        Parameters
        ----------
        params:
            Parameter dictionary (validated against schema).
        backend:
            Output backend — ``"svg"`` (default), ``"tikz"``, ``"py"``.
        style:
            Journal style key (e.g. ``"nature"``, ``"aps"``).

        Returns
        -------
        str
            Backend-specific vector string (SVG XML, TikZ code, etc.).
        """
        ...


class PrimitiveRegistry:
    """Primitive registry interface (§12.4-⑤).

    In P1, only the interface signature is established.
    Replaced in P4 with a directory-based pluggable implementation.

    Usage pattern (from P4 onwards):
    ::

        registry = PrimitiveRegistry.load_from_directory("maglab/figure/primitives/library")
        results = registry.search("Hall bar measurement geometry")
        primitive = registry.load(results[0]["name"])
        svg = primitive.render({"width_um": 50}, backend="svg", style="nature")
    """

    def __init__(self) -> None:
        # P1: empty registry — populated in P4
        self._index: dict[str, dict[str, Any]] = {}
        self._loaded: dict[str, Primitive] = {}

    def register(self, primitive: Primitive) -> None:
        """Register a primitive in the registry.

        Parameters
        ----------
        primitive:
            Object implementing the ``Primitive`` protocol.
        """
        self._index[primitive.name] = {
            "name": primitive.name,
            "category": primitive.category,
            "tags": primitive.tags,
            "description": primitive.description,
            "journal_styles": primitive.journal_styles,
        }
        self._loaded[primitive.name] = primitive

    def search(self, query: str) -> list[dict[str, Any]]:
        """Search the primitive index by natural language query (vector search implemented in P4).

        Parameters
        ----------
        query:
            Natural language search string (e.g. "Hall bar geometry", "skyrmion texture").

        Returns
        -------
        list[dict[str, Any]]
            List of matched primitive index entries (name, category, tags, description).
        """
        query_lower = query.lower()
        results: list[dict[str, Any]] = []
        for item in self._index.values():
            # P1: simple keyword matching — replaced with SPECTER2 embeddings in P4
            text = " ".join(
                [item["name"], item["category"], item["description"]] + item["tags"]
            ).lower()
            if any(word in text for word in query_lower.split()):
                results.append(item)
        return results

    def load(self, name: str) -> Primitive:
        """Load the full primitive body by name.

        Parameters
        ----------
        name:
            Primitive name.

        Raises
        ------
        KeyError
            When no primitive with the given name is registered.
        """
        if name not in self._loaded:
            raise KeyError(f"Primitive '{name}' is not in the registry.")
        return self._loaded[name]

    def list_all(self) -> list[dict[str, Any]]:
        """Return the complete list of registered primitive index entries."""
        return list(self._index.values())

    def __len__(self) -> int:
        return len(self._index)


# Module-level default registry instance (populated in P4)
default_registry: PrimitiveRegistry = PrimitiveRegistry()
