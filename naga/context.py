"""Shared context for a Naga run."""
from contextvars import ContextVar

# This context will hold information gathered during a run, like the git commit hash.
# It is initialized with an empty dictionary.
run_context: ContextVar[dict] = ContextVar("run_context", default={})
