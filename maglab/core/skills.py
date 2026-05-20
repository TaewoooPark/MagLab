"""Skill loader — SKILL.md discovery, parsing, and three-level progressive disclosure (§5.6, §5.17).

Search paths (in order):
1. ``.maglab/skills/`` — project-local skills
2. ``~/.local/share/maglab/skills/`` — user-global skills
3. Bundled ``skills/`` (relative to package root)

Three-level progressive disclosure:
- **L1** Metadata: ``name`` + ``description`` only (always loaded, ~100 tokens/skill)
- **L2** SKILL.md body: loaded on trigger
- **L3** Bundle files: loaded only on explicit access

SKILL.md frontmatter (YAML) required fields:
- ``name``        — 1–64 character kebab-case
- ``description`` — ≤1024 characters

MagLab extension fields:
- ``user-invocable``          — when false, for Claude background context only
- ``disable-model-invocation``— when true, user-invoked only
- ``paths``                   — auto-activation glob list
- ``allowed-tools``           — pre-approved tool list
- ``context``                 — when ``fork``, runs in isolated sub-agent

Dependencies: none (yaml, pathlib, re — standard/bundled libraries).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

_PKG_ROOT = Path(__file__).parent.parent.parent  # repository root
_BUNDLE_SKILLS_DIR = _PKG_ROOT / "skills"

_SEARCH_PATHS: list[Path] = [
    Path.cwd() / ".maglab" / "skills",
    Path.home() / ".local" / "share" / "maglab" / "skills",
    _BUNDLE_SKILLS_DIR,
]


# ---------------------------------------------------------------------------
# SKILL.md frontmatter validation
# ---------------------------------------------------------------------------

_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)


class SkillLoadError(Exception):
    """Skill load / validation error."""


def _extract_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Split YAML frontmatter and body from a SKILL.md file.

    Returns
    -------
    (frontmatter_dict, body_str)
    """
    m = _FRONTMATTER_RE.match(text)
    if not m:
        raise SkillLoadError("SKILL.md has no YAML frontmatter (--- delimiter).")
    fm_raw = m.group(1)
    body = text[m.end() :].lstrip("\n")
    try:
        fm = yaml.safe_load(fm_raw) or {}
    except yaml.YAMLError as exc:
        raise SkillLoadError(f"YAML frontmatter parse error: {exc}") from exc
    if not isinstance(fm, dict):
        raise SkillLoadError("Frontmatter is not a dict.")
    return fm, body


def _validate_frontmatter(fm: dict[str, Any], skill_dir: Path) -> None:
    """Validate required fields and constraints."""
    name = fm.get("name")
    if not name:
        raise SkillLoadError(f"[{skill_dir.name}] frontmatter is missing the 'name' field.")
    if not isinstance(name, str) or not (1 <= len(name) <= 64):
        raise SkillLoadError(f"[{skill_dir.name}] name must be a 1–64 character string.")
    if not _NAME_RE.match(name):
        raise SkillLoadError(
            f"[{skill_dir.name}] name='{name}' must be kebab-case (lowercase, digits, hyphens)."
        )
    description = fm.get("description")
    if not description:
        raise SkillLoadError(f"[{skill_dir.name}] frontmatter is missing the 'description' field.")
    if not isinstance(description, str) or len(description) > 1024:
        raise SkillLoadError(
            f"[{skill_dir.name}] description must be a string of ≤1024 characters."
        )


# ---------------------------------------------------------------------------
# Skill data structures
# ---------------------------------------------------------------------------


@dataclass
class SkillMeta:
    """L1 — metadata only."""

    name: str
    """Skill name (kebab-case)."""
    description: str
    """Skill description (trigger text)."""
    skill_dir: Path
    """Skill directory path."""
    license: str = ""
    """License string."""
    compatibility: dict[str, Any] = field(default_factory=dict)
    """Compatibility metadata."""
    user_invocable: bool = True
    """When False, for Claude background context only."""
    disable_model_invocation: bool = False
    """When True, user-invoked only."""
    paths: list[str] = field(default_factory=list)
    """Auto-activation glob list."""
    allowed_tools: list[str] = field(default_factory=list)
    """Pre-approved tool list."""
    context: str = ""
    """When ``fork``, runs in isolated sub-agent."""
    raw_frontmatter: dict[str, Any] = field(default_factory=dict)
    """Raw frontmatter dictionary."""


@dataclass
class Skill(SkillMeta):
    """L2 — SKILL.md body loaded."""

    body: str = ""
    """SKILL.md body (excluding frontmatter)."""


# ---------------------------------------------------------------------------
# Skill loader
# ---------------------------------------------------------------------------


