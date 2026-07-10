"""Read-only queries over FlexLock run directories — the agent-facing contract.

Everything here is side-effect free: run locks are read with ``yaml.safe_load``
(NOT ``RunRecord.load``, which resolves interpolations and can fire ``${vinc:}``
resolvers that create directories). The JSON shapes returned by these functions
are the stable contract consumed by the CLI (``show``/``graph``/``why``/
``stages``), the shipped skills, and the HTML report.
"""

import json
from pathlib import Path
from typing import Optional

import yaml

from .run_record import (
    RunRecord,
    LOCK_NAME,
    COMPLETE_MARKER,
    ERROR_NAME,
)

SCHEMA_VERSION = 1

MARKER_NAME = ".flexlock_marker"
TASKS_DB_NAME = "run.lock.tasks.db"

# Map task-DB statuses onto the run-dir status vocabulary.
_TASK_STATUS_MAP = {
    "done": "complete",
    "failed": "failed",
    "interrupted": "interrupted",
    "running": "running",
    "pending": "pending",
}


def _load_lock(run_dir: Path) -> Optional[dict]:
    """Parse ``run.lock`` with a side-effect-free loader, or ``None``."""
    lock = Path(run_dir) / LOCK_NAME
    if not lock.exists():
        return None
    try:
        with open(lock) as f:
            return yaml.safe_load(f)
    except Exception:
        return None


def _read_marker(run_dir: Path) -> Optional[dict]:
    marker = Path(run_dir) / MARKER_NAME
    if not marker.exists():
        return None
    try:
        return json.loads(marker.read_text())
    except Exception:
        return None


def _resolve_marker_db(run_dir: Path, marker: dict) -> Path:
    """Resolve the task DB path recorded in a ``.flexlock_marker``.

    The worker stores ``db`` relative to the task dir's *parent* (worker.py),
    so a relative path is resolved against ``run_dir.parent``.
    """
    db = Path(marker.get("db", ""))
    if not db.is_absolute():
        db = (Path(run_dir).parent / db)
    return db


def run_status(run_dir) -> dict:
    """Classify a run directory from what's on disk.

    Returns ``{"status", "detail", "kind", "tasks"|None, "error"|None}``.

    Precedence (see plan Phase B):
      1. ``.flexlock_marker`` → sweep-task dir (query the task DB row).
      2. ``run.complete`` → ``complete``.
      3. ``run.error`` → ``failed`` (payload attached).
      4. ``run.lock`` + task DB in dir → sweep master (aggregate counts).
      5. bare ``run.lock`` → ``interrupted`` (may still be running in-process).
      6. otherwise → ``unknown``.
    """
    run_dir = Path(run_dir)
    rec = RunRecord(run_dir)

    # 1. Sweep-task dir.
    marker = _read_marker(run_dir)
    if marker is not None:
        task_id = marker.get("task_id")
        db_path = _resolve_marker_db(run_dir, marker)
        if db_path.exists() and task_id:
            from .taskdb import get_task_status

            row = get_task_status(db_path, task_id)
            if row is not None:
                status = _TASK_STATUS_MAP.get(row["status"], "unknown")
                out = {
                    "status": status,
                    "detail": None,
                    "kind": "sweep_task",
                    "tasks": None,
                    "error": None,
                }
                if status == "failed" and row.get("error"):
                    out["error"] = {"traceback": row["error"], "node": row.get("node")}
                return out
        # DB missing/unreadable — fall through with a hint, but still note kind.
        detail = f"sweep-task dir but task DB unavailable at {db_path}"
        # Prefer local completion/failure markers if present.
        if rec.complete_path.exists():
            return {"status": "complete", "detail": detail, "kind": "sweep_task",
                    "tasks": None, "error": None}
        err = rec.load_error()
        if err is not None:
            return {"status": "failed", "detail": detail, "kind": "sweep_task",
                    "tasks": None, "error": err}
        return {"status": "unknown", "detail": detail, "kind": "sweep_task",
                "tasks": None, "error": None}

    # 2. Explicit success marker.
    if rec.complete_path.exists():
        return {"status": "complete", "detail": None, "kind": _plain_kind(run_dir),
                "tasks": _maybe_tasks(run_dir), "error": None}

    # 3. Failure sidecar.
    err = rec.load_error()
    if err is not None:
        return {"status": "failed", "detail": None, "kind": _plain_kind(run_dir),
                "tasks": None, "error": err}

    # 4. Sweep master (run.lock + task DB).
    lock = Path(run_dir) / LOCK_NAME
    db_path = Path(run_dir) / TASKS_DB_NAME
    if lock.exists() and db_path.exists():
        from .taskdb import get_status_counts

        counts = get_status_counts(db_path)
        status = _aggregate_sweep_status(counts)
        return {"status": status, "detail": None, "kind": "sweep_master",
                "tasks": counts, "error": None}

    # 5. Bare run.lock.
    if lock.exists():
        return {
            "status": "interrupted",
            "detail": "run.lock present without run.complete — interrupted, "
                      "or still running in-process (no liveness probe).",
            "kind": "run",
            "tasks": None,
            "error": None,
        }

    # 6. Nothing recognisable.
    return {"status": "unknown", "detail": "no run.lock/run.complete/marker found",
            "kind": "unknown", "tasks": None, "error": None}


