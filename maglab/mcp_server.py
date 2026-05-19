"""MagLab MCP server — fastmcp-based (§5.18, Appendix B).

P0 exposed tools (deterministic, no LLM involvement):
  - physics_compute    : formula calculation (formulas.py)
  - physics_check      : physics sanity check (oracle.py)
  - convert_units      : magnetic unit conversion (units.py)
  - material_lookup    : detailed lookup by material ID (materials.py)
  - material_search    : keyword material search (materials.py)
  - provenance_query   : DataPoint / lineage query (ledger.py)

P1 exposed tools (deterministic, no LLM involvement):
  - sim_validate       : static validation of MultiScaleSpec (sim/validate.py)
  - sim_run            : micromagnetic simulation run (sim/micro/)
  - sim_parse          : simulation output → JobResult parsing (sim/parse.py)
  - figure_render      : FigureSpec → vector figure render (figure/compose·export)
  - figure_export      : multi-format figure export (figure/export.py)

P4 instrument-domain tools (T-P4-28):
  - instr_search_manual   : search / download an instrument manual PDF
  - instr_ingest_manual   : ingest a local manual PDF into the RAG index
  - instr_generate_skill  : generate an instrument SKILL.md package
  - instr_scaffold        : generate a PyVISA backend skeleton
  - instr_safety_check    : run the SCPI safety-envelope validator

P0/P4 resources:
  - materials://           : full material list JSON
  - provenance://          : full DataPoint list JSON
  - manuals://             : list of cached instrument manuals

``maglab mcp serve`` entry point.
``create_server()`` — use to create a server instance directly in tests.

Design principles:
  - Read-only tools carry readOnlyHint=True; file-writing tools carry
    readOnlyHint=False (figure_render, figure_export, sim_run,
    instr_search_manual, instr_ingest_manual, instr_generate_skill,
    instr_scaffold).
  - Only deterministic functions are called — no LLM calls.
  - Full type hints throughout.
"""

from __future__ import annotations

import contextlib
from typing import Any

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

# ---------------------------------------------------------------------------
# Server factory
# ---------------------------------------------------------------------------


def create_server() -> FastMCP:
    """Create and return a MagLab MCP server instance with P0 tools registered.

    Returns:
        FastMCP server instance.
    """
    mcp = FastMCP(
        name="MagLab",
        instructions=(
            "MagLab magnetism & spintronics research lifecycle copilot MCP server. "
            "P0 tools: physics_compute·physics_check·convert_units·"
            "material_lookup·material_search·provenance_query. "
            "P1 tools: sim_validate·sim_run·sim_parse·figure_render·figure_export. "
            "All tools are deterministic and do not invoke the LLM."
        ),
    )

    _register_tools(mcp)
    _register_instrument_tools(mcp)
    _register_resources(mcp)

    return mcp


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------


_READ_ONLY_ANNOTATIONS = ToolAnnotations(readOnlyHint=True)

# Annotation for tools that write files to disk (figure_render, figure_export,
# sim_run, instr_ingest_manual, instr_generate_skill, instr_scaffold,
# instr_search_manual).  These tools create new files but do NOT destroy
# existing data, so destructiveHint=False.
_WRITE_ANNOTATIONS = ToolAnnotations(readOnlyHint=False, destructiveHint=False)


