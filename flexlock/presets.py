"""Presets: which named config produced a run, and the runs of a preset.

A *preset* is the address you already give on the command line: the ``-d``
target (a Python attribute holding a config) plus the ``-s`` selection. Nothing
is registered; the address is recorded on the selected node as a reserved
``_preset_`` key when the run is created::

    _preset_:
      defaults: sst_ml_mapping.starter.xps_glob:train_small_cloud_gap_compact
      select: main
      overrides: ["main.lit_module.lr=1e-4"]     # -o, as typed
      overrides_after_select: []                 # -O
      merges: []                                 # -m / -M files

Being a config key (like ``_snapshot_``), it travels unchanged through the
task DB, HPC workers and sweeps. It is never part of the fingerprint
(stripped at any depth), ignored by ``RunDiff``, and removed by
``instantiate``, so it can't change caching or reach user functions.

When a run completes, a symlink is added under the project's ``.flexlock/``::

    .flexlock/presets/<defaults>/<select>/<save_dir relative to project> -> run

These links are the index behind ``flexlock runs``, ``flexlock presets``
and (later) ``${run:...}``. They are derived data: ``flexlock reindex``
rebuilds them from the run records.
"""

import ast
import importlib
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

from loguru import logger
from omegaconf import DictConfig, OmegaConf, open_dict

PRESET_KEY = "_preset_"
PRESETS_DIRNAME = "presets"
ROOT_SELECT = "_root_"  # link dir name when the whole defaults object is the stage


# ── addresses ──


def _repo_relative(path: Path) -> str:
    """``path`` relative to its git work tree, else absolute."""
    path = path.resolve()
    try:
        from git.repo import Repo as GitRepo

        root = Path(
            GitRepo(path.parent, search_parent_directories=True).working_tree_dir
        ).resolve()
        return path.relative_to(root).as_posix()
    except Exception:
        return path.as_posix()


def canonical_defaults(import_path: str) -> str:
    """Canonical form of a ``-d`` / ``Project(defaults=...)`` string.

    - ``pkg.mod.attr`` and ``pkg.mod:attr`` → ``pkg.mod:attr``
    - ``path/file.py:attr`` and ``path/file.py`` (→ ``:defaults``) →
      repo-relative ``path/file.py:attr``
    - ``path/file.yaml`` (``-c``) → repo-relative path
    """
    s = str(import_path)
    is_file_like = ":" not in s and (s.endswith(".py") or Path(s).is_file())
    if is_file_like:
        if s.endswith(".py"):
            return f"{_repo_relative(Path(s))}:defaults"
        return _repo_relative(Path(s))
    if ":" in s:
        left, attr = s.split(":", 1)
        if Path(left).exists():
            return f"{_repo_relative(Path(left))}:{attr}"
        return s
    module, attr = s.rsplit(".", 1)
    return f"{module}:{attr}"


def address_matches(defaults: str, address: str) -> bool:
    """Whether a recorded ``defaults`` matches a user-typed ``address``.

    Suffix matching, so ``xps_glob:train_x`` or ``xps_glob.train_x`` or just
    ``train_x`` all match ``sst_ml_mapping.starter.xps_glob:train_x``.
    """
    a = address
    if ":" not in a and "/" not in a and "." in a:
        a = ":".join(a.rsplit(".", 1))
    if defaults == a:
        return True
    if ":" not in a:
        return defaults.endswith(":" + a)
    return defaults.endswith("." + a) or defaults.endswith("/" + a)


# ── recording ──


def _literal(s: str) -> str:
    """Escape interpolations so an override recorded as typed stays text."""
    return str(s).replace("${", "\\${")


def make_preset(
    defaults: str,
    select: Optional[str] = None,
    overrides: Iterable[str] = (),
    overrides_after_select: Iterable[str] = (),
    merges: Iterable[str] = (),
) -> dict:
    return {
        "defaults": canonical_defaults(defaults),
        "select": select or None,
        "overrides": [_literal(o) for o in overrides],
        "overrides_after_select": [_literal(o) for o in overrides_after_select],
        "merges": [_literal(m) for m in merges if m],
    }


