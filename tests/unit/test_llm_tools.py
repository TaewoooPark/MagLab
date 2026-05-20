"""Tests for the MagLab LLM tool registry."""

from __future__ import annotations

from pathlib import Path

import pytest

from maglab.llm.tools import call_tool, get_registered_tools, get_tool_definition


def test_bundled_llm_tools_are_registered() -> None:
    names = {tool.name for tool in get_registered_tools()}

    assert "workspace_context" in names
    assert "workspace_tree" in names
    assert "workspace_read_file" in names
    assert "workspace_search" in names
    assert "physics_compute" in names
    assert "material_build" in names
    assert "list_effects" in names
    assert "fit_effect" in names
    assert "symmetry_allowed" in names
    assert "analysis_consistency" in names
    assert "sim_design" in names
    assert "sim_validate" in names
    assert "sim_run" in names
    assert "sim_parse" in names
    assert "sim_doctor" in names
    assert "maglab_doctor" in names
    assert "figure_design" in names
    assert "figure_compose" in names
    assert "figure_render" in names
    assert "figure_export" in names
    assert "figure_list_primitives" in names
    assert "figure_show_primitive" in names
    assert "literature_search" in names
    assert "literature_find_authors" in names
    assert "literature_keywords" in names
    assert "journal_metrics" in names
    assert "instr_search_manual" in names
    assert "instr_ingest_manual" in names
    assert "instr_generate_skill" in names
    assert "instr_scaffold" in names
    assert "instr_safety_check" in names
    assert "reviewer_build_panel" in names
    assert "reviewer_run_review" in names
    assert "authoring_draft_section" in names
    assert "authoring_verify_citations" in names
    assert "comms_draft" in names
    assert "report_build" in names
    assert "provenance_query" in names


def test_tool_schema_preserves_dict_parameters() -> None:
    definition = get_tool_definition("physics_compute")

    assert definition is not None
    params = definition.parameters["properties"]
    assert params["params"]["type"] == "object"


def test_workspace_read_file_is_scoped_to_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "notes.md").write_text("sample text\n", encoding="utf-8")

    result = call_tool("workspace_read_file", {"path": "notes.md"})
    assert result["ok"] is True
    assert result["path"] == "notes.md"
    assert "sample text" in result["content"]

    escaped = call_tool("workspace_read_file", {"path": str(tmp_path.parent / "outside.md")})
    assert escaped["ok"] is False
    assert "escapes active workspace" in escaped["error"]


def test_workspace_read_file_uses_workspace_ignore_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "docs" / "generated").mkdir(parents=True)
    (tmp_path / "docs" / "generated" / "api.md").write_text("generated\n", encoding="utf-8")

    result = call_tool("workspace_read_file", {"path": "docs/generated/api.md"})

    assert result["ok"] is False
    assert "ignored" in result["error"]


def test_workspace_context_includes_marker_and_key_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "MAGLAB.md").write_text("# Project\nSpin Hall context\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Readme\n", encoding="utf-8")
    (tmp_path / "data").mkdir()

    result = call_tool("workspace_context", {"max_entries": 10, "max_maglab_chars": 100})

    assert result["ok"] is True
    assert result["root"] == str(tmp_path)
    assert result["maglab_md"] == str(tmp_path / "MAGLAB.md")
    assert "Spin Hall context" in result["maglab_md_excerpt"]
    assert "README.md" in result["key_paths"]
    assert "data/" in result["key_paths"]
    assert "Before answering project-specific questions" in result["prompt"]


