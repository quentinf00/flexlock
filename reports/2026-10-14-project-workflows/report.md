# Central recipes and project workflow notes

Updated 21 physically distinct AGENTS.md files, including MaxSS main and neural-field. Existing text was preserved in every file. The workflow section links central guidelines, release scope and transition proposal; local guidance covers SAR outcomes/coverage, SST retained reassessment, month sweeps, checkpoint evaluation, biomass aggregation or neural-field launch conventions as appropriate. No scientific configs or artifacts were reorganized. updates.json retains applied paths and before/after hashes; before/ contains original instructions.

Next bounded TODO implemented in isolation: private Slurm backend materialization writes a runnable payload/script and returns paths, argv and cwd; ordinary submission reuses it. Tests execute a real serialized callable locally and use fake sbatch for accepted-ID/dependency validation. No actual scheduler submission or project package upgrade occurred.

Remaining decisions: public prepare/export CLI ownership semantics, optional cache/pipeline default changes and removals, and SAR's produced/empty project contract. Production config cleanup follows a first bounded recipe adoption and caller audit. None is implied by an AGENTS.md link.

Validation: 39 Slurm materialization/script and workflow acceptance tests passed (49 existing OmegaConf deprecation warnings). All 21 applied sections were reread and checked for exactly one marker and preserved original instructions.
Existing HPC dependency tests: 21 additional passes, for 60 passing checks in this change.
