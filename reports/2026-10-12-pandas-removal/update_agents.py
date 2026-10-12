"""Append compatibility notes only for successfully migrated project aliases."""
import json
from pathlib import Path

REPORT = Path(__file__).resolve().parent
MARKER = '<!-- flexlock-release-compatibility -->'
TEXT = '''
<!-- flexlock-release-compatibility -->
## FlexLock release compatibility (2026-10-12)

The installed-environment migration pilot uses FlexLock 0.9.2. Project
manifests and lockfiles are not yet repinned: a Pixi synchronization can restore
an older installation. Before launching new work, check the actual environment:

```sh
python -c "import flexlock; print(flexlock.__version__, flexlock.__file__)"
```

Use the following execution contracts when working with the updated release:

- Destination ownership/collision checks run before scheduler submission.
  Use a fresh destination by default. Explicit `--force` may overwrite inactive
  prior provenance; it cannot bypass pending/running queue ownership. Inspect
  and continue an existing queue instead of resubmitting over it.
- Existing `${run_lock:...}` producers bind at submission; changing or removing
  their records before consumer execution causes failure. Choose concrete
  upstream paths. Promised inputs with `--after` retain that exact path and bind
  when available; a newer run is not an automatic replacement.
- Invalid declared outputs or missing authoritative records prevent successful
  reuse. Worker/queue failure must be checked; a scheduler submission ID is not
  evidence of successful computation or complete cohort coverage.
- Queue layout 2 omits `.flexlock-queue.json` for fresh nested products. Use
  FlexLock's `load_record` and shared queue readers rather than reading that
  pointer directly. All consumers of new queues need FlexLock 0.9.1+.
  Keep pending products with their ancestor queue; preserve referenced records
  when exporting or moving provenance. Existing/external pointers remain.
- Python configuration, `py2cfg`, `@` presets, direct upstream overrides and
  sweeps remain supported. Automatic cache discovery has not yet been retired;
  this pilot does not establish scientific equivalence or project acceptance.

FlexLock 0.9.2 removes its unused pandas dependency. It neither installs nor
downgrades pandas. Optional MLflow and scientific packages retain their own
dependency requirements. Library ownership checks passed for the migrated
installations; scientific workloads have not been replayed by this pilot.

This section documents FlexLock compatibility only. Existing project research,
knowledge and reporting instructions continue to apply.
<!-- /flexlock-release-compatibility -->
'''

def main():
    originals = json.loads((REPORT.parent/'2026-10-12-reader-migration'/'installations-before.json').read_text())
    migrated = json.loads((REPORT/'migration-results.json').read_text())
    prefixes = {Path(row['prefix']) for row in migrated
                if row['install_exit'] == row.get('probe_exit') == 0}
    projects = {Path(row['site']).parents[5] for row in originals
                if Path(row['real_site']).parents[2] in prefixes
                and '/work/projects/' in row['site']}
    changes = []
    for project in sorted(projects):
        target = project/'AGENTS.md'
        previous = target.read_text() if target.exists() else ''
        if MARKER in previous:
            start = previous.index(MARKER)
            end = previous.index('<!-- /flexlock-release-compatibility -->', start)
            end += len('<!-- /flexlock-release-compatibility -->')
            content = previous[:start] + TEXT.strip() + previous[end:]
        else:
            content = previous.rstrip() + '\n\n' + TEXT.strip() + '\n'
        backup = REPORT/'agents-before'/str(project.relative_to('/ontap/user/qfebvre'))/'AGENTS.md'
        backup.parent.mkdir(parents=True, exist_ok=True)
        if not backup.exists():
            backup.write_text(previous)
        target.write_text(content)
        changes.append(dict(project=str(project), agents=str(target), created=not bool(previous)))
    (REPORT/'agents-updates.json').write_text(json.dumps(changes, indent=2)+'\n')
    print(json.dumps(changes, indent=2))

if __name__ == '__main__':
    main()
