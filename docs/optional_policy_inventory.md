# Optional-policy caller inventory

> Superseded status (2026-10-16): the user approved immediate pre-1.0 removal
> of automatic cache search, marker-based partial-stage resume and chained fanout.
> The candidate implements removal, not deprecated opt-in compatibility. Historical
> inventories below explain prior decisions; use [current migration notes](release_0_10_0rc1.md)
> and [workflow guidelines](workflow_guidelines.md) for supported calls.

2026-10-07. Audited source: f6beec9, including concrete producer binding 82b09a9.
This inventory proposes boundaries and adoption steps. It changes no API, default,
installed package or project source. Recorded scan and probe (internal validation evidence)
retain revisions, dirty-source hashes, locations and search limits.

## What the callers require

| Policy | Inspected callers | Disposition and replacement |
|---|---|---|
| Automatic cross-run cache search (`smart_run`, `--check-exists`) | SST preparation explicitly uses `smart_run=True` and sibling candidates; SAR pipeline functions expose a default-off switch; sample/tutorial pipelines explicitly enable it; lab deliberately tests reuse failures | Retain as an opt-in compatibility policy. Fresh recipes pass False. Existing explicit True callers keep their behavior; migrating SST requires selecting and wiring retained preparation products first. |
| Implicit Python caching defaults | `Project.submit` and `run_stage` default True; `flexlock.submit` and `submit_config` forward to submit; CLI and `submit_pipeline` default off | Preserve defaults in this audit. Recommend a staged Python default change after isolated adoption and a release notice. Explicit reuse stays available. Static local searches cannot establish that external callers tolerate a change. |
| Same-path explicit reuse (`save_dir_policy='skip'`) | SAR pilot's content/config/code/environment-keyed products use skip with `smart_run=False`, plus project acceptance/coverage checks | Retain the bounded primitive. Distinguish it from searching for an equivalent stage in another run. The project owns identity and reuse acceptance; FlexLock checks the selected record/output contract. |
| Composite marker-based stage skip (`_skip_complete_`) | Library tests, lab queue continuation journeys; activated by pipeline smart_run or skip | Retain as optional compatibility. Finish an unchanged recorded queue, or explicitly select which fresh stages to execute. Completion markers and declared outputs do not establish source/config equivalence after changes. Keep worker failure and output-health coverage. |
| `submit_chained` / `ChainedResult` fanout | Five library usage tests plus implementation/documentation; no candidate external call in the bounded project scan | Keep the adapter callable; stop presenting it as a required core abstraction. Use a short project loop with explicit anchors, per-stage resources and terminal-result checks. No immediate removal based on a local negative search. |
| Worker-time unpinned `${run:...}` under `--after` | Lab's scheduler chain; parameterized library tests deliberately choose the newest of two later producers | Retain named advanced compatibility; exclude it from producer-bound chain guarantees. Supported recipe supplies the exact producer path plus its job ID. Ordinary submit-time discovery and explicit pins remain useful. |
| `run_stage` sibling search | Existing method implementation/documentation; no external candidate call in the bounded scan | Keep a thin compatibility wrapper. Use `submit` for execution; workflow code chooses any retained run. Its automatic search is an optional reuse policy, not a prerequisite for provenance. |
| Low-level `ParallelExecutor` | SAR confidence-population script directly queues variable-specific tasks | Keep bounded workers core. This caller does not request cache search, but bypasses Project's new upstream binding preflight. Inventory this adoption seam separately; do not remove the worker API as part of trimming caching. |

Fingerprint/source/data comparison, record readers, output validation and the queue
are not deprecated by these dispositions. A comparison may help someone decide
whether to reuse a result without making FlexLock the decision-maker.

## Concrete project impact

SST preparation (project-owned example) is a real reuse caller: it enumerates
sibling stage paths, submits with explicit cache search, then assigns the returned
path to its selected config. Downstream configs reference earlier stage directories.
Removing automatic reuse without replacing those selections would repeat expensive
preparation and could miswire downstream inputs. First introduce a project-owned
mapping of selected preparation stages to retained producer paths; validate products,
update the root configuration and select subsequent configs afterward. The isolated
frozen-matchup reassessment is a separate workflow and has no detected optional-policy
call; that does not migrate this older preparation script.

SAR's original data/training/validation/diagnostic/phase pipelines forward a
`smart_run` argument with default False. They already support fresh execution;
explicit True reuse should remain a compatibility choice. The processing pilot (project-owned example) is
more specific: it chooses a product key itself, validates frozen source/config/input
identity and calls `submit(..., save_dir_policy='skip')`. Preserve
that explicit reuse primitive and its coverage barrier. A mechanical replacement of
all skip uses with fresh execution would discard a useful, intentional workflow.

Both SAR and SST contain `cfg.save_dir = result.save_dir` after submission. With the
current detached `Project.get` contract, that assignment does not update the root
used to compile later stages. This is an adoption issue to fix in isolated consumers,
not a reason to change config selection semantics. The side-effect-free
probe (internal validation evidence) demonstrates
that a later stage still sees the fresh path until the root is explicitly updated.
Do not claim the scientific pipelines were executed or validated by this audit.

