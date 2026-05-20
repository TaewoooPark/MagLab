"""tests/unit/test_instrument_skillgen.py — instrument SKILL.md auto-generation unit tests."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from maglab.instrument.safety import SafetyProfile
from maglab.instrument.skillgen import (
    SkillGenerator,
    SkillPackage,
    _is_safety_critical,
    _make_skill_name,
    generate_skill,
)

# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------


def test_make_skill_name_basic():
    """Should generate a basic skill name in kebab-case."""
    name = _make_skill_name("Keithley", "2400")
    assert name == "keithley-2400"


def test_make_skill_name_with_spaces():
    """Should handle names containing spaces."""
    name = _make_skill_name("Stanford Research", "SR830")
    assert "-" in name
    assert name == name.lower()
    assert " " not in name


def test_make_skill_name_kebab_only():
    """Result should be in kebab-case (lowercase letters, digits, hyphens)."""
    name = _make_skill_name("Test", "Model-X1")
    # Only lowercase and hyphens
    import re

    assert re.match(r"^[a-z0-9\-]+$", name), f"not kebab-case: {name!r}"


def test_is_safety_critical_high_voltage():
    """High-voltage instruments should be classified as safety-critical."""
    profile = SafetyProfile(model="high-v", max_voltage_v=200.0)
    assert _is_safety_critical(profile)


def test_is_safety_critical_low_voltage():
    """Low-voltage instruments should not be safety-critical."""
    profile = SafetyProfile(model="low-v", max_voltage_v=5.0)
    assert not _is_safety_critical(profile)


def test_is_safety_critical_high_current():
    """High-current instruments should be classified as safety-critical."""
    profile = SafetyProfile(model="high-i", max_current_a=1.0)
    assert _is_safety_critical(profile)


def test_is_safety_critical_low_current():
    """Low-current instruments should not be safety-critical."""
    profile = SafetyProfile(model="low-i", max_current_a=0.1)
    assert not _is_safety_critical(profile)


def test_is_safety_critical_high_field():
    """High-field magnet instruments should be classified as safety-critical."""
    profile = SafetyProfile(model="magnet", max_field_t=2.0)
    assert _is_safety_critical(profile)


# ---------------------------------------------------------------------------
# SkillGenerator
# ---------------------------------------------------------------------------


def test_skill_generator_creates_directory():
    """The skill directory should be created during generation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        out_root = Path(tmpdir) / "skills"
        gen = SkillGenerator(output_root=out_root)
        pkg = gen.generate(model="SR830", manufacturer="Stanford Research")
        assert pkg.skill_dir.is_dir()


def test_skill_generator_default_output_is_workspace_local(tmp_path: Path, monkeypatch):
    """Generated skills should default to the current workspace, not the package bundle."""
    monkeypatch.chdir(tmp_path)
    gen = SkillGenerator()
    pkg = gen.generate(model="SR830", manufacturer="SRS")
    assert pkg.skill_dir == tmp_path / ".maglab" / "skills" / "srs-sr830"
    assert pkg.ok


def test_skill_generator_skill_md_exists():
    """SKILL.md file should be created."""
    with tempfile.TemporaryDirectory() as tmpdir:
        gen = SkillGenerator(output_root=Path(tmpdir) / "skills")
        pkg = gen.generate(model="SR830", manufacturer="Stanford Research")
        assert (pkg.skill_dir / "SKILL.md").is_file()
        assert pkg.ok


def test_skill_generator_all_files_created():
    """All required files should be created."""
    with tempfile.TemporaryDirectory() as tmpdir:
        gen = SkillGenerator(output_root=Path(tmpdir) / "skills")
        pkg = gen.generate(model="Keithley 2400", manufacturer="Keithley")

        assert (pkg.skill_dir / "SKILL.md").is_file()
        assert (pkg.skill_dir / "SCPI_REFERENCE.md").is_file()
        assert (pkg.skill_dir / "LIMITS.md").is_file()
        assert (pkg.skill_dir / "scripts" / "initialize.py").is_file()
        assert (pkg.skill_dir / "scripts" / "retrieve_scpi.py").is_file()
        assert (pkg.skill_dir / "evals" / "evals.json").is_file()


