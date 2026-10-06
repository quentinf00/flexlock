# Root-anchor CLI sweep fix and smaller-core migration plan

2026-10-06. Implementation: `ebc6d92c8e7e2ca658eb92600815562276262d6b`, isolated
`workflow/execution-acceptance` branch. Production installations remain unchanged.

Root-anchor sweep items now update the root config before stage selection and
reference freezing. Previously the selected stage retained the first upstream and
received root keys as unexpected callable arguments. Each item now receives its
chosen input; ordinary stage sweeps retain their scope. The existing executor,
queue and dispatch paths consume the compiled stage configs.

Validation: **218 passed**, including **11 new regression cases**, in 147.74 seconds.
The cases cover Python configs, serial/parallel execution, declared upstream lineage,
preview/enqueue agreement, selected overrides, dump/check, scope and mocked Slurm
submission. Existing runner, selection, sweep, swap, preset, pipeline and dependency
checks pass. This is a targeted compatibility set, not a full-suite rerun.
The 13 warnings concern existing vinc deprecation and empty resolver arguments.

- [Regression tests](../../tests/test_root_anchor_sweep.py)
- [CLI syntax and scope](../../docs/cli_reference.md)
- [M0–M5 migration plan](../../docs/slimmer_core_migration.md)
- [JUnit results](compatibility.xml) and [validation command/environment](validation.json)

Use repeated keys (`--sweep 'upstream_run=A,upstream_run=B'`) or scalar values with
`--sweep A,B --sweep-target upstream_run`. Abbreviated mixed dictionary/scalar
syntax is rejected with an actionable error. Root-aware dump exports a stage-config
list; interactive editing of these multiple configurations is unsupported.

M0 is complete at isolated engineering scope. M1 remains open: record aliasing,
cross-tag result lookup, missing-authoritative-record cache hits, data identity and
pre-submit collision/force contracts. Direct run_lock lineage without an explicit
snapshot declaration belongs to M2. No APIs were removed or deprecated by this
change; later policy separation and consumer adoption are planned work.
No live scheduler jobs, scientific runs or production upgrades occurred.