def _plain_kind(run_dir: Path) -> str:
    return "sweep_master" if (Path(run_dir) / TASKS_DB_NAME).exists() else "run"


def _maybe_tasks(run_dir: Path) -> Optional[dict]:
    db_path = Path(run_dir) / TASKS_DB_NAME
    if not db_path.exists():
        return None
    from .taskdb import get_status_counts

    return get_status_counts(db_path)


def _aggregate_sweep_status(counts: dict) -> str:
    """Roll per-task counts into one master status."""
    if counts.get("pending", 0) or counts.get("running", 0):
        return "running"
    if counts.get("failed", 0):
        return "failed"
    if counts.get("interrupted", 0):
        return "interrupted"
    return "complete"


def _lineage_from_lock(lock: dict) -> dict:
    """Return the lineage mapping, tolerating the ``lineage``/``prevs`` spellings."""
    return lock.get("lineage") or lock.get("prevs") or {}


def _upstream_list(lock: dict) -> list:
    out = []
    for name, entry in _lineage_from_lock(lock).items():
        if not isinstance(entry, dict):
            continue
        path = entry.get("path") or entry.get("config", {}).get("save_dir")
        info = entry.get("info", {})
        ts = entry.get("timestamp") or info.get("timestamp")
        out.append({"name": name, "path": str(path) if path else None, "timestamp": ts})
    return out


def _tag_for_path(run_dir: Path, scan_root: Path) -> Optional[str]:
    """Find a flexlock tag whose ``Path:`` message resolves to ``run_dir``."""
    from .cli import find_git_repo, get_flexlock_tags, get_tag_details

    repo = find_git_repo(str(scan_root))
    if not repo:
        return None
    target = str(Path(run_dir).resolve())
    try:
        for tag_name, tag_commit in get_flexlock_tags(repo).items():
            details = get_tag_details(repo, tag_commit)
            for line in details["message"].splitlines():
                if line.startswith("Path: "):
                    tagged = line[6:].strip()
                    if str(Path(tagged).resolve()) == target:
                        return tag_name
    except Exception:
        return None
    return None


def _downstream_list(run_dir: Path, scan_root: Path) -> list:
    """Scan ``scan_root`` for runs whose lineage resolves to ``run_dir``."""
    from .cli import find_results_dirs

    target = str(Path(run_dir).resolve())
    out = []
    for run in find_results_dirs(str(scan_root)):
        if str(Path(run["path"]).resolve()) == target:
            continue
        for entry in (run.get("lineage") or {}).values():
            if not isinstance(entry, dict):
                continue
            path = entry.get("path") or entry.get("config", {}).get("save_dir")
            if path and str(Path(path).resolve()) == target:
                lock = _load_lock(Path(run["path"])) or {}
                out.append({
                    "path": str(Path(run["path"]).resolve()),
                    "timestamp": run.get("timestamp"),
                    "note": lock.get("note"),
                })
                break
    return out


