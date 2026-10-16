# Shared source capture and configured stage scopes

2026-10-16. Implemented in the validation checkout; unreleased. No new configuration
option or per-stage source-capture mode is introduced.

## Start with a broad project scope

Reuse one source declaration across stages unless narrower scopes have a concrete
benefit. Select the source directories that actually exist in the checkout:

```python
from flexlock import py2cfg
from myproject.stages import prepare, train

source = dict(repos=dict(main=dict(
    path='/shared/checkouts/myproject-pinned',
    include=['src/', 'configs/', 'scripts/'],
)))

cfg = dict(
    run_dir='/shared/runs/example',
    prepare=py2cfg(prepare, save_dir='${run_dir}/prepare', _snapshot_=source),
    train=py2cfg(train, save_dir='${run_dir}/train', _snapshot_=source),
)
```

This excerpt supplies source tracking and destinations; callable input/output
arguments remain project-specific. It does not add stage dependencies implicitly.
An explicit repository without include still requests the full non-ignored checkout.
Prefer a broad source-directory scope when a repository also contains large generated
arrays or outputs. Add external helper/subprocess repositories explicitly as needed.

## Narrow scopes use the existing declaration

If useful, prepare can declare include=['src/myproject/preparation/',
'src/myproject/common/'] and train can declare include=['src/myproject/training/',
'src/myproject/common/']. Per-repository exclude retains its existing meaning.
Configured nested-target discovery still applies when enabled. No transitive import
tracing is added; an effective configured scope is not proof of every runtime dependency.
Use pinned, immutable checkouts between capture and execution; pickling does not
freeze imports. Existing code-drift checks and warnings still apply.

A campaign captures the union once. Its stage records retain that capture and now
also store each stage's effective configured scope. For the two-file example:

```yaml
# Preparation stage record — output metadata, not new config syntax
repos:
  main:
    path: /shared/checkouts/myproject-pinned
    tree: <tree-containing-prepare.py-and-train.py>
    include: [prepare.py, train.py]
source_scope:
  main:
    path: /shared/checkouts/myproject-pinned
    include: [prepare.py]
    exclude: []
```

- repos describes preserved source trees. A queued stage may inherit a campaign-wide
  capture, with additional repositories or broader include/exclude scope.
- source_scope describes effective tracking selections for this invocation, including
  explicit declarations and configured-target discovery. Paths are canonical repository
  paths. An empty include list means full non-ignored scope before exclusions.
- source_scope={} means this invocation tracks no repository; it does not prove the
  callable has no source dependencies. The campaign's source capture can remain present.
- Existing discovery metadata distinguishes explicit repositories from target discovery.
  No extra declaration, dependency graph or separate per-stage Git snapshot is required.

Serial records, directory-backed tasks and authoritative DB stage snapshots retain
this metadata. Producer lineage retains it too. load_record returns both sections;
show JSON/Markdown and HTML reports label capture separately from configured scope.
Historical records without source_scope remain without it; readers do not rediscover
old dependencies from today's imports or rewrite old records.

## Comparisons use the configured scope

For records carrying source_scope, source comparison considers that invocation's
selected repositories, matching them to preserved captures by canonical path when
campaign aliases differ. The proposed/current record's include/exclude scope applies
to the preserved trees. Explicit comparison overrides still take precedence.
An empty/full include selection must not fall back to a narrower target selection.
Missing capture evidence fails comparison even when the declarations match.

Consequently, a stage comparison can ignore another stage's changed source files
or repository environment locks while retaining that broader capture as provenance.
Environment lock identities are selected and renamed consistently with the stage's
repository aliases. Stage fingerprint computation itself is unchanged; it already
uses the stage tracking configuration.

This comparison is directional: a narrow proposed scope can be checked against a
broader preserved tree. Reversing to a full proposed scope fails when the other tree
omits required source. Historical records without source_scope retain their existing
capture-based comparison behavior. Neither scoped comparison nor a matching fingerprint
establishes scientific suitability of a retained preprocessing product.
