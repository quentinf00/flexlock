"""Tests for the static HTML report (Phase D)."""

import json
import re
from pathlib import Path

import yaml

from flexlock.report import generate_report, _json_island
from flexlock.run_record import RunRecord


def _make_run(base, name, *, config=None, note=None, lineage=None,
              complete=False, error=None, results=None):
    run_dir = Path(base) / name
    run_dir.mkdir(parents=True, exist_ok=True)
    cfg = config or {"_target_": "mod.func", "save_dir": str(run_dir)}
    data = {"timestamp": "2026-03-15T10:00:00", "config": cfg}
    if note is not None:
        data["note"] = note
    if lineage:
        data["lineage"] = lineage
    (run_dir / "run.lock").write_text(yaml.dump(data))
    rec = RunRecord(run_dir)
    if results is not None:
        rec.write_results(results)
    if complete:
        rec.mark_complete(result=results)
    if error is not None:
        try:
            raise ValueError(error)
        except ValueError as exc:
            rec.write_error(exc)
    return run_dir


def _extract_island(html):
    m = re.search(
        r'<script id="flexlock-data" type="application/json">(.*?)</script>',
        html, re.DOTALL,
    )
    assert m, "JSON island not found"
    return json.loads(m.group(1))


def test_report_generates_file(tmp_path):
    root = tmp_path / "results"
    a = _make_run(root, "extract", complete=True)
    _make_run(root, "train", error="boom", results={"acc": 0.8},
              lineage={"extract": {"path": str(a)}})
    out = tmp_path / "report.html"
    generate_report(root, out)
    assert out.exists()
    html = out.read_text()
    assert str(a.resolve()) in html


def test_report_json_island_parses(tmp_path):
    root = tmp_path / "results"
    a = _make_run(root, "extract", complete=True)
    _make_run(root, "train", complete=True, lineage={"extract": {"path": str(a)}})
    out = tmp_path / "report.html"
    generate_report(root, out)
    payload = _extract_island(out.read_text())
    graph = payload["graph"]
    assert len(graph["nodes"]) == 2
    assert len(graph["edges"]) == 1


def test_report_script_in_note_roundtrips(tmp_path):
    root = tmp_path / "results"
    _make_run(root, "run", complete=True, note="danger </script> here")
    out = tmp_path / "report.html"
    generate_report(root, out)
    payload = _extract_island(out.read_text())
    notes = [n["note"] for n in payload["graph"]["nodes"]]
    assert "danger </script> here" in notes


def test_report_embed_configs(tmp_path):
    root = tmp_path / "results"
    _make_run(root, "run", complete=True,
              config={"_target_": "m.f", "save_dir": str(root / "run"), "lr": 0.123})
    out = tmp_path / "report.html"
    generate_report(root, out, embed_configs=True)
    payload = _extract_island(out.read_text())
    node = payload["graph"]["nodes"][0]
    assert node["config"]["lr"] == 0.123


def test_report_failed_node_has_error(tmp_path):
    root = tmp_path / "results"
    _make_run(root, "run", error="kaboom")
    out = tmp_path / "report.html"
    generate_report(root, out)
    payload = _extract_island(out.read_text())
    node = payload["graph"]["nodes"][0]
    assert node["error"]["exc_message"] == "kaboom"


def test_json_island_escapes_closing_tag():
    island = _json_island({"x": "a</script>b"})
    assert "</script>" not in island
    assert json.loads(island.replace("<\\/", "</"))["x"] == "a</script>b"