def load_run_summary(run_dir, scan_root=None, downstream=True) -> dict:
    """Full JSON summary for ``flexlock show`` — the agent-facing run contract."""
    run_dir = Path(run_dir).resolve()
    scan_root = Path(scan_root).resolve() if scan_root else run_dir.parent

    st = run_status(run_dir)
    kind = st["kind"]
    lock = _load_lock(run_dir)

    # Sweep-task dirs carry no run.lock; reconstruct from the task DB snapshot
    # and inherit note/repos from the master lock.
    marker = _read_marker(run_dir)
    master_lock = None
    if lock is None and marker is not None:
        db_path = _resolve_marker_db(run_dir, marker)
        task_id = marker.get("task_id")
        if db_path.exists() and task_id:
            from .taskdb import get_task_snapshot

            snap = get_task_snapshot(db_path, task_id)
            if snap:
                lock = snap
        master_lock = _load_lock(db_path.parent) if db_path.exists() else None

    lock = lock or {}
    config = lock.get("config", {}) or {}
    repos = lock.get("repos") or (master_lock or {}).get("repos") or {}
    note = lock.get("note")
    if note is None and master_lock:
        note = master_lock.get("note")

    summary = {
        "schema_version": SCHEMA_VERSION,
        "path": str(run_dir),
        "kind": kind,
        "status": st["status"],
        "status_detail": st.get("detail"),
        "timestamp": lock.get("timestamp"),
        "note": note,
        "target": config.get("_target_") if isinstance(config, dict) else None,
        "fingerprint": lock.get("fingerprint"),
        "tag": _tag_for_path(run_dir, scan_root),
        "error": st.get("error"),
        "config": config,
        "results": RunRecord(run_dir).load_results() or {},
        "repos": repos,
        "data": lock.get("data") or {},
        "tasks": st.get("tasks"),
        "lineage": {
            "upstream": _upstream_list(lock),
            "downstream": _downstream_list(run_dir, scan_root) if downstream else [],
        },
    }
    return summary


def _all_tags_by_path(scan_root) -> dict:
    """One-shot ``{resolved_path: tag_name}`` map for a whole tree."""
    from .cli import find_git_repo, get_flexlock_tags, get_tag_details

    out = {}
    repo = find_git_repo(str(scan_root))
    if not repo:
        return out
    try:
        for tag_name, tag_commit in get_flexlock_tags(repo).items():
            details = get_tag_details(repo, tag_commit)
            for line in details["message"].splitlines():
                if line.startswith("Path: "):
                    out[str(Path(line[6:].strip()).resolve())] = tag_name
    except Exception:
        pass
    return out


def _numeric_metrics(results) -> dict:
    """Top-level numeric keys of a results payload."""
    if not isinstance(results, dict):
        return {}
    return {
        k: v for k, v in results.items()
        if isinstance(v, (int, float)) and not isinstance(v, bool)
    }


