"""P5 CLI commands — literature discovery, persona review, ELN, and anomaly explanation.

Commands exposed:
    maglab lit search     Extract weighted keywords from a folder of papers.
    maglab lit authors    Find authoritative researchers on a topic.
    maglab lit keywords   Extract weighted keywords from free text.
    maglab lit journal    Query journal impact metrics (SJR / OpenAlex / Eigenfactor).
    maglab lit graph      Query the magnetism knowledge graph.
    maglab review         Run the persona review panel on a manuscript.
    maglab lab note       Create an ELN entry.
    maglab lab plan       Generate a physics-aware measurement plan.
    maglab explain        Explain anomalous data/results (D2 abductive reasoning).

Wiring entry point::

    from maglab.commands.p5_literature import register
    register(app)

Heavy / optional dependencies (literature HTTP clients, sentence-transformers, etc.)
are imported lazily inside callbacks so that ``maglab --help`` works without
optional extras installed.
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

console = Console()

# ---------------------------------------------------------------------------
# lit sub-app
# ---------------------------------------------------------------------------

lit_app = typer.Typer(
    name="lit",
    help="[P5] Literature discovery intelligence (search·authors·keywords·journal·graph).",
    no_args_is_help=True,
)


@lit_app.command("search")
def lit_search(
    folder: str = typer.Argument(..., help="Path to a folder containing PDF/text papers."),
    top_n: int = typer.Option(30, "--top-n", "-n", help="Number of top keywords to extract."),
    show: int = typer.Option(10, "--show", "-s", help="Number of keywords to display in table."),
    matrix_out: str = typer.Option(
        "",
        "--matrix-out",
        "-o",
        help="Write evidence_matrix JSON to this path (default: <folder>/evidence_matrix.json).",
    ),
    session: str = typer.Option(
        "",
        "--session",
        help="Research session ID for the evidence matrix (default: folder name).",
    ),
    no_matrix: bool = typer.Option(
        False,
        "--no-matrix",
        help="Skip evidence matrix building (keyword extraction only).",
    ),
) -> None:
    """Extract weighted keywords from a folder of papers and build an evidence matrix (F3, §14.7).

    Reads all PDF and .txt files in FOLDER, applies TF-IDF + KeyBERT + YAKE
    keyword extraction, then searches OpenAlex with the top keywords to populate
    an ``EvidenceMatrix`` (evidence_matrix JSON).

    The evidence matrix records each found paper with DOI, tier, retraction
    status, and verification status — it is the primary output of the
    literature discovery pipeline.

    Note: full 5-agent orchestration (search-scout, citation-auditor,
    paper-reviewer, synthesis-editor) is deferred to P6.  This implementation
    executes the search-scout + evidence-accumulation steps directly.
    """
    from pathlib import Path

    from maglab.literature.keywords import extract_keywords_from_folder

    folder_path = Path(folder)
    if not folder_path.is_dir():
        console.print(f"[red]Folder not found:[/] {folder!r}")
        raise typer.Exit(1)

    with console.status(f"[dim]Extracting keywords from {folder_path} …[/]"):
        try:
            keywords = extract_keywords_from_folder(folder_path, top_n=top_n)
        except Exception as exc:  # noqa: BLE001
            console.print(f"[red]Keyword extraction failed:[/] {exc}")
            raise typer.Exit(1) from exc

    if not keywords:
        console.print("[yellow]No extractable text found in folder.[/]")
        raise typer.Exit(1)

    table = Table(title=f"Top keywords from {folder_path.name}", show_lines=False)
    table.add_column("Rank", style="dim", justify="right")
    table.add_column("Keyword", style="cyan")
    table.add_column("Score", justify="right")
    table.add_column("Methods")

    for i, kw in enumerate(keywords[:show], start=1):
        table.add_row(
            str(i),
            kw.keyword,
            f"{kw.score:.3f}",
            ", ".join(kw.source_methods),
        )
    console.print(table)
    console.print(
        f"[dim]Extracted {len(keywords)} keywords from folder "
        f"(showing top {min(show, len(keywords))}).[/]"
    )

    if no_matrix:
        return

    # Evidence matrix pipeline — search-scout phase (§14.7)
    # Full 5-agent orchestration deferred to P6; this executes the
    # search-scout + accumulation steps using the connector search API.
    _build_evidence_matrix(
        folder_path=folder_path,
        keywords=keywords,
        matrix_out=matrix_out,
        session_id=session or folder_path.name,
    )


def _build_evidence_matrix(
    folder_path: Path,
    keywords: list,
    matrix_out: str,
    session_id: str,
) -> None:
    """Build and persist an EvidenceMatrix from keyword-driven connector search.

    Search-scout phase of the literature orchestration pipeline (§14.7).
    Deferred agents (citation-auditor, paper-reviewer, synthesis-editor) are
    logged as TODOs for P6.

    Parameters
    ----------
    folder_path:
        Source folder (used for default output path).
    keywords:
        WeightedKeyword list from extract_keywords_from_folder.
    matrix_out:
        Path for the output JSON file; empty string → <folder>/evidence_matrix.json.
    session_id:
        Research session identifier for the EvidenceMatrix DB.
    """
    from pathlib import Path

    from maglab.literature.index import EvidenceEntry, EvidenceMatrix
    from maglab.literature.keywords import top_keyword_strings

    # Determine output path
    out_path = Path(matrix_out) if matrix_out else folder_path / "evidence_matrix.json"

    # Use a temp DB path to avoid polluting the global session
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp_db = Path(tmp.name)

    matrix = EvidenceMatrix(db_path=tmp_db, session_id=session_id)

    # Collect top query strings (use top 3 keywords for the search-scout query)
    query_terms = top_keyword_strings(keywords, n=3)
    query = " ".join(query_terms) if query_terms else "magnetism spintronics"

    console.print(f"[dim]Search-scout query: {query!r}[/]")

    # Search OpenAlex (search-scout agent role)
    records = []
    try:
        from maglab.literature.connectors import OpenAlexConnector

        oa = OpenAlexConnector()
        with console.status("[dim]Searching OpenAlex (search-scout) …[/]"):
            records = oa.search(query, max_results=20)
    except ImportError:
        console.print(
            "[yellow]pyalex not installed — skipping live search. Evidence matrix will be empty.[/]"
        )
    except Exception as exc:  # noqa: BLE001
        console.print(f"[yellow]OpenAlex search failed: {exc} — evidence matrix will be empty.[/]")

    # Populate the evidence matrix
    added = 0
    skipped_retracted = 0
    for i, rec in enumerate(records):
        # Assign tier: T1 for top 5 by citation, T2 for next 10, T3 for rest
        if i < 5:
            tier: str = "T1"
        elif i < 15:
            tier = "T2"
        else:
            tier = "T3"

        ref_key = rec.doi or f"nokey_{i}"
        # Normalize ref_key to a valid slug
        ref_key = ref_key.replace("/", "_").replace(":", "_")

        # Retraction check — flag retracted entries
        verification_status: str
        if rec.retraction_status == "retracted":
            verification_status = "failed"
            skipped_retracted += 1
        else:
            verification_status = "pending"

        entry = EvidenceEntry(
            ref_key=ref_key,
            tier=tier,  # type: ignore[arg-type]
            title=rec.title,
            authors=rec.authors,
            year=rec.year,
            venue=rec.venue,
            doi=rec.doi,
            url=rec.pdf_url,
            openalex_id=rec.openalex_id,
            s2_id=rec.s2_id,
            oa_status=rec.oa_status,
            retraction_status=rec.retraction_status,
            verification_status=verification_status,  # type: ignore[arg-type]
            notes=f"source={rec.source}; citations={rec.citation_count}",
        )
        if matrix.add(entry):
            added += 1

    # Serialize and write
    try:
        json_str = matrix.to_json()
        out_path.write_text(json_str, encoding="utf-8")
        console.print(
            f"[green]Evidence matrix:[/] {added} entries ({skipped_retracted} retracted flagged) "
            f"→ {out_path}"
        )
    except Exception as exc:  # noqa: BLE001
        console.print(f"[yellow]Could not write evidence matrix: {exc}[/]")
    finally:
        matrix.close()
        import contextlib

        with contextlib.suppress(Exception):
            tmp_db.unlink(missing_ok=True)

    # TODO (P6): run citation-auditor, paper-reviewer, synthesis-editor agents
    # on the collected records to enrich the evidence matrix with citation
    # lineage, per-paper review scores, and a synthesis narrative.


@lit_app.command("authors")
def lit_authors(
    topic: str = typer.Argument(..., help="Research topic (e.g. 'spin Hall effect')."),
    max_results: int = typer.Option(10, "--max", "-n", help="Maximum number of authors to return."),
    email: str = typer.Option("", "--email", help="Email for OpenAlex polite pool."),
    no_enrich: bool = typer.Option(
        False, "--no-enrich", help="Skip Semantic Scholar cross-enrichment."
    ),
) -> None:
    """Find authoritative researchers on a topic (§14.2).

    Searches OpenAlex by citation count and cross-enriches with Semantic Scholar.
    """
    with console.status(f"[dim]Searching authoritative authors for '{topic}' …[/]"):
        try:
            from maglab.literature.authors import find_authoritative_authors

            profiles = find_authoritative_authors(
                topic,
                max_results=max_results,
                email=email,
                enrich_s2=not no_enrich,
            )
        except ImportError as exc:
            console.print(
                f"[red]Missing dependency:[/] {exc}\nInstall with: pip install maglab[literature]"
            )
            raise typer.Exit(1) from exc
        except Exception as exc:  # noqa: BLE001
            console.print(f"[red]Author search failed:[/] {exc}")
            raise typer.Exit(1) from exc

    if not profiles:
        console.print(f"[yellow]No authoritative authors found for topic:[/] {topic!r}")
        return

    table = Table(title=f"Authoritative authors — {topic!r}", show_lines=False)
    table.add_column("Name", style="cyan")
    table.add_column("Affiliation")
    table.add_column("h-index", justify="right")
    table.add_column("Citations", justify="right")
    table.add_column("Source")

    for p in profiles:
        h = str(p.h_index) if p.h_index is not None else "—"
        cit = str(p.cited_by_count) if p.cited_by_count is not None else "—"
        table.add_row(p.name, p.affiliation[:40], h, cit, p.h_index_source or "—")
    console.print(table)

    # Show recent papers for top author
    if profiles and profiles[0].recent_papers:
        console.print(f"\n[bold]Recent papers by {profiles[0].name}:[/]")
        for paper in profiles[0].recent_papers[:3]:
            console.print(f"  • {paper.title[:80]}  [{paper.year}]  DOI:{paper.doi or '—'}")


@lit_app.command("keywords")
def lit_keywords(
    text: str = typer.Argument(..., help="Free text or query string to extract keywords from."),
    top_n: int = typer.Option(20, "--top-n", "-n", help="Number of keywords to return."),
) -> None:
    """Extract weighted keywords from free text (TF-IDF + KeyBERT + YAKE, F3)."""
    with console.status("[dim]Extracting keywords …[/]"):
        try:
            from maglab.literature.keywords import extract_keywords_from_texts

            keywords = extract_keywords_from_texts([text], top_n=top_n)
        except Exception as exc:  # noqa: BLE001
            console.print(f"[red]Keyword extraction failed:[/] {exc}")
            raise typer.Exit(1) from exc

    if not keywords:
        console.print("[yellow]No keywords extracted.[/]")
        raise typer.Exit(1)

    table = Table(title="Weighted keywords", show_lines=False)
    table.add_column("Rank", style="dim", justify="right")
    table.add_column("Keyword", style="cyan")
    table.add_column("Score", justify="right")
    table.add_column("TF-IDF", justify="right")
    table.add_column("KeyBERT", justify="right")
    table.add_column("YAKE", justify="right")

    for i, kw in enumerate(keywords, start=1):
        table.add_row(
            str(i),
            kw.keyword,
            f"{kw.score:.3f}",
            f"{kw.tfidf_score:.3f}",
            f"{kw.keybert_score:.3f}",
            f"{kw.yake_score:.3f}",
        )
    console.print(table)


@lit_app.command("journal")
def lit_journal(
    journal_name: str = typer.Argument(..., help="Journal name (e.g. 'Physical Review Letters')."),
    no_openalex: bool = typer.Option(
        False, "--no-openalex", help="Skip live OpenAlex lookup (offline mode)."
    ),
) -> None:
    """Query journal impact metrics: SJR, OpenAlex 2yr_mean_citedness, Eigenfactor (F4).

    Note: 'JCR Impact Factor' is a proprietary metric and is intentionally
    omitted.  Three open metrics with explicit source labels are provided instead.
    """
    with console.status(f"[dim]Querying metrics for '{journal_name}' …[/]"):
        try:
            from maglab.literature.journals import get_journal_metrics

            metrics = get_journal_metrics(journal_name, use_openalex=not no_openalex)
        except Exception as exc:  # noqa: BLE001
            console.print(f"[red]Journal metric query failed:[/] {exc}")
            raise typer.Exit(1) from exc

    table = Table(title=f"Journal metrics — {metrics.journal_name}", show_lines=False)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")
    table.add_column("Source")

    def _row(label: str, val: object, source: str) -> None:
        table.add_row(label, str(val) if val is not None else "[dim]N/A[/]", source)

    _row("SJR", metrics.sjr, metrics.sjr_source)
    _row("SJR Quartile", metrics.sjr_quartile or None, metrics.sjr_source)
    _row("SJR Year", metrics.sjr_year, metrics.sjr_source)
    _row("2yr Mean Citedness", metrics.openalex_2yr_mean_citedness, metrics.openalex_source)
    _row("h-index", metrics.h_index, metrics.openalex_source)
    _row("Eigenfactor", metrics.eigenfactor, metrics.eigenfactor_source)
    console.print(table)

    for note in metrics.notes:
        console.print(f"[dim]Note:[/] {note}")


@lit_app.command("graph")
def lit_graph(
    query: str = typer.Argument(..., help="Node label or DOI to query in the knowledge graph."),
    cite_map: str = typer.Option(
        "", "--cite-map", help="DOI to trace citation lineage (e.g. '10.1103/PhysRevLett.xxx')."
    ),
    depth: int = typer.Option(1, "--depth", "-d", help="Graph traversal depth."),
) -> None:
    """Query the magnetism knowledge graph and citation lineage (§14.6).

    Without --cite-map: shows nodes connected to QUERY by any edge type.
    With --cite-map DOI: shows typed citation lineage (extends/contradicts/…).
    """
    with console.status("[dim]Querying knowledge graph …[/]"):
        try:
            from maglab.literature.graph import get_graph

            kg = get_graph()
        except Exception as exc:  # noqa: BLE001
            console.print(f"[red]Knowledge graph unavailable:[/] {exc}")
            raise typer.Exit(1) from exc

    # Citation lineage mode
    if cite_map:
        try:
            edges = kg.citation_lineage(cite_map)
        except Exception as exc:  # noqa: BLE001
            console.print(f"[red]Citation lineage query failed:[/] {exc}")
            raise typer.Exit(1) from exc

        if not edges:
            console.print(f"[yellow]No citation edges found for DOI:[/] {cite_map!r}")
            return

        table = Table(title=f"Citation lineage — {cite_map}", show_lines=False)
        table.add_column("From", style="cyan")
        table.add_column("Relation")
        table.add_column("To", style="cyan")
        table.add_column("Evidence DOI")

        for edge in edges:
            table.add_row(
                edge.source_id,
                edge.edge_type,
                edge.target_id,
                edge.evidence_doi or "—",
            )
        console.print(table)
        return

    # Node neighbourhood mode — first try exact ID, then label search
    try:
        node = kg.get_node(query)
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Graph query failed:[/] {exc}")
        raise typer.Exit(1) from exc

    if node is None:
        # Try searching by label
        try:
            nodes = kg.find_nodes(query)
        except Exception as exc:  # noqa: BLE001
            nodes = []
            console.print(f"[dim]Graph search failed: {exc}[/]")

        if not nodes:
            console.print(f"[yellow]No node found for:[/] {query!r}")
            return

        table = Table(title=f"Knowledge graph — nodes matching '{query}'", show_lines=False)
        table.add_column("ID", style="cyan")
        table.add_column("Type")
        table.add_column("Label")

        for n in nodes[:20]:
            table.add_row(n.node_id, n.node_type, n.label)
        console.print(table)
        return

    console.print(f"[bold cyan]{node.label}[/]  type=[bold]{node.node_type}[/]  id={node.node_id}")
    try:
        neighbors = kg.get_neighbors(node.node_id)
    except Exception as exc:  # noqa: BLE001
        neighbors = []
        console.print(f"[dim]Edge query failed: {exc}[/]")

    if neighbors:
        table = Table(title="Connected edges", show_lines=False)
        table.add_column("Relation")
        table.add_column("Neighbour")
        table.add_column("Evidence DOI")
        for edge, neighbour_node in neighbors:
            table.add_row(edge.edge_type, neighbour_node.label, edge.evidence_doi or "—")
        console.print(table)
    else:
        console.print("[dim]No edges found for this node.[/]")


# ---------------------------------------------------------------------------
# review — top-level command
# ---------------------------------------------------------------------------


def review_command(
    manuscript: str = typer.Argument(
        ..., help="Manuscript text or path to a .txt/.md file to review."
    ),
    journal: str = typer.Option(
        "general", "--journal", "-j", help="Target journal (general·prl·prb·npj·nature_family)."
    ),
    author_ids: list[str] | None = typer.Option(  # noqa: B008
        None,
        "--author",
        "-a",
        help="Reviewer persona author ID (may be repeated for 3-person panel).",
    ),
) -> None:
    """Run the persona review panel on a manuscript (§15, F1).

    The panel consists of up to 3 AI reviewer personas grounded in their
    published corpus via RAG.  Seven safety guardrails are enforced:
    disclosure label, 3rd-person attribution, no fabricated citations, etc.

    MANUSCRIPT may be a path to a text/markdown file or an inline text string.
    """
    import pathlib

    # Resolve manuscript text
    ms_path = pathlib.Path(manuscript)
    if ms_path.is_file():
        try:
            ms_text = ms_path.read_text(encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            console.print(f"[red]Cannot read manuscript file:[/] {exc}")
            raise typer.Exit(1) from exc
    else:
        ms_text = manuscript

    if not ms_text.strip():
        console.print("[red]Manuscript is empty.[/]")
        raise typer.Exit(1)

    # Build panel personas
    try:
        from maglab.reviewer.corpus_rag import CorpusRAG
        from maglab.reviewer.panel import PersonaSpec, ReviewPanel
    except ImportError as exc:
        console.print(
            f"[red]Missing dependency:[/] {exc}\nInstall with: pip install maglab[reviewer]"
        )
        raise typer.Exit(1) from exc

    # Default personas if none provided
    if not author_ids:
        author_ids = ["persona-A", "persona-B", "persona-C"]

    personas = [
        PersonaSpec(author_id=aid, author_name=aid, paper_count=0) for aid in author_ids[:3]
    ]

    try:
        rag = CorpusRAG()
        panel = ReviewPanel(personas=personas, corpus_rag=rag, journal=journal)

        with console.status("[dim]Running persona review panel …[/]"):
            result = panel.review(ms_text, raise_on_disclosure_violation=False)
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Review panel failed:[/] {exc}")
        raise typer.Exit(1) from exc

    console.print(f"[bold]Persona Review Panel — journal:[/] {result.journal}")
    console.print()

    for pr in result.reviews:
        label = pr.persona.author_name or pr.persona.author_id
        console.print(f"[bold cyan]Reviewer: {label}[/]")
        console.print(pr.review_text[:600])
        if pr.validation_errors:
            for err in pr.validation_errors:
                console.print(f"  [yellow]Validation:[/] {err}")
        if not pr.disclosure_passed:
            console.print("  [red]WARNING: Disclosure guardrail violation detected.[/]")
        console.print()

    # Rubric summary
    table = Table(title="Rubric scores", show_lines=False)
    table.add_column("Reviewer", style="cyan")
    table.add_column("Dimension")
    table.add_column("Score", justify="right")
    table.add_column("Evidence sections")

    for pr in result.reviews:
        for dim_score in pr.score.scores:
            table.add_row(
                pr.persona.author_name or pr.persona.author_id,
                dim_score.dimension,
                f"{dim_score.score:.1f}",
                ", ".join(dim_score.evidence_sections[:2]),
            )
    console.print(table)

    # Meta-review — consensus and dissent synthesis (§15.3)
    try:
        from maglab.reviewer.meta_reviewer import MetaReviewer

        meta = MetaReviewer().synthesize(result)

        console.print()
        console.print("[bold]Meta-Review (§15.3)[/]")
        console.print(f"  Recommendation: [bold green]{meta.overall_recommendation}[/]")
        console.print()

        if meta.consensus:
            console.print("[bold]Consensus items:[/]")
            for c in meta.consensus:
                console.print(
                    f"  [{c.dimension.value}]  mean={c.mean_score:.1f}  "
                    f"std={c.std_score:.1f}  — {c.common_rationale[:80]}"
                )

        if meta.dissents:
            console.print()
            console.print("[bold yellow]Dissent items (score spread ≥3 pts):[/]")
            for d in meta.dissents:
                scores_str = ", ".join(f"{name}: {score:.0f}" for name, score in d.scores)
                console.print(f"  [{d.dimension.value}]  spread={d.range_:.1f} pts  ({scores_str})")
                console.print(f"    {d.rationale[:120]}")
        else:
            console.print("[dim]No significant dissents (all score spreads < 3 pts).[/]")

    except Exception as exc:  # noqa: BLE001
        console.print(f"[dim]Meta-review unavailable: {exc}[/]")


# ---------------------------------------------------------------------------
# lab sub-app
# ---------------------------------------------------------------------------

lab_app = typer.Typer(
    name="lab",
    help="[P5] Electronic lab notebook and measurement planning (note·plan).",
    no_args_is_help=True,
)


@lab_app.command("note")
def lab_note(
    text: str = typer.Argument(..., help="Note text or free-form observation to record."),
    sample: str = typer.Option("", "--sample", "-s", help="Sample ID or stack notation."),
    instrument: str = typer.Option("", "--instrument", "-i", help="Instrument used."),
    measurement_type: str = typer.Option(
        "general",
        "--type",
        "-t",
        help="Measurement type (general·magnetotransport·fmr·moke·vsm).",
    ),
    tags: list[str] | None = typer.Option(  # noqa: B008
        None, "--tag", help="Tag (may be repeated)."
    ),
    notebook_dir: str = typer.Option("notebook", "--dir", "-d", help="ELN notebook directory."),
    draft: bool = typer.Option(False, "--draft", help="Mark entry as auto-draft (unconfirmed)."),
) -> None:
    """Create an ELN entry in the notebook directory (§13.5, B1).

    The entry is saved as a dated Markdown file with YAML frontmatter
    (entry_id, date, sample, instrument, tags, datapoints).
    """
    import pathlib

    from maglab.lab.notebook.entry import ELNNotebook, MeasurementType

    # Resolve measurement type
    try:
        mtype = MeasurementType(measurement_type.lower())
    except ValueError:
        valid = [m.value for m in MeasurementType]
        console.print(
            f"[red]Unknown measurement type:[/] {measurement_type!r}. Valid: {', '.join(valid)}"
        )
        raise typer.Exit(1) from None

    nb_dir = pathlib.Path(notebook_dir)
    try:
        notebook = ELNNotebook(nb_dir)
        entry = notebook.create_entry(
            text,
            sample=sample,
            instrument=instrument,
            measurement_type=mtype,
            tags=list(tags) if tags else [],
            is_draft=draft,
        )
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]ELN entry creation failed:[/] {exc}")
        raise typer.Exit(1) from exc

    status = "[yellow](draft)[/]" if entry.is_draft else "[green]✓[/]"
    console.print(f"{status} ELN entry created: [bold]{entry.entry_id}[/]")
    console.print(
        f"  Date: {entry.date}  |  Sample: {entry.sample or '—'}  |  Type: {entry.measurement_type}"
    )
    console.print(f"  Notebook dir: {nb_dir.resolve()}")


@lab_app.command("note-list")
def lab_note_list(
    date_from: str = typer.Option(
        "",
        "--date-from",
        help="Filter entries on or after this date (YYYY-MM-DD).",
    ),
    date_to: str = typer.Option(
        "",
        "--date-to",
        help="Filter entries on or before this date (YYYY-MM-DD).",
    ),
    tag: list[str] | None = typer.Option(  # noqa: B008
        None, "--tag", help="Include only entries with this tag (may be repeated, OR logic)."
    ),
    sample: str = typer.Option(
        "",
        "--sample",
        "-s",
        help="Filter by sample ID (partial match).",
    ),
    measurement_type: str = typer.Option(
        "",
        "--type",
        "-t",
        help="Filter by measurement type (general·magnetotransport·fmr·moke·vsm).",
    ),
    notebook_dir: str = typer.Option("notebook", "--dir", "-d", help="ELN notebook directory."),
) -> None:
    """List ELN entries with optional date / tag / sample / type filters (§13.5, T-P5-17).

    Reads all Markdown entries in NOTEBOOK_DIR and prints a Rich table with
    entry_id, date, sample, type, and tags.  Filters are applied with AND
    logic between dimensions and OR logic within the ``--tag`` list.
    """
    import pathlib
    from datetime import date as _date

    from maglab.lab.notebook.entry import ELNNotebook, MeasurementType

    nb_dir = pathlib.Path(notebook_dir)

    # Parse date filters
    parsed_from: _date | None = None
    parsed_to: _date | None = None
    if date_from:
        try:
            parsed_from = _date.fromisoformat(date_from)
        except ValueError:
            console.print(
                f"[red]Invalid --date-from format:[/] {date_from!r} (expected YYYY-MM-DD)"
            )
            raise typer.Exit(1) from None
    if date_to:
        try:
            parsed_to = _date.fromisoformat(date_to)
        except ValueError:
            console.print(f"[red]Invalid --date-to format:[/] {date_to!r} (expected YYYY-MM-DD)")
            raise typer.Exit(1) from None

    # Parse measurement type filter
    mtype: MeasurementType | None = None
    if measurement_type:
        try:
            mtype = MeasurementType(measurement_type.lower())
        except ValueError:
            valid = [m.value for m in MeasurementType]
            console.print(
                f"[red]Unknown measurement type:[/] {measurement_type!r}. Valid: {', '.join(valid)}"
            )
            raise typer.Exit(1) from None

    try:
        notebook = ELNNotebook(nb_dir)
        entries = notebook.list_entries(
            date_from=parsed_from,
            date_to=parsed_to,
            tags=list(tag) if tag else None,
            sample=sample or None,
            measurement_type=mtype,
        )
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]ELN list failed:[/] {exc}")
        raise typer.Exit(1) from exc

    if not entries:
        console.print("[yellow]No entries found matching the given filters.[/]")
        return

    table = Table(title=f"ELN Entries — {nb_dir}", show_lines=False)
    table.add_column("Entry ID", style="cyan")
    table.add_column("Date")
    table.add_column("Sample")
    table.add_column("Type")
    table.add_column("Tags")
    table.add_column("Draft", justify="center")

    for entry in entries:
        table.add_row(
            entry.entry_id,
            str(entry.date),
            entry.sample or "—",
            entry.measurement_type.value if entry.measurement_type else "—",
            ", ".join(entry.tags) or "—",
            "[yellow]✓[/]" if entry.is_draft else "",
        )

    console.print(table)
    console.print(f"[dim]{len(entries)} entr{'y' if len(entries) == 1 else 'ies'} found.[/]")


@lab_app.command("plan")
def lab_plan(
    goal: str = typer.Argument(
        ..., help="Measurement goal (e.g. 'SOT efficiency CoFeB', 'FMR damping Py/Pt')."
    ),
    doe_type: str = typer.Option(
        "latin_hypercube",
        "--doe",
        help="DOE type (latin_hypercube·full_factorial·partial_factorial).",
    ),
    n_doe: int = typer.Option(10, "--n-doe", help="Number of DOE sample points."),
    output: str | None = typer.Option(
        None, "--output", "-o", help="Save checklist YAML to this path."
    ),
) -> None:
    """Generate a physics-aware measurement plan (§13.6, B3).

    Uses the effect registry measurement_config to map the research GOAL
    to required measurements, geometries, instruments, and sweep ranges.
    """
    from maglab.lab.planning.planner import MeasurementPlanner

    with console.status(f"[dim]Generating measurement plan for '{goal}' …[/]"):
        try:
            planner = MeasurementPlanner()
            plan = planner.plan(goal, doe_type=doe_type, n_doe_points=n_doe)
        except Exception as exc:  # noqa: BLE001
            console.print(f"[red]Measurement plan generation failed:[/] {exc}")
            raise typer.Exit(1) from exc

    console.print(f"[bold]Measurement Plan — goal:[/] {plan.goal}")
    console.print(
        f"  Steps: {len(plan.steps)}  |  Estimated total: {plan.total_estimated_hours:.1f} h"
    )
    console.print()

    table = Table(title="Measurement steps", show_lines=False)
    table.add_column("Step", style="dim", justify="right")
    table.add_column("Effect model", style="cyan")
    table.add_column("Geometry")
    table.add_column("Instrument hint")
    table.add_column("Est. (h)", justify="right")

    for step in plan.steps:
        table.add_row(
            step.step_id,
            step.effect_model,
            step.geometry[:40] or "—",
            step.instrument_hint[:30] or "—",
            f"{step.estimated_hours:.1f}",
        )
    console.print(table)

    if plan.doe_design:
        console.print(
            f"\n[cyan]DOE design ({doe_type}):[/] {len(plan.doe_design.get('points', []))} points"
        )

    # Save checklist YAML
    if output:
        import pathlib

        out_path = pathlib.Path(output)
        try:
            out_path.write_text(plan.checklist_yaml or plan.to_checklist_yaml(), encoding="utf-8")
            console.print(f"[green]✓[/] Checklist saved: {out_path}")
        except Exception as exc:  # noqa: BLE001
            console.print(f"[yellow]Could not save checklist:[/] {exc}")


# ---------------------------------------------------------------------------
# explain — top-level command
# ---------------------------------------------------------------------------


def explain_command(
    data: str = typer.Argument(
        ...,
        help="Anomalous data or result description (e.g. 'AHE sign reversal above 200 K').",
    ),
    min_candidates: int = typer.Option(
        2, "--min-candidates", "-n", help="Minimum number of mechanism candidates to return."
    ),
    json_out: bool = typer.Option(False, "--json", help="Output structured JSON instead of table."),
) -> None:
    """Explain anomalous experimental data via abductive reasoning (§5.11, D2).

    Generates mechanism candidates ranked by confidence, each grounded in
    literature evidence (RAG).  Discriminating tests are proposed for each
    candidate.

    LLM is used only for candidate text generation — it does NOT produce
    numerical physical values.
    """
    import json as _json

    from maglab.core.reasoning import explain_anomaly
    from maglab.reviewer.corpus_rag import CorpusRAG

    # Build a CorpusRAG instance and wire its search method as the RAG provider.
    # The index is empty at startup; it is populated as papers are added during
    # the explain pipeline. BM25-only mode is used (no embedding fn needed).
    rag = CorpusRAG()

    def _rag_search_fn(query: str, top_k: int = 5) -> list[dict]:
        results = rag.search(query, top_k=top_k)
        return [
            {
                "doi": r.chunk.doi,
                "title": r.chunk.title,
                "text": r.chunk.text,
                "score": r.score,
            }
            for r in results
        ]

    with console.status("[dim]Running anomaly explanation engine (D2) …[/]"):
        try:
            result = explain_anomaly(
                data, min_candidates=min_candidates, rag_search_fn=_rag_search_fn
            )
        except Exception as exc:  # noqa: BLE001
            console.print(f"[red]Explanation engine failed:[/] {exc}")
            raise typer.Exit(1) from exc

    if not result.candidates:
        console.print("[yellow]No mechanism candidates could be generated.[/]")
        raise typer.Exit(1)

    if json_out:
        console.print_json(_json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return

    console.print(f"[bold]Anomaly Explanation (D2) — query:[/] {result.query}")
    console.print(f"[dim]{result.disclaimer}[/]")
    console.print()

    table = Table(title="Mechanism candidates", show_lines=False)
    table.add_column("ID", style="dim")
    table.add_column("Mechanism", style="cyan")
    table.add_column("Confidence")
    table.add_column("Evidence (DOIs)")

    for cand in result.candidates:
        dois = ", ".join(d for d, _ in cand.supporting_evidence[:2]) or "—"
        table.add_row(
            cand.candidate_id,
            cand.mechanism[:60],
            cand.confidence.value,
            dois[:50],
        )
    console.print(table)

    if result.top_discriminating_tests:
        console.print("\n[bold]Top discriminating tests:[/]")
        for t in result.top_discriminating_tests[:3]:
            console.print(f"  [{t.test_id}] {t.description[:80]}  [{t.difficulty}]")


# ---------------------------------------------------------------------------
# register
# ---------------------------------------------------------------------------


def register(app: typer.Typer) -> None:
    """Attach P5 commands to the root maglab app."""
    app.add_typer(lit_app)
    app.add_typer(lab_app)
    app.command("review")(review_command)
    app.command("explain")(explain_command)
