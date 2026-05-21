"""Project artifact inventory helpers for reports, provenance, and tasks.

This module is intentionally deterministic and file-backed.  It only reports
artifacts that already exist in the active workspace or in an explicit runtime
database path; it does not invent task state or create provenance records.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import platformdirs

from maglab.core.checkpoint import CheckpointRecord, CheckpointStore, StepStatus

_APP = "maglab"

REPORT_DIRS: tuple[str, ...] = (
    "maglab_write",
    "maglab_slides",
    "maglab_poster",
    ".maglab/reports",
)
REPORT_EXTENSIONS: frozenset[str] = frozenset(
    {".bib", ".json", ".md", ".pdf", ".pptx", ".svg", ".tex", ".txt"}
)
PROVENANCE_NAME_RE = re.compile(r"(?:^|[_\-.])(prov|provenance)(?:[_\-.]|$)", re.IGNORECASE)
_SKIP_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".hg",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
    }
)


@dataclass(frozen=True)
class ArtifactRecord:
    """A workspace artifact exposed by the command surface."""

    path: str
    kind: str
    bytes: int
    modified: str
    detail: str = ""


@dataclass(frozen=True)
class TaskCheckpointSummary:
    """Checkpoint summary for one task ID."""

    task_id: str
    checkpoint_count: int
    by_status: dict[str, int]
    last_updated: str | None
    provenance_ids: list[str]
    checkpoints: list[dict[str, Any]]


def discover_report_artifacts(
    root: Path | str = ".", *, max_entries: int = 100
) -> list[ArtifactRecord]:
    """List generated report/presentation artifacts from known MagLab output dirs."""
    root_path = Path(root).resolve()
    artifacts: list[ArtifactRecord] = []
    for rel_dir in REPORT_DIRS:
        base = root_path / rel_dir
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in REPORT_EXTENSIONS:
                continue
            artifacts.append(
                _artifact_record(path, root_path, kind=_classify_report_artifact(path))
            )
    artifacts.sort(key=lambda item: item.modified, reverse=True)
    return artifacts[:max_entries]


def discover_provenance_artifacts(
    root: Path | str = ".", *, max_entries: int = 100
) -> list[ArtifactRecord]:
    """List provenance sidecars already present in the workspace."""
    root_path = Path(root).resolve()
    artifacts: list[ArtifactRecord] = []
    for path in _iter_workspace_files(root_path):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".json", ".jsonl", ".db", ".sqlite", ".sqlite3"}:
            continue
        if not PROVENANCE_NAME_RE.search(path.name):
            continue
        artifacts.append(
            _artifact_record(path, root_path, kind=_classify_provenance_artifact(path))
        )
    artifacts.sort(key=_provenance_artifact_sort_key)
    return artifacts[:max_entries]


def summarize_provenance_db(db_path: Path | str) -> dict[str, Any]:
    """Return a read-only summary of a W3C PROV SQLite store."""
    path = Path(db_path)
    if not path.exists():
        return {"db_path": str(path), "exists": False, "records": 0, "by_kind": {}}

    by_kind: dict[str, int] = {}
    records = 0
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as conn:
        try:
            cur = conn.execute("SELECT kind, COUNT(*) FROM prov_records GROUP BY kind")
        except sqlite3.Error:
            return {
                "db_path": str(path),
                "exists": True,
                "records": 0,
                "by_kind": {},
                "error": "not a MagLab provenance store",
            }
        for kind, count in cur.fetchall():
            by_kind[str(kind)] = int(count)
            records += int(count)
    return {"db_path": str(path), "exists": True, "records": records, "by_kind": by_kind}


def default_checkpoint_db_path() -> Path:
    """Return the default checkpoint DB path without creating it."""
    return Path(platformdirs.user_data_dir(_APP)) / "checkpoint.db"


def list_checkpoint_tasks(db_path: Path | str | None = None) -> list[dict[str, Any]]:
    """List task IDs present in the checkpoint database without creating it."""
    path = Path(db_path) if db_path is not None else default_checkpoint_db_path()
    if not path.exists():
        return []
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT task_id, COUNT(*) AS checkpoint_count, MAX(ts_updated) AS last_updated
                FROM checkpoints
                GROUP BY task_id
                ORDER BY last_updated DESC
                """
            ).fetchall()
        except sqlite3.Error:
            return []
    return [
        {
            "task_id": row["task_id"],
            "checkpoint_count": int(row["checkpoint_count"]),
            "last_updated": _format_ts(row["last_updated"]),
        }
        for row in rows
    ]


def summarize_task_checkpoints(
    task_id: str,
    *,
    db_path: Path | str | None = None,
) -> TaskCheckpointSummary:
    """Summarize persisted checkpoints for a task ID."""
    path = Path(db_path) if db_path is not None else default_checkpoint_db_path()
    if not path.exists():
        return TaskCheckpointSummary(
            task_id=task_id,
            checkpoint_count=0,
            by_status={status.value: 0 for status in StepStatus},
            last_updated=None,
            provenance_ids=[],
            checkpoints=[],
        )

    store = CheckpointStore(db_path=path)
    try:
        records = store.list_task(task_id)
    finally:
        store.close()
    return _checkpoint_summary(task_id, records)