def build_graph(results_root, include_groups=False) -> dict:
    """Build the experiment DAG JSON — backend for ``graph`` and the report.

    Nodes come from every ``run.lock`` under ``results_root`` plus every sweep
    task dir (identified by ``.flexlock_marker``, which has no run.lock). Edges
    capture lineage and sweep-item containment; edges pointing outside the scan
    materialise ``kind="external"`` stub nodes so the graph stays closed.
    """
    from datetime import datetime as _dt

    from .cli import find_results_dirs

    root = Path(results_root).resolve()
    tag_map = _all_tags_by_path(root)

    nodes: dict[str, dict] = {}
    edges: list[dict] = []

    def _node(node_id, **fields):
        nodes[node_id] = fields

    # 1. run.lock-backed nodes (runs + sweep masters).
    for run in find_results_dirs(str(root)):
        run_dir = Path(run["path"]).resolve()
        node_id = str(run_dir)
        lock = _load_lock(run_dir) or {}
        st = run_status(run_dir)
        config = lock.get("config", {}) or {}
        repos = lock.get("repos") or {}
        results = RunRecord(run_dir).load_results()
        _node(
            node_id,
            id=node_id,
            label=run_dir.name,
            kind=st["kind"] if st["kind"] != "unknown" else "run",
            status=st["status"],
            timestamp=lock.get("timestamp"),
            note=lock.get("note"),
            target=config.get("_target_") if isinstance(config, dict) else None,
            fingerprint=lock.get("fingerprint"),
            tag=tag_map.get(node_id),
            tree_hashes={n: (i or {}).get("tree") for n, i in repos.items()},
            data_hashes=lock.get("data") or {},
            metrics=_numeric_metrics(results),
        )

    # 2. sweep-task nodes (marker dirs, no run.lock).
    for marker_file in root.rglob(MARKER_NAME):
        task_dir = marker_file.parent.resolve()
        node_id = str(task_dir)
        if node_id in nodes:
            continue
        marker = _read_marker(task_dir) or {}
        st = run_status(task_dir)
        db_path = _resolve_marker_db(task_dir, marker)
        results = RunRecord(task_dir).load_results()
        _node(
            node_id,
            id=node_id,
            label=task_dir.name,
            kind="sweep_task",
            status=st["status"],
            timestamp=None,
            note=None,
            target=None,
            fingerprint=None,
            tag=tag_map.get(node_id),
            tree_hashes={},
            data_hashes={},
            metrics=_numeric_metrics(results),
        )
        # sweep-item edge from the master (task DB's parent dir).
        master_id = str(db_path.parent.resolve())
        edges.append({"source": master_id, "target": node_id, "type": "sweep_item"})

    # 3. lineage edges (materialise external stubs for out-of-scan sources).
    def _ensure_external(node_id):
        if node_id not in nodes:
            _node(node_id, id=node_id, label=Path(node_id).name, kind="external",
                  status="unknown", timestamp=None, note=None, target=None,
                  fingerprint=None, tag=tag_map.get(node_id), tree_hashes={},
                  data_hashes={}, metrics={})

    for run in find_results_dirs(str(root)):
        run_dir = Path(run["path"]).resolve()
        lock = _load_lock(run_dir) or {}
        for entry in _lineage_from_lock(lock).values():
            if not isinstance(entry, dict):
                continue
            path = entry.get("path") or entry.get("config", {}).get("save_dir")
            if not path:
                continue
            src = str(Path(path).resolve())
            _ensure_external(src)
            edges.append({"source": src, "target": str(run_dir), "type": "lineage"})

    # Drop sweep_item edges whose master somehow isn't a node.
    for e in edges:
        if e["type"] == "sweep_item":
            _ensure_external(e["source"])

    graph = {
        "schema_version": SCHEMA_VERSION,
        "root": str(root),
        "generated_at": _dt.now().isoformat(),
        "nodes": list(nodes.values()),
        "edges": edges,
    }
    if include_groups:
        graph["groups"] = _compute_groups(nodes)
    return graph


def _compute_groups(nodes: dict) -> dict:
    """Group node ids that share an identical tree-hash tuple / data dict."""
    same_tree: dict = {}
    same_data: dict = {}
    for node_id, n in nodes.items():
        trees = n.get("tree_hashes") or {}
        if trees and all(v for v in trees.values()):
            key = tuple(sorted(trees.items()))
            same_tree.setdefault(key, []).append(node_id)
        data = n.get("data_hashes") or {}
        if data:
            dkey = tuple(sorted(data.items()))
            same_data.setdefault(dkey, []).append(node_id)
    return {
        "same_tree": [sorted(v) for v in same_tree.values() if len(v) >= 2],
        "same_data": [sorted(v) for v in same_data.values() if len(v) >= 2],
    }


# Status → display colour, shared by mermaid/dot/HTML.
STATUS_COLORS = {
    "complete": "#4caf50",
    "failed": "#e53935",
    "interrupted": "#fb8c00",
    "running": "#1e88e5",
    "pending": "#9e9e9e",
    "unknown": "#bdbdbd",
    "external": "#e0e0e0",
}


