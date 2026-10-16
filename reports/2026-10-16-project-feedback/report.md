# Project-feedback fixes and investigations

2026-10-16. Changes are in the validation checkout, **unreleased**. Installed
project environments and the 0.9.3 wheel are unchanged. No scheduler jobs,
scientific campaigns, snapshot-ref cleanup or artifact reorganization were run.

## Implemented

| Finding | Change |
| --- | --- |
| Numeric-looking CLI identifiers silently change type | Warn for ambiguous integer spellings with underscores or 16+ digits; retain YAML parsing and show inner quoting. No annotation-driven coercion. |
| `python -m` invents a `src.…` target | Prefer the actual module spec name in py2cfg; keep direct-script fallback. Tested from a separate worker directory. |
| Exports omit selected-node changes | Apply `-M` then `-O` to `--dump` and `--enqueue`. Actual CLI tests cover both root and selected overrides. |
| Campaign scan includes internal index | Skip exactly `.flexlock`; other unexpected directories still fail coverage. |
| Chunk task success masks missing member outcomes | Add a project-owned example checking frozen chunk membership and declared outcome outputs; non-OK outcomes require named acceptance. |
| Array workers share default log files | Render `slurm-%A_%a.out/err` for array directives, keep single-job filenames and custom logging controls. |
| Run timestamps lack a timezone | Include local UTC offset in new snapshots/completion/error records; do not rewrite historical timestamps or directory names. |

The [follow-up guide](../../docs/project_feedback_followup.md) also documents
legacy producer adapters and snapshot-ref retention limits. The
[workflow guidelines](../../docs/workflow_guidelines.md) contain the chunk example;
the [CLI reference](../../docs/cli_reference.md#string-identifiers-and-numeric-looking-hashes)
shows shell/YAML quoting. Central project reviews link the current rollout and
unreleased follow-up without changing their bounded scientific acceptance.

## Reproduced; design work remains separate

[Composite attribution](composite-attribution.json): a two-stage local pipeline
explicitly selects a.py for one stage and b.py for the other. Both materialized
stage records capture a.py + b.py from the campaign master. Their configs still
retain their individual declarations. This establishes capture union versus
stage attribution; it does not justify deleting union source evidence. Distinct
record/report labels and comparison semantics need review before changing fields.

[Hashing duplication](hashing-duplication.json): two require_product calls for
different fields on one two-product producer read both 32-KiB files twice:
131,072 bytes for 65,536 unique product bytes. Changing a product afterwards is
rejected even though run.lock is unchanged. This is a repeated-read reproduction,
not a throughput benchmark. Batch validation within one consumer is worth exploring;
record-only or cross-consumer integrity shortcuts are not implemented.

The [reproducer](investigate.py) uses temporary Git repositories, tiny toy stages
and files. It does not execute project science. The [investigation log](investigation.log)
records completion.

## Validation

The focused final run passes **164 tests, one expected failure**; see
[log](focused-tests.log). This includes the defensive regression ensuring that a
numeric-override warning never resolves a later duplicate-key interpolation.
The initial full-suite process was interrupted by a server restart before finishing;
its incomplete output is not an acceptance result. The fresh full-suite run against the final implementation passed: **1,072 passed,
2 skipped, 1 xfailed**, with 39 existing warnings, in 368.08 seconds. See the
[full log](full-suite.log). `git diff --check` passes for code and documentation.
