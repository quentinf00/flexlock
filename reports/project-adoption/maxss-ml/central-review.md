# Central review — MaxSS submission

2026-10-14. Initial review of report.md; evidence review remains open. This is not
central acceptance or a claim that the project's remaining callers are migrated.

The submission is usefully bounded: main/worktree import checks, explicit bindings,
fresh stage roots, fixture chain and reassessment, with no unauthorized scheduler
run or training. It explicitly lists deferred active configs and raw SQL readers.
Those deferrals prevent treating the whole project as fully adopted; distinguish
acceptance of the I39 pilot from closure of the broader adoption task.

Core findings triage:

1. Composite source union in stage records: inspect actual records and capture
   semantics before calling this incorrect provenance. A campaign source superset
   differs from per-stage dependency attribution. Keep this open for reproduction.
2. Full output SHA on consumption: a verified record digest alone cannot replace
   product checks. The record can stay unchanged while product bytes mutate.
   Performance work may reduce duplicate checks, or propose an explicitly weaker
   integrity contract, but must preserve current default guarantees.
3. Absolute python_exe warning: audit warning conditions independently; an
   absolute interpreter can intentionally select the environment without shell
   activation. This is a candidate bounded quality-of-life fix.

Next review: inspect local patch/records, check concrete producer acceptance and
orchestrator recovery, and state pilot acceptance separately from deferred callers.
No changes to the project's submitted report or scientific code made here.
