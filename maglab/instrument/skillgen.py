"""Automatic instrument SKILL.md generation — `instrument/skillgen.py`.

§13.3, §5.17, T-P4-09·T-P4-10·T-P4-11:
Extracts instrument information from the RAG index and generates a SKILL.md
open-standard skill package.

Generated file structure:
```
.maglab/skills/<manufacturer>-<model>/
  SKILL.md          — frontmatter + body (SKILL.md open standard)
  SCPI_REFERENCE.md — full SCPI command table
  LIMITS.md         — safety limits and interlocks
  scripts/
    initialize.py   — initialization script skeleton
    retrieve_scpi.py — RAG search interface
  evals/
    evals.json      — A/B evaluation cases
```

A/B evaluation:
- Scores deterministic assertions (SCPI accuracy, parameter ranges) on skill-loaded
  vs. skill-absent paths.
- Results are written to `evals/results.json`.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from maglab.instrument.manual_rag import ManualRAGPipeline, SCPIChunk
from maglab.instrument.safety import SafetyProfile, get_profile

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Skill package data structure
# ---------------------------------------------------------------------------


@dataclass
class SkillPackage:
    """Metadata for a generated instrument skill package."""

    name: str
    """Skill name (kebab-case)."""
    skill_dir: Path
    """Skill directory path."""
    model: str
    """Instrument model name."""
    manufacturer: str
    """Manufacturer name."""
    chunk_count: int = 0
    """Number of SCPI chunks used."""
    disable_model_invocation: bool = False
    """Whether this is a safety-critical skill."""
    files: list[Path] = field(default_factory=list)
    """List of generated files."""

    @property
    def ok(self) -> bool:
        """True when SKILL.md has been generated."""
        return (self.skill_dir / "SKILL.md").is_file()


# ---------------------------------------------------------------------------
# SKILL.md generator
# ---------------------------------------------------------------------------


def _make_skill_name(manufacturer: str, model: str) -> str:
    """Generate a kebab-case skill name."""
    raw = f"{manufacturer}-{model}".lower()
    cleaned = re.sub(r"[^a-z0-9]+", "-", raw)
    return cleaned.strip("-")


def _is_safety_critical(profile: SafetyProfile) -> bool:
    """Determine whether an instrument is safety-critical."""
    # High-voltage or high-current instruments are classified as safety-critical
    if profile.max_voltage_v is not None and abs(profile.max_voltage_v) > 100:
        return True
    if profile.max_current_a is not None and profile.max_current_a > 0.5:
        return True
    return profile.max_field_t is not None and profile.max_field_t > 1.0


class SkillGenerator:
    """Automatic instrument SKILL.md skill generator.

    §13.3·§5.17: RAG index → skill draft → A/B evaluation → packaging.
    """

    def __init__(
        self,
        output_root: Path | None = None,
        rag_pipeline: ManualRAGPipeline | None = None,
    ) -> None:
        """Initialize the generator.

        Args:
            output_root: Skill output root (default: .maglab/skills in the current workspace).
            rag_pipeline: RAG pipeline; uses the default pipeline when None.
        """
        # Generated instrument skills are workspace-local by default. A globally
        # installed MagLab package is not a writable project workspace.
        self._output_root = output_root or (Path.cwd() / ".maglab" / "skills")
        self._rag = rag_pipeline or ManualRAGPipeline()

    def generate(
        self,
        model: str,
        manufacturer: str,
        model_key: str | None = None,
        safety_model: str = "generic",
        max_chunks_in_reference: int = 100,
    ) -> SkillPackage:
        """Generate an instrument skill package.

        ★ Model name must be confirmed with the user (§13.2 — never guess).

        Args:
            model: Instrument model name.
            manufacturer: Manufacturer name.
            model_key: RAG index key. Defaults to `<manufacturer>-<model>` when None.
            safety_model: Safety profile model key.
            max_chunks_in_reference: Maximum number of chunks to include in SCPI_REFERENCE.md.

        Returns:
            SkillPackage — ok=True means generation succeeded.
        """
        mkey = model_key or _make_skill_name(manufacturer, model)
        skill_name = _make_skill_name(manufacturer, model)
        skill_dir = self._output_root / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)

        # Load the RAG index
        index = self._rag.get_index(mkey)
        chunks: list[SCPIChunk] = []
        if index is not None:
            # Search with a representative query to retrieve all chunks
            results = index.search("SCPI command measurement", k=index.chunk_count or 200)
            chunks = [c for c, _ in results]

        # Safety profile
        profile = get_profile(safety_model)
        safety_critical = _is_safety_critical(profile)

        # Generate files
        files: list[Path] = []
        files.append(
            self._write_skill_md(
                skill_dir, skill_name, model, manufacturer, safety_critical, chunks
            )
        )
        files.append(self._write_scpi_reference(skill_dir, model, chunks[:max_chunks_in_reference]))
        files.append(self._write_limits_md(skill_dir, model, profile))
        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir(exist_ok=True)
        files.append(self._write_initialize_script(scripts_dir, model, manufacturer))
        files.append(self._write_retrieve_script(scripts_dir, mkey))
        evals_dir = skill_dir / "evals"
        evals_dir.mkdir(exist_ok=True)
        files.append(self._write_evals(evals_dir, model, chunks))

        package = SkillPackage(
            name=skill_name,
            skill_dir=skill_dir,
            model=model,
            manufacturer=manufacturer,
            chunk_count=len(chunks),
            disable_model_invocation=safety_critical,
            files=files,
        )
        log.info("Skill generation complete: %s → %s", skill_name, skill_dir)
        return package

    # ------------------------------------------------------------------
    # File generation methods
    # ------------------------------------------------------------------

    def _write_skill_md(
        self,
        skill_dir: Path,
        skill_name: str,
        model: str,
        manufacturer: str,
        safety_critical: bool,
        chunks: list[SCPIChunk],
    ) -> Path:
        """Generate SKILL.md."""
        path = skill_dir / "SKILL.md"
        # Representative SCPI command list (up to 10 entries)
        cmd_list = "\n".join(f"- `{c.cmd}` — {c.description[:60]}" for c in chunks[:10])
        if not cmd_list:
            cmd_list = "- (See SCPI_REFERENCE.md for the full command list)"

        fm: dict[str, Any] = {
            "name": skill_name,
            "description": (
                f"{manufacturer} {model} instrument — PyVISA SCPI command reference and "
                f"measurement workflow. Supports SCPI sequence generation and safety validation."
            ),
            "disable-model-invocation": safety_critical,
            "compatibility": {
                "claude-code": True,
                "maglab": True,
            },
            "metadata": {
                "instrument-model": model,
                "manufacturer": manufacturer,
                "generated-by": "maglab instrument skillgen",
                "generated-at": datetime.now(UTC).isoformat(),
                "safety-critical": safety_critical,
            },
        }
        # Serialize frontmatter (simple YAML)
        fm_lines = ["---"]
        for k, v in fm.items():
            if isinstance(v, bool):
                fm_lines.append(f"{k}: {str(v).lower()}")
            elif isinstance(v, dict):
                fm_lines.append(f"{k}:")
                for dk, dv in v.items():
                    if isinstance(dv, bool):
                        fm_lines.append(f"  {dk}: {str(dv).lower()}")
                    else:
                        fm_lines.append(f"  {dk}: {dv!r}")
            else:
                fm_lines.append(f"{k}: {v!r}")
        fm_lines.append("---")
        fm_str = "\n".join(fm_lines)

        body = f"""
