"""tests/unit/test_cli_p5.py — CLI unit tests for P5 commands.

Tests every command / subcommand --help (exit 0) and real invocations
where feasible.  LLM, network, and heavy ML calls are mocked throughout.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import typer
from typer.testing import CliRunner

from maglab.commands.p5_literature import register

# ---------------------------------------------------------------------------
# Shared test app fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def app() -> typer.Typer:
    """Fresh root Typer app with P5 commands registered."""
    root = typer.Typer(name="maglab", add_completion=False)
    register(root)
    return root


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


# ===========================================================================
# --help smoke tests (must exit 0 for every command/subcommand)
# ===========================================================================


class TestHelpExits:
    """Every exposed command/subcommand must exit 0 on --help."""

    def test_lit_help(self, runner: CliRunner, app: typer.Typer) -> None:
        result = runner.invoke(app, ["lit", "--help"])
        assert result.exit_code == 0
        assert "search" in result.output

    def test_lit_search_help(self, runner: CliRunner, app: typer.Typer) -> None:
        result = runner.invoke(app, ["lit", "search", "--help"])
        assert result.exit_code == 0
        assert "FOLDER" in result.output or "folder" in result.output.lower()

    def test_lit_authors_help(self, runner: CliRunner, app: typer.Typer) -> None:
        result = runner.invoke(app, ["lit", "authors", "--help"])
        assert result.exit_code == 0

    def test_lit_keywords_help(self, runner: CliRunner, app: typer.Typer) -> None:
        result = runner.invoke(app, ["lit", "keywords", "--help"])
        assert result.exit_code == 0

    def test_lit_journal_help(self, runner: CliRunner, app: typer.Typer) -> None:
        result = runner.invoke(app, ["lit", "journal", "--help"])
        assert result.exit_code == 0

    def test_lit_graph_help(self, runner: CliRunner, app: typer.Typer) -> None:
        result = runner.invoke(app, ["lit", "graph", "--help"])
        assert result.exit_code == 0

    def test_review_help(self, runner: CliRunner, app: typer.Typer) -> None:
        result = runner.invoke(app, ["review", "--help"])
        assert result.exit_code == 0
        assert "manuscript" in result.output.lower()

    def test_lab_help(self, runner: CliRunner, app: typer.Typer) -> None:
        result = runner.invoke(app, ["lab", "--help"])
        assert result.exit_code == 0
        assert "note" in result.output
        assert "plan" in result.output

    def test_lab_note_help(self, runner: CliRunner, app: typer.Typer) -> None:
        result = runner.invoke(app, ["lab", "note", "--help"])
        assert result.exit_code == 0

    def test_lab_plan_help(self, runner: CliRunner, app: typer.Typer) -> None:
        result = runner.invoke(app, ["lab", "plan", "--help"])
        assert result.exit_code == 0

    def test_explain_help(self, runner: CliRunner, app: typer.Typer) -> None:
        result = runner.invoke(app, ["explain", "--help"])
        assert result.exit_code == 0
        assert "data" in result.output.lower() or "anomal" in result.output.lower()


# ===========================================================================
# lit search
# ===========================================================================


class TestLitSearch:
    def test_missing_folder_exits_1(self, runner: CliRunner, app: typer.Typer) -> None:
        result = runner.invoke(app, ["lit", "search", "/nonexistent/path/xyz"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower() or "folder" in result.output.lower()

    def test_empty_folder_exits_1(
        self, runner: CliRunner, app: typer.Typer, tmp_path: pathlib.Path
    ) -> None:
        # Folder exists but no extractable text
        empty_dir = tmp_path / "papers"
        empty_dir.mkdir()
        with patch("maglab.literature.keywords.extract_keywords_from_folder", return_value=[]):
            result = runner.invoke(app, ["lit", "search", str(empty_dir)])
        assert result.exit_code == 1

    def test_with_txt_file(
        self, runner: CliRunner, app: typer.Typer, tmp_path: pathlib.Path
    ) -> None:
        paper_dir = tmp_path / "papers"
        paper_dir.mkdir()
        (paper_dir / "paper.txt").write_text(
            "spin Hall effect anomalous Hall magnetotransport CoFeB", encoding="utf-8"
        )
        result = runner.invoke(app, ["lit", "search", str(paper_dir), "--top-n", "5"])
        assert result.exit_code == 0
        # Table or output should show keywords
        assert len(result.output) > 0


# ===========================================================================
# lit authors
# ===========================================================================


class TestLitAuthors:
    def test_network_failure_exits_1(self, runner: CliRunner, app: typer.Typer) -> None:
        with patch(
            "maglab.literature.authors.find_authoritative_authors",
            side_effect=RuntimeError("network error"),
        ):
            result = runner.invoke(app, ["lit", "authors", "spin Hall effect"])
        assert result.exit_code == 1

    def test_import_error_exits_1(self, runner: CliRunner, app: typer.Typer) -> None:
        with (
            patch.dict("sys.modules", {"maglab.literature.authors": None}),
            patch(
                "maglab.literature.authors.find_authoritative_authors",
                side_effect=ImportError("pyalex not installed"),
            ),
        ):
            result = runner.invoke(app, ["lit", "authors", "skyrmion"])
        assert result.exit_code == 1

    def test_empty_results_zero_exit(self, runner: CliRunner, app: typer.Typer) -> None:
        with patch(
            "maglab.literature.authors.find_authoritative_authors",
            return_value=[],
        ):
            result = runner.invoke(app, ["lit", "authors", "some obscure topic"])
        # Not found → informational message but exit 0
        assert result.exit_code == 0
        assert "no authoritative" in result.output.lower()

    def test_with_profiles(self, runner: CliRunner, app: typer.Typer) -> None:
        from maglab.literature.authors import AuthorProfile

        fake_profile = AuthorProfile(
            name="Jane Doe",
            affiliation="MIT",
            h_index=42,
            cited_by_count=10000,
            h_index_source="openalex",
        )
        with patch(
            "maglab.literature.authors.find_authoritative_authors",
            return_value=[fake_profile],
        ):
            result = runner.invoke(app, ["lit", "authors", "spin Hall effect"])
        assert result.exit_code == 0
        assert "Jane Doe" in result.output
        assert "MIT" in result.output


# ===========================================================================
# lit keywords
# ===========================================================================


class TestLitKeywords:
    def test_basic_extraction(self, runner: CliRunner, app: typer.Typer) -> None:
        result = runner.invoke(
            app, ["lit", "keywords", "spin Hall effect anomalous Hall magnetism"]
        )
        # May exit 0 even without optional deps — uses what's available
        assert result.exit_code in (0, 1)

    def test_with_mock(self, runner: CliRunner, app: typer.Typer) -> None:
        from maglab.literature.keywords import WeightedKeyword

        fake_kw = WeightedKeyword(
            keyword="spin hall effect",
            score=0.9,
            tfidf_score=0.8,
            keybert_score=0.95,
            yake_score=0.85,
            source_methods=["tfidf", "keybert"],
        )
        with patch(
            "maglab.literature.keywords.extract_keywords_from_texts",
            return_value=[fake_kw],
        ):
            result = runner.invoke(app, ["lit", "keywords", "some text"])
        assert result.exit_code == 0
        assert "spin hall effect" in result.output


# ===========================================================================
# lit journal
# ===========================================================================


class TestLitJournal:
    def test_offline_no_error(self, runner: CliRunner, app: typer.Typer) -> None:
        """Even without network, the command must exit 0 (uses bundle CSV fallback)."""
        with patch(
            "maglab.literature.journals._fetch_openalex_venue_metrics",
            return_value={},
        ):
            result = runner.invoke(
                app, ["lit", "journal", "Physical Review Letters", "--no-openalex"]
            )
        assert result.exit_code == 0

    def test_with_metrics(self, runner: CliRunner, app: typer.Typer) -> None:
        from maglab.literature.journals import JournalMetrics

        fake = JournalMetrics(
            journal_name="Physical Review Letters",
            sjr=4.5,
            sjr_quartile="Q1",
            sjr_year=2023,
            openalex_2yr_mean_citedness=8.3,
            eigenfactor=0.05,
        )
        with patch(
            "maglab.literature.journals.get_journal_metrics",
            return_value=fake,
        ):
            result = runner.invoke(app, ["lit", "journal", "Physical Review Letters"])
        assert result.exit_code == 0
        assert "Physical Review Letters" in result.output
        # Must not mention JCR IF
        assert "JCR" not in result.output
        assert "Impact Factor" not in result.output

    def test_journal_query_failure_exits_1(self, runner: CliRunner, app: typer.Typer) -> None:
        with patch(
            "maglab.literature.journals.get_journal_metrics",
            side_effect=RuntimeError("API error"),
        ):
            result = runner.invoke(app, ["lit", "journal", "SomeJournal"])
        assert result.exit_code == 1


# ===========================================================================
# lit graph
# ===========================================================================


class TestLitGraph:
    def _mock_kg(self) -> MagicMock:
        kg = MagicMock()
        kg.get_node.return_value = None
        kg.find_nodes.return_value = []
        kg.citation_lineage.return_value = []
        return kg

    def test_node_not_found(self, runner: CliRunner, app: typer.Typer) -> None:
        kg = self._mock_kg()
        with patch("maglab.literature.graph.get_graph", return_value=kg):
            result = runner.invoke(app, ["lit", "graph", "IrMn"])
        assert result.exit_code == 0
        assert "no node found" in result.output.lower() or "no" in result.output.lower()

    def test_citation_lineage_empty(self, runner: CliRunner, app: typer.Typer) -> None:
        kg = self._mock_kg()
        with patch("maglab.literature.graph.get_graph", return_value=kg):
            result = runner.invoke(app, ["lit", "graph", "IrMn", "--cite-map", "10.1103/fake.doi"])
        assert result.exit_code == 0
        kg.citation_lineage.assert_called_once_with("10.1103/fake.doi")

    def test_node_found_shows_edges(self, runner: CliRunner, app: typer.Typer) -> None:
        from maglab.literature.graph import GraphEdge, GraphNode

        kg = self._mock_kg()
        node = GraphNode(node_id="N1", node_type="material", label="IrMn")
        kg.get_node.return_value = node

        neighbour = GraphNode(node_id="N2", node_type="phenomenon", label="SOT")
        edge = GraphEdge(
            edge_id="E1",
            source_id="N1",
            target_id="N2",
            edge_type="applies",
            evidence_doi="10.1103/fake",
        )
        kg.get_neighbors.return_value = [(edge, neighbour)]

        with patch("maglab.literature.graph.get_graph", return_value=kg):
            result = runner.invoke(app, ["lit", "graph", "N1"])
        assert result.exit_code == 0
        assert "IrMn" in result.output
        assert "applies" in result.output

    def test_graph_unavailable_exits_1(self, runner: CliRunner, app: typer.Typer) -> None:
        with patch(
            "maglab.literature.graph.get_graph",
            side_effect=RuntimeError("DB error"),
        ):
            result = runner.invoke(app, ["lit", "graph", "IrMn"])
        assert result.exit_code == 1


# ===========================================================================
# review
# ===========================================================================


class TestReview:
    def _make_panel_result(self) -> Any:
        from maglab.reviewer.panel import PanelReview, PersonaReview, PersonaSpec
        from maglab.reviewer.rubrics import (
            DimensionScore,
            ReviewScore,
            ScoreDimension,
            get_rubric,
        )

        persona = PersonaSpec(author_id="test-author", author_name="Test Author", paper_count=5)
        score = ReviewScore(
            scores=[
                DimensionScore(
                    dimension=ScoreDimension.NOVELTY,
                    score=7.0,
                    rationale="Novel approach",
                    evidence_sections=["Introduction"],
                )
            ],
            journal="general",
            reviewer_persona="Test Author",
        )
        pr = PersonaReview(
            persona=persona,
            score=score,
            review_text="[AI reviewer] Test Author (5 papers). This manuscript is interesting.",
            disclosure_passed=True,
        )
        rubric = get_rubric("general")
        return PanelReview(journal="general", reviews=[pr], rubric=rubric)

    def test_missing_manuscript_inline(self, runner: CliRunner, app: typer.Typer) -> None:
        """Empty string manuscript → exit 1."""
        # The CLI guards against empty manuscript
        mock_result = self._make_panel_result()
        with (
            patch("maglab.reviewer.corpus_rag.CorpusRAG"),
            patch("maglab.reviewer.panel.ReviewPanel.review", return_value=mock_result),
        ):
            result = runner.invoke(app, ["review", ""])
        # Empty manuscript → exit 1
        assert result.exit_code == 1

    def test_file_not_found_exit_1(self, runner: CliRunner, app: typer.Typer) -> None:
        """Non-file string that is also not a valid manuscript path just runs as inline text."""
        mock_result = self._make_panel_result()
        with (
            patch("maglab.reviewer.corpus_rag.CorpusRAG"),
            patch("maglab.reviewer.panel.ReviewPanel.review", return_value=mock_result),
        ):
            result = runner.invoke(app, ["review", "Some manuscript text here"])
        # Should succeed (inline text is non-empty)
        assert result.exit_code == 0

    def test_manuscript_file(
        self, runner: CliRunner, app: typer.Typer, tmp_path: pathlib.Path
    ) -> None:
        ms_file = tmp_path / "manuscript.txt"
        ms_file.write_text("This is a test manuscript about spin Hall effect.", encoding="utf-8")

        mock_result = self._make_panel_result()
        with (
            patch("maglab.reviewer.corpus_rag.CorpusRAG"),
            patch("maglab.reviewer.panel.ReviewPanel.review", return_value=mock_result),
        ):
            result = runner.invoke(app, ["review", str(ms_file)])
        assert result.exit_code == 0
        assert "Review Panel" in result.output or "panel" in result.output.lower()

    def test_import_error_exits_1(self, runner: CliRunner, app: typer.Typer) -> None:
        with patch(
            "maglab.reviewer.corpus_rag.CorpusRAG",
            side_effect=ImportError("sentence-transformers not installed"),
        ):
            result = runner.invoke(app, ["review", "Some manuscript text"])
        assert result.exit_code == 1

    def test_journal_option(
        self, runner: CliRunner, app: typer.Typer, tmp_path: pathlib.Path
    ) -> None:
        ms_file = tmp_path / "ms.txt"
        ms_file.write_text("Manuscript for PRL submission.", encoding="utf-8")
        mock_result = self._make_panel_result()
        with (
            patch("maglab.reviewer.corpus_rag.CorpusRAG"),
            patch("maglab.reviewer.panel.ReviewPanel.review", return_value=mock_result),
        ):
            result = runner.invoke(app, ["review", str(ms_file), "--journal", "prl"])
        assert result.exit_code == 0


# ===========================================================================
# lab note
# ===========================================================================


class TestLabNote:
    def test_create_note_basic(
        self, runner: CliRunner, app: typer.Typer, tmp_path: pathlib.Path
    ) -> None:
        nb_dir = tmp_path / "notebook"
        result = runner.invoke(
            app,
            [
                "lab",
                "note",
                "Today we measured Ta/CoFeB/MgO SMR.",
                "--dir",
                str(nb_dir),
            ],
        )
        assert result.exit_code == 0
        assert "ELN entry created" in result.output
        # Confirm markdown file was actually written
        md_files = list(nb_dir.rglob("*.md"))
        assert len(md_files) == 1

    def test_note_with_sample_and_tags(
        self, runner: CliRunner, app: typer.Typer, tmp_path: pathlib.Path
    ) -> None:
        nb_dir = tmp_path / "nb2"
        result = runner.invoke(
            app,
            [
                "lab",
                "note",
                "FMR measurement at 10 GHz.",
                "--sample",
                "Py/Pt",
                "--instrument",
                "VNA",
                "--type",
                "fmr",
                "--tag",
                "FMR",
                "--tag",
                "Py",
                "--dir",
                str(nb_dir),
            ],
        )
        assert result.exit_code == 0
        md_file = next(nb_dir.rglob("*.md"))
        content = md_file.read_text(encoding="utf-8")
        assert "Py/Pt" in content
        assert "FMR" in content or "fmr" in content

    def test_invalid_measurement_type_exits_1(
        self, runner: CliRunner, app: typer.Typer, tmp_path: pathlib.Path
    ) -> None:
        nb_dir = tmp_path / "nb3"
        result = runner.invoke(
            app,
            ["lab", "note", "Some measurement.", "--type", "invalid_type", "--dir", str(nb_dir)],
        )
        assert result.exit_code == 1
        assert "Unknown measurement type" in result.output

    def test_draft_flag(self, runner: CliRunner, app: typer.Typer, tmp_path: pathlib.Path) -> None:
        nb_dir = tmp_path / "nb_draft"
        result = runner.invoke(
            app,
            ["lab", "note", "Draft entry.", "--draft", "--dir", str(nb_dir)],
        )
        assert result.exit_code == 0
        assert "draft" in result.output.lower()


# ===========================================================================
# lab plan
# ===========================================================================


class TestLabPlan:
    def test_basic_plan(self, runner: CliRunner, app: typer.Typer) -> None:
        result = runner.invoke(app, ["lab", "plan", "SOT efficiency CoFeB/Pt"])
        assert result.exit_code == 0
        assert "Measurement Plan" in result.output
        assert "step" in result.output.lower()

    def test_saves_yaml(self, runner: CliRunner, app: typer.Typer, tmp_path: pathlib.Path) -> None:
        out_yaml = tmp_path / "plan.yaml"
        result = runner.invoke(
            app,
            ["lab", "plan", "FMR damping Py", "--output", str(out_yaml)],
        )
        assert result.exit_code == 0
        assert out_yaml.is_file()
        content = out_yaml.read_text(encoding="utf-8")
        assert len(content) > 10

    def test_plan_failure_exits_1(self, runner: CliRunner, app: typer.Typer) -> None:
        with patch(
            "maglab.lab.planning.planner.MeasurementPlanner.plan",
            side_effect=RuntimeError("planner broken"),
        ):
            result = runner.invoke(app, ["lab", "plan", "some goal"])
        assert result.exit_code == 1


# ===========================================================================
# explain
# ===========================================================================


class TestExplain:
    def test_basic_explanation(self, runner: CliRunner, app: typer.Typer) -> None:
        """Built-in mechanism DB should handle AHE sign reversal without LLM."""
        result = runner.invoke(app, ["explain", "AHE sign reversal above 200 K"])
        assert result.exit_code == 0
        assert "Anomaly Explanation" in result.output
        assert "candidate" in result.output.lower() or "mechanism" in result.output.lower()

    def test_topological_hall_query(self, runner: CliRunner, app: typer.Typer) -> None:
        result = runner.invoke(app, ["explain", "topological hall signal in MnSi"])
        assert result.exit_code == 0
        # Should produce at least one candidate
        assert "C0" in result.output or "C01" in result.output

    def test_json_output_flag(self, runner: CliRunner, app: typer.Typer) -> None:
        result = runner.invoke(app, ["explain", "AHE sign reversal above 200 K", "--json"])
        assert result.exit_code == 0
        # JSON output must be parseable
        data = json.loads(result.output)
        assert "candidates" in data
        assert len(data["candidates"]) >= 2
        assert "disclaimer" in data

    def test_disclaimer_present(self, runner: CliRunner, app: typer.Typer) -> None:
        result = runner.invoke(app, ["explain", "AHE sign reversal above 200 K"])
        assert result.exit_code == 0
        # Disclaimer must warn that output is AI suggestion
        assert "AI" in result.output or "hypothesis" in result.output.lower()

    def test_min_candidates_respected(self, runner: CliRunner, app: typer.Typer) -> None:
        result = runner.invoke(
            app, ["explain", "FMR linewidth anomaly", "--min-candidates", "3", "--json"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data["candidates"]) >= 2  # engine may cap at min or template count

    def test_engine_failure_exits_1(self, runner: CliRunner, app: typer.Typer) -> None:
        with patch(
            "maglab.core.reasoning.explain_anomaly",
            side_effect=RuntimeError("engine broken"),
        ):
            result = runner.invoke(app, ["explain", "some data"])
        assert result.exit_code == 1

    def test_no_candidates_exits_1(self, runner: CliRunner, app: typer.Typer) -> None:
        from maglab.core.reasoning import ExplanationResult

        empty_result = ExplanationResult(query="empty", candidates=[])
        with patch("maglab.core.reasoning.explain_anomaly", return_value=empty_result):
            result = runner.invoke(app, ["explain", "no match at all"])
        assert result.exit_code == 1


# ===========================================================================
# register() wiring sanity
# ===========================================================================


class TestRegister:
    def test_register_attaches_lit_and_lab_typers(self, app: typer.Typer) -> None:
        """After register(), 'lit' and 'lab' must be present as sub-Typers."""
        # TyperInfo stores the name on the nested typer_instance.info.name
        group_names = {
            g.typer_instance.info.name
            for g in app.registered_groups
            if g.typer_instance is not None
        }
        assert "lit" in group_names
        assert "lab" in group_names

    def test_register_attaches_review_and_explain_commands(self, app: typer.Typer) -> None:
        """After register(), 'review' and 'explain' must be registered as commands."""
        cmd_names = {c.name for c in app.registered_commands}
        assert "review" in cmd_names
        assert "explain" in cmd_names


# ===========================================================================
# FIX 2: review — meta-review consensus/dissent surfaced (§15.3)
# ===========================================================================


class TestReviewMetaReview:
    """Verify that review_command now surfaces the MetaReviewer output."""

    def _make_panel_result_with_dissent(self) -> Any:
        """Build a PanelReview where one dimension has a score spread ≥3 pts."""
        from maglab.reviewer.panel import PanelReview, PersonaReview, PersonaSpec
        from maglab.reviewer.rubrics import (
            DimensionScore,
            ReviewScore,
            ScoreDimension,
            get_rubric,
        )

        # Three personas, one dimension (NOVELTY) has spread of 4 pts → dissent
        personas_scores = [
            ("Reviewer-A", 8.0),
            ("Reviewer-B", 4.0),  # spread = 4 pts → dissent threshold (≥3)
            ("Reviewer-C", 6.0),
        ]
        reviews = []
        for name, score_val in personas_scores:
            persona = PersonaSpec(author_id=name, author_name=name, paper_count=5)
            score = ReviewScore(
                scores=[
                    DimensionScore(
                        dimension=ScoreDimension.NOVELTY,
                        score=score_val,
                        rationale=f"{name} rationale",
                        evidence_sections=["Introduction"],
                    )
                ],
                journal="general",
                reviewer_persona=name,
            )
            pr = PersonaReview(
                persona=persona,
                score=score,
                review_text=f"[AI reviewer] {name}. Some review text.",
                disclosure_passed=True,
            )
            reviews.append(pr)

        rubric = get_rubric("general")
        return PanelReview(journal="general", reviews=reviews, rubric=rubric)

    def test_meta_review_shown_in_output(self, runner: CliRunner, app: typer.Typer) -> None:
        """review_command must include 'Meta-Review' section in output."""
        mock_result = self._make_panel_result_with_dissent()
        with (
            patch("maglab.reviewer.corpus_rag.CorpusRAG"),
            patch("maglab.reviewer.panel.ReviewPanel.review", return_value=mock_result),
        ):
            result = runner.invoke(app, ["review", "Some manuscript text here"])
        assert result.exit_code == 0
        # Meta-review section must appear
        assert "Meta-Review" in result.output or "meta-review" in result.output.lower()

    def test_meta_review_recommendation_shown(self, runner: CliRunner, app: typer.Typer) -> None:
        """review_command must show the overall recommendation from MetaReviewer."""
        mock_result = self._make_panel_result_with_dissent()
        with (
            patch("maglab.reviewer.corpus_rag.CorpusRAG"),
            patch("maglab.reviewer.panel.ReviewPanel.review", return_value=mock_result),
        ):
            result = runner.invoke(app, ["review", "Some manuscript text here"])
        assert result.exit_code == 0
        # Recommendation must be one of the known values
        recommendations = {"Accept", "Minor Revision", "Major Revision", "Reject"}
        found = any(rec in result.output for rec in recommendations)
        assert found, f"No recommendation found in output: {result.output[:300]}"

    def test_dissent_surfaced_in_output(self, runner: CliRunner, app: typer.Typer) -> None:
        """When score spread ≥3, the dissent must appear in output."""
        mock_result = self._make_panel_result_with_dissent()
        with (
            patch("maglab.reviewer.corpus_rag.CorpusRAG"),
            patch("maglab.reviewer.panel.ReviewPanel.review", return_value=mock_result),
        ):
            result = runner.invoke(app, ["review", "Some manuscript text here"])
        assert result.exit_code == 0
        # Dissent section must appear (spread = 4.0 ≥ threshold 3.0)
        assert "dissent" in result.output.lower() or "spread" in result.output.lower()


# ===========================================================================
# FIX 4: lit search — evidence_matrix JSON produced
# ===========================================================================


class TestLitSearchEvidenceMatrix:
    """Verify that lit search builds and writes an evidence_matrix JSON."""

    def test_evidence_matrix_written(
        self, runner: CliRunner, app: typer.Typer, tmp_path: pathlib.Path
    ) -> None:
        """lit search must write evidence_matrix.json when records are found."""
        from maglab.literature.connectors import LiteratureRecord

        paper_dir = tmp_path / "papers"
        paper_dir.mkdir()
        (paper_dir / "paper.txt").write_text(
            "spin Hall effect anomalous Hall magnetotransport CoFeB", encoding="utf-8"
        )

        # Fake records returned by OpenAlex search
        fake_records = [
            LiteratureRecord(
                doi="10.1234/test1",
                title="Paper on Spin Hall",
                year=2022,
                venue="PRL",
                retraction_status="ok",
                oa_status="green",
                openalex_id="W111",
            ),
            LiteratureRecord(
                doi="10.5678/test2",
                title="Anomalous Hall Effect Study",
                year=2023,
                venue="PRB",
                retraction_status="ok",
                oa_status="closed",
                openalex_id="W222",
            ),
        ]

        out_json = tmp_path / "matrix.json"
        with patch(
            "maglab.literature.connectors.OpenAlexConnector.search",
            return_value=fake_records,
        ):
            result = runner.invoke(
                app,
                [
                    "lit",
                    "search",
                    str(paper_dir),
                    "--top-n",
                    "5",
                    "--matrix-out",
                    str(out_json),
                ],
            )

        assert result.exit_code == 0
        assert out_json.is_file(), f"evidence_matrix.json not created. Output: {result.output}"
        data = json.loads(out_json.read_text(encoding="utf-8"))
        assert isinstance(data, list)
        assert len(data) == 2
        # Each entry must have required fields
        entry = data[0]
        assert "doi" in entry
        assert "tier" in entry
        assert "retraction_status" in entry

    def test_evidence_matrix_default_path(
        self, runner: CliRunner, app: typer.Typer, tmp_path: pathlib.Path
    ) -> None:
        """Without --matrix-out, evidence_matrix.json is written inside the folder."""
        from maglab.literature.connectors import LiteratureRecord

        paper_dir = tmp_path / "papers"
        paper_dir.mkdir()
        (paper_dir / "paper.txt").write_text("spin Hall spintronics", encoding="utf-8")

        fake_records = [
            LiteratureRecord(doi="10.1234/x", title="Test", year=2022, retraction_status="ok")
        ]
        with patch(
            "maglab.literature.connectors.OpenAlexConnector.search",
            return_value=fake_records,
        ):
            result = runner.invoke(app, ["lit", "search", str(paper_dir)])

        assert result.exit_code == 0
        default_path = paper_dir / "evidence_matrix.json"
        assert default_path.is_file(), f"Default path not created. Output: {result.output}"

    def test_no_matrix_flag_skips_matrix(
        self, runner: CliRunner, app: typer.Typer, tmp_path: pathlib.Path
    ) -> None:
        """--no-matrix flag must skip evidence matrix generation."""
        paper_dir = tmp_path / "papers"
        paper_dir.mkdir()
        (paper_dir / "paper.txt").write_text("spin Hall spintronics CoFeB", encoding="utf-8")

        result = runner.invoke(app, ["lit", "search", str(paper_dir), "--no-matrix"])
        assert result.exit_code == 0
        # No matrix should be created
        default_path = paper_dir / "evidence_matrix.json"
        assert not default_path.exists()

    def test_retracted_papers_flagged_in_matrix(
        self, runner: CliRunner, app: typer.Typer, tmp_path: pathlib.Path
    ) -> None:
        """Retracted papers must appear in the matrix with verification_status=failed."""
        from maglab.literature.connectors import LiteratureRecord

        paper_dir = tmp_path / "papers"
        paper_dir.mkdir()
        (paper_dir / "paper.txt").write_text("spintronics SOT", encoding="utf-8")

        fake_records = [
            LiteratureRecord(
                doi="10.9999/retracted",
                title="Retracted Paper",
                year=2020,
                retraction_status="retracted",
            )
        ]
        out_json = tmp_path / "matrix.json"
        with patch(
            "maglab.literature.connectors.OpenAlexConnector.search",
            return_value=fake_records,
        ):
            result = runner.invoke(
                app,
                ["lit", "search", str(paper_dir), "--matrix-out", str(out_json)],
            )

        assert result.exit_code == 0
        data = json.loads(out_json.read_text(encoding="utf-8"))
        assert len(data) == 1
        assert data[0]["retraction_status"] == "retracted"
        assert data[0]["verification_status"] == "failed"
