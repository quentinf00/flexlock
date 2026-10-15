# FlexLock 0.9.3: validation and local rollout

2026-10-15. Final state: **51 of 53 inventoried environments upgraded**, **19
project manifest/lock pins validated**, and **21 project feedback files delivered**.
SOBA and the project template remain blocked by their own dependency issues.
MaxSS was deferred while job 1370177 ran, then migrated after successful completion
and a fresh scheduler check. Scientific adoption remains separately scoped.

## Release and compatibility

The local wheel is [flexlock-0.9.3-py3-none-any.whl](flexlock-0.9.3-py3-none-any.whl).
SHA256: `1b08a55cc17b60e674424f4d1ba977c81c995df9899659692500c590b59473d1`.
Its Python sources match this checkout; package requirements match 0.9.2.
This is a local release, not a public package-index publication.

- Return payloads live in the authoritative record's `result` section. Scientific
  `results.json` files survive execution; historical sidecars remain readable.
- Source capture and comparison share include/exclude scopes. Nested configured
  targets in Git/src/editable checkouts are discovered; ordinary imported helper
  code still needs an explicit declaration. Explicit repository scopes take precedence.
- Completed composite stages can feed nested submissions while their parent task
  runs. Authoritative stage evidence is required and other active owners still block.
- Terminal export preserves unresolved references. Exact cached producer selection,
  absolute-interpreter Slurm warnings and Python-version symlink-loop guards are fixed.

See [release notes](../../docs/release_0_9_3.md) and the
[record/source migration contract](../../docs/record_and_source_scope_migration.md).
Cache discovery/defaults and the scheduler API are unchanged. New workflow recipes
disable automatic cache discovery explicitly. No prepared-job export API is added.

## Validation

| Check | Evidence and result |
| --- | --- |
| Full library suite | [final log](full-suite-release.log): **1,053 passed, 2 skipped, 1 xfailed**, 348.66 s |
| SAR acceptance | [log](sar-acceptance.log): **16 passed**, actual tiny NetCDF fixtures |
| SAR installed-wheel CLI chain | [log](sar-chain-installed.log), [summary](sar-chain.json): six stages, five SAFE items, four produced and one explicitly empty, train/val/test assembly accepted |
| Source scopes and retained readers | [summary](project-checks.json): HAFS main + geo-jepa, Biomass scoped trees; capture/comparison equal; HAFS, SST and Biomass retained records readable |
| Installed packages | [installation results](installation-results.json): all 51 installations pass record-result, scientific-sidecar preservation, legacy-reader and queue-ownership probes |
| Final versions/backups | [audit](final-version-audit.json): all 53 versions checked; every upgraded prefix has a verified 0.9.2 backup archive |
| Project pins | [audit](final-pin-audit.json): 19 manifest/lock pairs match reviewed candidates and passed Pixi validation |

The [caller audit](caller-audit.json) found 30 physical checkouts and seven with
result-path references. Those references are callable-owned scientific products or
their readers; no literal core-only sidecar consumer requiring a blind rename was
found. Dynamic/external callers remain a limitation of this source audit.

The SAR acceptance helper needed its stage path lookup corrected to recognize
`record_dir`, with historical `config.save_dir` fallback; see [patch](sar-helper.patch).
The real chain also exposed the completed-parent ownership issue, now covered by
four library regressions. Earlier intermediate test/chain logs are retained for
diagnosis; the final logs linked above determine acceptance.

## Rollout and outstanding blockers

[Installation results](installation-results.json), [pin results](pin-results.json)
and [guidance updates](guidance-updates.json) are the current authoritative inventory.
Initial and before-MaxSS snapshots preserve the rollout history.

The first pass upgraded 42 prefixes. Biomass's owner then repaired its moved
`mlflow-pixi` dependency; the FlexLock-only retry preserved that repair and upgraded
four more prefixes. Finally, MaxSS job 1370177 completed successfully at scheduler
time `2026-10-15T15:53:13`. A fresh queue check found no replacement MaxSS work; its
five family prefixes and three manifest/lock pairs were migrated. The main-hpc /
neural-field-src launch convention is retained. SST jobs appearing on the later
queue check were left untouched; no environments were reinstalled for that check.

Only FlexLock was installed by the rollout: dependencies were not resolved or
upgraded, unrelated distribution names were unchanged, and reviewed project locks
preserve non-FlexLock packages. Biomass's separate project-owner repair is recorded
as the baseline for its retry, not attributed to the FlexLock pin.

Remaining deferrals, both still on 0.9.2:

- **SOBA**: `mlflow-pixi` points to the removed personal registry checkout. Its
  project owner must review the canonical shared registry binding at
  `/scale/project/lops-siam-model-registry/mlflow_pixi`, validate the project lock,
  then retry the prepared core pin.
- **project_template**: duplicate dev dependency tables and the unsatisfiable
  `better-exceptions>=0.4.0,<0.5` constraint prevent validation. The attempted
  candidate was restored; the intended dependency constraint needs a project decision.

Their feedback files describe the blockers. These failures do not justify changing
scientific model selection or silently relaxing dependency constraints.

## Preservation and workflow handoff

Each upgraded prefix has an old-version package/entrypoint archive. New rollback
archives and pin candidates were moved from home to
`/scale/scratch/qfebvre/flexlock093-rollout-preserved/` after the home quota filled;
see [relocation map](artifact-relocation.json). Only this rollout's newly created
files were relocated. Backups are on scratch storage and should be retained elsewhere
if needed beyond that storage's retention policy.

Historical scientific products and records were not reorganized or rewritten.
The separate dirty FlexLock source checkout remains untouched; importing it directly
does not use this wheel. Library-development prefixes updated at package level still
need their own manifest review before a later Pixi synchronization.

Nineteen projects' AGENTS.md compatibility sections now describe the breaking result
storage/source-scope contracts and link the central guidance; all 21 candidate roots
have feedback linked from existing task boards. Project-specific protocols and
pending scientific validation remain in those boards. No training, full data campaign,
publication or deployment was launched by this rollout.

The central [connected lifecycle draft](../../docs/workflow_lifecycle.md) extends the
recipes from reusable processing through experiments, release packaging and batch
inference. SAR preprocessing is validated; collocation, portable model release and
bounded L2 processing remain the project's FLEXLOCK-LIFECYCLE implementation and
validation task. Current mechanics do not retroactively fill historical source gaps.