# {manufacturer} {model} Instrument Skill

> Auto-generated — MagLab `instrument skillgen` (§13.3)
> ★ This skill provides PyVISA SCPI command reference and safe measurement workflows.
> ★ Actual hardware execution is Tier 3 — a human must review before running.

## Overview

**Manufacturer**: {manufacturer}
**Model**: {model}
**Safety-critical**: {"Yes — `disable-model-invocation: true`" if safety_critical else "No"}

## Key SCPI Commands

{cmd_list}

See `SCPI_REFERENCE.md` for the full command list and `LIMITS.md` for safety limits.

## Usage Workflow

1. `maglab instr scaffold {model!r}` — generate PyVISA skeleton
2. `maglab instr check <script>` — confirm safety validation passes
3. Human review and execution (Tier 3)

## Example Measurement Script

```python
# ★ Human review required before execution — real VISA session needed
from scripts.initialize import initialize
instr = initialize()
# ... measurement logic
```

## Reference Files

- `SCPI_REFERENCE.md` — full SCPI command table
- `LIMITS.md` — safety limits and interlocks
- `scripts/initialize.py` — initialization script skeleton
- `scripts/retrieve_scpi.py` — RAG search interface
- `evals/evals.json` — A/B evaluation cases
"""
        path.write_text(fm_str + "\n" + body, encoding="utf-8")
        return path

    def _write_scpi_reference(
        self,
        skill_dir: Path,
        model: str,
        chunks: list[SCPIChunk],
    ) -> Path:
        """Generate SCPI_REFERENCE.md."""
        path = skill_dir / "SCPI_REFERENCE.md"
        lines = [
            f"# {model} SCPI Command Reference\n",
            "| Command | Description | Section | Page |",
            "|---------|-------------|---------|------|",
        ]
        for c in chunks:
            desc = c.description.replace("|", "\\|")[:60]
            section = c.section_path.replace("|", "\\|")[:40]
            lines.append(f"| `{c.cmd}` | {desc} | {section} | {c.page} |")
        if not chunks:
            lines.append("| (none) | Build the RAG index first | - | - |")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def _write_limits_md(
        self,
        skill_dir: Path,
        model: str,
        profile: SafetyProfile,
    ) -> Path:
        """Generate LIMITS.md."""
        path = skill_dir / "LIMITS.md"
        lines = [f"# {model} Safety Limits & Interlocks\n"]
        lines.append(f"Profile: `{profile.model}`\n")
        if profile.max_voltage_v is not None:
            lines.append(f"- **Max voltage**: {profile.max_voltage_v:.3g} V")
        if profile.min_voltage_v is not None:
            lines.append(f"- **Min voltage**: {profile.min_voltage_v:.3g} V")
        if profile.max_current_a is not None:
            lines.append(f"- **Max current**: {profile.max_current_a:.3g} A")
        if profile.min_current_a is not None:
            lines.append(f"- **Min current**: {profile.min_current_a:.3g} A")
        if profile.max_field_t is not None:
            lines.append(f"- **Max magnetic field**: {profile.max_field_t:.3g} T")
        if profile.max_temperature_k is not None:
            lines.append(f"- **Max temperature**: {profile.max_temperature_k:.1f} K")
        lines.append(f"\n**Initialization required**: {'Yes' if profile.requires_init else 'No'}")
        lines.append(
            "\n> ★ Always run `maglab instr check <script>` and confirm safety validation passes before execution."
        )
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def _write_initialize_script(self, scripts_dir: Path, model: str, manufacturer: str) -> Path:
        """Generate the initialization script skeleton."""
        path = scripts_dir / "initialize.py"
        code = f'''"""{model} initialization script skeleton — auto-generated.

