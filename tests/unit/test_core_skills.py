"""maglab.core.skills unit tests — deterministic, no network/LLM."""

from __future__ import annotations

from pathlib import Path

import pytest

from maglab.core.skills import (
    Skill,
    SkillLoader,
    SkillLoadError,
    SkillMeta,
    _extract_frontmatter,
    _validate_frontmatter,
)

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def make_skill_dir(
    base: Path,
    *,
    name: str = "test-skill",
    description: str = "Test skill description.",
    extra_fm: str = "",
    body: str = "## Body\n\nSkill detail.",
) -> Path:
    """Create a temporary skill directory and return its path."""
    skill_dir = base / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    fm = f'name: {name}\ndescription: "{description}"\nlicense: MIT\n{extra_fm}'
    content = f"---\n{fm}---\n\n{body}"
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
    return skill_dir


# ---------------------------------------------------------------------------
# frontmatter extraction & validation
# ---------------------------------------------------------------------------


def test_extract_frontmatter_basic() -> None:
    text = '---\nname: my-skill\ndescription: "description"\n---\n\n## Body\nContent.'
    fm, body = _extract_frontmatter(text)
    assert fm["name"] == "my-skill"
    assert fm["description"] == "description"
    assert "Body" in body


def test_extract_frontmatter_no_separator_raises() -> None:
    with pytest.raises(SkillLoadError, match="frontmatter"):
        _extract_frontmatter("This file has no frontmatter.")


def test_extract_frontmatter_invalid_yaml_raises() -> None:
    text = "---\n: invalid: yaml: :\n---\nBody"
    # SkillLoadError must be raised on YAML error
    with pytest.raises(SkillLoadError):
        _extract_frontmatter(text)


def test_validate_frontmatter_valid(tmp_path: Path) -> None:
    skill_dir = tmp_path / "ok-skill"
    fm = {"name": "ok-skill", "description": "Valid skill."}
    _validate_frontmatter(fm, skill_dir)  # must not raise


def test_validate_frontmatter_missing_name(tmp_path: Path) -> None:
    with pytest.raises(SkillLoadError, match="name"):
        _validate_frontmatter({"description": "description"}, tmp_path / "x")


def test_validate_frontmatter_missing_description(tmp_path: Path) -> None:
    with pytest.raises(SkillLoadError, match="description"):
        _validate_frontmatter({"name": "my-skill"}, tmp_path / "x")


def test_validate_frontmatter_invalid_name_format(tmp_path: Path) -> None:
    with pytest.raises(SkillLoadError, match="kebab"):
        _validate_frontmatter({"name": "My Skill!", "description": "description"}, tmp_path / "x")


def test_validate_frontmatter_name_too_long(tmp_path: Path) -> None:
    with pytest.raises(SkillLoadError, match="1–64"):
        _validate_frontmatter({"name": "a" * 65, "description": "description"}, tmp_path / "x")


def test_validate_frontmatter_description_too_long(tmp_path: Path) -> None:
    with pytest.raises(SkillLoadError, match="1024"):
        _validate_frontmatter({"name": "my-skill", "description": "X" * 1025}, tmp_path / "x")


# ---------------------------------------------------------------------------
# SkillLoader — discover (L1)
# ---------------------------------------------------------------------------


def test_discover_finds_valid_skill(tmp_path: Path) -> None:
    make_skill_dir(tmp_path, name="my-skill")
    loader = SkillLoader(extra_paths=[tmp_path])
    metas = loader.discover()
    names = [m.name for m in metas]
    assert "my-skill" in names


def test_discover_skips_invalid_skill_with_error(tmp_path: Path) -> None:
    # invalid SKILL.md (no frontmatter)
    bad_dir = tmp_path / "bad-skill"
    bad_dir.mkdir()
    (bad_dir / "SKILL.md").write_text("no frontmatter", encoding="utf-8")

    # a valid skill must also be present so the invalid one is skipped
    make_skill_dir(tmp_path, name="good-skill")

    loader = SkillLoader(extra_paths=[tmp_path])
    metas = loader.discover()
    names = [m.name for m in metas]
    assert "good-skill" in names
    assert "bad-skill" not in names
    assert "bad-skill" in loader.errors or len(loader.errors) >= 1