def attach(node_cfg, preset: dict) -> None:
    """Set ``_preset_`` on a runnable node (``_target_`` and ``save_dir``).

    Other nodes (``proj.get("params")``, a model sub-config) are left alone.
    """
    if not isinstance(node_cfg, DictConfig) or not (
        "_target_" in node_cfg and "save_dir" in node_cfg
    ):
        return
    with open_dict(node_cfg):
        node_cfg[PRESET_KEY] = preset


def preset_of(cfg) -> Optional[dict]:
    """The ``_preset_`` of a config (DictConfig or plain dict), or ``None``."""
    if cfg is None:
        return None
    try:
        value = cfg.get(PRESET_KEY)
    except Exception:
        return None
    if value is None:
        return None
    if OmegaConf.is_config(value):
        value = OmegaConf.to_container(value, resolve=False)
    return value if isinstance(value, dict) and value.get("defaults") else None


# ── links ──


def presets_dir_for(base) -> Path:
    """The presets link dir serving ``base`` (next to its fingerprint index)."""
    from .index import resolve_index_path

    return resolve_index_path(Path(base).resolve()).parent / PRESETS_DIRNAME


def presets_dir(save_dir) -> Path:
    """The presets link dir a run in ``save_dir`` is recorded under."""
    return presets_dir_for(Path(save_dir).resolve().parent)


def _select_dirname(select: Optional[str]) -> str:
    return select or ROOT_SELECT


def _link_name(save_dir: Path, pdir: Path) -> str:
    project = pdir.parent.parent  # <project>/.flexlock/presets
    rel = os.path.relpath(save_dir, project)
    if rel.startswith(".."):
        rel = str(save_dir).lstrip(os.sep)
    return rel.replace(os.sep, "__")


def link_run(save_dir, cfg) -> Optional[Path]:
    """Record a completed run under its preset. Never raises."""
    preset = preset_of(cfg)
    if preset is None:
        return None
    try:
        save_dir = Path(save_dir).resolve()
        pdir = presets_dir(save_dir)
        link_dir = pdir / preset["defaults"] / _select_dirname(preset.get("select"))
        link_dir.mkdir(parents=True, exist_ok=True)
        link = link_dir / _link_name(save_dir, pdir)
        tmp = link_dir / f".{link.name}.{os.getpid()}.tmp"
        tmp.unlink(missing_ok=True)
        os.symlink(os.path.relpath(save_dir, link_dir), tmp)
        os.replace(tmp, link)  # atomic; a rerun refreshes the link's mtime
        return link
    except Exception as exc:
        logger.debug(f"Could not link {save_dir} under its preset: {exc}")
        return None


# ── lookup ──


@dataclass
class PresetRun:
    path: Path
    defaults: str
    select: Optional[str]
    completed: float  # link mtime: when the run (last) completed

    def record(self) -> Optional[dict]:
        from .record import load_record

        return load_record(self.path)


def presets_roots(start=None, extra: Iterable = ()) -> List[Path]:
    """Presets dirs to search: explicit ones, the one serving ``start`` (cwd),
    and any ``.flexlock/presets`` up to two levels below ``start``."""
    from .index import INDEX_DIRNAME

    start = Path(start or Path.cwd()).resolve()
    roots = [Path(r).resolve() / INDEX_DIRNAME / PRESETS_DIRNAME for r in extra]
    roots.append(presets_dir_for(start))
    for pattern in (f"*/{INDEX_DIRNAME}", f"*/*/{INDEX_DIRNAME}"):
        roots.extend(p / PRESETS_DIRNAME for p in start.glob(pattern))
    seen, out = set(), []
    for r in roots:
        if r not in seen and r.is_dir():
            seen.add(r)
            out.append(r)
    return out


def _iter_links(pdir: Path):
    """Yield ``(defaults, select, link)`` for every link under ``pdir``."""
    for dirpath, dirnames, filenames in os.walk(pdir):
        # os.walk lists a symlink to a directory under dirnames (without
        # descending into it), a dangling one under filenames.
        links = [
            n for n in dirnames + filenames
            if not n.startswith(".") and os.path.islink(os.path.join(dirpath, n))
        ]
        if not links:
            continue
        select_dir = Path(dirpath)
        defaults = select_dir.parent.relative_to(pdir).as_posix()
        select = None if select_dir.name == ROOT_SELECT else select_dir.name
        for name in links:
            yield defaults, select, select_dir / name


