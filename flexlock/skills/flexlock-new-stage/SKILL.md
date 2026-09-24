---
name: flexlock-new-stage
description: Scaffold a new FlexLock pipeline stage correctly the first time — target importability, snapshot declarations, lineage refs, and pipeline_dir anchoring. Use when adding a stage to a defaults tree or debugging why a stage won't run/track.
---

# Add a FlexLock stage

A stage is a config mapping with a `_target_`. Each item below lists the rule and
the **symptom** you'll see if you skip it.

## Checklist

1. **Target lives in an importable module.**
   `_target_: myproject.train.train` — never a function defined in `__main__`.
   *Symptom:* `ModuleNotFoundError` / `Can't get attribute` in a worker, or a
   sweep task that fails instantly on every node.

2. **Guard the entrypoint.** Any script that submits must wrap submission in
   `if __name__ == "__main__":`. *Symptom:* spawned workers (sweeps, `isolated=True`)
   re-execute your submit code and fork-bomb / re-queue tasks.

3. **Relative refs inside a subtree use `${.x}`**, not cross-tree absolute paths.
   *Symptom:* `InterpolationResolutionError`, or a ref that silently points at the
   root instead of the stage when the stage is selected in isolation.

4. **Anchor outputs on a shared `pipeline_dir`.**
   ```yaml
   pipeline_dir: outputs/exp_${now:%Y%m%d}
   extract: { _target_: proj.extract, save_dir: ${pipeline_dir}/extract }
   train:   { _target_: proj.train,   save_dir: ${pipeline_dir}/train }
   ```
   *Symptom:* stages scatter across unrelated dirs; lineage/gc can't relate them.

5. **Architecture knobs read from upstream via `${run_lock:}`** rather than being
   re-specified. *Symptom:* silent train/eval config drift; false cache hits.

5b. **Inputs from another experiment via `${run:<preset>,<select>}`**, never a
   copied versioned path (`results/train_x_0005`). It resolves to the newest
   complete run of that preset at submit, is logged and recorded as lineage;
   pin with a third argument (`,0005`) when a result must stay fixed.
   *Symptom:* stale hard-coded paths; inference silently using an old model.

6. **Declare lineage + tracked inputs under `_snapshot_`.**
   ```yaml
   train:
     _snapshot_:
       prevs: [ "${extract.save_dir}" ]   # upstream FlexLock runs
       data:  { train_csv: "${.input}" }  # hashed data inputs
   ```
   *Symptom:* `flexlock show` reports no `lineage`/`data`; downstream runs don't
   invalidate when upstream changes.

## Verify before a real run

```bash
flexlock stages -d myproject.pipeline.cfg          # stage appears with right key
flexlock-run -d myproject.pipeline.cfg -s train --print-config   # config resolves
flexlock-run -d myproject.pipeline.cfg -s train --dry-run        # (HPC) script renders
```

`flexlock stages` walks the config **without resolving**, and
`--print-config`/`--check`/`--dry-run` never create or claim directories —
all safe to run repeatedly while iterating.