def test_workspace_context_prunes_ignored_heavy_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "MAGLAB.md").write_text("# Project\n", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "hidden.js").write_text("should not appear\n", encoding="utf-8")
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "workflow.yml").write_text("ci\n", encoding="utf-8")
    (tmp_path / ".maglab" / "cache").mkdir(parents=True)
    (tmp_path / ".maglab" / "cache" / "font.json").write_text("cache\n", encoding="utf-8")
    (tmp_path / ".maglab" / "runtime").mkdir(parents=True)
    (tmp_path / ".maglab" / "runtime" / "budget.db").write_text("runtime\n", encoding="utf-8")
    (tmp_path / ".playwright-mcp").mkdir()
    (tmp_path / ".playwright-mcp" / "page.yml").write_text("runtime\n", encoding="utf-8")
    (tmp_path / "pkg.egg-info").mkdir()
    (tmp_path / "pkg.egg-info" / "PKG-INFO").write_text("generated\n", encoding="utf-8")
    (tmp_path / "docs" / "generated").mkdir(parents=True)
    (tmp_path / "docs" / "generated" / "api.md").write_text("generated\n", encoding="utf-8")
    (tmp_path / "impl" / "review").mkdir(parents=True)
    (tmp_path / "impl" / "review" / "audit.md").write_text("generated\n", encoding="utf-8")
    (tmp_path / "tests" / "fixtures").mkdir(parents=True)
    (tmp_path / "tests" / "fixtures" / "sample.txt").write_text("fixture\n", encoding="utf-8")
    (tmp_path / "notes.md").write_text("visible\n", encoding="utf-8")

    result = call_tool("workspace_context", {"max_entries": 20})

    assert result["ok"] is True
    assert "notes.md" in result["entries"]
    assert "node_modules/" not in result["entries"]
    assert all("hidden.js" not in entry for entry in result["entries"])
    assert all(".github" not in entry for entry in result["entries"])
    assert all(".maglab" not in entry for entry in result["entries"])
    assert all(".playwright-mcp" not in entry for entry in result["entries"])
    assert all(".egg-info" not in entry for entry in result["entries"])
    assert all("docs/generated" not in entry for entry in result["entries"])
    assert all("impl/review" not in entry for entry in result["entries"])
    assert all("tests/fixtures" not in entry for entry in result["entries"])


def test_workspace_tree_tool_supports_type_and_depth_filters(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "analysis.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "sample.csv").write_text("x,y\n0,0\n", encoding="utf-8")

    docs = call_tool("workspace_tree", {"entry_type": "docs", "max_depth": 1})
    code = call_tool("workspace_tree", {"entry_type": "code"})
    data = call_tool("workspace_tree", {"entry_type": "data"})

    assert docs["ok"] is True
    assert docs["entries"] == ["README.md"]
    assert "src/analysis.py" in code["entries"]
    assert "data/sample.csv" in data["entries"]


def test_workspace_search_returns_line_matches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "MAGLAB.md").write_text("alpha\nspin Hall signal\n", encoding="utf-8")

    result = call_tool("workspace_search", {"pattern": "spin Hall", "glob": "*.md"})
    assert result["ok"] is True
    assert result["matches"] == [{"path": "MAGLAB.md", "line": 2, "text": "spin Hall signal"}]


def test_workspace_search_uses_workspace_ignore_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "docs" / "generated").mkdir(parents=True)
    (tmp_path / "docs" / "generated" / "api.md").write_text("hidden spin Hall\n", encoding="utf-8")
    (tmp_path / "notes.md").write_text("visible spin Hall\n", encoding="utf-8")

    result = call_tool("workspace_search", {"pattern": "spin Hall", "glob": "*.md"})

    assert result["ok"] is True
    assert result["matches"] == [{"path": "notes.md", "line": 1, "text": "visible spin Hall"}]


def test_physics_compute_tool_returns_deterministic_result() -> None:
    result = call_tool(
        "physics_compute",
        {"formula": "exchange_length", "params": {"A": 1.3e-11, "Ms": 8.0e5}},
    )

    assert result["ok"] is True
    assert result["formula"] == "exchange_length"
    assert result["result"] > 0


def test_material_build_tool_uses_offline_sources() -> None:
    result = call_tool("material_build", {"stack": "Permalloy(5)/MgO(2)"})

    assert result["ok"] is True
    assert result["stack_str"] == "Permalloy(5)/MgO(2)"
    assert result["layers"]


