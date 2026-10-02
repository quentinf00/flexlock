"""Partial-freeze of OmegaConf interpolations when detaching a sub-node.

``select_and_freeze_root_refs`` selects a sub-node out of a root config and
makes it *self-contained* — pickle-able, mergeable, and safe to hand to a
worker — by resolving the references that point *outside* the sub-tree while
preserving the ones that must stay live.

OmegaConf resolves interpolations lazily against the config's root at access
time, so a detached node loses every ``${...}`` that pointed to the root. But
plain ``to_container(resolve=True)`` is too blunt: it would also fire resolver
calls (``${vinc:}``, ``${latest:}``, ``${run_lock:}``) that must run *later*,
on the worker, at submit time. So this module walks the ``${...}`` grammar and
decides, per interpolation, whether to freeze or preserve it:

- **Simple refs outside the sub-tree** (``${root_anchor}``, ``${a.b}``) are
  resolved against the root by OmegaConf itself — following multi-hop chains,
  mixed strings (``${pipeline_dir}/split``), and nested resolver-arg refs — and
  baked to concrete values. Delegating to OmegaConf (rather than hand-rolling a
  chain-follower) is what makes the historical ``_resolve_in_root`` class of
  bugs structurally impossible.
- **Resolver calls** (``${name:args}``) are preserved as frozen call strings
  (their arguments are pre-resolved by OmegaConf under the freeze stubs), so
  they fire later at submit/stage time.
- **Relative refs** (``${.foo}``) and **refs inside the sub-tree** are preserved
  verbatim.

The only public entry points are :func:`select_and_freeze_root_refs` and
:func:`freeze_deferred`; everything else is a private helper for the scan.
"""

from omegaconf import OmegaConf, DictConfig, ListConfig

# Sentinel: an external ref that OmegaConf could not resolve from the root.
_UNRESOLVED = object()


def freeze_deferred(cfg: "DictConfig | ListConfig", *, defer_runs=False) -> "DictConfig | ListConfig":
    """Eager-resolve every interpolation except the deferred resolvers.

    Deep-copies ``cfg`` (detaching it from any parent), then resolves it under
    :func:`flexlock.resolvers.deferred_stubbed`. OmegaConf resolves all simple
    refs, cross-tree refs, multi-hop chains, mixed strings, and relative refs
    itself; the deferred resolvers (``run_lock``/``latest``) collapse to
    self-contained call strings that fire later at stage start. The result is
    a plain config of concrete values plus frozen deferred call strings, safe
    to serialize with ``resolve=False``.

    ``defer_runs=True`` additionally preserves run calls for scheduler chains;
    call ``freeze_run_refs(..., defer_unpinned=True)`` first to bind pins and
    record their lineage.
    """
    from .resolvers import deferred_stubbed

    detached = OmegaConf.create(
        OmegaConf.to_container(cfg, resolve=False, throw_on_missing=False)
    )
    with deferred_stubbed(defer_runs=defer_runs):
        OmegaConf.resolve(detached)
    return detached


def select_and_freeze_root_refs(root_cfg: DictConfig, key: str | None) -> DictConfig:
    """Select a sub-node from `root_cfg` and freeze its root-scope references.

    The returned config is self-contained: it can be pickled, round-tripped
    through ``OmegaConf.to_container``/``OmegaConf.create``, and merged with
    other configs without losing context.

    Three kinds of interpolations are handled distinctly:

    - **Simple refs to keys outside the sub-tree** (e.g. ``${root_anchor}``)
      are resolved against ``root_cfg`` (by OmegaConf) and substituted as
      concrete values. If the target is itself a resolver call
      (``${vinc:}``/``${run_lock:}``), the frozen call string is substituted so
      the resolver still fires later.
    - **Resolver calls** (``${name:args}``) are preserved as frozen call
      strings, with any nested simple refs in their args resolved.
    - **Relative refs** (``${.foo}``) and **refs to keys inside the sub-tree**
      are preserved verbatim.

    Args:
        root_cfg: The full root configuration.
        key: Dot-path to the sub-node. If ``None``, returns ``root_cfg``
            unchanged.

    Returns:
        A new ``DictConfig`` (or the same root if ``key is None``).

    Raises:
        KeyError: If ``key`` is not found in ``root_cfg``.
        UnresolvedInterpolationError: If the sub-node references a key that
            exists in neither the sub-tree nor the root.
    """
    if key is None:
        return root_cfg

    sub_node = OmegaConf.select(root_cfg, key, throw_on_missing=False)
    if sub_node is None:
        raise KeyError(f"Key '{key}' not found in config")

    if not isinstance(sub_node, (DictConfig, ListConfig)):
        return sub_node

    from .resolvers import frozen_resolvers

    sub_raw = OmegaConf.to_container(sub_node, resolve=False, throw_on_missing=False)
    # A detached working copy of the whole root. External refs are resolved
    # against it by OmegaConf; the sub-tree stays attached for context. Stub
    # every resolver so ${name:args} calls freeze to call strings instead of
    # firing at selection time.
    work = OmegaConf.create(
        OmegaConf.to_container(root_cfg, resolve=False, throw_on_missing=False)
    )
    with frozen_resolvers():
        transformed = _freeze_walk(sub_raw, sub_raw, work)
    return OmegaConf.create(transformed)


def _freeze_walk(value, sub_raw, work):
    if isinstance(value, dict):
        return {k: _freeze_walk(v, sub_raw, work) for k, v in value.items()}
    if isinstance(value, list):
        return [_freeze_walk(v, sub_raw, work) for v in value]
    if isinstance(value, str) and "${" in value:
        whole = _whole_string_interp(value)
        if whole is not None:
            return _freeze_whole_string(whole, sub_raw, work, fallback_str=value)
        return _freeze_embedded(value, sub_raw, work)
    return value


