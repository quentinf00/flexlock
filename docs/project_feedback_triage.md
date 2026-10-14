# Project feedback and core follow-ups — 2026-10-14

Project acceptance applies to a concrete recipe and declared evidence scope.
Core proposals are handled independently: reproduce, identify the contract and
affected callers, choose a bounded fix or an explicit API/release decision, add
a meaningful regression check, then validate and ship. An accepted project report
does not authorize every proposed core behavior change. Do not silently install
validation-branch changes into project environments.

| ID / priority | Finding | Evidence / disposition | Next step |
|---|---|---|---|
| C1 / urgent | Core overwrites callable-owned results.json | Independently reproduced through RunRecord.write_results(None); worker writes results before output validation | Define collision-safe return-result storage and reader compatibility. Reserved filename changes disk/API expectations; review concrete proposal before release. Warn-only still loses data. |
| C2 / high | Downstream composite snapshot resolves promised input too early | SAR cli-chain.log: _stages_[3]._snapshot_.data.bindings | Add minimal regression, defer only legitimately promised producer input resolution until stage start; preserve binding/output checks. Sequential submissions are current workaround. |
| C3 / high | Source scopes do not limit snapshot staging | RunTracker.record_env invokes create_shadow_snapshot without include/exclude; then stores scopes as comparison metadata | Separate source-capture scope from comparison scope. Design explicit exclusions/capture policy, test dirty/untracked files and identity completeness before deploying; do not snapshot large arrays in a reproduction. |
| C4 / medium | Nested _target_ repositories absent from automatic provenance | Mocked two-repo config records only top-level alpha, never beta | Audit historical intended contract. Consider recursive target discovery with canonical deduplication and explicit-scope precedence; no transitive import scan implied. Test selected configs, discovery disabled and stage attribution. |
| C5 / medium | Composite records carry campaign repository superset | MaxSS separately submitted stages scoped; composite source union reported | Reproduce and clarify captured source versus per-stage dependency attribution. No provenance rewriting. |
| C6 / medium | Mandatory missing root anchor is resolved before sweep item supplies it | SAR failed/successful previews | Minimal scope-order regression; retain -o base anchor workaround. No silent override scope change. |
| C7 / medium | py2cfg target from __main__/python -m can be non-importable | HAFS-tools report; inspect existing warning/path fallback | Reproduce importable __spec__.name cases and launch context; stable imported callable is workaround. |
| C8 / medium | Scalar overrides can change textual identities | HAFS-JEPA 183_3; HAFS-tools all-digit SHA | Document quoting strings first. Signature coercion could destroy literal identity and alter existing semantics; not automatically approved. Add parsing examples/checks. |
| C9 / medium | Per-item retained preparation remains expensive | HAFS-tools 18–21 s retained items; duplicate SHA checks in MaxSS | Profile config/source/store reads separately with bounded fixtures. Do not substitute producer-record hashes for product bytes. |
| C10 / low | Worker array logs share filenames | HAFS-tools rendered script | Review %A/%a defaults against explicit profile paths and reader assumptions. |
| C11 / low | Record timestamp has no timezone | HAFS-tools report | Audit readers and choose backwards-compatible timezone-aware serialization. |
| G1 / docs | Legacy producer acceptance adapters | HAFS-JEPA helper inspected | Document explicit required files, historical path base, completion/status, present-byte identity and missing historical provenance. No blanket acceptance of old records. |
| G2 / docs | Hidden FlexLock indexes misclassified as campaign items | HAFS-tools fixed own gate | Audit shared example; exclude specifically owned control entries rather than blindly accepting arbitrary extras. |
| G3 / docs | Processing/release terminology and portable inference | SAR FLEXLOCK-LIFECYCLE queued | Review project implementation/evidence and proposed guideline patch; track/arm/run stays optional. |

Repository discovery today follows the selected stage's **top-level** _target_.
collect_target_include_patterns recursively walks nested targets for cache
comparison file scopes; it is not repository provenance discovery. Ordinary
imports inside a callable and subprocess imports require explicit repository
declarations. HAFS-JEPA's probe internally imports geo_jepa, so its declaration
remains necessary even if C4 is implemented. An existing record from before that
declaration cannot be claimed to contain the sibling source snapshot.

Absolute-interpreter activation warning was fixed centrally in a0a934b; it is not
installed in the reported 0.9.2 environments. Cache-discovery/default retirement
remains a separate previously tracked release decision.
