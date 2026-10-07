# Optional-policy caller inventory

2026-10-07. Bounded static audit of source f6beec9. No default, API, package install,
scientific source or workload changed. [Dispositions and workflow replacements](../../docs/optional_policy_inventory.md),
[raw inventory](inventory.json), [read-only scanner](scan.py), [config probe](config-probe.json).

The important dependency is explicit cross-run reuse in SST preparation. SAR's
older pipelines forward a default-off cache switch; its processing pilot uses
explicit same-path skip with project-owned identity and output checks. Sample/tutorial
projects explicitly enable cache search. The lab has an unpinned worker-time producer
selection under after. No external submit_chained or run_stage candidate was found
in the bounded project selection; library tests/documentation remain real contracts.
This negative result is not proof of no installed or out-of-scope callers.

The Project.get probe confirms that modifying a detached selected stage does not
change later root-bound stage inputs. An explicit root update does. SAR/SST source
contains post-submit cfg.save_dir assignment; isolated adoption must correct that
wiring. No scientific pipeline was run to certify its current behavior.

## Scope and method

The scanner selects Python, shell, YAML and TOML source through rg, respecting ignore
rules and excluding generated outputs/reports/environments. It retains hashes for
all selected files, lexical policy occurrences and AST candidate calls. Candidate
method names do not establish receiver type or runtime reachability. Manual review
excluded SST pool.submit as a ThreadPool call; sample expanded kwargs explicitly
carry smart_run=True. The sample config docstring's omitted smart_run example is
documentation, not an executable call. Original dirty source is identified by file
hashes and status rather than HEAD alone. Duplicate pilot/original files are not
counted as distinct user dependencies.

| Scope | Selected source files | Interpretation |
|---|---:|---|
| Isolated FlexLock | 110 | Implementation/tests; docs inspected separately |
| Workflow lab | 15 | Includes deliberate failure/compatibility journeys |
| Original SAR | 111 | Dirty source preserved |
| SAR pilot | 102 | Includes copied old pipelines and new processing adapter |
| Original SST | 152 | Dirty source preserved |
| SST pilot | 123 | Copied preparation and isolated reassessment remain distinct |
| Sample project | 32 | Explicit caches and manual anchor/resource loop |
| Tutorial project | 26 | Explicit cache-enabled three-stage pipeline |
| Project template | 11 | No candidate optional-policy call |
| zendag | 21 | Lexical run_stage names are external command strings |

703 selected files in total across scopes, with duplicates. Two zendag exported
IPython Python files do not parse as standard Python; their lexical search is retained
but AST results are incomplete. Notebooks/ipynb, ignored files, outputs, other projects,
installed package users and dynamic calls are not exhaustively inventoried.

Verification: JSON parsing, selected-file hash verification, local Markdown links,
Python snippet syntax and the side-effect-free config/default probe. No test suite,
scheduler call or scientific target was run for this inventory. Earlier implementation
validation remains in its own revision-bound reports.

Next: preserve optional adapters/defaults, make selected-product and root-update
recipes concrete in isolated adoption, and measure thousand-item queue/source/data/
binding overhead before broader policy/default changes. The bounded inventory is
complete; optional-policy separation and production adoption remain open.