def test_analysis_tools_list_fit_and_symmetry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    csv_path = tmp_path / "hall.csv"
    csv_path.write_text("B,rho_xy\n-1,-2e-10\n0,0\n1,2e-10\n", encoding="utf-8")

    listed = call_tool("list_effects", {})
    fit = call_tool("fit_effect", {"effect": "ordinary_hall", "data_path": "hall.csv"})
    symmetry = call_tool("symmetry_allowed", {"point_group": "m3m"})

    assert listed["ok"] is True
    assert any(effect["name"] == "ordinary_hall" for effect in listed["effects"])
    assert fit["ok"] is True
    assert fit["path"] == "hall.csv"
    assert "R_H" in fit["params"]
    assert symmetry["ok"] is True
    assert symmetry["ahe_allowed"] is True


def test_analysis_consistency_carrier_density_check() -> None:
    result = call_tool(
        "analysis_consistency",
        {
            "carrier": {
                "r_0": 1.0e-10,
                "r_0_unc": 1.0e-12,
                "n_hall": 6.2e28,
                "n_hall_unc": 1.0e27,
                "rtol": 0.5,
            }
        },
    )

    assert result["ok"] is True
    assert result["trigger_explain"] is False


def test_sim_design_and_parse_tools_use_structured_specs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    spec = {
        "name": "py_smoke",
        "scales": [
            {
                "scale": "micro",
                "engine": "magnumnp",
                "material": {"Ms_Am": 8.0e5, "A_Jm": 1.3e-11, "alpha": 0.02},
                "geometry": {"nx": 4, "ny": 4, "nz": 1, "dx_nm": 5, "dy_nm": 5, "dz_nm": 5},
            }
        ],
    }
    designed = call_tool("sim_design", {"spec_dict": spec})
    assert designed["ok"] is True
    assert designed["scale_count"] == 1

    table = tmp_path / "table.txt"
    table.write_text("# t (s)\tmx ()\n0.0\t1.0\n", encoding="utf-8")
    parsed = call_tool("sim_parse", {"engine": "mumax3", "output_path": "table.txt"})
    assert parsed["ok"] is True
    assert parsed["result"]["engine"] == "mumax3"
    assert "mx" in parsed["result"]["quantities"]


def test_figure_primitive_tools_expose_catalog() -> None:
    listed = call_tool("figure_list_primitives", {"query": "hall", "max_results": 5})

    assert listed["ok"] is True
    assert listed["primitives"]
    first_name = listed["primitives"][0]["name"]

    shown = call_tool("figure_show_primitive", {"name": first_name})
    assert shown["ok"] is True
    assert shown["name"] == first_name


def test_figure_design_and_compose_tools_validate_renderability() -> None:
    spec = {
        "figure_id": "schematic_smoke",
        "journal": "prl",
        "column_width": "single",
        "layout": {"nrows": 1, "ncols": 1},
        "panels": [
            {
                "panel_id": "a",
                "panel_type": "schematic",
                "title": "Stack",
                "extra": {"kind": "stack"},
            }
        ],
    }

    designed = call_tool("figure_design", {"spec_dict": spec})
    composed = call_tool("figure_compose", {"spec_dict": spec})

    assert designed["ok"] is True
    assert designed["journal"] == "aps"
    assert designed["panel_count"] == 1
    assert composed["ok"] is True
    assert composed["axes_count"] == 1


def test_literature_keywords_and_journal_metrics_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    from maglab.literature.keywords import WeightedKeyword

    def fake_keywords(texts, *, top_n=30, ngram_range=(1, 3), rerank_fn=None):
        return [
            WeightedKeyword(
                keyword="spin hall",
                score=1.0,
                tfidf_score=1.0,
                source_methods=["tfidf"],
            )
        ][:top_n]

    monkeypatch.setattr("maglab.literature.keywords.extract_keywords_from_texts", fake_keywords)

    keywords = call_tool("literature_keywords", {"texts": ["spin Hall effect"], "top_n": 1})
    metrics = call_tool(
        "journal_metrics", {"journal_name": "Physical Review Letters", "use_openalex": False}
    )

    assert keywords["ok"] is True
    assert keywords["keywords"][0]["keyword"] == "spin hall"
    assert metrics["ok"] is True
    assert "Impact Factor" not in str(metrics)


