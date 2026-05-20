"""Unit tests for skills/revision-letter/, skills/cover-letter/, skills/academic-email/
SKILL.md packages (Appendix C bundle comms skills)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

# Root of the repository (two levels up from tests/unit/)
_REPO_ROOT = Path(__file__).parent.parent.parent
_SKILLS_DIR = _REPO_ROOT / "skills"

_COMMS_SKILLS = ["revision-letter", "cover-letter", "academic-email"]


class TestCommsSkillsExist:
    """Each comms SKILL.md package directory and file must exist."""

    @pytest.mark.parametrize("skill_name", _COMMS_SKILLS)
    def test_skill_directory_exists(self, skill_name: str) -> None:
        """skills/<name>/ directory exists."""
        path = _SKILLS_DIR / skill_name
        assert path.is_dir(), f"Missing directory: skills/{skill_name}/"

    @pytest.mark.parametrize("skill_name", _COMMS_SKILLS)
    def test_skill_md_file_exists(self, skill_name: str) -> None:
        """skills/<name>/SKILL.md file exists."""
        path = _SKILLS_DIR / skill_name / "SKILL.md"
        assert path.is_file(), f"Missing file: skills/{skill_name}/SKILL.md"


class TestCommsSkillsFrontmatter:
    """Each SKILL.md must have valid YAML frontmatter with required keys."""

    @pytest.fixture(params=_COMMS_SKILLS)
    def skill_frontmatter(self, request):
        """Parse and return the YAML frontmatter for each comms skill."""
        skill_name = request.param
        path = _SKILLS_DIR / skill_name / "SKILL.md"
        text = path.read_text(encoding="utf-8")
        # Extract frontmatter between first pair of "---" delimiters
        parts = text.split("---", 2)
        assert len(parts) >= 3, f"{skill_name}/SKILL.md has no YAML frontmatter"
        fm = yaml.safe_load(parts[1])
        return skill_name, fm

    def test_frontmatter_has_name(self, skill_frontmatter) -> None:
        """YAML frontmatter contains a 'name' key."""
        skill_name, fm = skill_frontmatter
        assert "name" in fm, f"{skill_name}/SKILL.md frontmatter missing 'name'"

    def test_frontmatter_name_matches_directory(self, skill_frontmatter) -> None:
        """'name' in frontmatter matches the directory name."""
        skill_name, fm = skill_frontmatter
        assert fm["name"] == skill_name, (
            f"{skill_name}/SKILL.md name={fm['name']!r} doesn't match directory"
        )

    def test_frontmatter_has_description(self, skill_frontmatter) -> None:
        """YAML frontmatter contains a 'description' key."""
        skill_name, fm = skill_frontmatter
        assert "description" in fm, f"{skill_name}/SKILL.md frontmatter missing 'description'"

    def test_frontmatter_description_is_non_empty(self, skill_frontmatter) -> None:
        """Description is a non-empty string."""
        skill_name, fm = skill_frontmatter
        desc = str(fm.get("description", "")).strip()
        assert len(desc) > 0, f"{skill_name}/SKILL.md description is empty"

    def test_frontmatter_has_license(self, skill_frontmatter) -> None:
        """YAML frontmatter contains a 'license' key."""
        skill_name, fm = skill_frontmatter
        assert "license" in fm, f"{skill_name}/SKILL.md frontmatter missing 'license'"

    def test_frontmatter_has_compatibility(self, skill_frontmatter) -> None:
        """YAML frontmatter contains a 'compatibility' key."""
        skill_name, fm = skill_frontmatter
        assert "compatibility" in fm, f"{skill_name}/SKILL.md frontmatter missing 'compatibility'"


class TestCommsSkillsBody:
    """Each SKILL.md body must contain required sections and integrity markers."""

    @pytest.mark.parametrize("skill_name", _COMMS_SKILLS)
    def test_body_contains_overview(self, skill_name: str) -> None:
        """SKILL.md body contains an Overview section."""
        text = (_SKILLS_DIR / skill_name / "SKILL.md").read_text(encoding="utf-8")
        assert "## Overview" in text, f"{skill_name}/SKILL.md missing '## Overview'"

    @pytest.mark.parametrize("skill_name", _COMMS_SKILLS)
    def test_body_contains_inputs(self, skill_name: str) -> None:
        """SKILL.md body contains an Inputs section."""
        text = (_SKILLS_DIR / skill_name / "SKILL.md").read_text(encoding="utf-8")
        assert "## Inputs" in text or "Input" in text, (
            f"{skill_name}/SKILL.md missing Inputs section"
        )

    @pytest.mark.parametrize("skill_name", _COMMS_SKILLS)
    def test_body_contains_human_review_required(self, skill_name: str) -> None:
        """SKILL.md body mentions HUMAN REVIEW REQUIRED (integrity guardrail)."""
        text = (_SKILLS_DIR / skill_name / "SKILL.md").read_text(encoding="utf-8")
        assert "HUMAN REVIEW REQUIRED" in text, (
            f"{skill_name}/SKILL.md does not mention HUMAN REVIEW REQUIRED"
        )

    @pytest.mark.parametrize("skill_name", _COMMS_SKILLS)
    def test_body_contains_no_auto_send(self, skill_name: str) -> None:
        """SKILL.md body states that auto-send is prohibited."""
        text = (_SKILLS_DIR / skill_name / "SKILL.md").read_text(encoding="utf-8")
        assert "auto-send" in text.lower() or "no auto" in text.lower(), (
            f"{skill_name}/SKILL.md does not mention auto-send prohibition"
        )

    @pytest.mark.parametrize("skill_name", _COMMS_SKILLS)
    def test_body_references_agent_module(self, skill_name: str) -> None:
        """SKILL.md body references the corresponding comms agent module."""
        text = (_SKILLS_DIR / skill_name / "SKILL.md").read_text(encoding="utf-8")
        assert "maglab.authoring.comms" in text, (
            f"{skill_name}/SKILL.md does not reference maglab.authoring.comms"
        )

    @pytest.mark.parametrize("skill_name", _COMMS_SKILLS)
    def test_body_contains_fill_marker(self, skill_name: str) -> None:
        """SKILL.md body mentions [FILL] placeholder convention."""
        text = (_SKILLS_DIR / skill_name / "SKILL.md").read_text(encoding="utf-8")
        assert "[FILL" in text, f"{skill_name}/SKILL.md does not mention [FILL] convention"


class TestCommsSkillsDiscoverable:
    """Skills are discoverable by the skill list command."""

    def test_skill_list_includes_comms_skills(self) -> None:
        """maglab skill list output includes all three comms skills."""
        from typer.testing import CliRunner

        from maglab.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["skill", "list"])
        assert result.exit_code == 0, f"skill list failed: {result.stdout}"
        for skill_name in _COMMS_SKILLS:
            assert skill_name in result.stdout, (
                f"'{skill_name}' not found in skill list output:\n{result.stdout}"
            )
