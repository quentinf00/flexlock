# Optional cache policy: load the selected producer once

This bounded internal correction preserves Python `smart_run=True` defaults,
CLI opt-in behavior, explicit automatic reuse and `save_dir_policy='skip'`.
It does not install a release or migrate scientific project source.

## Finding and correction

Serial and sweep cache-hit branches first called `_find_matching_run` with
the caller's comparison filters, then called `get_result`, which performed
another lookup without those filters. That repeated discovery could load a
different producer from the one initially accepted. It also repeated cache
lookup work on every hit.

Both branches now pass the selected directory directly to the existing
`_load_cached_result`. Pipeline cache hits already use this pattern. Existing
authoritative-record checks and output validation still run; no fingerprint,
discovery or reuse-acceptance rules change.

The regression test uses real records for producer A and B and a selector that
would return B on a second lookup. Serial and sweep paths must each perform
one filtered lookup, return A's result and retain A's record directory.

Validation with `/tmp/flexlock-no-pandas/bin/python -m pytest`:

- `test_cache_selection_once`, `test_save_dir_guard`, `test_index`, and
  `test_workflow_integrity`: **41 passed**, 81 warnings, 51.73 seconds.
- Pipeline all-cached and marker-resume compatibility cases: **2 passed**,
  15 warnings, 1.32 seconds.

Warnings are the existing suite warnings. No Slurm jobs were launched.

## Next release boundary

Project adoption can proceed independently. Keep explicit automatic reuse
available while owners replace implicit artifact selection. A future default
change from Python `smart_run=True` to False remains a public behavior decision:
it needs a release notice and completed adoption evidence, not an internal
refactor. Same-path explicit skip, authoritative record readers, fingerprints
and output validation remain distinct supported primitives.

Legacy recursive fallback remains enabled by default when automatic reuse is
requested (`FLEXLOCK_INDEX_FALLBACK` defaults True). This patch does not claim
that legacy discovery has been removed or disabled. The CLI's ordinary fresh
execution already avoids that search unless explicitly requested.
