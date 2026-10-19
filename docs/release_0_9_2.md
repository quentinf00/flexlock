# FlexLock 0.9.2: remove unused pandas dependency

Rollout status as of 2026-10-14: all 53 originally inventoried environment prefixes
have been upgraded, including MaxSS after its training finished. Later-discovered
legacy/example consumers must verify their installations individually. The initial
batch counts below are historical evidence. See the
project rollout (internal validation evidence),
MaxSS completion (internal validation evidence), and
[project adoption handoffs](project_adoption_handoff.md). Scientific workflow
adoption remains project-owned and reviewed separately.

This local release follows [0.9.1](release_0_9_1.md). Its only runtime/package
change is removing the unused pandas dependency and updating the version.
FlexLock's runtime package has no pandas imports. Optional MLflow and scientific
packages still declare and resolve their own dependencies; this change does not
claim compatibility for every MLflow/pandas combination or uninstall pandas
from project environments.

The wheel imports from its installed location in a clean environment with no
pandas installed. 59 focused queue-layout, producer-binding, task-record and
mocked MLflow integration checks pass in that environment. The earlier 202-case
execution/reader suite covers the unchanged runtime from 0.9.1.

22 idle compatible installations now use 0.9.2, including seven installations
previously excluded solely by the pandas constraint. All installed-package
probes pass; the other package dependencies were not changed. Active-job
environments, older incompatible GitPython installations and the broken docs
environment remain deferred.

Compatibility notes have been added to AGENTS.md in the ten identified migrated
projects. They cover stricter destination ownership, upstream binding, failure
and output validation, new queue-reader requirements and current rollout
limitations. Unidentified environment prefixes still need project mapping.
Project manifest/lockfile repinning remains open. See
[project instruction policy](project_migration_agents.md) and the
rollout evidence (internal validation evidence).