def write_task_scaffold(
    goal: str,
    *,
    root: Path | str = ".",
    task_id: str | None = None,
) -> Path:
    """Create a workspace-local task scaffold under ``.maglab/tasks``."""
    root_path = Path(root).resolve()
    slug = _slugify(task_id or goal)
    task_dir = root_path / ".maglab" / "tasks"
    task_dir.mkdir(parents=True, exist_ok=True)
    path = task_dir / f"{slug}.md"
    if path.exists():
        return path

    now = datetime.now(UTC).isoformat(timespec="seconds")
    resolved_task_id = task_id or slug
    path.write_text(
        "\n".join(
            [
                "---",
                f"task_id: {resolved_task_id}",
                f"created_at: {now}",
                "status: pending",
                "provenance_ids: []",
                "artifacts: []",
                "---",
                "",
                f"# {goal}",
                "",
                "## Objective",
                goal,
                "",
                "## Plan",
                "- [ ] Define the scientific question and required inputs.",
                "- [ ] Run deterministic MagLab tools for calculations, fitting, or simulation.",
                "- [ ] Attach provenance IDs and generated artifacts.",
                "- [ ] Run integrity checks before reporting.",
                "",
                "## Checkpoints",
                "| Step | Status | Provenance | Artifact |",
                "|---|---|---|---|",
                "| setup | pending |  |  |",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return path


def task_scaffold_inventory(root: Path | str = ".") -> list[ArtifactRecord]:
    """List workspace-local task scaffold files."""
    root_path = Path(root).resolve()
    base = root_path / ".maglab" / "tasks"
    if not base.exists():
        return []
    artifacts = [
        _artifact_record(path, root_path, kind="task-scaffold")
        for path in base.glob("*.md")
        if path.is_file()
    ]
    artifacts.sort(key=lambda item: item.modified, reverse=True)
    return artifacts


def _artifact_record(path: Path, root: Path, *, kind: str) -> ArtifactRecord:
    stat = path.stat()
    detail = _artifact_detail(path)
    try:
        rel = path.relative_to(root)
    except ValueError:
        rel = path
    return ArtifactRecord(
        path=str(rel),
        kind=kind,
        bytes=stat.st_size,
        modified=_format_ts(stat.st_mtime) or "",
        detail=detail,
    )


def _artifact_detail(path: Path) -> str:
    if path.name == "HUMAN_REVIEW_REQUIRED.txt":
        return "human-review-marker"
    if path.suffix.lower() == ".json":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return ""
        if isinstance(data, list):
            return f"{len(data)} json records"
        if isinstance(data, dict):
            return f"{len(data)} json keys"
    return ""


def _classify_report_artifact(path: Path) -> str:
    parts = {part.lower() for part in path.parts}
    name = path.name.lower()
    if "maglab_slides" in parts or name.startswith("slides."):
        return "slides"
    if "maglab_poster" in parts or name.startswith("poster."):
        return "poster"
    if name == "main.tex":
        return "manuscript"
    if name == "HUMAN_REVIEW_REQUIRED.txt".lower():
        return "review-marker"
    return "report"


def _classify_provenance_artifact(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".db", ".sqlite", ".sqlite3"}:
        return "provenance-db"
    if suffix == ".jsonl":
        return "provenance-jsonl"
    return "provenance-json"


def _provenance_artifact_sort_key(item: ArtifactRecord) -> tuple[int, str, str]:
    kind_priority = {
        "provenance-json": 0,
        "provenance-jsonl": 1,
        "provenance-db": 2,
    }
    return (kind_priority.get(item.kind, 99), item.path.lower(), item.modified)


def _checkpoint_summary(task_id: str, records: list[CheckpointRecord]) -> TaskCheckpointSummary:
    by_status = {status.value: 0 for status in StepStatus}
    checkpoints: list[dict[str, Any]] = []
    provenance_ids: list[str] = []
    last_updated: float | None = None
    for record in records:
        by_status[record.status.value] = by_status.get(record.status.value, 0) + 1
        if record.provenance_id and record.provenance_id not in provenance_ids:
            provenance_ids.append(record.provenance_id)
        last_updated = max(last_updated or record.ts_updated, record.ts_updated)
        checkpoints.append(
            {
                "checkpoint_id": record.checkpoint_id,
                "idempotency_key": record.idempotency_key,
                "status": record.status.value,
                "provenance_id": record.provenance_id,
                "updated": _format_ts(record.ts_updated),
                "payload": record.payload,
            }
        )
    return TaskCheckpointSummary(
        task_id=task_id,
        checkpoint_count=len(records),
        by_status=by_status,
        last_updated=_format_ts(last_updated) if last_updated else None,
        provenance_ids=provenance_ids,
        checkpoints=checkpoints,
    )


def _format_ts(ts: float | int | str | None) -> str | None:
    if ts is None:
        return None
    try:
        value = float(ts)
    except (TypeError, ValueError):
        return str(ts)
    return datetime.fromtimestamp(value, tz=UTC).isoformat(timespec="seconds")


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug[:80] or f"task-{int(time.time())}"


def artifact_records_to_dicts(records: list[ArtifactRecord]) -> list[dict[str, Any]]:
    """JSON helper for command modules."""
    return [asdict(record) for record in records]


def _iter_workspace_files(root: Path) -> list[Path]:
    paths: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            name
            for name in dirnames
            if name not in _SKIP_DIRS and not (name.startswith(".") and name != ".maglab")
        ]
        base = Path(dirpath)
        paths.extend(base / filename for filename in filenames)
    return paths
