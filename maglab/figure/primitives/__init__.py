"""maglab.figure.primitives — Magnetic schematic primitive library (§12.4).

P1: ``Primitive`` protocol and ``PrimitiveRegistry`` interface (``spec.py``).
P4: ``CatalogRegistry`` implementation, catalog, and ``SchematicRenderer`` (``registry.py``).
"""

from maglab.figure.primitives.ingest import (
    PrimitiveIngestError,
    PrimitiveIngestResult,
    ingest_primitive,
)
from maglab.figure.primitives.registry import CatalogRegistry, make_default_registry
from maglab.figure.primitives.spec import Category, Primitive, PrimitiveRegistry, default_registry

__all__ = [
    "Category",
    "Primitive",
    "PrimitiveRegistry",
    "default_registry",
    "CatalogRegistry",
    "make_default_registry",
    "PrimitiveIngestError",
    "PrimitiveIngestResult",
    "ingest_primitive",
]