Sample/tutorial projects explicitly enable caching; changing only the Python default
would leave those requests intact. The sample’s manual resource/anchor loop (project-owned example) already
routes resource profiles and updates project anchors. It is useful replacement
material for fanout, but needs terminal-result and product-acceptance guards before
being promoted as the migration recipe.

The lab scheduler chain (project-owned example) passes a producer job ID but chooses training via
an unpinned `${run:...}` on the worker. The replacement is a concrete training stage
path plus that same job ID. Preserve the old journey and its evidence as compatibility
coverage; add the concrete-path journey before changing the replay entry point.

## Small workflow replacements

Select retained products explicitly and update root anchors before selecting a
consumer. In an SST-style config with consumers referring to `prepare_data.save_dir`:

```python
from omegaconf import OmegaConf
from flexlock import Project

proj = Project('myproject.cfgmod.cfg')
selected = '/shared/runs/preparation/base/run-A/prepare'
# Project-owned checks establish completion, output health and scientific suitability.
accept_preparation(selected)
OmegaConf.update(proj.defaults, 'prepare_data.save_dir', selected)
consumer = proj.get('compute_climatology')
result = proj.submit(consumer)
result.raise_on_failure()
if not result.is_success:
    raise RuntimeError(f'Consumer is not complete: {result.status}')
```

`accept_preparation` is an explicitly project-defined validator, not a new FlexLock
API. Prefer a root `upstream_run` plus run_lock fields in new configs; existing
cross-stage save_dir references can migrate incrementally. Persist selected paths
in the project's config/ledger so reruns do not select a different producer. For a
new producer, set the anchor to its actual result path before selecting consumers.
An already detached consumer cannot be rewired by later root changes.

A small fanout loop replaces the synchronous part of submit_chained without a new
orchestration type. Each downstream stage below consumes the same sweep parent,
matching the existing adapter's wiring rather than implicitly consuming the previous
iteration's downstream result:

```python
from omegaconf import OmegaConf
from flexlock import Project

parents = proj.submit('train', sweep=items, wait=True)
for parent in parents:
    parent.raise_on_failure()
    if not parent.is_success:
        raise RuntimeError(f'Parent is not complete: {parent.status}')
    accept_training(parent.save_dir)  # Project-owned product/schema check.
    branch = Project(OmegaConf.to_container(proj.defaults, resolve=False))
    OmegaConf.update(branch.defaults, 'upstream_run', parent.save_dir)
    for stage, profile in [('infer', cpu_profile), ('assess', cpu_profile)]:
        OmegaConf.update(branch.defaults, f'{stage}.save_dir',
                         f'{parent.save_dir}/downstream/{stage}')
        result = branch.submit(stage, slurm_config=profile, wait=True)
        result.raise_on_failure()
        if not result.is_success:
            raise RuntimeError(f'{stage} is not complete: {result.status}')
```

`proj`, `items`, profiles and accept_training belong to the project. This illustration
requires its downstream configs to use the upstream_run anchor. If assess consumes
infer instead, update a separate inference anchor to that result before selecting
assess. For asynchronous launches, use concrete future producer paths and `--after`;
[the existing orchestration example](../examples/slimmer_workflows/orchestrate.py)
records IDs for separate allocations. A SUBMITTED result is not a completed product.
This audit syntax-checks these illustrative snippets; it does not run science or jobs.

## Compatibility checks to keep

- Automatic cache choice: test_index's end-to-end/index-only lookup cases,
  test_save_dir_guard's cache-before-guard/increment cases and
  test_pipeline_tasks::test_submit_pipeline_smart_run_all_cached.
- Explicit reuse/output health: skip cases in test_save_dir_guard,
  test_workflow_integrity's deleted/corrupt-output cases, SAR processing pilot tests.
- Marker continuation: test_pipeline_tasks::test_composite_skip_complete_resumes_past_done_stages
  and test_workflow_integrity::test_pipeline_cli_failure_and_resume.
- Fanout adapter: the five submit_chained tests in test_chained_and_paths.
  Bare-path loader tests in that same module remain core configuration coverage.
- Advanced worker-time discovery: test_presets::test_chained_run_binds_on_worker_and_records_lineage,
  test_chained_mixed_pinned_and_future_refs and test_chained_nested_run_lock.
  Keep them separate in interpretation from concrete-binding tests in test_submit_bindings.

These are contract locations, not a claim that this audit reran the test suite.
Do not delete mixed modules when moving an optional policy out of introductory docs.

## Next migration steps

1. Keep policy adapters and defaults intact while changing introductory guidance to
   explicit fresh execution versus explicit selected-product reuse.
2. In isolated lab/consumer checkouts, replace the scheduler newest lookup, correct
   root-anchor propagation and demonstrate selected-stage SST preparation reuse.
   Preserve older scientific output and historical evidence.
3. Measure thousand-item configuration/queue work, source capture, directory hashing
   and record binding separately, with cache search on/off. Provenance costs remain
   even when smart_run=False; removing cache search cannot by itself fix all overhead.
4. After working replacement examples and owner-reviewed adoption, decide the Python
   default change and compatibility notice. Keep explicit True and existing adapters
   available; remove APIs only after demonstrated replacement use.

This completes the bounded caller inventory, not M3's entire policy separation or
M5 adoption. No second execution engine, mandatory artifact schema or automatic
scientific reuse decision is introduced.