def test_discover_empty_directory_returns_empty(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Returns an empty list when only an empty directory is searched."""
    import maglab.core.skills as skills_mod

    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    # replace the default search paths with a temporary empty directory
    monkeypatch.setattr(skills_mod, "_SEARCH_PATHS", [empty_dir])
    loader = SkillLoader(extra_paths=[])
    metas = loader.discover()
    assert metas == []


def test_discover_deduplicates_same_name(tmp_path: Path) -> None:
    dir_a = tmp_path / "dir-a"
    dir_a.mkdir()
    dir_b = tmp_path / "dir-b"
    dir_b.mkdir()
    make_skill_dir(dir_a, name="shared-skill")
    make_skill_dir(dir_b, name="shared-skill")
    loader = SkillLoader(extra_paths=[dir_a, dir_b])
    metas = loader.discover()
    names = [m.name for m in metas]
    assert names.count("shared-skill") == 1


# ---------------------------------------------------------------------------
# SkillLoader — load (L2)
# ---------------------------------------------------------------------------


def test_load_returns_skill_with_body(tmp_path: Path) -> None:
    make_skill_dir(tmp_path, name="full-skill", body="## Detail\n\nSkill body.")
    loader = SkillLoader(extra_paths=[tmp_path])
    skill = loader.load("full-skill")
    assert isinstance(skill, Skill)
    assert "Detail" in skill.body


def test_load_nonexistent_raises_keyerror(tmp_path: Path) -> None:
    loader = SkillLoader(extra_paths=[tmp_path])
    with pytest.raises(KeyError):
        loader.load("ghost-skill")


def test_load_caches_result(tmp_path: Path) -> None:
    make_skill_dir(tmp_path, name="cached-skill")
    loader = SkillLoader(extra_paths=[tmp_path])
    skill1 = loader.load("cached-skill")
    skill2 = loader.load("cached-skill")
    assert skill1 is skill2  # must be the same object


# ---------------------------------------------------------------------------
# MagLab extension field parsing
# ---------------------------------------------------------------------------


def test_extension_fields_parsed(tmp_path: Path) -> None:
    extra = (
        "user-invocable: false\n"
        "disable-model-invocation: true\n"
        'context: "fork"\n'
        'paths:\n  - "*.py"\n'
    )
    make_skill_dir(tmp_path, name="ext-skill", extra_fm=extra)
    loader = SkillLoader(extra_paths=[tmp_path])
    meta = loader.discover()[0]
    assert meta.user_invocable is False
    assert meta.disable_model_invocation is True
    assert meta.context == "fork"
    assert "*.py" in meta.paths


# ---------------------------------------------------------------------------
# SkillLoader — get_bundle_file (L3)
# ---------------------------------------------------------------------------


def test_get_bundle_file_returns_path_when_exists(tmp_path: Path) -> None:
    skill_dir = make_skill_dir(tmp_path, name="bundled-skill")
    scripts_dir = skill_dir / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "run.py").write_text("# script", encoding="utf-8")

    loader = SkillLoader(extra_paths=[tmp_path])
    loader.discover()
    p = loader.get_bundle_file("bundled-skill", "scripts/run.py")
    assert p is not None
    assert p.is_file()


def test_get_bundle_file_returns_none_when_missing(tmp_path: Path) -> None:
    make_skill_dir(tmp_path, name="no-bundle")
    loader = SkillLoader(extra_paths=[tmp_path])
    loader.discover()
    p = loader.get_bundle_file("no-bundle", "scripts/nonexistent.py")
    assert p is None


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------


def test_search_by_name(tmp_path: Path) -> None:
    make_skill_dir(tmp_path, name="magnetotransport-fitting", description="Hall fitting skill.")
    make_skill_dir(tmp_path, name="physics-calculator", description="Physics calculator.")
    loader = SkillLoader(extra_paths=[tmp_path])
    results = loader.search("magnetotransport")
    assert len(results) == 1
    assert results[0].name == "magnetotransport-fitting"


def test_search_by_description(tmp_path: Path) -> None:
    make_skill_dir(tmp_path, name="ahe-fitter", description="AHE effect fitting tool.")
    loader = SkillLoader(extra_paths=[tmp_path])
    results = loader.search("AHE")
    assert len(results) >= 1


def test_search_no_match_returns_empty(tmp_path: Path) -> None:
    make_skill_dir(tmp_path, name="x-skill", description="X description.")
    loader = SkillLoader(extra_paths=[tmp_path])
    results = loader.search("NOT_PRESENT_XYZ_123")
    assert results == []


# ---------------------------------------------------------------------------
# Bundle skills/ directory — works even when empty
# ---------------------------------------------------------------------------


def test_loader_works_with_empty_bundle_dir(tmp_path: Path) -> None:
    empty = tmp_path / "empty-bundle"
    empty.mkdir()
    loader = SkillLoader(extra_paths=[empty])
    metas = loader.discover()
    assert isinstance(metas, list)  # must not raise even when empty


# ---------------------------------------------------------------------------
# SkillMeta field validation
# ---------------------------------------------------------------------------


def test_skill_meta_fields(tmp_path: Path) -> None:
    make_skill_dir(tmp_path, name="meta-check", description="Meta field check.")
    loader = SkillLoader(extra_paths=[tmp_path])
    metas = loader.discover()
    m = next(x for x in metas if x.name == "meta-check")
    assert isinstance(m, SkillMeta)
    assert m.name == "meta-check"
    assert m.description == "Meta field check."
    assert m.license == "MIT"
    assert m.skill_dir.is_dir()
