"""Partial-freeze of OmegaConf interpolations when detaching a sub-node.

``select_and_freeze_root_refs`` selects a sub-node out of a root config and
makes it *self-contained* — pickle-able, mergeable, and safe to hand to a
worker — by resolving the references that point *outside* the sub-tree while
preserving the ones that must stay live.

OmegaConf resolves interpolations lazily against the config's root at access
time, so a detached node loses every ``${...}`` that pointed to the root. But
plain ``to_container(resolve=True)`` is too blunt: it would also fire resolver
calls (``${vinc:}``, ``${latest:}``, ``${run_lock:}``) that must run *later*,
on the worker, at submit time. There is no OmegaConf primitive for "resolve
these interpolations but not those", so this module implements a selective
freeze over the ``${...}`` grammar:

- **Simple refs outside the sub-tree** (``${root_anchor}``, ``${a.b}``) are
  resolved against the root and baked to concrete values, following multi-hop
  chains (including through mixed strings like ``${pipeline_dir}/split``).
- **Resolver calls** (``${name:args}``) are preserved; their argument lists are
  processed so nested simple refs inside them still freeze.
- **Relative refs** (``${.foo}``) and **refs inside the sub-tree** are preserved
  verbatim.

The only public entry point is :func:`select_and_freeze_root_refs`; everything
else is a private helper for the string-level scan.
"""

from omegaconf import OmegaConf, DictConfig, ListConfig


def select_and_freeze_root_refs(root_cfg: DictConfig, key: str | None) -> DictConfig:
    """Select a sub-node from `root_cfg` and freeze its root-scope references.

    The returned config is self-contained: it can be pickled, round-tripped
    through ``OmegaConf.to_container``/``OmegaConf.create``, and merged with
    other configs without losing context.

    Three kinds of interpolations are handled distinctly:

    - **Simple refs to keys outside the sub-tree** (e.g. ``${root_anchor}``)
      are resolved against ``root_cfg`` and substituted as concrete values.
      If the target value is itself an interpolation (e.g. another
      ``${...}`` string), the unresolved string is substituted verbatim so
      resolvers like ``${vinc:}`` still fire at submit time.
    - **Resolver calls** (``${name:args}``) are preserved unchanged. Their
      argument lists are recursively processed so nested simple refs inside
      them are still frozen.
    - **Refs to keys inside the sub-tree** are preserved unchanged.

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

    sub_raw = OmegaConf.to_container(sub_node, resolve=False, throw_on_missing=False)
    root_raw = OmegaConf.to_container(root_cfg, resolve=False, throw_on_missing=False)

    transformed = _freeze_walk(sub_raw, sub_raw, root_raw)
    return OmegaConf.create(transformed)


def _freeze_walk(value, sub_raw, root_raw):
    if isinstance(value, dict):
        return {k: _freeze_walk(v, sub_raw, root_raw) for k, v in value.items()}
    if isinstance(value, list):
        return [_freeze_walk(v, sub_raw, root_raw) for v in value]
    if isinstance(value, str) and "${" in value:
        whole = _whole_string_interp(value)
        if whole is not None and _find_top_level_colon(whole) is None:
            # OmegaConf relative refs (.foo, ..foo, ...foo) navigate from the
            # interpolation site and can't be statically frozen — pass through.
            if whole.startswith("."):
                return value
            return _freeze_simple_ref(whole, sub_raw, root_raw, fallback_str=value)
        return _process_interps_in_string(value, sub_raw, root_raw)
    return value


def _whole_string_interp(s: str) -> str | None:
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


def _find_balanced_interp(s: str, start: int) -> tuple[int, int] | None:
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


def _find_top_level_colon(inner: str) -> int | None:
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


def _resolve_in_root(ref: str, root_raw: dict, _visited: frozenset = frozenset()):
    """Follow a chain of simple refs in root_raw to a concrete value.

    Stops at resolver calls (``${name:args}``), relative refs, or concrete
    values, so that resolver calls are preserved for runtime resolution while
    simple-ref chains (e.g. ``pipeline_dir = ${save_dir}``) are fully expanded.
    Returns ``None`` if ``ref`` is not found in ``root_raw``.
    """
    if ref in _visited or not _path_exists(root_raw, ref):
        return None
    val = _get_raw(root_raw, ref)
    if not isinstance(val, str) or "${" not in val:
        return val  # Concrete value
    whole = _whole_string_interp(val)
    if whole is None:
        # Mixed string (embedded interps), e.g. split.save_dir =
        # "${pipeline_dir}/split". The embedded refs are themselves root-scoped,
        # so freeze them too — otherwise a multi-hop chain like
        # prepare.listing_path = "${split.save_dir}/train.txt" leaves a dangling
        # ${pipeline_dir} in the detached sub-config (InterpolationKeyError).
        return _freeze_embedded_in_root(val, root_raw, _visited | {ref})
    if _find_top_level_colon(whole) is not None or whole.startswith("."):
        return val  # Resolver call or relative ref — preserve as-is
    return _resolve_in_root(whole, root_raw, _visited | {ref})


def _freeze_embedded_in_root(s: str, root_raw: dict, _visited: frozenset) -> str:
    """Freeze embedded ``${...}`` refs of a root-sourced mixed string.

    Mirrors :func:`_process_one_interp` but with root-only scope (no sub-tree):
    used when a simple root ref resolves to another mixed string, so multi-hop
    chains collapse to concrete values. Resolver calls (``${name:args}``) and
    relative refs (``${.foo}``) are preserved; refs absent from root are left
    verbatim (they fail later at resolve time, as before).
    """
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
        colon = _find_top_level_colon(inner)
        if colon is not None:
            name = inner[:colon]
            args = _freeze_embedded_in_root(inner[colon + 1 :], root_raw, _visited)
            out.append("${" + name + ":" + args + "}")
        elif inner.startswith("."):
            out.append("${" + inner + "}")
        else:
            resolved = _resolve_in_root(inner, root_raw, _visited)
            if resolved is None:
                out.append("${" + inner + "}")  # not in root — preserve verbatim
            else:
                out.append(str(resolved))
        pos = end
    return "".join(out)


def _freeze_simple_ref(ref: str, sub_raw, root_raw, fallback_str: str):
    """Process a simple ref (``${name}`` or ``${a.b}``). Used for whole-string
    interpolations where we want to preserve the target's native type."""
    if _path_exists(sub_raw, ref):
        sub_val = _get_raw(sub_raw, ref)
        if not (isinstance(sub_val, str) and f"${{{ref}}}" in sub_val):
            return fallback_str
    if not _path_exists(root_raw, ref):
        from .exceptions import UnresolvedInterpolationError

        first = ref.split(".")[0]
        raise UnresolvedInterpolationError(
            f"Interpolation ${{{ref}}} could not be resolved: '{first}' not "
            f"found in the sub-tree or root config. Set it via overrides= or "
            f"OmegaConf.update(proj.defaults, '{first}', ...)."
        )
    return _resolve_in_root(ref, root_raw)


