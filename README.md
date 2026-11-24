# FlexLock

Python configuration and run provenance for research and offline data processing.

[Documentation](https://quentinf00.github.io/flexlock/) · MIT licensed

FlexLock lets you write a config in Python, select and override it from the CLI,
and execute locally or through cluster workers. Run records capture configuration,
declared source/data dependencies, upstream producers, outputs and return values.

The **0.10.0 release** removes automatic cross-run cache search and partial-stage
resume policy. See [breaking changes](docs/release_0_10.md).

## Configuration and execution

```python
# cfgmod.py
from flexlock import py2cfg
from myproject.stages import prepare, train

cfg = dict(
    runs_root='/shared/project/runs',
    track='intensity', arm='baseline', run='20261016-seed3',
    run_dir='${runs_root}/${track}/${arm}/${run}',
    upstream_run='/shared/project/runs/preparation/base/20261001/prepare',
    main=py2cfg(train,
        save_dir='${run_dir}/train',
        input_path='${run_lock:${upstream_run},config.output_path}',
        checkpoint_path='${run_dir}/train/model.pt',
        _snapshot_=dict(data=dict(dataset='${...input_path}')),
        _outputs_=dict(model=dict(path='model.pt', sha256=True))),
)
```

```bash
flexlock-run -d cfgmod.cfg -s main -o upstream_run=/shared/runs/other/prepare
flexlock-run -d cfgmod.cfg -s main --sweep-file configs/smoke.yaml --n_jobs 2
flexlock-run -d cfgmod.cfg -s main --slurm-config configs/slurm_gpu.yaml
```

Choose fresh destinations for independent runs. Occupied run directories raise
before scheduler submission; active ownership also prevents forced overwrites.
Use the [workflow recipes](docs/workflow_guidelines.md) for named sweeps, per-item
destinations and explicit producer selection.

Python submission uses the same execution kernel:

```python
from flexlock import Project

project = Project('cfgmod.cfg')
result = project.submit('main')
result.raise_on_failure()
print(result.save_dir, result.result)
```

## Provenance and explicit reuse

Source snapshots describe the declared repository scope, including include/exclude
patterns. Data hashes and upstream bindings record what the callable consumed.
Comparison tools provide evidence for deciding whether preparation remains acceptable
after a code change; FlexLock does not choose that scientific policy.

```bash
flexlock-diff /shared/runs/producer_a /shared/runs/producer_b
```

Consumers bind concrete producer paths with `run_lock`. FlexLock resolves and records
the selected producer accurately and rejects identity changes at consumption time.
It does not silently substitute a newer producer.

```python
selected = project.submit(cfg, save_dir_policy='skip')
```

`skip` reuses exactly the selected complete destination after authoritative-record
and declared-output validation. It returns the producer's recorded config. It does
not certify equivalence to a new config or current source. `force=True` intentionally
reruns in place and records the new attempt while keeping products in place.

## Sweeps and ordered stages

Sweep files keep large cohorts out of comma-separated CLI arguments. Workers claim
tasks from a shared SQLite queue, allowing many items with a bounded worker allocation.
Project coverage checks distinguish successful processing, valid empty outcomes,
exclusions, missing products and failures.

CLI `-s prepare train assess` executes selected stages in order on one allocation,
with distinct provenance and fail-fast execution. Independent pipeline items can run
in parallel. Stages needing different resources use separate scheduler jobs and
`--after`, with concrete future producer paths and an accepted-ID ledger.

An unchanged recorded queue can continue pending work without rerunning done rows.
For a partially completed pipeline, explicitly select remaining stages, bind retained
producers and use fresh destinations. There is no automatic marker-based stage skip.

## Further reading

- [Workflow guidelines and five executable recipes](docs/workflow_guidelines.md)
- [Python API](docs/python_api.md) and [CLI reference](docs/cli_reference.md)
- [Source attribution](docs/source_attribution.md) and [HPC integration](docs/hpc_integration.md)
- [Slim-core design](docs/philosophy.md) and [migration notes](docs/release_0_10.md)

Install this release with `pip install flexlock==0.10.2` or from the
`quentinf00` Conda channel. See the migration notes before upgrading existing callers.
