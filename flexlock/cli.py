"""Unified FlexLock CLI: ls, tag, gc subcommands."""

import argparse
import json
import sys
import yaml
from datetime import datetime
from pathlib import Path
from git.repo import Repo as GitRepo

from .git_utils import sanitize_ref_name


def find_git_repo(start_path="."):
    """Find the git repository from the given path, falling back to CWD."""
    try:
        return GitRepo(start_path, search_parent_directories=True)
    except Exception:
        pass
    # Run dirs are often outside the project git tree (different mount, symlink, etc.)
    # Fall back to searching from CWD so commands work from the project root.
    if str(Path(start_path).resolve()) != str(Path(".").resolve()):
        try:
            return GitRepo(".", search_parent_directories=True)
        except Exception:
            pass
    return None


def find_results_dirs(root="."):
    """Find all directories containing run.lock files."""
    results = []
    for lock_file in Path(root).rglob("run.lock"):
        run_dir = lock_file.parent
        try:
            with open(lock_file) as f:
                data = yaml.safe_load(f)
            results.append({
                "path": str(run_dir),
                "timestamp": data.get("timestamp", ""),
                "config": data.get("config", {}),
                "repos": data.get("repos", {}),
                "lineage": data.get("lineage") or data.get("prevs", {}),
            })
        except Exception:
            results.append({
                "path": str(run_dir),
                "timestamp": "",
                "config": {},
                "repos": {},
                "lineage": {},
            })
    # Sort by timestamp descending
    results.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return results


def get_flexlock_tags(repo):
    """Get all flexlock tags from git refs."""
    tags = {}
    prefix = "refs/flexlock/tags/"
    try:
        refs = repo.git.for_each_ref(
            "--format=%(refname) %(objectname)",
            prefix,
        )
        for line in refs.strip().splitlines():
            if not line.strip():
                continue
            parts = line.split()
            ref = parts[0]
            commit = parts[1]
            tag_name = ref[len(prefix):]
            tags[tag_name] = commit
    except Exception:
        pass
    return tags


def get_tag_details(repo, tag_commit_hash):
    """Get details about a tag commit, including linked lineage shadow commits."""
    details = {"parents": [], "message": "", "timestamp": ""}
    try:
        # Get commit message
        details["message"] = repo.git.log(
            "-1", "--format=%B", tag_commit_hash
        ).strip()
        # Get timestamp
        details["timestamp"] = repo.git.log(
            "-1", "--format=%aI", tag_commit_hash
        ).strip()
        # Get parent commits (lineage shadow commits)
        parent_line = repo.git.log(
            "-1", "--format=%P", tag_commit_hash
        ).strip()
        if parent_line:
            details["parents"] = parent_line.split()
    except Exception:
        pass
    return details


def get_shadow_ref_for_path(repo, run_path):
    """Find the shadow commit ref matching a run path."""
    prefix = "refs/flexlock/runs/"
    try:
        refs = repo.git.for_each_ref(
            "--format=%(refname) %(objectname)",
            prefix,
        )
        sanitized = sanitize_ref_name(str(run_path))
        for line in refs.strip().splitlines():
            if not line.strip():
                continue
            ref = line.split()[0]
            ref_suffix = ref[len(prefix):]
            # Match if ref contains the run path
            if sanitized in ref_suffix or ref_suffix in sanitized:
                return line.split()[1]
    except Exception:
        pass
    return None


def collect_lineage_refs(repo, run_dir):
    """Collect shadow commit hashes for a run and all its lineage."""
    refs = []

    # Get shadow ref for this run
    shadow = get_shadow_ref_for_path(repo, run_dir)
    if shadow:
        refs.append(shadow)

    # Load run.lock to find lineage
    lock_file = Path(run_dir) / "run.lock"
    if lock_file.exists():
        try:
            with open(lock_file) as f:
                data = yaml.safe_load(f)

            # Get shadow refs from repos recorded in run.lock
            repos_data = data.get("repos", {})
            for repo_info in repos_data.values():
                commit = repo_info.get("commit")
                if commit and commit not in refs:
                    refs.append(commit)

            # Recurse into lineage
            lineage = data.get("lineage") or data.get("prevs", {})
            for nested_data in lineage.values():
                nested_path = nested_data.get("path") or nested_data.get("config", {}).get("save_dir")
                if nested_path:
                    nested_refs = collect_lineage_refs(repo, nested_path)
                    for r in nested_refs:
                        if r not in refs:
                            refs.append(r)
        except Exception:
            pass

    return refs