def graph_to_mermaid(graph: dict) -> str:
    """Render the graph JSON as a Mermaid ``graph TD`` diagram."""
    lines = ["graph TD"]
    id_map = {n["id"]: f"n{i}" for i, n in enumerate(graph["nodes"])}
    statuses_seen = set()
    for n in graph["nodes"]:
        nid = id_map[n["id"]]
        label = f"{n['label']}<br/>{n['status']}"
        lines.append(f'    {nid}["{label}"]')
        statuses_seen.add(n["status"])
    for e in graph["edges"]:
        s = id_map.get(e["source"])
        t = id_map.get(e["target"])
        if s and t:
            arrow = "-.->" if e["type"] == "sweep_item" else "-->"
            lines.append(f"    {s} {arrow} {t}")
    # classDef per status + assignments.
    for status in sorted(statuses_seen):
        color = STATUS_COLORS.get(status, "#bdbdbd")
        lines.append(f"    classDef {status} fill:{color},color:#fff;")
    for n in graph["nodes"]:
        lines.append(f"    class {id_map[n['id']]} {n['status']};")
    return "\n".join(lines)


def graph_to_dot(graph: dict) -> str:
    """Render the graph JSON as Graphviz DOT."""
    lines = ["digraph flexlock {", "    rankdir=TB;", '    node [style=filled, shape=box];']
    id_map = {n["id"]: f"n{i}" for i, n in enumerate(graph["nodes"])}
    for n in graph["nodes"]:
        color = STATUS_COLORS.get(n["status"], "#bdbdbd")
        label = f"{n['label']}\\n{n['status']}"
        lines.append(f'    {id_map[n["id"]]} [label="{label}", fillcolor="{color}"];')
    for e in graph["edges"]:
        s = id_map.get(e["source"])
        t = id_map.get(e["target"])
        if s and t:
            style = "dashed" if e["type"] == "sweep_item" else "solid"
            lines.append(f'    {s} -> {t} [style={style}];')
    lines.append("}")
    return "\n".join(lines)


def format_summary_md(summary: dict) -> str:
    """Render a human-readable Markdown view of a ``load_run_summary`` dict."""
    name = Path(summary["path"]).name
    lines = [f"# {name} — {summary['status'].upper()}", ""]

    meta = []
    if summary.get("tag"):
        meta.append(f"- **tag:** {summary['tag']}")
    if summary.get("note"):
        meta.append(f"- **note:** {summary['note']}")
    if summary.get("target"):
        meta.append(f"- **target:** `{summary['target']}`")
    if summary.get("timestamp"):
        meta.append(f"- **timestamp:** {summary['timestamp']}")
    meta.append(f"- **kind:** {summary['kind']}")
    meta.append(f"- **path:** `{summary['path']}`")
    if summary.get("status_detail"):
        meta.append(f"- **note on status:** {summary['status_detail']}")
    lines += meta + [""]

    err = summary.get("error")
    if err:
        lines += ["## Error", ""]
        if err.get("exc_type"):
            lines.append(f"`{err.get('exc_type')}`: {err.get('exc_message', '')}")
            lines.append("")
        tb = err.get("traceback")
        if tb:
            lines += ["```", tb.rstrip(), "```", ""]

    tasks = summary.get("tasks")
    if tasks:
        lines += ["## Tasks", ""]
        lines.append("| pending | running | done | failed | interrupted |")
        lines.append("|---|---|---|---|---|")
        lines.append(
            f"| {tasks.get('pending', 0)} | {tasks.get('running', 0)} | "
            f"{tasks.get('done', 0)} | {tasks.get('failed', 0)} | "
            f"{tasks.get('interrupted', 0)} |"
        )
        lines.append("")

    results = summary.get("results") or {}
    if isinstance(results, dict) and results:
        lines += ["## Results", "", "| key | value |", "|---|---|"]
        for k, v in results.items():
            lines.append(f"| {k} | {v} |")
        lines.append("")

    lineage = summary.get("lineage", {})
    up = lineage.get("upstream") or []
    down = lineage.get("downstream") or []
    if up or down:
        lines += ["## Lineage", ""]
        if up:
            lines.append("**Upstream:**")
            for u in up:
                lines.append(f"- {u.get('name')}: `{u.get('path')}`")
        if down:
            lines.append("**Downstream:**")
            for d in down:
                note = f" — {d['note']}" if d.get("note") else ""
                lines.append(f"- `{d.get('path')}`{note}")
        lines.append("")

    config = summary.get("config") or {}
    if config:
        import yaml as _yaml

        lines += ["## Config", "", "```yaml",
                  _yaml.safe_dump(config, default_flow_style=False, sort_keys=False).rstrip(),
                  "```", ""]

    return "\n".join(lines)
