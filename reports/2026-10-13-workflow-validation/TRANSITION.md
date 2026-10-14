# Fresh workflow transition: project review draft

Keep the current projects usable while adding a small, explicit new entrypoint. Existing runs stay at their current locations; selected legacy artifacts are bound by concrete paths. This is a proposal, not an artifact relocation or scientific protocol change.

## Sequence

1. Freeze one retained input set and record its exact paths, identities, scope and limitations.
2. Add one Python config with stage constructors, one track/arm binding file and a fresh run root.
3. Run a bounded local validation and the file-list coverage gate; inspect source/data/upstream receipts.
4. Validate scheduler profiles and a separate CPU/GPU/CPU chain.
5. Adopt the entrypoint for one new real run; keep old entrypoints during that comparison.
6. Archive unused config entrypoints only after callers are audited. Relocating artifacts requires a separate dependency/queue audit.

## Per-project starting point

| Project | Config inventory | First useful cleanup |
|---|---:|---|
| tmpl_smoke | 5 root config files | Begin with one cfg.py and one bindings file; expand into stages/tracks/runs only if there are genuine reuse or comparison needs. |
| biomass_explo_app | 0 root config files | Freeze item membership and existing feature/model bindings, then add a coverage report before aggregation. Preserve historical batch outputs. |
| nextgems_tc | 1 root config files | Freeze storm-catalogue membership with smoke/full/repair selections, explicit chunk outcomes and a coverage gate. The month-sweep example belongs to nextgems_tc_tracking, not this consumer. |
| tcwind_benchtools | 7 root config files | Use a retained-input diagnostic/reassessment entrypoint and explicit outputs; keep dependency source paths stable. |
| geosplat_diffusion | 0 root config files | Begin with one cfg.py and one bindings file; expand into stages/tracks/runs only if there are genuine reuse or comparison needs. |
| sar-ml-enhanced | 12 root config files | Separate split, per-SAFE extraction receipts, coverage publication and train/val/test datasets. Replace shared receipt roots and missing-CSV skips with explicit coverage decisions. |
| perda | 0 root config files | Begin with one cfg.py and one bindings file; expand into stages/tracks/runs only if there are genuine reuse or comparison needs. |
| sst_ml_mapping | 4 root config files | Begin with one cfg.py and one bindings file; expand into stages/tracks/runs only if there are genuine reuse or comparison needs. |
| sst_ml_zarrpatch | 52 root config files | Keep T15/T20 evidence paths. Start with frozen reassessment bindings; group scientific arms separately from resource profiles. Review the 44 root resource profiles by actual allocation/environment differences. |
| geo-jepa | 2 root config files | Separate pretraining/data bindings from evaluation arms; keep checkpoints and split definitions. Start with a retained-checkpoint evaluation recipe. |
| hafs-jepa | 5 root config files | Separate pretraining/data bindings from evaluation arms; keep checkpoints and split definitions. Start with a retained-checkpoint evaluation recipe. |
| le-tc-wm | 0 root config files | Separate pretraining/data bindings from evaluation arms; keep checkpoints and split definitions. Start with a retained-checkpoint evaluation recipe. |
| soba_bench | 0 root config files | Begin with one cfg.py and one bindings file; expand into stages/tracks/runs only if there are genuine reuse or comparison needs. |
| confild | 4 root config files | Begin with one cfg.py and one bindings file; expand into stages/tracks/runs only if there are genuine reuse or comparison needs. |
| hafs_tools | 2 root config files | Begin with one cfg.py and one bindings file; expand into stages/tracks/runs only if there are genuine reuse or comparison needs. |
| omnihafs | 4 root config files | Begin with one cfg.py and one bindings file; expand into stages/tracks/runs only if there are genuine reuse or comparison needs. |
| biomass_proc | 4 root config files | Freeze item membership and existing feature/model bindings, then add a coverage report before aggregation. Preserve historical batch outputs. |
| tc_demo | 4 root config files | Begin with one cfg.py and one bindings file; expand into stages/tracks/runs only if there are genuine reuse or comparison needs. |

Counts cover configs/configure/confs only; they are not counts of all Python configuration in src packages. No byte-identical root Slurm profile groups were found, so merging profiles blindly is not justified.

## Neural-field worktree

Keep the main environment plus worktree-source launch convention while validating the migration. Its standalone manifest has explicit local package paths and a 0.9.2 pin. Preserve the completed models and panels. A fresh neural-field run can import an existing arm config and override an absolute save_dir before resolution; logger and checkpoint paths must follow it. The arm name is a label, not a hidden architecture selector.

## Cleanup decisions that need review

- SAR: define legitimate empty extraction outcomes explicitly. A missing CSV alone is not evidence of an empty input. Dataset preparation currently skips missing CSVs; the new workflow must require complete accepted coverage before calling it.
- Preserve split/test membership and preprocessing. A new directory layout does not authorize changing the scientific protocol.
- Legacy receipts can contain relative save_dir values. Select the actual producer directory; resolve relative artifact paths only with a documented historical base. Do not rewrite old locks to make the new layout look consistent.
- A retained file inspection may publish current hashes in a new acceptance record, with historical limitations. It cannot invent original source or checkpoint identities.
- Do not move pending products independently of their queue, delete queue DBs, or rewrite upstream paths as cleanup.
- Avoid mandatory track/arm schemas, registries, one config file per sweep item, or a new orchestration framework.

