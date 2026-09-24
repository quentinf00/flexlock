"""Diff utilities for FlexLock."""

import os
from typing import Any, Dict, Set
from omegaconf import OmegaConf, DictConfig, ListConfig
from loguru import logger


class RunDiff:
    def __init__(
        self,
        current: dict,
        target: dict,
        ignore_keys: list = None,
        current_save_dir: str = None,
        target_save_dir: str = None,
        match_include: list = None,
        match_exclude: list = None,
    ):
        """
        Initialize RunDiff for comparing two run snapshots.

        Args:
            current: Current/proposed run snapshot
            target: Target/existing run snapshot
            ignore_keys: Additional keys to ignore during comparison
            current_save_dir: Save directory of current run (for normalization)
            target_save_dir: Save directory of target run (for normalization)
            match_include: Override include patterns for git comparison
            match_exclude: Override exclude patterns for git comparison
        """
        self.current = current
        self.target = target

        # Keys that legitimately appear inside the user config and are
        # FlexLock-managed (or explicitly requested) — ignored at *any* depth.
        self.always_ignore = set(ignore_keys or []) | {"save_dir", "_snapshot_"}

        # Keys FlexLock injects at the snapshot top level (run metadata). These
        # are only ignored at the top of the config subtree — a user
        # hyperparameter named e.g. ``time`` or ``system`` nested deeper must
        # NOT be silently ignored (issue 7), which would cause false cache hits.
        self.toplevel_ignore = {
            "timestamp",
            "note",
            "system",
            "job_id",
            "work_dir",
            "cwd",
            "date",
            "time",
            "datetime",
        }

        # Back-compat: some callers/tests read ``ignore_keys``.
        self.ignore_keys = self.always_ignore | self.toplevel_ignore

        # For value normalization (handling interpolation)
        self.c_dir = str(current_save_dir) if current_save_dir else None
        self.t_dir = str(target_save_dir) if target_save_dir else None

        # Override patterns for git comparison (takes priority over snapshot-level patterns)
        self.match_include = match_include
        self.match_exclude = match_exclude

        self.diffs = {}

    def _normalize_val(self, val: Any, root_dir: str) -> Any:
        """
        If the value is a string and contains the save_dir path,
        replace it with a placeholder <SAVE_DIR> to allow comparison.

        Args:
            val: Value to normalize
            root_dir: Root directory path to replace

        Returns:
            Normalized value
        """
        if not (root_dir and isinstance(val, str)):
            return val
        # Prefix-only: replace an exact match or a genuine path prefix, never an
        # arbitrary substring (issue 8). ``outputs/other`` must not be rewritten
        # just because save_dir is ``outputs``.
        if val == root_dir:
            return "<SAVE_DIR>"
        if val.startswith(root_dir + os.sep):
            return "<SAVE_DIR>" + val[len(root_dir):]
        return val

    def compare_git(self):
        """Compare git tree hashes, with optional include/exclude filtering."""
        diff = []
        c_repos = self.current.get("repos", {})
        t_repos = self.target.get("repos", {})

        # Iterate the union so a repo present on only one side is flagged
        # symmetrically (issue 9) instead of being silently ignored.
        for name in set(c_repos) | set(t_repos):
            c_info = c_repos.get(name)
            t_info = t_repos.get(name)
            if not c_info:
                diff.append(f"Repo {name} only in target")
                continue
            if not t_info:
                diff.append(f"Repo {name} missing")
                continue

            # Compare Tree Hashes (Content Identity)
            if c_info.get("tree") != t_info.get("tree"):
                # Trees differ — check if RELEVANT files changed
                # Priority: RunDiff-level override > snapshot-level patterns
                include = (
                    self.match_include or c_info.get("include") or t_info.get("include")
                )
                exclude = (
                    self.match_exclude or c_info.get("exclude") or t_info.get("exclude")
                )

                if include or exclude:
                    repo_path = c_info.get("path") or t_info.get("path")
                    if repo_path and self._trees_match_filtered(
                        repo_path, c_info["tree"], t_info["tree"], include, exclude
                    ):
                        continue  # Relevant files unchanged — match

                diff.append(f"Repo {name}: Content changed")

        if diff:
            self.diffs["git"] = diff
        return len(diff) == 0

    def _trees_match_filtered(
        self, repo_path, tree1, tree2, include=None, exclude=None
    ):
        """
        Check if two trees match when filtered by include/exclude patterns.

        Uses git diff-tree with pathspec filtering to compare only relevant files.
        Returns True if no relevant files differ, False otherwise.
        """
        try:
            from git.repo import Repo as GitRepo

            repo = GitRepo(repo_path, search_parent_directories=True)

            # Build git pathspec: include patterns + :(exclude) patterns
            pathspec = list(include or [])
            if exclude:
                pathspec.extend(f":(exclude){pat}" for pat in exclude)

            args = ["-r", "--name-only", "--no-commit-id", tree1, tree2]
            if pathspec:
                args.append("--")
                args.extend(pathspec)

            output = repo.git.diff_tree(*args).strip()
            return len(output) == 0  # No relevant files changed
        except Exception as e:
            logger.debug(f"Filtered git comparison failed: {e}")
            return False  # Conservative: treat as different

    def compare_config(self):
        """
        Compare configurations with recursive diff, ignoring specified keys
        and normalizing path values.
        """
        c_cfg = self.current.get("config", {})
        t_cfg = self.target.get("config", {})

        def _recursive_diff(d1, d2, path=""):
            """Recursively compare two config structures."""
            diff = []

            # Handle DictConfigs vs Primitives
            if isinstance(d1, (dict, DictConfig)) and isinstance(
                d2, (dict, DictConfig)
            ):
                # Injected run-metadata keys are ignored only at the top of the
                # config subtree; user keys are compared at every depth.
                ignore_here = self.always_ignore
                if path == "":
                    ignore_here = ignore_here | self.toplevel_ignore

                all_keys = set(d1.keys()) | set(d2.keys())
                for k in all_keys:
                    if k in ignore_here:
                        continue

                    new_path = f"{path}.{k}" if path else k

                    if k not in d1:
                        diff.append(f"Missing in current: {new_path}")
                    elif k not in d2:
                        diff.append(f"Extra in current: {new_path}")
                    else:
                        diff.extend(_recursive_diff(d1[k], d2[k], new_path))

            elif isinstance(d1, (list, tuple, ListConfig)) and isinstance(
                d2, (list, tuple, ListConfig)
            ):
                if len(d1) != len(d2):
                    diff.append(f"List length mismatch {path}: {len(d1)} vs {len(d2)}")
                else:
                    for i, (v1, v2) in enumerate(zip(d1, d2)):
                        diff.extend(_recursive_diff(v1, v2, f"{path}[{i}]"))

            else:
                # Value Comparison with Normalization
                logger.debug(
                    f"Comparing values at {path}: {d1} vs {d2} after normalization with dirs {self.c_dir}, {self.t_dir}"
                )

                v1_norm = self._normalize_val(d1, self.c_dir)
                v2_norm = self._normalize_val(d2, self.t_dir)

                if v1_norm != v2_norm:
                    diff.append(f"Value mismatch {path}: {v1_norm} != {v2_norm}")

            return diff

        diff = _recursive_diff(c_cfg, t_cfg)

        if diff:
            self.diffs["config"] = diff

        return len(diff) == 0

    def compare_data(self):
        """Compare data hashes."""
        c_data = self.current.get("data", {})
        t_data = self.target.get("data", {})

        if c_data == t_data:
            return True

        # Name which keys/hashes differ instead of a bare "Data differs" (issue 9).
        detail = []
        for key in sorted(set(c_data) | set(t_data)):
            cv = c_data.get(key)
            tv = t_data.get(key)
            if key not in c_data:
                detail.append(f"{key}: only in target")
            elif key not in t_data:
                detail.append(f"{key}: only in current")
            elif cv != tv:
                detail.append(f"{key}: {cv} != {tv}")
        self.diffs["data"] = detail or ["Data differs"]
        return False

    def compare_env(self):
        """Compare environment lockfile hashes.

        A target without an ``env`` section predates environment hashing; it
        is treated as a match so existing caches keep working (the index
        backfill then records the run under its env-aware fingerprint).
        """
        c_env = self.current.get("env") or {}
        t_env = self.target.get("env")
        if t_env is None or c_env == t_env:
            return True
        detail = []
        for key in sorted(set(c_env) | set(t_env)):
            if key not in c_env:
                detail.append(f"{key}: only in target")
            elif key not in t_env:
                detail.append(f"{key}: only in current")
            elif c_env[key] != t_env[key]:
                detail.append(f"{key}: lockfile changed")
        self.diffs["env"] = detail
        return False

    def is_match(self):
        """Check if the current run matches the target run."""
        return (
            self.compare_git()
            and self.compare_config()
            and self.compare_data()
            and self.compare_env()
        )