# ── ls subcommand ──────────────────────────────────────────────

def cmd_ls(args):
    """List runs in results directories."""
    search_root = args.path or "."
    runs = find_results_dirs(search_root)

    if not runs:
        print(f"No runs found under {search_root}")
        return

    # Get tags for annotation
    repo = find_git_repo(search_root)
    tags = {}
    tag_to_path = {}
    if repo:
        all_tags = get_flexlock_tags(repo)
        # Build reverse mapping: try to match tags to run paths
        for tag_name, tag_commit in all_tags.items():
            details = get_tag_details(repo, tag_commit)
            # Parse tag message for path info
            for line in details["message"].splitlines():
                if line.startswith("Path: "):
                    tagged_path = line[6:].strip()
                    tags[tagged_path] = tag_name
                    tag_to_path[tag_name] = tagged_path

    # Display
    if args.format == "json":
        print(json.dumps(runs, indent=2, default=str))
        return

    for i, run in enumerate(runs):
        path = run["path"]
        ts = run["timestamp"]
        tag_label = ""
        if path in tags:
            tag_label = f"  [{tags[path]}]"

        # Format timestamp nicely
        try:
            dt = datetime.fromisoformat(ts)
            ts_fmt = dt.strftime("%Y-%m-%d %H:%M")
        except (ValueError, TypeError):
            ts_fmt = ts[:16] if ts else "unknown"

        # Stage name from path
        stage = Path(path).name

        print(f"  {ts_fmt}  {stage:20s}  {path}{tag_label}")

        if args.verbose:
            cfg = run.get("config", {})
            if "_target_" in cfg:
                print(f"             target: {cfg['_target_']}")
            lineage = run.get("lineage", {})
            if lineage:
                print(f"             lineage: {', '.join(lineage.keys())}")


# ── tag subcommand ─────────────────────────────────────────────

def cmd_tag(args):
    """Tag a run directory with a human-readable name."""
    if args.list:
        _tag_list(args)
        return

    if args.delete:
        _tag_delete(args)
        return

    if not args.name or not args.path:
        print("Usage: flexlock tag <name> <path>", file=sys.stderr)
        sys.exit(1)

    run_dir = Path(args.path).resolve()
    lock_file = run_dir / "run.lock"
    if not lock_file.exists():
        print(f"Error: No run.lock found at {run_dir}", file=sys.stderr)
        sys.exit(1)

    repo = find_git_repo(str(run_dir))
    if not repo:
        print("Error: Not in a git repository", file=sys.stderr)
        sys.exit(1)

    tag_name = sanitize_ref_name(args.name)
    ref = f"refs/flexlock/tags/{tag_name}"

    # Collect all lineage shadow commits to link as parents
    lineage_refs = collect_lineage_refs(repo, str(run_dir))

    # Build parent args for commit-tree
    parent_args = []
    for parent_hash in lineage_refs:
        parent_args.extend(["-p", parent_hash])

    # If no lineage refs found, use HEAD as parent to keep the commit reachable
    if not parent_args:
        parent_args = ["-p", repo.head.commit.hexsha]

    # Create tag commit with metadata in message
    msg = (
        f"FlexLock Tag: {args.name}\n"
        f"Path: {run_dir}\n"
        f"Tagged: {datetime.now().isoformat()}\n"
    )
    if args.message:
        msg += f"\n{args.message}\n"

    # Use the tree from the first parent (or HEAD)
    tree_source = lineage_refs[0] if lineage_refs else repo.head.commit.hexsha
    try:
        tree_hash = repo.git.rev_parse(f"{tree_source}^{{tree}}")
    except Exception:
        tree_hash = repo.head.commit.tree.hexsha

    tag_commit = repo.git.commit_tree(tree_hash, *parent_args, "-m", msg)
    repo.git.update_ref(ref, tag_commit)

    n_parents = len(lineage_refs)
    print(f"Tagged '{args.name}' -> {run_dir}")
    print(f"  ref: {ref}")
    print(f"  linked {n_parents} lineage commit(s)")