class SkillLoader:
    """Loader that discovers, parses, and caches skills.

    Parameters
    ----------
    extra_paths:
        Additional search paths inserted before the default paths.
    """

    def __init__(self, extra_paths: list[Path] | None = None) -> None:
        search = list(extra_paths or []) + list(_SEARCH_PATHS)
        # Remove duplicates (preserve order)
        seen: set[Path] = set()
        self._search_paths: list[Path] = []
        for p in search:
            if p not in seen:
                seen.add(p)
                self._search_paths.append(p)
        self._meta_cache: dict[str, SkillMeta] = {}
        self._skill_cache: dict[str, Skill] = {}
        self._errors: dict[str, str] = {}

    # ------------------------------------------------------------------
    # L1 — metadata loading
    # ------------------------------------------------------------------

    def discover(self) -> list[SkillMeta]:
        """Discover skills across all search paths and return L1 metadata.

        Already-cached skills are not re-discovered.
        Skills with errors are recorded in ``self.errors`` and skipped.
        """
        results: dict[str, SkillMeta] = {}
        for base in self._search_paths:
            if not base.is_dir():
                continue
            for skill_dir in sorted(base.iterdir()):
                if not skill_dir.is_dir():
                    continue
                skill_md = skill_dir / "SKILL.md"
                if not skill_md.is_file():
                    continue
                try:
                    meta = self._load_meta(skill_dir, skill_md)
                    if meta.name not in results:
                        results[meta.name] = meta
                        self._meta_cache[meta.name] = meta
                except SkillLoadError as exc:
                    self._errors[skill_dir.name] = str(exc)
        return list(results.values())

    def list_meta(self) -> list[SkillMeta]:
        """Return the cached L1 metadata list (calls discover() if empty)."""
        if not self._meta_cache:
            self.discover()
        return list(self._meta_cache.values())

    # ------------------------------------------------------------------
    # L2 — body loading
    # ------------------------------------------------------------------

    def load(self, name: str) -> Skill:
        """Load skill L2 by name (includes body).

        Parameters
        ----------
        name:
            Skill name.

        Raises
        ------
        KeyError:
            When the skill cannot be found.
        SkillLoadError:
            When the skill structure is invalid.
        """
        if name in self._skill_cache:
            return self._skill_cache[name]
        # Not in cache — run discover and retry
        if name not in self._meta_cache:
            self.discover()
        if name not in self._meta_cache:
            raise KeyError(f"Skill not found: {name!r}")
        meta = self._meta_cache[name]
        skill_md = meta.skill_dir / "SKILL.md"
        text = skill_md.read_text(encoding="utf-8")
        _, body = _extract_frontmatter(text)
        skill = Skill(
            name=meta.name,
            description=meta.description,
            skill_dir=meta.skill_dir,
            license=meta.license,
            compatibility=meta.compatibility,
            user_invocable=meta.user_invocable,
            disable_model_invocation=meta.disable_model_invocation,
            paths=meta.paths,
            allowed_tools=meta.allowed_tools,
            context=meta.context,
            raw_frontmatter=meta.raw_frontmatter,
            body=body,
        )
        self._skill_cache[name] = skill
        return skill

    # ------------------------------------------------------------------
    # L3 — bundle file access
    # ------------------------------------------------------------------

    def get_bundle_file(self, name: str, relative_path: str) -> Path | None:
        """Return the path to a skill bundle file (None if not found).

        L3 level — call only on explicit access.
        """
        if name not in self._meta_cache:
            self.discover()
        if name not in self._meta_cache:
            return None
        p = self._meta_cache[name].skill_dir / relative_path
        return p if p.exists() else None

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(self, query: str) -> list[SkillMeta]:
        """Simple text search across name and description."""
        pattern = re.compile(re.escape(query), re.IGNORECASE)
        return [
            m for m in self.list_meta() if pattern.search(m.name) or pattern.search(m.description)
        ]

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def errors(self) -> dict[str, str]:
        """Errors encountered during loading {skill_dir_name: error_message}."""
        return dict(self._errors)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load_meta(skill_dir: Path, skill_md: Path) -> SkillMeta:
        text = skill_md.read_text(encoding="utf-8")
        fm, _ = _extract_frontmatter(text)
        _validate_frontmatter(fm, skill_dir)
        return SkillMeta(
            name=fm["name"],
            description=fm["description"],
            skill_dir=skill_dir,
            license=str(fm.get("license", "")),
            compatibility=fm.get("compatibility") or {},
            user_invocable=bool(fm.get("user-invocable", True)),
            disable_model_invocation=bool(fm.get("disable-model-invocation", False)),
            paths=fm.get("paths") or [],
            allowed_tools=fm.get("allowed-tools") or [],
            context=str(fm.get("context", "")),
            raw_frontmatter=fm,
        )


# ---------------------------------------------------------------------------
# Module-level default loader (singleton pattern)
# ---------------------------------------------------------------------------

_default_loader: SkillLoader | None = None


def get_loader() -> SkillLoader:
    """Return the default SkillLoader instance (initialised on first call)."""
    global _default_loader
    if _default_loader is None:
        _default_loader = SkillLoader()
    return _default_loader


def list_skills() -> list[SkillMeta]:
    """Return the full skill L1 list using the default loader."""
    return get_loader().list_meta()