# --- string-level scan helpers ------------------------------------------------


def _whole_string_interp(s: str) -> "str | None":
    """If ``s`` is exactly ``${...}`` (one balanced block, nothing else), return
    the inner expression. Otherwise return None."""
    if not s.startswith("${"):
        return None
    found = _find_balanced_interp(s, 0)
    if found is None:
        return None
    start, end = found
    if start == 0 and end == len(s):
        return s[2:-1]
    return None


def _find_balanced_interp(s: str, start: int) -> "tuple[int, int] | None":
    """Find the next ``${...}`` block in ``s`` starting at ``start``. Returns
    ``(open_idx, close_idx_exclusive)`` or ``None``. Handles nested ``${...}``."""
    i = s.find("${", start)
    if i == -1:
        return None
    depth = 0
    j = i
    while j < len(s):
        if s[j : j + 2] == "${":
            depth += 1
            j += 2
        elif s[j] == "}":
            depth -= 1
            j += 1
            if depth == 0:
                return (i, j)
        else:
            j += 1
    return None


def _find_top_level_colon(inner: str) -> "int | None":
    """In the content between ``${`` and ``}``, find the first ``:`` not nested
    inside a ``${...}`` block. Returns the index, or ``None`` if no colon."""
    depth = 0
    for i, ch in enumerate(inner):
        if inner[i : i + 2] == "${":
            depth += 1
        elif ch == "}" and depth > 0:
            depth -= 1
        elif ch == ":" and depth == 0:
            return i
    return None


def _path_exists(d, dotted: str) -> bool:
    cur = d
    for p in dotted.split("."):
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        else:
            return False
    return True


def _get_raw(d, dotted: str):
    cur = d
    for p in dotted.split("."):
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        else:
            return None
    return cur


# --- freezing --------------------------------------------------------------


def _resolve_external(ref: str, work):
    """Resolve a simple ref against the root via OmegaConf.

    OmegaConf follows the full chain (multi-hop, mixed strings, nested
    resolver-arg refs). Under the freeze stubs, a target that is itself a
    resolver call comes back as a frozen call string. Returns ``_UNRESOLVED``
    when the ref is absent from the root.
    """
    val = OmegaConf.select(work, ref, throw_on_missing=False, default=_UNRESOLVED)
    if isinstance(val, (DictConfig, ListConfig)):
        return OmegaConf.to_container(val, resolve=False)
    return val


def _is_internal(ref: str, sub_raw) -> bool:
    """A simple ref is *internal* (preserve verbatim) when it resolves within
    the sub-tree and isn't self-shadowing (its own value isn't ``${ref}``)."""
    if not _path_exists(sub_raw, ref):
        return False
    sub_val = _get_raw(sub_raw, ref)
    return not (isinstance(sub_val, str) and f"${{{ref}}}" in sub_val)


def _unresolved_error(ref: str):
    from .exceptions import UnresolvedInterpolationError

    first = ref.split(".")[0]
    raise UnresolvedInterpolationError(
        f"Interpolation ${{{ref}}} could not be resolved: '{first}' not "
        f"found in the sub-tree or root config. Set it via overrides= or "
        f"OmegaConf.update(proj.defaults, '{first}', ...)."
    )


def _freeze_whole_string(inner: str, sub_raw, work, fallback_str: str):
    """Freeze a whole-string interpolation ``${inner}``. Preserves the target's
    native type for simple external refs (e.g. ``${batch_size}`` → int)."""
    if _find_top_level_colon(inner) is not None:
        # Resolver call — preserve as a frozen call string.
        return "${" + _freeze_resolver_args(inner, sub_raw, work) + "}"
    if inner.startswith("."):
        return fallback_str  # relative ref — resolved later at access site
    if _is_internal(inner, sub_raw):
        return fallback_str  # intra-sub-tree ref — resolves after detachment
    val = _resolve_external(inner, work)
    if val is _UNRESOLVED:
        _unresolved_error(inner)
    return val


def _freeze_embedded(s: str, sub_raw, work) -> str:
    """Freeze every ``${...}`` block embedded in a larger string."""
    out = []
    pos = 0
    while pos < len(s):
        found = _find_balanced_interp(s, pos)
        if found is None:
            out.append(s[pos:])
            break
        start, end = found
        out.append(s[pos:start])
        inner = s[start + 2 : end - 1]
        out.append(_freeze_one_block(inner, sub_raw, work))
        pos = end
    return "".join(out)


def _freeze_one_block(inner: str, sub_raw, work) -> str:
    """Freeze one ``${inner}`` block, returning the ``${...}`` text to embed."""
    if _find_top_level_colon(inner) is not None:
        return "${" + _freeze_resolver_args(inner, sub_raw, work) + "}"
    if inner.startswith("."):
        return "${" + inner + "}"  # relative ref — preserved
    if _is_internal(inner, sub_raw):
        return "${" + inner + "}"  # intra-sub-tree ref — preserved
    val = _resolve_external(inner, work)
    if val is _UNRESOLVED:
        _unresolved_error(inner)
    return str(val) if val is not None else "null"


def _freeze_resolver_args(inner: str, sub_raw, work) -> str:
    """Freeze the ``name:args`` body of a resolver call — the call is preserved,
    nested simple refs in the args are frozen."""
    colon = _find_top_level_colon(inner)
    name = inner[:colon]
    args = inner[colon + 1 :]
    return name + ":" + _freeze_embedded(args, sub_raw, work)