def _tag_list(args):
    """List all flexlock tags."""
    repo = find_git_repo(".")
    if not repo:
        print("Error: Not in a git repository", file=sys.stderr)
        sys.exit(1)

    tags = get_flexlock_tags(repo)
    if not tags:
        print("No tags found.")
        return

    for tag_name, tag_commit in sorted(tags.items()):
        details = get_tag_details(repo, tag_commit)
        ts = details["timestamp"]
        try:
            dt = datetime.fromisoformat(ts)
            ts_fmt = dt.strftime("%Y-%m-%d %H:%M")
        except (ValueError, TypeError):
            ts_fmt = "unknown"

        path_str = ""
        for line in details["message"].splitlines():
            if line.startswith("Path: "):
                path_str = line[6:].strip()

        n_parents = len(details["parents"])
        print(f"  {tag_name:20s}  {ts_fmt}  ({n_parents} commits)  {path_str}")

        if args.verbose:
            for parent in details["parents"]:
                try:
                    parent_msg = repo.git.log("-1", "--format=%s", parent).strip()
                    print(f"      {parent[:10]}  {parent_msg}")
                except Exception:
                    print(f"      {parent[:10]}")


def _tag_delete(args):
    """Delete a flexlock tag."""
    repo = find_git_repo(".")
    if not repo:
        print("Error: Not in a git repository", file=sys.stderr)
        sys.exit(1)

    tag_name = sanitize_ref_name(args.delete)
    ref = f"refs/flexlock/tags/{tag_name}"

    try:
        repo.git.update_ref("-d", ref)
        print(f"Deleted tag '{args.delete}'")
    except Exception as e:
        print(f"Error: Could not delete tag '{args.delete}': {e}", file=sys.stderr)
        sys.exit(1)


# ── gc subcommand ──────────────────────────────────────────────

def cmd_gc(args):
    """Garbage collect untagged run directories and orphaned shadow refs."""
    search_root = args.path or "."
    runs = find_results_dirs(search_root)

    if not runs:
        print(f"No runs found under {search_root}")
        return

    # --incomplete: prune only run dirs that have run.lock but no run.complete.
    # These are previous attempts interrupted before the user function returned;
    # no tag protection logic is needed (they were never completed).
    if getattr(args, "incomplete", False):
        incomplete = [
            r for r in runs
            if not (Path(r["path"]) / "run.complete").exists()
        ]
        if not incomplete:
            print("No incomplete runs found.")
            return
        print(f"Found {len(incomplete)} incomplete run(s) (run.lock without run.complete):")
        for run in incomplete:
            print(f"  {run['path']}")
        if args.dry_run:
            print("\n(dry run — no files deleted)")
            return
        if not args.force:
            answer = input(f"\nDelete {len(incomplete)} incomplete run directories? [y/N] ")
            if answer.lower() not in ("y", "yes"):
                print("Aborted.")
                return
        import shutil
        deleted = 0
        for run in incomplete:
            try:
                shutil.rmtree(run["path"])
                deleted += 1
            except Exception as e:
                print(f"  Error deleting {run['path']}: {e}", file=sys.stderr)
        print(f"Deleted {deleted} incomplete run directories.")
        return

    repo = find_git_repo(search_root)

    # Collect tagged paths
    tagged_paths = set()
    if repo:
        all_tags = get_flexlock_tags(repo)
        for tag_name, tag_commit in all_tags.items():
            details = get_tag_details(repo, tag_commit)
            for line in details["message"].splitlines():
                if line.startswith("Path: "):
                    tagged_paths.add(line[6:].strip())

    # Also collect paths that are lineage dependencies of tagged runs
    protected_paths = set(tagged_paths)
    for tagged_path in tagged_paths:
        _collect_lineage_paths(tagged_path, protected_paths)

    # Identify unprotected runs
    to_remove = []
    to_keep = []
    for run in runs:
        resolved = str(Path(run["path"]).resolve())
        if resolved in protected_paths or run["path"] in protected_paths:
            to_keep.append(run)
        else:
            to_remove.append(run)

    if not to_remove:
        print("Nothing to clean up — all runs are tagged or are lineage dependencies.")
        return

    print(f"Found {len(to_remove)} untagged run(s) to remove:")
    for run in to_remove:
        ts = run.get("timestamp", "unknown")
        try:
            dt = datetime.fromisoformat(ts)
            ts_fmt = dt.strftime("%Y-%m-%d %H:%M")
        except (ValueError, TypeError):
            ts_fmt = ts[:16] if ts else "unknown"
        print(f"  {ts_fmt}  {run['path']}")

    print(f"\nKeeping {len(to_keep)} tagged/protected run(s).")

    if args.dry_run:
        print("\n(dry run — no files deleted)")
        return

    # Confirm
    if not args.force:
        answer = input(f"\nDelete {len(to_remove)} run directories? [y/N] ")
        if answer.lower() not in ("y", "yes"):
            print("Aborted.")
            return

    # Delete
    import shutil
    deleted = 0
    for run in to_remove:
        try:
            shutil.rmtree(run["path"])
            deleted += 1
        except Exception as e:
            print(f"  Error deleting {run['path']}: {e}", file=sys.stderr)

    print(f"Deleted {deleted} run directories.")

    # Clean orphaned shadow refs
    if repo and args.refs:
        _gc_shadow_refs(repo, protected_paths)


