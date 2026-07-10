---
name: flexlock-report
description: Turn a FlexLock results tree into a written report — per-stage metric tables, delta explanations between runs, and a shareable HTML file. Use when asked to summarize results, compare experiments, or explain why two runs differ.
---

# FlexLock report

## 1. Structure from the graph

```bash
flexlock graph <results_root> --format json
```

Group `nodes` by stage (`label`); build a per-stage table of leaf runs with their
`status`, `timestamp`, `note`, and `metrics`. Follow `edges` (`type: lineage`) to
show which runs feed which.

## 2. Metrics per leaf

For each leaf run of interest:

```bash
flexlock show <run_dir> --format json    # .results holds the return payload
```

## 3. Explain deltas between interesting pairs

```bash
flexlock why <run_a> <run_b> --format json
```

Read `diffs` (config/data/git) and `commits.<repo>.a_to_b` (real commit subjects
between the two runs' shadow commits). If `trees_identical` is true the code was
unchanged — the delta is config/data. If `error` is set the shadow commits were
gc'd; fall back to the `diffs` section.

**Cache LLM diff-summaries** as sidecars so you don't re-explain unchanged pairs:
`<run_b>/.flexlock/why_<hash(run_a)>.md`. Reuse the sidecar when both runs'
`fingerprint`s are unchanged; regenerate otherwise.

## 4. Ship the HTML

```bash
flexlock report <results_root> -o report.html --title "My experiment"
```

The file is self-contained (opens offline, no CDN). Add `--embed-configs` to
include full per-run configs in the detail pane, `--groups` to surface runs
sharing identical code/data. Point the reader at the failure rows (red) and the
tagged runs.