def _process_interps_in_string(s: str, sub_raw, root_raw) -> str:
    """Process all ``${...}`` blocks in a string. Used for embedded
    interpolations (mixed literal + interp) and resolver-call arguments."""
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
        out.append(_process_one_interp(inner, sub_raw, root_raw))
        pos = end
    return "".join(out)


def _process_one_interp(inner: str, sub_raw, root_raw) -> str:
    """Process the content inside a single ``${...}``. Returns the
    (possibly modified) ``${...}`` form as a string suitable for embedding
    back into the source string."""
    colon_idx = _find_top_level_colon(inner)
    if colon_idx is not None:
        # Resolver call — recurse into args, preserve outer call
        resolver_name = inner[:colon_idx]
        args = inner[colon_idx + 1 :]
        processed_args = _process_interps_in_string(args, sub_raw, root_raw)
        return "${" + resolver_name + ":" + processed_args + "}"

    # Relative refs (.foo, ..foo) — resolved by OmegaConf at access time.
    if inner.startswith("."):
        return "${" + inner + "}"

    # Simple ref
    ref = inner
    if _path_exists(sub_raw, ref):
        sub_val = _get_raw(sub_raw, ref)
        if not (isinstance(sub_val, str) and f"${{{ref}}}" in sub_val):
            return "${" + ref + "}"
    if not _path_exists(root_raw, ref):
        from .exceptions import UnresolvedInterpolationError

        first = ref.split(".")[0]
        raise UnresolvedInterpolationError(
            f"Interpolation ${{{ref}}} could not be resolved: '{first}' not "
            f"found in the sub-tree or root config. Set it via overrides= or "
            f"OmegaConf.update(proj.defaults, '{first}', ...)."
        )
    val = _resolve_in_root(ref, root_raw)
    if isinstance(val, str):
        return val
    return str(val) if val is not None else "null"