def _register_tools(mcp: FastMCP) -> None:
    """Register P0 and P1 tools with the MCP server."""

    read_only = _READ_ONLY_ANNOTATIONS
    write_op = _WRITE_ANNOTATIONS

    # ------------------------------------------------------------------
    # 1. physics_compute
    # ------------------------------------------------------------------

    @mcp.tool(
        name="physics_compute",
        description=(
            "Compute a magnetic physics quantity using a deterministic formula. "
            "formula: formula name (exchange_length·bloch_wall_width·kittel_freq_in_plane, etc.), "
            "params: parameter dictionary in {'key': float} format. "
            "Result is an SI-unit float or Quantity serialization."
        ),
        annotations=read_only,
    )
    def physics_compute(formula: str, params: dict[str, float]) -> dict[str, Any]:
        """Deterministic formula calculation tool.

        Args:
            formula: Name of a formula defined in formulas.py.
            params:  Formula parameters {'param_name': float}.

        Returns:
            {'formula': str, 'result': float|str, 'params': dict}
        """
        from maglab.physics import formulas as _f

        fn = getattr(_f, formula, None)
        if fn is None:
            available = [n for n in dir(_f) if not n.startswith("_") and callable(getattr(_f, n))]
            return {
                "ok": False,
                "error": f"Unknown formula: {formula!r}",
                "available": available[:30],
            }
        try:
            result = fn(**params)
            # Handle Quantity objects
            result_val: Any
            if hasattr(result, "value"):
                result_val = {"value": result.value, "units": getattr(result, "units", "")}
            else:
                result_val = result
            return {"ok": True, "formula": formula, "params": params, "result": result_val}
        except Exception as exc:
            return {"ok": False, "error": str(exc), "formula": formula, "params": params}

    # ------------------------------------------------------------------
    # 2. physics_check
    # ------------------------------------------------------------------

    @mcp.tool(
        name="physics_check",
        description=(
            "Check the sanity of physical parameters using the oracle. "
            "params: {'alpha': 0.01, 'Ms': 800000, ...} format. "
            "ok=True means physically valid; ok=False returns reason/param."
        ),
        annotations=read_only,
    )
    def physics_check(params: dict[str, float]) -> dict[str, Any]:
        """Oracle sanity check tool.

        Args:
            params: Dictionary of physical parameters to check.

        Returns:
            {'ok': bool, 'reason': str, 'param': str, 'checks': list[str]}
        """
        from maglab.physics.oracle import check

        result = check(params)
        return {
            "ok": result.ok,
            "reason": result.reason,
            "param": result.param,
            "value": result.value,
            "checks": list(result.checks),
        }

    # ------------------------------------------------------------------
    # 3. convert_units
    # ------------------------------------------------------------------

    @mcp.tool(
        name="convert_units",
        description=(
            "Perform a magnetic unit conversion. "
            "Automatically selects the conversion function from from_unit and to_unit. "
            "Example: from_unit='Oe', to_unit='Am', value=1000."
        ),
        annotations=read_only,
    )
    def convert_units(value: float, from_unit: str, to_unit: str) -> dict[str, Any]:
        """Magnetic unit conversion tool.

        Args:
            value:     Numeric value to convert.
            from_unit: Source unit string (e.g. 'Oe', 'emu_cm3', 'tesla').
            to_unit:   Target unit string (e.g. 'Am', 'Am', 'Oe').

        Returns:
            {'ok': bool, 'input': float, 'from': str, 'to': str, 'result': float}
        """
        from maglab.physics import units as _u

        fn_name = f"{from_unit}_to_{to_unit}"
        fn = getattr(_u, fn_name, None)
        if fn is None:
            # List available conversions
            available = [n for n in dir(_u) if "_to_" in n and not n.startswith("_")]
            return {
                "ok": False,
                "error": f"Conversion function not found: {fn_name!r}",
                "available": available[:30],
            }
        try:
            result = fn(value)
            return {
                "ok": True,
                "input": value,
                "from": from_unit,
                "to": to_unit,
                "result": result,
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    # ------------------------------------------------------------------
    # 4. material_lookup
    # ------------------------------------------------------------------

    @mcp.tool(
        name="material_lookup",
        description=(
            "Look up detailed properties of a magnetic material by ID. "
            "material_id: 'Permalloy'·'YIG'·'CoFeB'·'GdFeCo', etc. "
            "Returns null if not found."
        ),
        annotations=read_only,
    )
    def material_lookup(material_id: str) -> dict[str, Any] | None:
        """Material ID lookup tool.

        Args:
            material_id: Unique material identifier string.

        Returns:
            Material properties dictionary, or None if not found.
        """
        from maglab.physics.materials import lookup

        mat = lookup(material_id)
        if mat is None:
            return None
        return mat.model_dump()

    # ------------------------------------------------------------------
    # 5. material_search
    # ------------------------------------------------------------------

    @mcp.tool(
        name="material_search",
        description=(
            "Search magnetic materials by keyword. "
            "query: partial string of name, formula, or ID. "
            "Returns a list of matching materials (id·name·formula)."
        ),
        annotations=read_only,
    )
    def material_search(query: str) -> list[dict[str, Any]]:
        """Material keyword search tool.

        Args:
            query: Search keyword string.

        Returns:
            List of material property dictionaries.
        """
        from maglab.physics.materials import search

        results = search(query)
        return [m.model_dump() for m in results]

    # ------------------------------------------------------------------
    # 6. provenance_query
    # ------------------------------------------------------------------

    @mcp.tool(
        name="provenance_query",
        description=(
            "Look up provenance information by DataPoint ID. "
            "datapoint_id: UUID string. "
            "Returns null if not found; otherwise returns DataPoint + lineage info."
        ),
        annotations=read_only,
    )
    def provenance_query(datapoint_id: str) -> dict[str, Any] | None:
        """DataPoint provenance query tool.

        Args:
            datapoint_id: DataPoint UUID string.

        Returns:
            {'datapoint': dict, 'lineage': list} or None.
        """
        from maglab.provenance.ledger import ProvenanceLedger

        ledger = ProvenanceLedger()
        dp = ledger.get(datapoint_id)
        if dp is None:
            return None
        lineage = ledger.lineage(datapoint_id)
        return {
            "datapoint": dp.model_dump(),
            "lineage": lineage,
        }

    # ==================================================================
    # P1 tools
    # ==================================================================

    # ------------------------------------------------------------------
    # 7. sim_validate
    # ------------------------------------------------------------------

    @mcp.tool(
        name="sim_validate",
        description=(
            "Statically validate a MultiScaleSpec JSON (full Appendix D micromagnetic rules). "
            "spec_dict: serialized MultiScaleSpec dictionary. "
            "ok=True means passed; ok=False returns a violations list."
        ),
        annotations=read_only,
    )
    def sim_validate(spec_dict: dict[str, Any]) -> dict[str, Any]:
        """MultiScaleSpec static validation tool.

        Args:
            spec_dict: Serialized MultiScaleSpec dictionary.

        Returns:
            {'ok': bool, 'violations': list[dict] | None, 'error': str | None}
        """
        from maglab.sim.spec import MultiScaleSpec
        from maglab.sim.validate import ValidationError, validate

        try:
            spec = MultiScaleSpec.model_validate(spec_dict)
        except Exception as exc:
            return {"ok": False, "violations": None, "error": f"spec parse error: {exc}"}

        try:
            validate(spec)
            return {"ok": True, "violations": [], "error": None}
        except ValidationError as exc:
            return {
                "ok": False,
                "violations": [
                    {
                        "rule": v.rule,
                        "message": v.message,
                        "actual": v.actual,
                        "recommended": v.recommended,
                        "scale_label": v.scale_label,
                    }
                    for v in exc.violations
                ],
                "error": str(exc),
            }

    # ------------------------------------------------------------------
    # 8. sim_run
    # ------------------------------------------------------------------

    @mcp.tool(
        name="sim_run",
        description=(
            "Run a micromagnetic simulation from a MultiScaleSpec. "
            "spec_dict: serialized MultiScaleSpec dictionary. "
            "Returns ok=False and error if external solver is not installed. "
            "On success, returns job_id and summary."
        ),
        annotations=write_op,
    )
    def sim_run(spec_dict: dict[str, Any]) -> dict[str, Any]:
        """Micromagnetic simulation run tool.

        Args:
            spec_dict: Serialized MultiScaleSpec dictionary.

        Returns:
            {'ok': bool, 'job_id': str, 'summary': str, 'error': str | None}
        """
        from maglab.sim.plot import run_sim_overlay
        from maglab.sim.spec import MultiScaleSpec

        try:
            MultiScaleSpec.model_validate(spec_dict)
        except Exception as exc:
            return {"ok": False, "job_id": "", "summary": "", "error": f"spec parse error: {exc}"}

        import warnings

        dps: list[Any] = []
        caught: list[str] = []

        try:
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                dps = run_sim_overlay(spec_dict)
                for warning in w:
                    caught.append(str(warning.message))
        except Exception as exc:
            return {"ok": False, "job_id": "", "summary": "", "error": str(exc)}

        if not dps and caught:
            return {
                "ok": False,
                "job_id": "",
                "summary": "",
                "error": "; ".join(caught),
            }

        import uuid

        job_id = f"mcp_{uuid.uuid4().hex[:8]}"
        return {
            "ok": True,
            "job_id": job_id,
            "summary": f"Simulation complete — {len(dps)} DataPoint(s) created",
            "datapoints": [dp.model_dump(mode="json") for dp in dps],
            "error": None,
        }

    # ------------------------------------------------------------------
    # 9. sim_parse
    # ------------------------------------------------------------------

    @mcp.tool(
        name="sim_parse",
        description=(
            "Parse a simulation output file and return a structured JobResult. "
            "engine: 'mumax3'|'oommf'|'magnumnp'. "
            "file_path: path to the output file. "
            "The LLM receives only the JobResult summary, not the raw file."
        ),
        annotations=read_only,
    )
    def sim_parse(engine: str, file_path: str) -> dict[str, Any]:
        """Simulation output parsing tool.

        Args:
            engine:    Solver engine name ('mumax3'|'oommf'|'magnumnp').
            file_path: Path to the output file to parse.

        Returns:
            {'ok': bool, 'summary': str, 'quantities': dict, 'error': str | None}
        """
        from pathlib import Path

        from maglab.sim.parse import parse_mumax3_table, parse_oommf_odt

        fp = Path(file_path)
        if not fp.exists():
            return {
                "ok": False,
                "summary": "",
                "quantities": {},
                "error": f"File not found: {file_path}",
            }

        try:
            if engine == "mumax3":
                result = parse_mumax3_table(fp)
            elif engine == "oommf":
                result = parse_oommf_odt(fp)
            else:
                return {
                    "ok": False,
                    "summary": "",
                    "quantities": {},
                    "error": f"Unsupported engine: {engine!r}. Supported: mumax3·oommf",
                }
        except Exception as exc:
            return {"ok": False, "summary": "", "quantities": {}, "error": str(exc)}

        qty_summary = {k: len(v) for k, v in result.quantities.items()}
        return {
            "ok": True,
            "summary": result.summary(),
            "job_id": result.job_id,
            "engine": result.engine,
            "converged": result.converged,
            "elapsed_s": result.elapsed_s,
            "quantities": qty_summary,
            "ovf_paths": result.ovf_paths,
            "error": result.error_message or None,
        }

    # ------------------------------------------------------------------
    # 10. figure_render
    # ------------------------------------------------------------------

    @mcp.tool(
        name="figure_render",
        description=(
            "Receive a FigureSpec JSON, render a vector figure, and export it to a file. "
            "spec_dict: serialized FigureSpec dictionary. "
            "output_path: output file path (including extension). "
            "fmt: 'pdf'|'svg'|'eps'. "
            "datapoints: DataPoint ID → DataPoint dict (optional). "
            "data-plot panels missing DataPoint bindings are blocked with IntegrityError."
        ),
        annotations=write_op,
    )
    def figure_render(
        spec_dict: dict[str, Any],
        output_path: str,
        fmt: str = "pdf",
        datapoints: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """FigureSpec render tool.

        Args:
            spec_dict:   Serialized FigureSpec dictionary.
            output_path: Output file path.
            fmt:         Format ('pdf'|'svg'|'eps').
            datapoints:  DataPoint ID → DataPoint dict (optional).

        Returns:
            {'ok': bool, 'path': str, 'error': str | None}
        """
        from maglab.figure.compose import FigureComposer
        from maglab.figure.export import FigureExporter
        from maglab.figure.spec import FigureSpec
        from maglab.provenance.datapoint import DataPoint

        try:
            spec = FigureSpec.model_validate(spec_dict)
        except Exception as exc:
            return {"ok": False, "path": "", "error": f"FigureSpec parse error: {exc}"}

        ledger: dict[str, DataPoint] = {}
        if datapoints:
            for dp_id, dp_dict in datapoints.items():
                with contextlib.suppress(Exception):
                    ledger[dp_id] = DataPoint.model_validate(dp_dict)

        try:
            fig = FigureComposer().compose(spec, ledger)
        except Exception as exc:
            return {"ok": False, "path": "", "error": str(exc)}

        try:
            saved = FigureExporter().export(fig, output_path, fmt=fmt)  # type: ignore[arg-type]
            return {"ok": True, "path": str(saved), "error": None}
        except Exception as exc:
            return {"ok": False, "path": "", "error": str(exc)}
        finally:
            import matplotlib.pyplot as plt

            with contextlib.suppress(Exception):
                plt.close(fig)

    # ------------------------------------------------------------------
    # 11. figure_export
    # ------------------------------------------------------------------

    @mcp.tool(
        name="figure_export",
        description=(
            "Export a FigureSpec JSON to multiple formats. "
            "spec_dict: serialized FigureSpec dictionary. "
            "stem: output path stem (no extension). "
            "formats: list of formats (e.g. ['pdf','svg']). "
            "Only panels renderable without DataPoint bindings are output."
        ),
        annotations=write_op,
    )
    def figure_export(
        spec_dict: dict[str, Any],
        stem: str,
        formats: list[str] | None = None,
        datapoints: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """FigureSpec multi-format export tool.

        Args:
            spec_dict:  Serialized FigureSpec dictionary.
            stem:       Output path stem (no extension).
            formats:    Format list. Defaults to ['pdf','svg'] if None.
            datapoints: DataPoint ID → DataPoint dict (optional).

        Returns:
            {'ok': bool, 'paths': dict[str,str], 'error': str | None}
        """
        from maglab.figure.compose import FigureComposer
        from maglab.figure.export import FigureExporter
        from maglab.figure.spec import FigureSpec
        from maglab.provenance.datapoint import DataPoint

        try:
            spec = FigureSpec.model_validate(spec_dict)
        except Exception as exc:
            return {"ok": False, "paths": {}, "error": f"FigureSpec parse error: {exc}"}

        ledger: dict[str, DataPoint] = {}
        if datapoints:
            for dp_id, dp_dict in datapoints.items():
                with contextlib.suppress(Exception):
                    ledger[dp_id] = DataPoint.model_validate(dp_dict)

        fmts = formats or ["pdf", "svg"]

        try:
            fig = FigureComposer().compose(spec, ledger)
        except Exception as exc:
            return {"ok": False, "paths": {}, "error": str(exc)}

        try:
            results = FigureExporter().export_all(
                fig,
                stem,
                formats=fmts,  # type: ignore[arg-type]
            )
            return {
                "ok": True,
                "paths": {k: str(v) for k, v in results.items()},
                "error": None,
            }
        except Exception as exc:
            return {"ok": False, "paths": {}, "error": str(exc)}
        finally:
            import matplotlib.pyplot as plt

            with contextlib.suppress(Exception):
                plt.close(fig)


# ---------------------------------------------------------------------------
# P4 instrument-domain tool registration (T-P4-28)
# ---------------------------------------------------------------------------


def _register_instrument_tools(mcp: FastMCP) -> None:
    """Register P4 instrument-domain tools with the MCP server (T-P4-28)."""

    read_only = _READ_ONLY_ANNOTATIONS
    write_op = _WRITE_ANNOTATIONS

    # ------------------------------------------------------------------
    # 12. instr_search_manual
    # ------------------------------------------------------------------

    @mcp.tool(
        name="instr_search_manual",
        description=(
            "Search the web for an instrument manual PDF and download it to the local cache. "
            "model: instrument model name (★ must be confirmed with the user — never guess). "
            "manufacturer: optional manufacturer name. "
            "Returns ok=True and pdf_path on success, ok=False and error on failure."
        ),
        annotations=write_op,  # downloads PDF + sha256.txt to local cache — not read-only
    )
    def instr_search_manual(
        model: str,
        manufacturer: str | None = None,
    ) -> dict[str, Any]:
        """Search and download an instrument manual PDF.

        Args:
            model:        Instrument model name (user-confirmed, never guessed).
            manufacturer: Manufacturer name (optional; inferred from model when None).

        Returns:
            {'ok': bool, 'pdf_path': str | None, 'cached': bool, 'error': str | None}
        """
        from maglab.instrument.manual_search import ManualSearcher

        searcher = ManualSearcher()
        try:
            result = searcher.search_and_download(model, manufacturer=manufacturer)
            return {
                "ok": result.ok,
                "pdf_path": str(result.pdf_path) if result.pdf_path else None,
                "url": result.url,
                "cached": result.cached,
                "sha256": result.sha256,
                "error": result.error,
            }
        except Exception as exc:
            return {"ok": False, "pdf_path": None, "url": None, "cached": False, "error": str(exc)}

    # ------------------------------------------------------------------
    # 13. instr_ingest_manual
    # ------------------------------------------------------------------

    @mcp.tool(
        name="instr_ingest_manual",
        description=(
            "Ingest a local instrument manual PDF into the SCPI RAG index. "
            "model: instrument model name (★ must be confirmed with the user — never guess). "
            "pdf_path: local path to the PDF file. "
            "manufacturer: optional manufacturer name. "
            "Returns ok=True with chunk_count on success."
        ),
        annotations=write_op,
    )
    def instr_ingest_manual(
        model: str,
        pdf_path: str,
        manufacturer: str | None = None,
    ) -> dict[str, Any]:
        """Ingest a local manual PDF into the RAG index.

        Args:
            model:        Instrument model name (user-confirmed, never guessed).
            pdf_path:     Local file path to the PDF manual.
            manufacturer: Manufacturer name (optional).

        Returns:
            {'ok': bool, 'chunk_count': int, 'model_key': str, 'error': str | None}
        """
        from pathlib import Path

        from maglab.instrument.manual_rag import ManualRAGPipeline
        from maglab.instrument.manual_search import ManualSearcher

        try:
            p = Path(pdf_path)
            if not p.exists():
                return {"ok": False, "chunk_count": 0, "model_key": "", "error": f"File not found: {pdf_path}"}

            # Cache the local file
            searcher = ManualSearcher()
            cache_result = searcher.ingest_local(model, p, manufacturer=manufacturer)

            # Build RAG index — model is used as the model_key for the index
            pipeline = ManualRAGPipeline()
            index = pipeline.ingest(model_key=model, pdf_path=p)
            return {
                "ok": True,
                "chunk_count": index.chunk_count,
                "model_key": model,
                "cached_at": str(cache_result.pdf_path) if cache_result.pdf_path else None,
                "error": None,
            }
        except Exception as exc:
            return {"ok": False, "chunk_count": 0, "model_key": "", "error": str(exc)}

    # ------------------------------------------------------------------
    # 14. instr_generate_skill
    # ------------------------------------------------------------------

    @mcp.tool(
        name="instr_generate_skill",
        description=(
            "Generate an instrument SKILL.md package from the RAG index. "
            "model: instrument model name (★ must be confirmed with the user — never guess). "
            "manufacturer: manufacturer name. "
            "safety_model: safety profile key (default 'generic'). "
            "Returns ok=True with skill_dir and generated file list on success."
        ),
        annotations=write_op,
    )
    def instr_generate_skill(
        model: str,
        manufacturer: str,
        safety_model: str = "generic",
        output_dir: str | None = None,
    ) -> dict[str, Any]:
        """Generate an instrument skill package.

        Args:
            model:        Instrument model name (user-confirmed, never guessed).
            manufacturer: Manufacturer name.
            safety_model: Safety profile key (e.g. 'keithley-2400', 'sr830', 'generic').
            output_dir:   Override output directory (optional).

        Returns:
            {'ok': bool, 'skill_dir': str, 'files': list[str], 'error': str | None}
        """
        from pathlib import Path

        from maglab.instrument.skillgen import SkillGenerator

        try:
            output_root = Path(output_dir) if output_dir else None
            gen = SkillGenerator(output_root=output_root)
            pkg = gen.generate(model=model, manufacturer=manufacturer, safety_model=safety_model)
            return {
                "ok": pkg.ok,
                "skill_dir": str(pkg.skill_dir),
                "files": [str(f) for f in pkg.files],
                "chunk_count": pkg.chunk_count,
                "error": None if pkg.ok else "SKILL.md was not generated",
            }
        except Exception as exc:
            return {"ok": False, "skill_dir": "", "files": [], "error": str(exc)}

    # ------------------------------------------------------------------
    # 15. instr_scaffold
    # ------------------------------------------------------------------

    @mcp.tool(
        name="instr_scaffold",
        description=(
            "Generate a PyVISA backend skeleton Python file for an instrument. "
            "model: instrument model name (★ must be confirmed with the user — never guess). "
            "iface: interface type (GPIB, USB, TCPIP, SERIAL, PXI). "
            "output_path: optional path to save the generated file. "
            "Returns ok=True with the generated code on success."
        ),
        annotations=write_op,
    )
    def instr_scaffold(
        model: str,
        iface: str = "GPIB",
        output_path: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Generate a PyVISA backend skeleton.

        Args:
            model:       Instrument model name (user-confirmed, never guessed).
            iface:       Interface type (GPIB, USB, TCPIP, SERIAL, PXI).
            output_path: Optional path to save the file.
            options:     Resource string options (gpib_addr, host, etc.).

        Returns:
            {'ok': bool, 'code': str, 'output_path': str | None, 'error': str | None}
        """
        from pathlib import Path

        from maglab.instrument.scaffold import generate_scaffold

        try:
            out = Path(output_path) if output_path else None
            code = generate_scaffold(model=model, iface=iface, output_path=out, options=options)
            return {
                "ok": True,
                "code": code,
                "output_path": str(out) if out else None,
                "error": None,
            }
        except Exception as exc:
            return {"ok": False, "code": "", "output_path": None, "error": str(exc)}

    # ------------------------------------------------------------------
    # 16. instr_safety_check
    # ------------------------------------------------------------------

    @mcp.tool(
        name="instr_safety_check",
        description=(
            "Run the SCPI safety-envelope validator on a list of SCPI commands or a Python script. "
            "commands: list of SCPI command strings (mutually exclusive with script_text). "
            "script_text: Python script text to extract and validate SCPI commands from. "
            "model: safety profile key (default 'generic'). "
            "Returns ok=True when safe; ok=False with violations on failure."
        ),
        annotations=read_only,
    )
    def instr_safety_check(
        model: str = "generic",
        commands: list[str] | None = None,
        script_text: str | None = None,
    ) -> dict[str, Any]:
        """Run SCPI safety-envelope validation.

        Args:
            model:       Safety profile key (e.g. 'keithley-2400', 'sr830', 'generic').
            commands:    List of SCPI command strings.
            script_text: Python script text (alternative to commands).

        Returns:
            {'ok': bool, 'profile': str, 'violations': list[dict], 'warnings': list[dict],
             'summary': str, 'error': str | None}
        """
        from maglab.instrument.safety import check_scpi, check_script

        try:
            if script_text is not None:
                result = check_script(script_text, model=model)
            elif commands is not None:
                result = check_scpi(commands, model=model)
            else:
                return {
                    "ok": False,
                    "profile": model,
                    "violations": [],
                    "warnings": [],
                    "summary": "",
                    "error": "Either 'commands' or 'script_text' must be provided.",
                }

            def _violation_dict(v: Any) -> dict[str, Any]:
                return {
                    "type": str(v.violation_type),
                    "line": v.line_number,
                    "command": v.command,
                    "message": v.message,
                    "is_error": v.is_error,
                }

            return {
                "ok": result.ok,
                "profile": result.profile_used,
                "violations": [_violation_dict(v) for v in result.violations],
                "warnings": [_violation_dict(w) for w in result.warnings],
                "summary": result.summary(),
                "error": None,
            }
        except Exception as exc:
            return {
                "ok": False,
                "profile": model,
                "violations": [],
                "warnings": [],
                "summary": "",
                "error": str(exc),
            }


# ---------------------------------------------------------------------------
# Resource registration
# ---------------------------------------------------------------------------


def _register_resources(mcp: FastMCP) -> None:
    """Register P0 resources with the MCP server."""

    @mcp.resource("materials://")
    def materials_resource() -> str:
        """Return the full magnetic material list as JSON.

        Returns:
            Material list JSON string.
        """
        import json

        from maglab.physics.materials import list_materials

        mats = list_materials()
        return json.dumps(
            [m.model_dump() for m in mats],
            ensure_ascii=False,
            indent=2,
        )

    @mcp.resource("provenance://")
    def provenance_resource() -> str:
        """Return the full list of registered DataPoints as JSON.

        Returns:
            DataPoint list JSON string.
        """
        import json

        from maglab.provenance.ledger import ProvenanceLedger

        ledger = ProvenanceLedger()
        ids = ledger.all_ids()
        items = []
        for dp_id in ids:
            dp = ledger.get(dp_id)
            if dp is not None:
                items.append(dp.model_dump())
        return json.dumps(items, ensure_ascii=False, indent=2, default=str)

    @mcp.resource("manuals://")
    def manuals_resource() -> str:
        """Return the list of cached instrument manuals as JSON.

        Lists all PDFs under the standard manual cache root
        (``~/.local/share/maglab/manuals/``).

        Returns:
            JSON array of ``{manufacturer, model, pdf_path, sha256}`` entries.
        """
        import json
        from pathlib import Path

        cache_root = Path.home() / ".local" / "share" / "maglab" / "manuals"
        entries: list[dict[str, Any]] = []

        if cache_root.is_dir():
            for mfr_dir in sorted(cache_root.iterdir()):
                if not mfr_dir.is_dir():
                    continue
                for model_dir in sorted(mfr_dir.iterdir()):
                    if not model_dir.is_dir():
                        continue
                    pdfs = sorted(model_dir.glob("*.pdf"))
                    sha_file = model_dir / "sha256.txt"
                    sha256 = sha_file.read_text(encoding="utf-8").strip() if sha_file.is_file() else None
                    for pdf in pdfs:
                        entries.append(
                            {
                                "manufacturer": mfr_dir.name,
                                "model": model_dir.name,
                                "pdf_path": str(pdf),
                                "sha256": sha256,
                            }
                        )

        return json.dumps(entries, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Module-level convenience function (for CLI entry point)
# ---------------------------------------------------------------------------


def serve(transport: str = "stdio", host: str = "127.0.0.1", port: int = 8765) -> None:
    """Start the MagLab MCP server.

    Args:
        transport: Transport mode ('stdio' or 'http').
        host:      HTTP bind address (used only in http mode).
        port:      HTTP port (used only in http mode).
    """
    server = create_server()
    if transport == "http":
        server.run(transport="http", host=host, port=port)
    else:
        server.run(transport="stdio")