def test_instrument_safety_and_provenance_tools(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "run_provenance.json").write_text('{"activity":"fit"}\n', encoding="utf-8")

    unsafe = call_tool(
        "instr_safety_check",
        {"model": "keithley-2400", "commands": [":SOUR:VOLT 999"]},
    )
    provenance = call_tool("provenance_query", {})

    assert unsafe["ok"] is False
    assert unsafe["violations"]
    assert provenance["ok"] is True
    assert provenance["artifacts"][0]["path"] == "run_provenance.json"


def test_sim_run_mock_backend_writes_workspace_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    blocked = call_tool("sim_run", {"backend": "local"})
    result = call_tool("sim_run", {"backend": "mock", "work_dir": "runs/pipeline"})

    assert blocked["ok"] is False
    assert "allow_real=True" in blocked["error"]
    assert result["ok"] is True
    assert result["backend"] == "mock"
    assert result["path"] == "runs/pipeline"
    assert (tmp_path / "runs" / "pipeline" / "pipeline_result.json").is_file()


def test_instrument_scaffold_tool_generates_workspace_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    result = call_tool(
        "instr_scaffold",
        {"model": "SR-830", "iface": "GPIB", "output_path": "generated/sr830.py"},
    )

    assert result["ok"] is True
    assert result["output_path"] == "generated/sr830.py"
    assert "class Sr830" in result["code"]
    assert (tmp_path / "generated" / "sr830.py").is_file()


def test_reviewer_tools_build_and_run_dummy_panel() -> None:
    panel = call_tool("reviewer_build_panel", {"journal": "general"})
    review = call_tool(
        "reviewer_run_review",
        {"journal": "general", "manuscript": "We report a spin Hall measurement."},
    )

    assert panel["ok"] is True
    assert len(panel["personas"]) == 3
    assert panel["rubric"]["journal"] == "general"
    assert review["ok"] is True
    assert len(review["reviews"]) == 3
    assert all("AI Reviewer" in item["review_text"] for item in review["reviews"])


def test_authoring_tools_draft_and_verify_guarded_text() -> None:
    drafted = call_tool(
        "authoring_draft_section",
        {
            "section": "methods",
            "context": "Samples were grown by pulsed laser deposition.",
        },
    )
    verified = call_tool(
        "authoring_verify_citations",
        {"draft_tex": "No citation is used in this deterministic smoke draft."},
    )

    assert drafted["ok"] is True
    assert drafted["section"] == "methods"
    assert "HUMAN REVIEW REQUIRED" in drafted["tex"]
    assert verified["ok"] is True
    assert verified["missing_keys"] == []


def test_comms_draft_tool_marks_human_review_required() -> None:
    result = call_tool(
        "comms_draft",
        {
            "kind": "email",
            "inputs": {
                "email_type": "question",
                "recipient": "Professor [FILL: name]",
                "topic": "spin Hall metrology follow-up",
            },
        },
    )

    assert result["ok"] is True
    assert result["text"].startswith("HUMAN REVIEW REQUIRED")
    assert result["fill_markers"]


def test_report_build_writes_workspace_inventory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "tasks").mkdir()
    (tmp_path / "tasks" / "task.md").write_text("# Task\n", encoding="utf-8")

    result = call_tool("report_build", {"output_path": "reports/inventory.json"})

    assert result["ok"] is True
    assert result["path"] == "reports/inventory.json"
    assert (tmp_path / "reports" / "inventory.json").is_file()
    assert "tasks" in result["counts"]
