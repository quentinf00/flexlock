# Project instructions and shared knowledge

FlexLock owns tool behavior, workflow recipes and the agent skills shipped with
the package. Research conventions, literature and cross-project findings belong
to a separately maintained knowledge repository; using FlexLock does not require
access to any particular private knowledge base.

Commit a short `AGENTS.md` at each project root alongside its code. Keep nested
instructions beside the code they govern. Record practical commands, local
invariants, accepted work and links to applicable conventions. If another agent
uses `CLAUDE.md`, keep it as a short pointer to the same instructions.

Pin shared conventions to a reviewed repository commit or release, and explicitly
instruct agents to read the applicable files. A hyperlink alone does not load
external instructions. Record project-specific exceptions locally; do not copy
an entire evolving tool manual into each project.

Keep host-specific paths in local setup notes or environment configuration. Shared
documentation should use relative links, portable placeholders and canonical
repository URLs. Do not place credentials in instructions or versioned setup files.

An `AGENTS.md` template and generated project instructions are separate artifacts:
the template is versioned by its owner, while each generated project's adapted
file is committed and reviewed in that project's Git history.