def _collect_lineage_paths(run_path, protected):
    """Recursively collect all lineage paths as protected."""
    lock_file = Path(run_path) / "run.lock"
    if not lock_file.exists():
        return

    try:
        with open(lock_file) as f:
            data = yaml.safe_load(f)
        lineage = data.get("lineage") or data.get("prevs", {})
        for nested_data in lineage.values():
            nested_path = nested_data.get("path") or nested_data.get("config", {}).get("save_dir")
            if nested_path:
                resolved = str(Path(nested_path).resolve())
                if resolved not in protected:
                    protected.add(resolved)
                    protected.add(nested_path)
                    _collect_lineage_paths(nested_path, protected)
    except Exception:
        pass


def _gc_shadow_refs(repo, protected_paths):
    """Remove shadow refs that don't belong to any tagged run."""
    prefix = "refs/flexlock/runs/"
    try:
        refs = repo.git.for_each_ref(
            "--format=%(refname)",
            prefix,
        )
    except Exception:
        return

    # Collect shadow refs that are parents of tag commits
    protected_commits = set()
    all_tags = get_flexlock_tags(repo)
    for tag_commit in all_tags.values():
        details = get_tag_details(repo, tag_commit)
        protected_commits.update(details["parents"])

    removed = 0
    for ref in refs.strip().splitlines():
        if not ref.strip():
            continue
        try:
            commit = repo.git.rev_parse(ref.strip())
            if commit not in protected_commits:
                repo.git.update_ref("-d", ref.strip())
                removed += 1
        except Exception:
            pass

    if removed:
        print(f"Cleaned {removed} orphaned shadow ref(s).")


# ── Main entry point ───────────────────────────────────────────

def cmd_migrate_cache_markers(args):
    """Backfill run.complete for pre-existing dirs that look complete.

    The old heuristic (lock + any non-lock file present) is applied once
    to existing run dirs so they remain cache-hits after the upgrade to
    explicit completion markers.
    """
    from .snapshot import write_complete_marker

    search_root = args.path or "."
    runs = find_results_dirs(search_root)
    if not runs:
        print(f"No runs found under {search_root}")
        return

    candidates = []
    for run in runs:
        p = Path(run["path"])
        if (p / "run.complete").exists():
            continue
        has_output = False
        for f in p.iterdir():
            if f.name in ("run.lock", "run.complete"):
                continue
            if f.name.startswith("."):
                continue
            has_output = True
            break
        if has_output:
            candidates.append(p)

    if not candidates:
        print("No runs to migrate — every complete-looking dir already has run.complete.")
        return

    print(f"Will backfill run.complete in {len(candidates)} dir(s):")
    for p in candidates:
        print(f"  {p}")

    if args.dry_run:
        print("\n(dry run — no markers written)")
        return

    if not args.force:
        answer = input(f"\nWrite run.complete in {len(candidates)} dirs? [y/N] ")
        if answer.lower() not in ("y", "yes"):
            print("Aborted.")
            return

    written = 0
    for p in candidates:
        try:
            write_complete_marker(p)
            written += 1
        except Exception as e:
            print(f"  Error writing marker for {p}: {e}", file=sys.stderr)
    print(f"Wrote {written} markers.")


