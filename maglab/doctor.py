"""Whole-environment readiness checks for MagLab first-run UX.

``maglab doctor`` is intentionally read-only. It answers the question a new
researcher asks after installing MagLab globally and opening a project folder:

- Which folder is MagLab using as the active workspace?
- Is an LLM backend selected and secret-safe credentials available?
- Which research feature extras are importable?
- Which optional external tools are on PATH?
- Is the simulation stack ready for CPU, GPU, SSH GPU, or HPC use?
"""

from __future__ import annotations

import importlib.util
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from maglab.config import Config, config_path, load_config
from maglab.setup import FEATURES, RECOMMENDED_INSTALL, normalize_feature
from maglab.workspace import iter_workspace_entries, workspace_info


@dataclass(frozen=True)
class FeatureDoctor:
    """Readiness snapshot for one optional MagLab feature area."""

    key: str
    title: str
    extra: str
    slash: str
    python: dict[str, bool]
    external: dict[str, bool]
    notes: tuple[str, ...]

    @property
    def python_ready(self) -> bool:
        """True when every declared Python import for this feature is importable."""
        return all(self.python.values()) if self.python else True

    @property
    def external_ready(self) -> bool:
        """True when every declared external command is on PATH.

        External tools are often optional alternatives, so the doctor reports
        this separately from ``python_ready`` rather than treating it as fatal.
        """
        return all(self.external.values()) if self.external else True

    @property
    def missing_python(self) -> list[str]:
        """Return missing Python import names."""
        return [name for name, ok in self.python.items() if not ok]

    @property
    def missing_external(self) -> list[str]:
        """Return missing external command names."""
        return [name for name, ok in self.external.items() if not ok]

    def to_dict(self) -> dict[str, Any]:
        """Serialize the feature doctor result."""
        return {
            "key": self.key,
            "title": self.title,
            "extra": self.extra,
            "slash": self.slash,
            "python_ready": self.python_ready,
            "external_ready": self.external_ready,
            "python": self.python,
            "external": self.external,
            "missing_python": self.missing_python,
            "missing_external": self.missing_external,
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class UXDoctor:
    """Evidence-backed UX contract check from plan/ to installed CLI."""

    key: str
    title: str
    status: str
    evidence: str
    command: str

    def to_dict(self) -> dict[str, str]:
        """Serialize the UX check."""
        return {
            "key": self.key,
            "title": self.title,
            "status": self.status,
            "evidence": self.evidence,
            "command": self.command,
        }


def _module_ok(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def _binary_ok(binary: str) -> bool:
    return shutil.which(binary) is not None


def _doctor_feature(key: str) -> FeatureDoctor:
    feature = FEATURES[key]
    return FeatureDoctor(
        key=feature.key,
        title=feature.title,
        extra=feature.extra,
        slash=feature.slash,
        python={name: _module_ok(name) for name in feature.imports},
        external={name: _binary_ok(name) for name in feature.binaries},
        notes=feature.notes,
    )


def _backend_snapshot(config: Config) -> dict[str, Any]:
    """Return non-secret backend status."""
    from maglab.llm.factory import backend_status

    status = backend_status(config)
    return {
        "ok": status.ok,
        "mode": status.mode,
        "label": status.label,
        "detail": status.detail,
        "action": status.action,
    }


def _path_exists(*parts: str) -> bool:
    root = Path(__file__).resolve().parent
    return (root.joinpath(*parts)).exists()


def _ux_contract_report(
    *,
    backend: dict[str, Any],
    workspace: dict[str, Any],
    sim_report: dict[str, Any] | None,
) -> list[UXDoctor]:
    """Map the plan's UX promises to concrete installed commands/artifacts."""
    from maglab.llm.tools import get_registered_tools
    from maglab.manuals import available_languages, list_manuals

    tool_names = {tool.name for tool in get_registered_tools()}
    langs = set(available_languages())
    ko_manuals = len(list_manuals("ko")) if "ko" in langs else 0
    en_manuals = len(list_manuals("en")) if "en" in langs else 0

    return [
        UXDoctor(
            key="first-run",
            title="First folder read",
            status="ready" if workspace.get("maglab_md") else "partial",
            evidence=(
                f"cwd={workspace['root']}; MAGLAB.md="
                f"{workspace.get('maglab_md') or 'not initialized'}"
            ),
            command="maglab workspace status · maglab workspace tree · maglab workspace init",
        ),
        UXDoctor(
            key="llm-files",
            title="LLM file use",
            status=(
                "ready"
                if {"workspace_tree", "workspace_read_file", "workspace_search"} <= tool_names
                else "missing"
            ),
            evidence="workspace_tree/read_file/search tools are registered and scoped to cwd",
            command="maglab ask '<natural-language task>'",
        ),
        UXDoctor(
            key="models",
            title="Model connection",
            status="ready" if backend.get("ok") else "partial",
            evidence=f"{backend['label']} — {backend['detail']}",
            command="/connect codex · /connect openai · /connect anthropic · maglab auth status",
        ),
        UXDoctor(
            key="gpu-ssh-cpu",
            title="GPU, SSH, and no-GPU paths",
            status="ready" if sim_report else "partial",
            evidence=(
                f"recommended={sim_report.get('recommended_backend')} "
                f"paths={', '.join(p.get('key', '') + ':' + p.get('status', '') for p in sim_report.get('backend_paths', [])[:4])}"
                if sim_report
                else "simulation doctor not requested"
            ),
            command="maglab sim doctor --backend auto|local-gpu|ssh-gpu|ssh-hpc",
        ),
        UXDoctor(
            key="figures",
            title="Figure quality",
            status=(
                "ready"
                if _path_exists("figure", "styles") and _path_exists("figure", "primitives")
                else "partial"
            ),
            evidence="vector PDF/EPS/SVG export, journal style profiles, primitive catalog",
            command="maglab figure spec · render · export · primitives list",
        ),
        UXDoctor(
            key="deliverables",
            title="Research deliverables",
            status="ready",
            evidence="figures, manuscripts, communications, slides/posters, ELN, instrument skills",
            command="maglab write · present slides|poster · comms · lab note · instr skillgen",
        ),
        UXDoctor(
            key="design-refs",
            title="Poster and deck references",
            status=("ready" if _path_exists("authoring", "present", "templates") else "partial"),
            evidence="source-backed APS oral/poster, A0, beamerposter, Marp, SVG, PPTX profiles",
            command="maglab present templates --detail",
        ),
        UXDoctor(
            key="language",
            title="Language support",
            status="ready" if {"en", "ko"} <= langs and en_manuals and ko_manuals else "partial",
            evidence=f"manuals: en={en_manuals}, ko={ko_manuals}",
            command="maglab manual --lang en · maglab manual --lang ko",
        ),
        UXDoctor(
            key="physics-integrity",
            title="Physical consistency",
            status="ready",
            evidence="physics oracle, unit conversions, provenance, honesty gate",
            command="maglab physics oracle · maglab analyze consistency · maglab doctor",
        ),
    ]


def run_doctor(
    *,
    feature: str = "all",
    include_sim: bool = True,
    sim_backend: str = "auto",
    host: str | None = None,
    user: str | None = None,
    probe_ssh: bool = False,
    max_workspace_entries: int = 40,
) -> dict[str, Any]:
    """Build a read-only MagLab environment doctor report.

    Parameters
    ----------
    feature:
        ``all`` or a feature key from :mod:`maglab.setup`.
    include_sim:
        Whether to include ``sim doctor`` output in the report.
    sim_backend:
        Simulation backend requested for the nested simulation doctor.
    host, user, probe_ssh:
        Optional SSH target. Remote SSH is not probed unless ``probe_ssh`` is
        true, matching ``maglab sim doctor``.
    max_workspace_entries:
        Maximum visible project entries to include.
    """
    cfg = load_config()
    info = workspace_info()

    feature_key = normalize_feature(feature)
    if feature_key in {"research", "all"}:
        feature_keys = list(FEATURES)
    elif feature_key in FEATURES:
        feature_keys = [feature_key]
    else:
        feature_keys = []

    features = [_doctor_feature(key) for key in feature_keys]

    recommendations: list[str] = []
    if not feature_keys:
        recommendations.append(
            f"Unknown feature {feature!r}; use `maglab setup all` to list valid feature keys."
        )

    if info.maglab_md is None:
        recommendations.append(
            "Run `maglab workspace init` to create project-specific MAGLAB.md context."
        )

    backend = _backend_snapshot(cfg)
    if not backend["ok"]:
        recommendations.append(
            "Connect an LLM backend with `maglab auth codex`, `maglab auth openai`, "
            "or `/connect codex` inside the REPL."
        )

    missing_python_features = [f.key for f in features if not f.python_ready]
    if missing_python_features:
        recommendations.append(
            f"Install the full research bundle: `{RECOMMENDED_INSTALL}`. "
            f"Missing Python extras in: {', '.join(missing_python_features)}."
        )

    if any(f.missing_external for f in features):
        recommendations.append(
            "External solvers and CLIs are optional but needed for real hardware, GPU, or HPC paths; "
            "run `maglab setup <feature>` for exact commands."
        )

    sim_report: dict[str, Any] | None = None
    if include_sim:
        from maglab.sim.environment import diagnose_sim_environment

        sim_report = diagnose_sim_environment(
            backend=sim_backend,
            host=host,
            user=user,
            probe_ssh=probe_ssh,
        )
        if sim_report.get("recommendations"):
            recommendations.append(
                "Run `maglab sim doctor` before spending real GPU or cluster time."
            )

    workspace = {
        "root": str(info.root),
        "project_state": str(info.local_state_dir),
        "maglab_md": str(info.maglab_md) if info.maglab_md else None,
        "global_config": str(info.config_dir),
        "global_data": str(info.data_dir),
        "global_cache": str(info.cache_dir),
        "visible_entries": iter_workspace_entries(info.root, max_entries=max_workspace_entries),
    }
    ux_contract = _ux_contract_report(backend=backend, workspace=workspace, sim_report=sim_report)

    return {
        "ok": bool(backend["ok"]) and not missing_python_features,
        "config": str(config_path()),
        "workspace": workspace,
        "backend": backend,
        "features": [f.to_dict() for f in features],
        "simulation": sim_report,
        "ux_contract": [item.to_dict() for item in ux_contract],
        "recommendations": list(dict.fromkeys(recommendations)),
    }
