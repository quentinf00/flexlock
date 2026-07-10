"""Zero-dependency static HTML report built on the graph JSON.

The report is a single self-contained HTML file (all CSS/JS inline, no CDN) so
it opens offline on an HPC login node. Its stable contract is the embedded JSON
island (``<script id="flexlock-data">``), which external tools can extract and
parse independently of the rendering.
"""

import json
from importlib.resources import files
from pathlib import Path

from . import query
from .run_record import _atomic_write

TEMPLATE_NAME = "report_template.html"


def _load_template() -> str:
    return files("flexlock").joinpath(TEMPLATE_NAME).read_text(encoding="utf-8")


def _json_island(data: dict) -> str:
    """Serialize + escape so a ``</script>`` (e.g. inside a note) can't break out.

    ``</`` → ``<\\/`` is a valid JSON string escape (``\\/`` decodes to ``/``),
    so ``JSON.parse`` round-trips the original text.
    """
    return json.dumps(data, default=str).replace("</", "<\\/")


def generate_report(
    results_root,
    out_path,
    title=None,
    include_groups=True,
    embed_configs=False,
) -> Path:
    """Render the static HTML report for ``results_root`` to ``out_path``."""
    results_root = Path(results_root)
    graph = query.build_graph(results_root, include_groups=include_groups)

    if embed_configs:
        for node in graph["nodes"]:
            lock = query._load_lock(Path(node["id"]))
            node["config"] = (lock or {}).get("config", {}) if lock else {}
            # Attach the failure payload too, for the detail pane.
            if node.get("status") == "failed":
                st = query.run_status(Path(node["id"]))
                if st.get("error"):
                    node["error"] = st["error"]
    else:
        # Even without full configs, surface error payloads for failed nodes.
        for node in graph["nodes"]:
            if node.get("status") == "failed":
                st = query.run_status(Path(node["id"]))
                if st.get("error"):
                    node["error"] = st["error"]

    payload = {"graph": graph, "colors": query.STATUS_COLORS}
    report_title = title or f"FlexLock report — {results_root}"

    html = _load_template()
    html = html.replace("{{TITLE}}", _html_escape(report_title))
    html = html.replace("{{DATA}}", _json_island(payload))

    out_path = Path(out_path)
    _atomic_write(out_path, html)
    return out_path


def _html_escape(s: str) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