def cmd_reindex(args):
    """Rebuild the project-wide fingerprint index from run.lock files."""
    from . import index

    root = Path(args.path) if args.path else Path(".")
    n = index.reindex(root)
    print(f"Reindexed {n} run(s) under {root}")


# ── show subcommand ────────────────────────────────────────────

def cmd_show(args):
    """Show a single run's status, metadata, lineage, and config."""
    from . import query

    run_dir = Path(args.run_dir)
    if not run_dir.exists():
        print(f"Error: no such directory: {run_dir}", file=sys.stderr)
        sys.exit(1)

    summary = query.load_run_summary(
        run_dir,
        scan_root=args.root,
        downstream=not args.no_downstream,
    )

    if args.format == "json":
        print(json.dumps(summary, indent=2, default=str))
    else:
        print(query.format_summary_md(summary))


# ── graph subcommand ───────────────────────────────────────────

def cmd_graph(args):
    """Emit the experiment DAG as JSON, Mermaid, or DOT."""
    from . import query

    root = Path(args.path or ".")
    graph = query.build_graph(root, include_groups=args.groups)

    if args.format == "mermaid":
        print(query.graph_to_mermaid(graph))
    elif args.format == "dot":
        print(query.graph_to_dot(graph))
    else:
        print(json.dumps(graph, indent=2, default=str))


# ── why subcommand ─────────────────────────────────────────────

def cmd_why(args):
    """Explain the difference between two runs (config/git/data + commits)."""
    from . import query

    for p in (args.run_a, args.run_b):
        if not Path(p).exists():
            print(f"Error: no such directory: {p}", file=sys.stderr)
            sys.exit(1)

    result = query.why(args.run_a, args.run_b)
    if args.format == "json":
        print(json.dumps(result, indent=2, default=str))
    else:
        print(query.format_why_text(result))


# ── stages subcommand ──────────────────────────────────────────

def _load_defaults_cfg(defaults, config_path=None):
    """Load a defaults tree (+ optional -c YAML merge) as a DictConfig.

    Shared loader used by ``stages``; kept decoupled from argparse so callers
    can pass plain strings.
    """
    from omegaconf import OmegaConf
    from .utils import load_python_defaults

    loaded = load_python_defaults(defaults)
    cfg = loaded if OmegaConf.is_config(loaded) else OmegaConf.create(loaded)
    if config_path:
        cfg.merge_with(OmegaConf.load(config_path))
    return cfg


def cmd_stages(args):
    """List runnable stages (mappings with _target_) in a defaults tree."""
    from . import query

    if not args.defaults:
        print("Error: -d/--defaults is required", file=sys.stderr)
        sys.exit(1)

    cfg = _load_defaults_cfg(args.defaults, args.config)
    stages = query.list_stage_nodes(cfg)

    if args.format == "json":
        print(json.dumps(stages, indent=2, default=str))
    elif args.format == "keys":
        for s in stages:
            print(s["key"])
    else:
        if not stages:
            print("No stages (mappings with _target_) found.")
            return
        for s in stages:
            indent = "  " * max(s["depth"] - 1, 0)
            save = f"  → {s['save_dir']}" if s.get("save_dir") else ""
            print(f"{indent}{s['key']:30s} {s['target']}{save}")


