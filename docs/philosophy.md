# FlexLock's role

FlexLock has two core responsibilities: configurable Python calls and provenance.
Local/cluster execution, sweeps and worker task claims make those calls practical
at different scales. Scientific orchestration policy belongs in project workflows.

## Configuration

Write configs as Python dictionaries and `py2cfg` calls. Presets, CLI selection,
overrides, node replacement with `@` and named sweep files support composition
without requiring a separate config file per work item. A file-list campaign and
an experiment sweep use the same task-claim primitive.

## Provenance

An authoritative run record captures configuration, declared source/data scope,
upstream producer bindings, declared output evidence and the callable's return
value. Source capture can discover repositories from nested `_target_` values;
it does not prove all transitive imports were captured. Explicit repositories and
include/exclude scopes express project intent. Per-invocation `source_scope`
distinguishes a stage's attribution from a campaign's shared source capture.

Comparisons supply evidence. They do not decide whether yesterday's preparation
remains acceptable after today's source edit. That decision can differ between
data production, model exploration and an inference release.

## Explicit artifact selection

Projects choose concrete producer runs and bind consumers through config anchors
and `run_lock`. FlexLock records the selected identity and verifies it at consumption.
No equivalent-run search or worker-time newest-run selection substitutes a producer.
Same-path `skip` validates a complete selected record and its outputs; it does not
certify equivalence to the proposed config or current source.

Keep project organization readable. Track/arm/run can name scientific or processing
variation; products, processing and inference packages may also have explicit role
names. These are conventions rather than mandatory library abstractions. Project
coverage checks establish cohort membership, valid emptiness and acceptance.

## Execution and recovery

Workers claim queue tasks; an unchanged recorded queue can drain pending rows while
done rows remain done. Ordered stages execute fail-fast with separate records, on
one allocation. Different resources use ordinary scheduler jobs and dependencies.
A small project coordinator records accepted scheduler IDs and concrete producer paths.

A partially completed pipeline requires an explicit recovery choice: select remaining
stages, bind retained producers and choose fresh destinations. Completion markers do
not justify automatic stage reuse. Occupied-destination and active-ownership guards
remain mechanical protections against overwritten provenance and conflicting execution.

## Scope

Research and offline data processing form a continuum. FlexLock can record the path
from inputs to trained models and inference packages, including processing variants
and deployment artifacts. Serving, artifact publication, retention, access control,
scientific acceptance and production rollout remain project responsibilities.

Historical scientific producers may require project-owned integration with imperfect
provenance. FlexLock does not add scientific legacy adapters. Once the API stabilizes,
projects should plan fresh pipelines under the current bookkeeping conventions.

See [workflow guidelines](workflow_guidelines.md) and
[candidate migration notes](release_0_10_0rc1.md).
