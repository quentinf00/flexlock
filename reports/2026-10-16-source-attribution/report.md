# Source attribution with a shared campaign capture

2026-10-16. User-approved direction: preserve shared capture, expose configured
stage scopes separately, recommend broad project-level declarations. Implemented
in the validation checkout; **unreleased**, with no installed-environment changes.

## Behavior

- Configuration remains _snapshot_.repos with existing path/module/include/exclude
  and configured-target discovery. No new option, dependency graph or capture mode.
- repos retains preserved source trees, potentially the campaign union.
- source_scope records effective tracking selections for this invocation: canonical
  repository paths, include and exclude lists. Discovery origin stays in discovery.
  This describes configured scope, not a complete runtime import dependency graph.
- Source comparisons use the proposed/current invocation's scope and match campaign
  aliases by canonical path. Missing capture fails comparison. Full include selections
  do not fall back to a narrower target scope. Explicit comparison overrides retain
  precedence. Historical records without the field retain capture-based behavior.
- Environment-lock comparison selects the stage's repositories consistently, including
  aliases and name collisions. An unrelated captured repository no longer causes a
  stage-specific difference. Stage fingerprint computation is unchanged.
- Directory and DB records, producer lineage, show JSON/Markdown and graph/HTML
  reports expose the distinction. Historical records are not rewritten or rediscovered.
  Commit history remains history of captured repositories, which can be broader than
  the stage's source scope.

See the [contract and config examples](../../docs/source_attribution.md). Broad
source/config/script directories shared across stages are the starting recommendation;
finer scope declarations are optional. Capture/comparison cannot establish whether
retained preparation remains scientifically suitable after a code change.

## Evidence

The new tests exercise real temporary repositories and local toy pipelines in both
directory and database modes. Cases cover a shared repository under different names,
the same name used for different repositories, exclusions, unrelated stage source
and environment changes, explicit comparison overrides, a stage with tracking disabled,
missing captured trees, full-versus-narrow comparison, upstream lineage retention and
historical readers. No scientific project pipeline or Slurm submission was run.

The [standalone probe](probe.py) separately verifies **one capture per campaign**
for a shared repository across two stages. Both stages preserve a.py + b.py, while
source_scope selects the appropriate file for each. A change to b.py preserves
stage A's source match and changes stage B's result; see [JSON](probe.json) and
[log](probe.log). These temporary fixtures validate mechanics, not scientific provenance.

Focused regression result: **132 passed**, 24 warnings, in 17.24 s;
see [log](focused-tests.log). Full suite: **1,076 passed, 2 skipped, 1 xfailed**, 39 warnings, in 348.64 s;
see [log](full-suite.log). Code/documentation whitespace checks also pass.