def main():
    parser = argparse.ArgumentParser(
        prog="flexlock",
        description="FlexLock experiment management CLI",
    )
    subparsers = parser.add_subparsers(dest="command")

    # ls
    ls_parser = subparsers.add_parser("ls", help="List runs in results directories")
    ls_parser.add_argument("path", nargs="?", help="Root directory to search (default: .)")
    ls_parser.add_argument("-v", "--verbose", action="store_true", help="Show extra details")
    ls_parser.add_argument("--format", choices=["table", "json"], default="table")
    ls_parser.set_defaults(func=cmd_ls)

    # tag
    tag_parser = subparsers.add_parser("tag", help="Tag a run with a human-readable name")
    tag_parser.add_argument("name", nargs="?", help="Tag name")
    tag_parser.add_argument("path", nargs="?", help="Path to run directory")
    tag_parser.add_argument("-m", "--message", help="Optional tag message")
    tag_parser.add_argument("-l", "--list", action="store_true", help="List all tags")
    tag_parser.add_argument("-d", "--delete", metavar="TAG", help="Delete a tag")
    tag_parser.add_argument("-v", "--verbose", action="store_true", help="Show tag details")
    tag_parser.set_defaults(func=cmd_tag)

    # gc
    gc_parser = subparsers.add_parser("gc", help="Clean up untagged runs")
    gc_parser.add_argument("path", nargs="?", help="Root directory to search (default: .)")
    gc_parser.add_argument("-n", "--dry-run", action="store_true", help="Show what would be deleted")
    gc_parser.add_argument("-f", "--force", action="store_true", help="Skip confirmation")
    gc_parser.add_argument("--refs", action="store_true", help="Also clean orphaned shadow git refs")
    gc_parser.add_argument(
        "--incomplete",
        action="store_true",
        help="Only delete run dirs with run.lock but no run.complete (interrupted attempts)",
    )
    gc_parser.set_defaults(func=cmd_gc)

    # migrate-cache-markers
    mig_parser = subparsers.add_parser(
        "migrate-cache-markers",
        help="Backfill run.complete for existing complete-looking run dirs",
    )
    mig_parser.add_argument("path", nargs="?", help="Root directory to search (default: .)")
    mig_parser.add_argument("-n", "--dry-run", action="store_true")
    mig_parser.add_argument("-f", "--force", action="store_true", help="Skip confirmation")
    mig_parser.set_defaults(func=cmd_migrate_cache_markers)

    # reindex
    reindex_parser = subparsers.add_parser(
        "reindex",
        help="Rebuild the project-wide fingerprint index from run.lock files",
    )
    reindex_parser.add_argument(
        "path", nargs="?", help="Root directory to walk (default: .)"
    )
    reindex_parser.set_defaults(func=cmd_reindex)

    # show
    show_parser = subparsers.add_parser(
        "show", help="Show a single run's status, metadata, lineage, and config"
    )
    show_parser.add_argument("run_dir", help="Path to the run directory")
    show_parser.add_argument(
        "--format", choices=["md", "json"], default="md",
        help="Output format (default: md; agents use json)",
    )
    show_parser.add_argument(
        "--root", metavar="DIR",
        help="Root to scan for downstream runs and tags (default: run's parent)",
    )
    show_parser.add_argument(
        "--no-downstream", action="store_true",
        help="Skip the downstream lineage scan (faster)",
    )
    show_parser.set_defaults(func=cmd_show)

    # graph
    graph_parser = subparsers.add_parser(
        "graph", help="Emit the experiment DAG (json/mermaid/dot)"
    )
    graph_parser.add_argument("path", nargs="?", help="Results root (default: .)")
    graph_parser.add_argument(
        "--format", choices=["json", "mermaid", "dot"], default="json"
    )
    graph_parser.add_argument(
        "--groups", action="store_true",
        help="Include same-tree / same-data groupings in JSON output",
    )
    graph_parser.set_defaults(func=cmd_graph)

    # why
    why_parser = subparsers.add_parser(
        "why", help="Explain the difference between two runs"
    )
    why_parser.add_argument("run_a", help="First run directory")
    why_parser.add_argument("run_b", help="Second run directory")
    why_parser.add_argument("--format", choices=["text", "json"], default="text")
    why_parser.set_defaults(func=cmd_why)

    # stages
    stages_parser = subparsers.add_parser(
        "stages", help="List runnable stages in a defaults tree"
    )
    stages_parser.add_argument(
        "-d", "--defaults", required=True,
        help="Python import path for the defaults (pkg.mod.var or file.py:var)",
    )
    stages_parser.add_argument(
        "-c", "--config", metavar="FILE", help="Optional YAML to merge into defaults"
    )
    stages_parser.add_argument(
        "--format", choices=["text", "keys", "json"], default="text",
        help="text (default), keys (bare keys for fzf), or json",
    )
    stages_parser.set_defaults(func=cmd_stages)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
