# Remaining migration decisions

2026-10-14. Review proposals, not installed changes. Shared guidelines and local
AGENTS links are in place in 21 distinct consumer checkouts. All 53 inventoried
environment prefixes use FlexLock 0.9.2. Config organization and scientific
workflow adoption are incremental; an upgraded package does not establish either.

## SAR: queue status and CSV presence before assembly

Accepted correction: mandatory per-SAFE outcome receipts are unnecessary for the
current extractor. Its normal return with no CSV denotes no usable extracted
features. An exception is a failed task. Successful tasks with a CSV may have
produced it or skipped an existing file; status and presence do not distinguish
those two cases.

Freeze the expected SAFE membership and bind each member to its exact queue task
and expected CSV path. Before assembly, require terminal successful status for
all process members. With that evidence, CSV absence can count as empty, provided
products have not been moved/deleted and the status belongs to the same invocation.
Failed, pending, running, missing or mismatched task evidence must block assembly.
Explicit exclusions remain separate. Report produced/present and empty counts;
stop clearly on an all-empty cohort instead of concatenating an empty list.

Use fresh destinations for fresh extraction so an existing-file skip cannot be
mistaken for new processing. Deliberate existing CSV reuse needs explicit provenance
and product acceptance checks. No mandatory item.json or new extractor return type
is required. Separate FlexLock record directories still avoid record collisions;
CSV layout changes are a separate project choice, not imposed by this decision.

The earlier receipt validator was a tested proposal, now withdrawn from active
examples. Receipts may be reconsidered if durable empty-outcome evidence independent
of the queue, or detailed empty reasons, becomes useful. Historical reports preserve
what was investigated, not the accepted workflow. No scientific SAR source or split
protocol was changed.

## Slurm: keep ordinary submission; defer public export

The private backend materialization seam is implemented and locally tested. Keep
profiles, --after and --print-job-id as the supported workflow. A hold is already
expressible through a profile directive. My recommendation is to defer a new public
export flag until a real workflow requires delayed manual submission: raw sbatch
would leave acceptance, repeated launch and reservation ownership to the project.

If accepted later, a public export proposal must specify destination reservations,
when they may be released, how manually accepted IDs are recorded, and whether
arrays/dependencies may change after preparation. Merely printing a runnable
command does not settle those questions. The private seam adds no installed API.

## Optional caching and project cleanup

CLI caching is opt-in today; Python submit/run_stage still default to smart_run=True.
Do not report caching as removed. New recipes explicitly use False. Next validate
the SST retained-preparation mapping in isolation, updating root anchors before
selecting downstream configs. Keep explicit True compatibility callers and bounded
same-path skip reuse. A future Python default change needs a release decision.

Adopt one useful workflow per project before reorganizing directories. Keep old
configs until their callers are audited, and keep historical artifacts at their
selected paths. No bulk archive or artifact move is needed for the core migration.

## Execution order

1. Implement the accepted SAR queue-status/CSV coverage gate in an isolated pilot.
   Public Slurm export remains deferred pending a concrete use case.
2. Build an isolated SST retained-preparation selection example and validate root
   propagation and retained product checks without running expensive preparation.
   The synthetic SST-style regression now passes: a detached config edit leaves
   later selections unchanged, while updating the root before selection consumes
   the accepted retained product without creating the unused preparation path.
   Actual SST preparation configuration adoption remains to be validated.
3. Validate the SAR pilot with a produced item, a genuinely empty item, failure
   and incomplete cohort rejection before scientific assembly adoption.
4. Choose the Python caching default for a subsequent release after those callers
   have explicit alternatives. Then update docs, compatibility notices and tests.
5. Adopt reviewed configs gradually; archive only after caller and retention audits.