def test_skill_md_frontmatter_valid():
    """SKILL.md frontmatter should be valid YAML."""
    with tempfile.TemporaryDirectory() as tmpdir:
        gen = SkillGenerator(output_root=Path(tmpdir) / "skills")
        pkg = gen.generate(model="SR830", manufacturer="SRS")

        import yaml

        content = (pkg.skill_dir / "SKILL.md").read_text(encoding="utf-8")
        import re

        m = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
        assert m, "frontmatter not found."
        fm = yaml.safe_load(m.group(1))
        assert "name" in fm
        assert "description" in fm
        assert len(fm["description"]) <= 1024


def test_skill_md_loadable_by_skill_loader():
    """Generated SKILL.md should be parseable by SkillLoader."""
    with tempfile.TemporaryDirectory() as tmpdir:
        out_root = Path(tmpdir) / "skills"
        gen = SkillGenerator(output_root=out_root)
        pkg = gen.generate(model="SR830", manufacturer="SRS")

        from maglab.core.skills import SkillLoader

        loader = SkillLoader(extra_paths=[out_root])
        metas = loader.discover()
        names = [m.name for m in metas]
        assert pkg.name in names


def test_evals_json_valid():
    """evals.json should be valid JSON."""
    with tempfile.TemporaryDirectory() as tmpdir:
        gen = SkillGenerator(output_root=Path(tmpdir) / "skills")
        pkg = gen.generate(model="SR830", manufacturer="SRS")

        evals_path = pkg.skill_dir / "evals" / "evals.json"
        data = json.loads(evals_path.read_text(encoding="utf-8"))
        assert "cases" in data
        assert isinstance(data["cases"], list)
        assert len(data["cases"]) > 0


def test_safety_critical_flag_set_correctly():
    """Safety-critical instruments should have disable_model_invocation set to True."""
    with tempfile.TemporaryDirectory() as tmpdir:
        gen = SkillGenerator(output_root=Path(tmpdir) / "skills")
        # Keithley-2400 profile has max_voltage=210V → safety-critical
        pkg = gen.generate(
            model="Keithley 2400",
            manufacturer="Keithley",
            safety_model="keithley-2400",
        )
        assert pkg.disable_model_invocation is True

        import re

        import yaml

        content = (pkg.skill_dir / "SKILL.md").read_text(encoding="utf-8")
        m = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
        fm = yaml.safe_load(m.group(1))
        assert fm.get("disable-model-invocation") is True


# ---------------------------------------------------------------------------
# A/B evaluation
# ---------------------------------------------------------------------------


def test_ab_evaluation_creates_results_json():
    """results.json should be created after running A/B evaluation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        gen = SkillGenerator(output_root=Path(tmpdir) / "skills")
        pkg = gen.generate(model="SR830", manufacturer="SRS")
        result = gen.run_ab_evaluation(pkg.skill_dir, "SR830")
        assert (pkg.skill_dir / "evals" / "results.json").is_file()
        assert "skill_score" in result
        assert "baseline_score" in result


def test_ab_evaluation_skill_wins():
    """Skill-loaded score should be greater than or equal to baseline."""
    with tempfile.TemporaryDirectory() as tmpdir:
        gen = SkillGenerator(output_root=Path(tmpdir) / "skills")
        pkg = gen.generate(model="SR830", manufacturer="SRS")
        result = gen.run_ab_evaluation(pkg.skill_dir, "SR830")
        assert result["skill_wins"] is True


# ---------------------------------------------------------------------------
# generate_skill convenience function
# ---------------------------------------------------------------------------


def test_generate_skill_convenience():
    """generate_skill() convenience function should return a SkillPackage."""
    with tempfile.TemporaryDirectory() as tmpdir:
        pkg = generate_skill(
            model="SR830",
            manufacturer="SRS",
            output_root=Path(tmpdir) / "skills",
        )
        assert isinstance(pkg, SkillPackage)
        assert pkg.ok
