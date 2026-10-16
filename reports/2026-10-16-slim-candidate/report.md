# Slim-core candidate validation

2026-10-16. Candidate: **0.10.0rc1**, based on source-attribution commit
0b88a5681a859d9d267ce99cd30d55550e22d10e plus this change. The user explicitly
approved removing retired APIs now, rather than retaining deprecated opt-in behavior.
Installed project environments remain on their previous release.

## Implemented boundary

- Removed automatic cross-run execution cache search, its submission keywords and
  CLI flag, Project.exists/get_result, sibling discovery and automatic index writes.
- Removed submit_chained/ChainedResult and marker-based partial-stage resume.
  Old flagged composites fail clearly before executing any stage body; old Python
  kwargs including smart_run=False fail before dispatch.
- Retained configuration composition, named sweeps, provenance/comparison,
  concrete upstream bindings, local/cluster workers, scheduler dependencies,
  ordered fail-fast stages, exact-path reuse and unchanged recorded queue continuation.
- Same-path reuse validates the producer's recorded output contract even when a
  proposed config removes it, and returns the producer's config. It is not proof
  of current-source/config equivalence. Partial pipeline recovery selects remaining
  stages and concrete retained producers explicitly.
- Queue continuation recognizes the same task ID in the same recorded queue.
  An installed-wheel check caught a serial continuation regression; the fix also
  rejects foreign queues and changed payloads. This is ownership/deduplication,
  not a source-equivalence test or an automatic stage-resume policy.
- Retained explicit inspection/reindex utilities. Source include/exclude capture,
  source_scope, data hashing and record diff are independent of reuse policy.
- Worker-time unpinned run selectors under --after fail before dispatch. Explicit
  pins bind at submission; concrete promised run_lock producers resolve at stage start.

See [release/migration notes](../../docs/release_0_10_0rc1.md) and
[workflow guidelines](../../docs/workflow_guidelines.md). README, current API/CLI,
quickstart, usage, HPC and resolver guides now describe the slim core. Historical
plans retain dated evidence with a superseding notice.

## Validation

Full suite: **1,086 passed, 2 skipped, 1 expected failure**, 34 warnings, **338.92 s**,
on Python 3.13.14; see [log](full-suite.log). Retired feature-only tests were replaced
by explicit selection/continuation and rejection checks; the remaining mixed-module
coverage was preserved. The full suite includes the five workflow recipes, future
producer chains with mocked schedulers, source attribution and negative coverage gates.

The final wheel passes standalone validation from outside the checkout. All **49
packaged files** match the checkout and isolated installed package; see
[identity manifest](wheel-identity.json) and [wheel acceptance](wheel-acceptance.json).
The six runtime dependencies are unchanged. The wheel is available locally at
`dist/flexlock-0.10.0rc1-py3-none-any.whl`; no release tag or publication was made.

Final build used an existing read-only Hatchling installation from a cached Pixi
build prefix after the ordinary uv build cache was cleared/unavailable. No dependency
installation in a project environment or network download was needed. The build
context and hash are preserved in [build context](build-context.json) and identity evidence.

See [validation summary](validation.json). No real scheduler call, scientific pipeline,
project environment upgrade or artifact migration was performed by these toy checks.

Regression coverage includes rejected retired kwargs, fresh destinations, selected
record/output integrity, partial composite refusal, historical marker preservation,
unchanged pending/done queue continuation, same-queue ownership, foreign/changed
payload refusal, explicit remaining-stage recovery, source attribution and the five
workflow recipes. Feature-only retired tests are listed in retired-tests.json;
mixed modules retain their loader, output-health, guard and provenance checks.
The inventory records 16 removed feature-only functions and three consolidated
worker-time selector cases, with their original source hashes.

## Preparation and local execution measurements

All scheduler boundaries are mocked or rejected. Fixtures use synthetic 4-KiB files.
Initial matched tracked preparation (without declared output contracts): baseline
**8.586 s**, candidate **8.593 s**, each 1,000 pending rows, **1,010 files** and one
mocked scheduler call. These are single samples, not evidence of a speedup.

A later tracked preparation with output contracts took **64.983 s** while the full
suite and other validations were running. Plain preparation with output contracts
was **7.538 s**. The quiet final-source result below checks this variation; the single outlier cannot
by itself be attributed to output contracts.

Final-source tracked preparation with declared output contracts, after the full
suite finished: **9.203 s**, **1,010 files**, **1,000 pending rows**, one mocked
scheduler call. The earlier 64.983 s sample did not reproduce under this bounded
quiet rerun; external/shared-filesystem variation is not controlled, so no general
throughput or output-contract speedup claim follows.

A final-source repeat matching the original no-output-contract preparation fixture
took **8.753 s**, versus the **8.586 s** baseline single sample. This supports the
absence of a large preparation regression; it is not a measured optimization gain.

A real local 100-item run with source/data tracking and declared outputs completed
all 100 rows, validated every product and exact membership, and made no scheduler
call: **89.081 s**, **608 files**. This end-to-end timing is separate from preparation.

## Project rollout boundary

The bounded read-only audit covers 32 physical roots and finds 48 literal references
in 17 roots. It includes comments/tutorials as well as actual calls. Dynamic kwargs,
notebooks and wrapper defaults can escape the literal scan. Old SST preparation,
JEPA stage wrappers, HAFS scripts and tutorial/sample pipelines need attention;
recent explicit-producer recipes mostly retain their semantics but must remove
obsolete False kwargs where present. Do not automatically convert True into fresh
scientific computation. Project owners select retained producers or plan intentional
fresh full pipelines after stabilization. Scientific legacy integration remains
project-owned. These checks do not constitute central scientific acceptance.
