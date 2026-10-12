# Reader migration pilot, 2026-10-12

User approved requiring updated readers and migrating project installations,
then explicitly chose to defer environments used by running/pending jobs.

Implemented queue layout 2 and built the local FlexLock 0.9.1 wheel. Fresh nested
products use ancestor queues; existing, external and nonstandard-name pointers
remain. Directory creation and mutexes remain. SQLite metadata records layout
and minimum reader without an extra file. Required upstream binding and
controller ownership checks reject pending/running replacements even when an
old run.lock exists; future binding preserves the exact unresolved reference.

202 focused tests pass (`tests.xml`). Initial broader checks exposed a low-level
directory-creation regression and old pointer assumptions in submit-binding
tests; both were corrected before the final suite and wheel build.

Inventory found 53 distinct prefixes among 201 path aliases. 17 are conservatively
deferred for active SST, MaxSS, HAFS-JEPA, NextGEMS and biomass jobs. 19 other
prefixes have dependency mismatches/import errors. Two otherwise eligible
prefixes (shared FlexLock development environment and tcwind-benchtools beneath
the active MaxSS project) are additionally deferred. The remaining 15 prefixes
were installed and verified independently, without PYTHONPATH overrides.

Backups: `/ontap/user/qfebvre/flexlock-migration-backups-20261012`.
`migration-results.json` records installations and probes; every probe verifies
version, installed import path and a scratch pointerless active reservation.
No project code, scientific outputs, shared source checkout, AGENTS instructions,
or project manifest/lockfile was modified. Durable project pins remain required;
ordinary Pixi sync can revert this installed-environment pilot.

The first migration attempt stopped before installation because `select.py`
shadowed the stdlib module; the helper was renamed before the successful run.

This turn's earlier metadata prototype measured files 2,007 -> 1,007 and median
preparation 17.53 -> 13.34 seconds. Those are prototype measurements, not a fresh
performance measurement of this release (which preserves low-level mkdir and
adds DB layout metadata). No live scheduler submission or scientific replay.

Pandas investigation: MLflow 3.16.1 released metadata declares pandas<4
([source](https://raw.githubusercontent.com/mlflow/mlflow/v3.16.1/pyproject.release.toml)).
FlexLock has no direct pandas import in its runtime package. Its current wheel
still declares pandas<3; no project pandas downgrade has been performed. Core
and optional MLflow compatibility checks are the next step before relaxing it.