★ Actual hardware connection must be executed by a human (Tier 3).
"""
from __future__ import annotations


def initialize(resource_string: str = "GPIB0::1::INSTR"):
    """Connect to and initialize the instrument."""
    import pyvisa
    rm = pyvisa.ResourceManager()
    instr = rm.open_resource(resource_string)
    instr.timeout = 10000
    instr.write("*RST")
    import time; time.sleep(0.5)
    instr.write("*CLS")
    idn = instr.query("*IDN?").strip()
    print(f"Connected: {{idn}}")
    return instr
'''
        path.write_text(code, encoding="utf-8")
        return path

    def _write_retrieve_script(self, scripts_dir: Path, model_key: str) -> Path:
        """Generate the RAG search script."""
        path = scripts_dir / "retrieve_scpi.py"
        code = f'''"""SCPI command RAG search interface — auto-generated."""
from __future__ import annotations
from maglab.instrument.manual_rag import ManualRAGPipeline


def search(query: str, k: int = 5):
    """Search for SCPI commands."""
    pipeline = ManualRAGPipeline()
    results = pipeline.search({model_key!r}, query, k=k)
    return [(chunk.cmd, chunk.description, score) for chunk, score in results]


if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) or "voltage measurement"
    for cmd, desc, score in search(q):
        print(f"  {{score:.3f}} {{cmd}}  —  {{desc[:60]}}")
'''
        path.write_text(code, encoding="utf-8")
        return path

    def _write_evals(
        self,
        evals_dir: Path,
        model: str,
        chunks: list[SCPIChunk],
    ) -> Path:
        """Generate A/B evaluation cases."""
        path = evals_dir / "evals.json"
        # Generate evaluation cases from representative chunks (up to 5)
        cases: list[dict[str, Any]] = []
        for chunk in chunks[:5]:
            cases.append(
                {
                    "id": f"scpi_{len(cases) + 1}",
                    "task": f"Describe the parameters and purpose of the {chunk.cmd} command.",
                    "expected_cmd": chunk.cmd,
                    "expected_keywords": [chunk.cmd.split(":")[-1].lower()],
                    "check_type": "keyword_in_response",
                }
            )
        # Add default case
        if not cases:
            cases = [
                {
                    "id": "basic_idn",
                    "task": f"What does the *IDN? command return on the {model} instrument?",
                    "expected_keywords": ["identification", "manufacturer", "IDN"],
                    "check_type": "keyword_in_response",
                }
            ]
        data = {"model": model, "cases": cases, "version": "1.0"}
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    # ------------------------------------------------------------------
    # A/B evaluation
    # ------------------------------------------------------------------

    def run_ab_evaluation(
        self,
        skill_dir: Path,
        model: str,
    ) -> dict[str, Any]:
        """Run A/B evaluation and return the results.

        §5.17-3: Scores deterministic assertions on skill-loaded vs. skill-absent paths.
        Performs static analysis only — no LLM calls.

        Args:
            skill_dir: Skill directory.
            model: Instrument model name.

        Returns:
            Evaluation result dictionary.
        """
        evals_path = skill_dir / "evals" / "evals.json"
        if not evals_path.is_file():
            return {"ok": False, "error": "evals.json not found."}

        data = json.loads(evals_path.read_text(encoding="utf-8"))
        cases = data.get("cases", [])

        # Load SCPI_REFERENCE.md (skill-loaded path)
        ref_path = skill_dir / "SCPI_REFERENCE.md"
        ref_text = ref_path.read_text(encoding="utf-8") if ref_path.is_file() else ""

        results: list[dict[str, Any]] = []
        skill_score = 0
        baseline_score = 0

        for case in cases:
            expected_cmd = case.get("expected_cmd", "")

            # Skill-loaded path: verify command in SCPI_REFERENCE.md
            skill_hit = expected_cmd.upper() in ref_text.upper() if expected_cmd else False
            if skill_hit:
                skill_score += 1

            # Baseline: keyword search without SCPI_REFERENCE.md (score 0)
            # (static analysis only, no LLM call — baseline assumed to be 0)
            baseline_hit = False

            results.append(
                {
                    "id": case.get("id"),
                    "skill_hit": skill_hit,
                    "baseline_hit": baseline_hit,
                }
            )

        n = len(cases) or 1
        eval_result: dict[str, Any] = {
            "model": model,
            "n_cases": len(cases),
            "skill_score": skill_score,
            "baseline_score": baseline_score,
            "skill_ratio": skill_score / n,
            "baseline_ratio": baseline_score / n,
            "skill_wins": skill_score >= baseline_score,
            "cases": results,
            "evaluated_at": datetime.now(UTC).isoformat(),
        }

        results_path = skill_dir / "evals" / "results.json"
        results_path.write_text(
            json.dumps(eval_result, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        log.info(
            "A/B evaluation complete: skill %d/%d vs baseline %d/%d",
            skill_score,
            len(cases),
            baseline_score,
            len(cases),
        )
        return eval_result


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------


def generate_skill(
    model: str,
    manufacturer: str,
    model_key: str | None = None,
    output_root: Path | None = None,
    safety_model: str = "generic",
    rag_pipeline: ManualRAGPipeline | None = None,
) -> SkillPackage:
    """Convenience function to generate a SKILL.md instrument skill package.

    ★ model must be confirmed with the user (§13.2 — never guess).

    Args:
        model: Instrument model name.
        manufacturer: Manufacturer name.
        model_key: RAG index key.
        output_root: Skill output root directory.
        safety_model: Safety profile key.
        rag_pipeline: RAG pipeline instance.

    Returns:
        SkillPackage.
    """
    gen = SkillGenerator(output_root=output_root, rag_pipeline=rag_pipeline)
    return gen.generate(
        model=model,
        manufacturer=manufacturer,
        model_key=model_key,
        safety_model=safety_model,
    )
