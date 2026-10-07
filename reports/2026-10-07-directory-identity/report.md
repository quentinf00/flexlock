# Directory-content identity

2026-10-07. Isolated workflow/execution-acceptance branch.

Directory identity now reads selected relative paths and file bytes on every check.
Root mtime, file count and maximum child mtime are no longer accepted as unchanged
content evidence. Directory cache reuse/writes and the size-dependent fallback are
removed. Match/ignore filters are applied for each check; overlapping selections
are deduplicated. Existing digest fields remain, with additive data_identity evidence
naming the method and algorithm. Single-file mtime caching remains labelled.

70 selected checks passed in 18.90 seconds: data_hash, snapshot, discovery_policy,
reviewed_record_contracts and index. [JUnit](validation.xml). Source stayed unchanged
through the run. This is not the full suite; no scheduler jobs or production changes.

Identity excludes empty directories, permissions and timestamps; symlinked files
are read through their targets under the selected relative name. Inputs must remain
stable while being read; no atomic filesystem snapshot is claimed. Full rereading
cost remains for the M4 benchmark. Old records remain readable, but formerly stale
cached directory digests can produce different equivalence decisions after correction.
M2 existing-producer pre-dispatch binding/change policy is next.
