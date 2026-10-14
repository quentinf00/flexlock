# Central review — SST

2026-10-14. Reviewed submission, local evidence.json and workflow runner/acceptance
source. Bounded retained-preparation/reassessment evidence is positive; whole
project adoption is not accepted or complete.

The runner changes root anchors before selection and explicitly disables cache
search. Legacy acceptance distinguishes current byte identities from historical
provenance; cube metadata identity is explicitly weaker than hashing full data.
The evidence records 24 matching metric rows for six products and concrete bound
producer records. Mapping, old implicit preparation pipelines and T20 input-binding
configs are explicitly deferred. No science-changing replay is claimed.

Follow-up requested before closing:

- The central report's implementation.patch/caller-inventory.json/evidence.json
  relative links have no files at their central destinations at inspection. Supply
  them or link their actual local locations; local evidence.json exists.
- Scheduler ID capture parses the log message "Submitted SlurmBackend job". Use
  the supported --print-job-id CLI output pattern, or explicitly mark this runner's
  scheduler mode as provisional and test rejection/partial-reporting recovery.
  The report currently describes persisted IDs but scheduler mode was only previewed.
- Keep acceptance of the retained-input recipe separate from the remaining active
  caller migrations. No need repeat expensive reassessment for a documentation fix.

No project source, scientific artifacts, submitted report or active jobs changed
by this review.