def all_runs(roots: Iterable[Path]) -> List[PresetRun]:
    """Every complete run linked under ``roots``; dangling links are pruned."""
    runs = []
    for pdir in roots:
        for defaults, select, link in _iter_links(pdir):
            target = Path(os.path.realpath(link))
            if not (target / "run.complete").exists():
                if not target.exists():
                    link.unlink(missing_ok=True)
                continue
            runs.append(
                PresetRun(target, defaults, select, os.lstat(link).st_mtime)
            )
    return runs


def find_runs(
    address: str,
    select: Optional[str] = None,
    roots: Optional[Iterable[Path]] = None,
    strict: bool = False,
) -> List[PresetRun]:
    """Complete runs of a preset, newest first.

    Any run of the preset matches, whatever its overrides; ``strict=True``
    keeps only runs made with no ``-o``/``-O``/``-m``/``-M`` at all.
    """
    roots = presets_roots() if roots is None else list(roots)
    out = [
        r for r in all_runs(roots)
        if address_matches(r.defaults, address)
        and (select is None or r.select == select)
    ]
    if strict:
        out = [r for r in out if _is_plain(r)]
    out.sort(key=lambda r: r.completed, reverse=True)
    return out


def _is_plain(run: PresetRun) -> bool:
    record = run.record() or {}
    p = preset_of(record.get("config") or {}) or {}
    return not (p.get("overrides") or p.get("overrides_after_select") or p.get("merges"))


# ── catalogue ──


def _leading_comments(source: str) -> dict:
    """``{name: comment block}`` for top-level assignments in ``source``."""
    lines = source.splitlines()
    out = {}
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return out
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        block = []
        i = node.lineno - 2
        while i >= 0 and lines[i].strip().startswith("#"):
            block.append(lines[i].strip().lstrip("#").strip())
            i -= 1
        text = " ".join(reversed([b for b in block if b and not set(b) <= set("=-")]))
        for target in node.targets:
            if isinstance(target, ast.Name):
                out[target.id] = text
    return out


def _load_module(spec: str):
    """Import a module by dotted name or file path (as ``-d`` would)."""
    if spec.endswith(".py") or Path(spec).is_file():
        from .utils import load_python_defaults

        load_python_defaults(f"{spec}:__name__")  # imports & registers it
        return sys.modules[Path(spec).stem], _repo_relative(Path(spec))
    return importlib.import_module(spec), spec


def list_presets(module_spec: str, roots: Optional[Iterable[Path]] = None) -> list:
    """Config-valued attributes of a module that hold runnable stages.

    A stage is a mapping with ``_target_`` and ``save_dir``, either the
    attribute itself (``-s`` omitted) or one of its direct children
    (``-s <key>``). Deeper nodes (models, callbacks) are building blocks.
    Each entry carries its leading comment block and its run count.
    """
    from .query import list_stage_nodes

    module, prefix = _load_module(module_spec)
    try:
        source = Path(module.__file__).read_text()
    except (OSError, TypeError):
        source = ""
    comments = _leading_comments(source)

    roots = presets_roots() if roots is None else list(roots)
    counts = {}
    for r in all_runs(roots):
        counts[(r.defaults, r.select)] = counts.get((r.defaults, r.select), 0) + 1

    out = []
    for name, value in vars(module).items():
        if name.startswith("_") or not isinstance(value, (dict, DictConfig)):
            continue
        try:
            # py2cfg nodes are DictConfigs inside plain dicts: normalize first.
            container = OmegaConf.to_container(OmegaConf.create(value), resolve=False)
            stages = [
                s for s in list_stage_nodes(container)
                if s["depth"] <= 1 and s.get("save_dir") is not None
            ]
        except Exception:
            continue
        if not stages:
            continue
        defaults = canonical_defaults(f"{prefix}:{name}")
        selects = [s["key"] or None for s in stages]
        out.append({
            "name": name,
            "defaults": defaults,
            "selects": selects,
            "comment": comments.get(name, ""),
            "runs": {
                (sel or ""): n
                for (d, sel), n in counts.items()
                if d == defaults and sel in selects
            },
        })
    return out
