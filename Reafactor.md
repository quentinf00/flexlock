Here is the comprehensive summary of the final design architecture and implementation plan for **FlexLock**.

---

# 1. Architecture Overview

**FlexLock** is a framework for reproducible Python experiments.
*   **Philosophy**: "Python for Structure, YAML for Experiments, Git/Hashing for State."
*   **Workflow**:
    1.  Define schemas/defaults in Python (`py2cfg`).
    2.  Configure via CLI or YAML overrides.
    3.  Execute via `FlexLockRunner` (handles dependency injection).
    4.  Snapshot state using **Shadow Git Commits** (code) and **SQLite Caching** (data).

---

# 2. Part I: Configuration & Execution

### A. The CLI (`flexlock`)
The CLI is the primary entry point for running experiments and sweeps.

**Command Structure:**
```bash
flexlock --defaults pkg.config.defaults --select stage1 [OVERRIDES...]
```

**Arguments:**
*   **Config Source**:
    *   `-d, --defaults`: Python import path (e.g., `pkg.config.defaults`) containing the schema.
    *   `-c, --config`: Path to a base YAML file (overrides defaults).
*   **Selection**:
    *   `-s, --select`: Dot-path to select a specific node (experiment/stage) to run.
*   **Sweeps**:
    *   `--sweep-from`: Key in the *root* config containing a list of task overrides (triggers `ParallelExecutor`).
*   **Overrides (Two-Stage)**:
    *   **Outer** (Pre-selection): `-m, --merge` (file), `-o, --overrides` (dotlist).
    *   **Inner** (Post-selection): `-M, --merge-after-select`, `-O, --overrides-after-select`.
*   **Execution**:
    *   `--n_jobs`: Number of parallel workers (for sweeps).

### B. The Python API (`flexlock.api`)
Used for building complex pipelines (DAGs) and programmatic control.

```python
from flexlock import Project

proj = Project(defaults="pkg.config.defaults")

# 1. Run Stage 1 (Sweep)
cfg_1 = proj.get("stage1")
tasks = proj.get("grid_search_params")
results = proj.submit(cfg_1, sweep=tasks, n_jobs=4)

# 2. Run Stage 2 (Single, dependent on Stage 1)
cfg_2 = proj.get("stage2")
cfg_2.input_path = results[0].save_dir
proj.submit(cfg_2)
```

### C. Configuration Utilities
1.  **`py2cfg`**:
    *   Extracts default values from functions and classes.
    *   Supports nested calls: `py2cfg(train, opt=py2cfg(Adam, lr=1e-3))`.
    *   **Best Practice**: Function signatures should use `opt=None` to avoid mutable default traps.
2.  **`save_dir` Injection**:
    *   FlexLock ensures a `save_dir` key exists before instantiation.
    *   **Priority**:
        1.  Explicitly defined in YAML/Config.
        2.  Auto-generated: `outputs/{name}/{date}_{time}`.
3.  **`instantiate`**:
    *   Uses `hydra.utils.instantiate` to recursively create objects based on `_target_`.

---

# 3. Part II: Reproducibility & State (The Backend)

### A. Git Versioning (`git_utils`)
**Strategy**: "Shadow Index" (Plumbing).
Instead of modifying the user's workspace or creating patch files, we use Git's internal plumbing to snapshot the exact state of the workspace.

*   **Mechanism**:
    1.  Copy `.git/index` to a temp file.
    2.  Set `GIT_INDEX_FILE` env var to temp file.
    3.  `git add --all` (captures untracked & modified files).
    4.  `git write-tree` -> Returns **Tree Hash**.
    5.  `git commit-tree` -> Returns **Commit Hash** (The "Shadow Commit").
    6.  Create a ref `refs/flexlock/runs/{id}` to prevent Garbage Collection.
*   **Equality Check**: Compare **Tree Hash**. If `Tree A == Tree B`, the code is mathematically identical, regardless of commit history.

### B. Data Hashing (`data_hash`)
**Strategy**: SQLite Cache + Tiered Hashing.

*   **Storage**: `~/.cache/flexlock/hashes.db` (SQLite) to ensure safe concurrent writes during parallel runs.
*   **Logic**:
    1.  **Fast Mode**: If directory has > 1000 files (configurable), hash based on `(mtime, size, file_count)`.
    2.  **Strict Mode**: Read file content (XXHash).
    3.  **Parallel**: Use `joblib` to hash files in parallel.

### C. Snapshotting (`snapshot`)
**Strategy**: Atomic `RunTracker`.

*   **Output**: `run.lock` (YAML).
*   **Contents**:
    *   `config`: Resolved DictConfig.
    *   `repos`: Git info (Shadow Commit Hash + Tree Hash).
    *   `data`: Input data hashes.
    *   `lineage`: Paths/IDs of upstream `run.lock` files.
*   **Safety**: Uses `tempfile` + `os.replace` for atomic writes.

### D. Smart Resume (`diff`)
**Strategy**: `RunDiff` class.

*   Compares a "Proposed" state (Live) vs "Stored" state (`run.lock`).
*   **Match Logic**:
    *   Config: Dictionary equality (ignoring `save_dir`/timestamps).
    *   Data: Hash equality.
    *   Git: **Tree Hash** equality (The Shadow Tree).

---

# 4. Implementation Plan

### Phase 1: Core & Utilities
- [ ] **`flexlock/utils.py`**:
    - [ ] Update `py2cfg` to handle Classes (`__init__`) and nested `py2cfg` objects.
    - [ ] Implement `load_python_defaults(path_str)`.
- [ ] **`flexlock/data_hash.py`**:
    - [ ] Refactor to use **SQLite** instead of JSON for caching.
    - [ ] Implement tiered hashing (Fast vs Strict).

### Phase 2: Git & State
- [ ] **`flexlock/git_utils.py`**:
    - [ ] Implement `shadow_index` context manager (`GIT_INDEX_FILE`).
    - [ ] Implement `create_shadow_snapshot` returning `{commit, tree, is_dirty}`.
    - [ ] Add logic to write `refs/flexlock/...`.
- [ ] **`flexlock/snapshot.py`**:
    - [ ] Implement `RunTracker` class.
    - [ ] Implement atomic save.
    - [ ] Integrate new `git_utils` and `data_hash`.

### Phase 3: The Runner
- [ ] **`flexlock/runner.py`**:
    - [ ] Implement `FlexLockRunner` class.
    - [ ] **Load Config**: Base -> Outer -> Select -> Inner.
    - [ ] **Inject**: `_prepare_save_dir`.
    - [ ] **Diff/Skip**: Implement `check_if_exists()` using `RunDiff`.
    - [ ] **Dispatch**: `_execute_single` (Instantiate) vs `_execute_batch` (ParallelExecutor).
- [ ] **`flexlock/parallel.py`**:
    - [ ] Update worker to perform `Merge -> Snapshot -> Instantiate`.

### Phase 4: Interface
- [ ] **`flexlock/cli.py`**:
    - [ ] Add `diff` command.
    - [ ] Main entry point.
- [ ] **`flexlock/api.py`**:
    - [ ] Implement `Project` class wrapping the Runner.
- [ ] **Decorator**:
    - [ ] Update `@flexcli` to support dual mode (importable function vs CLI entry).

### Phase 5: Diffing
- [ ] **`flexlock/diff.py`**:
    - [ ] Implement `RunDiff`.
    - [ ] Logic to compare Config, Data, and **Git Tree Hash**.



## Implementation details
Here is the compilation of the key implementation details for the final **FlexLock** design.

### 1. Core Utilities (`flexlock/utils.py`)
Handles Python-first configuration and dynamic loading.

```python
# flexlock/utils.py
import inspect
import importlib
import sys
import functools
from pathlib import Path
from omegaconf import OmegaConf

def py2cfg(obj, **overrides):
    """
    Generates a default configuration dict from a function or class signature.
    Supports nested py2cfg calls and handles decorated functions.
    """
    # 1. Unwrap decorated functions
    if hasattr(obj, "_original_fn"):
        obj = obj._original_fn
        
    # 2. Determine target and signature source
    if inspect.isclass(obj):
        target = f"{obj.__module__}.{obj.__qualname__}"
        sig_obj = obj.__init__
    elif inspect.isroutine(obj):
        target = f"{obj.__module__}.{obj.__qualname__}"
        sig_obj = obj
    else:
        raise ValueError(f"py2cfg expects class or function, got {type(obj)}")

    # 3. Build Config
    config = {"_target_": target}
    
    try:
        sig = inspect.signature(sig_obj)
        params = list(sig.parameters.values())
        
        # Skip 'self'
        if inspect.isclass(obj) or (hasattr(sig_obj, '__self__') and sig_obj.__name__ != '__init__'):
             if params and params[0].name == 'self':
                 params = params[1:]

        for param in params:
            if param.default is not param.empty:
                # We generally only capture primitive defaults here.
                # Complex defaults (classes) should be handled via explicit overrides 
                # or None defaults in the function signature.
                config[param.name] = param.default
    except (ValueError, TypeError):
        pass

    # 4. Apply overrides (nested py2cfg calls happen here)
    config.update(overrides)
    return config

def load_python_defaults(import_path: str):
    """Dynamically imports a module or file path to retrieve 'defaults'."""
    if ":" in import_path:
        # Path based: "configs/my_conf.py:defaults"
        path_str, var_name = import_path.split(":")
        file_path = Path(path_str).resolve()
        spec = importlib.util.spec_from_file_location("dynamic_defaults", file_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return getattr(module, var_name)
    else:
        # Module based: "pkg.config.defaults"
        module_name, var_name = import_path.rsplit(".", 1)
        module = importlib.import_module(module_name)
        return getattr(module, var_name)
```

### 2. Git Versioning (`flexlock/git_utils.py`)
Implements the **Shadow Index** strategy for safe, clean snapshots.

```python
# flexlock/git_utils.py
import os
import shutil
import uuid
from pathlib import Path
from contextlib import contextmanager
from git import Repo

@contextmanager
def shadow_index(repo: Repo):
    """Context manager for Git Plumbing operations without touching user index."""
    git_dir = Path(repo.git_dir)
    temp_index = git_dir / f"index_shadow_{uuid.uuid4().hex}"
    
    # Clone current index to temp file for speed
    try:
        if (git_dir / "index").exists():
            shutil.copy2(git_dir / "index", temp_index)
    except Exception:
        pass 

    env = os.environ.copy()
    env["GIT_INDEX_FILE"] = str(temp_index)
    
    try:
        yield env
    finally:
        if temp_index.exists():
            temp_index.unlink()

def create_shadow_snapshot(repo_path: str = ".", ignore_patterns: list = None):
    """
    Creates a Shadow Commit.
    Returns: {commit_hash, tree_hash, is_dirty}
    """
    repo = Repo(repo_path, search_parent_directories=True)
    ignore_patterns = ignore_patterns or []

    with shadow_index(repo) as shadow_env:
        git = repo.git
        
        # 1. Stage everything (Modified + Untracked) into Shadow Index
        git.add("--all", env=shadow_env)
        
        # 2. Remove ignored patterns from Shadow Index
        if ignore_patterns:
            try:
                git.rm("--cached", "-r", "--ignore-unmatch", *ignore_patterns, env=shadow_env)
            except Exception:
                pass

        # 3. Write Tree (This is the content fingerprint)
        tree_hash = git.write_tree(env=shadow_env)
        
        # 4. Create Shadow Commit (Lineage)
        parent = repo.head.commit.hexsha
        msg = f"FlexLock Shadow: {parent[:7]} + Changes"
        shadow_commit = git.commit_tree(tree_hash, "-p", parent, "-m", msg, env=shadow_env)
        
        # 5. Save Ref (Prevent Garbage Collection)
        ref_name = f"refs/flexlock/runs/{shadow_commit}"
        git.update_ref(ref_name, shadow_commit)

        return {
            "commit": shadow_commit,
            "tree": tree_hash, # <--- The key for Equality Checks
            "is_dirty": repo.is_dirty(untracked_files=True)
        }
```

### 3. Data Hashing (`flexlock/data_hash.py`)
Implements **SQLite** caching and tiered hashing.

```python
# flexlock/data_hash.py
import sqlite3
import os
import xxhash
from pathlib import Path
from joblib import Parallel, delayed

CACHE_DIR = Path.home() / ".cache" / "flexlock"
CACHE_DB = CACHE_DIR / "hashes.db"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

def _get_db():
    conn = sqlite3.connect(CACHE_DB)
    conn.execute('CREATE TABLE IF NOT EXISTS cache (path TEXT PRIMARY KEY, mtime REAL, hash TEXT)')
    return conn

def _hash_file_content(path):
    hasher = xxhash.xxh64()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()

def hash_data(path_str, use_cache=True, fast_mode=True):
    path = Path(path_str).resolve()
    
    # 1. Check Cache
    if use_cache:
        mtime = path.stat().st_mtime
        with _get_db() as conn:
            row = conn.execute("SELECT hash, mtime FROM cache WHERE path=?", (str(path),)).fetchone()
            if row and row[1] == mtime:
                return row[0]

    # 2. Compute Hash
    if path.is_dir():
        # ... (Include logic for parallel directory walking) ...
        # Simplified:
        final_hash = "dir_hash_placeholder" 
    else:
        final_hash = _hash_file_content(path)

    # 3. Update Cache
    if use_cache:
        with _get_db() as conn:
             conn.execute("INSERT OR REPLACE INTO cache VALUES (?, ?, ?)", (str(path), mtime, final_hash))
             
    return final_hash
```

### 4. Snapshotting (`flexlock/snapshot.py`)
Atomic write of the `run.lock` file using the new utilities.

```python
# flexlock/snapshot.py
import yaml
import tempfile
import os
from datetime import datetime
from pathlib import Path
from .git_utils import create_shadow_snapshot
from .data_hash import hash_data
from omegaconf import OmegaConf

class RunTracker:
    def __init__(self, save_dir):
        self.save_dir = Path(save_dir)
        self.data = {"timestamp": datetime.now().isoformat()}

    def record_env(self, repos: dict):
        self.data["repos"] = {}
        for name, path in repos.items():
            # Uses the Shadow Index logic
            self.data["repos"][name] = create_shadow_snapshot(path)

    def record_data(self, data_paths: dict):
        self.data["data"] = {k: hash_data(v) for k, v in data_paths.items()}

    def save(self, config):
        self.save_dir.mkdir(parents=True, exist_ok=True)
        self.data["config"] = OmegaConf.to_container(config, resolve=True)
        
        # Atomic Write
        with tempfile.NamedTemporaryFile("w", dir=self.save_dir, delete=False) as tf:
            yaml.dump(self.data, tf, sort_keys=False)
            tmp_name = tf.name
        os.replace(tmp_name, self.save_dir / "run.lock")

def snapshot(cfg, repos=None, data=None):
    if "save_dir" not in cfg: return
    tracker = RunTracker(cfg.save_dir)
    if repos: tracker.record_env(repos)
    if data: tracker.record_data(data)
    tracker.save(cfg)
```

### 5. Diff & Resume (`flexlock/diff.py`)
Implements **Tree Hash** comparison.

```python
# flexlock/diff.py
class RunDiff:
    def __init__(self, current, target):
        self.current = current
        self.target = target
        self.diffs = {}

    def compare_git(self):
        diff = []
        c_repos = self.current.get("repos", {})
        t_repos = self.target.get("repos", {})

        for name, c_info in c_repos.items():
            t_info = t_repos.get(name)
            if not t_info:
                diff.append(f"Repo {name} missing")
                continue
            
            # The Magic: Compare Tree Hashes (Content Identity)
            if c_info.get("tree") != t_info.get("tree"):
                 diff.append(f"Repo {name}: Content changed")
        
        if diff: self.diffs["git"] = diff
        return len(diff) == 0

    def is_match(self):
        # Implement config and data comparison here as well
        return self.compare_git() and self.compare_config() and self.compare_data()
```

### 6. The Runner (`flexlock/runner.py`)
Handles the loading pipeline and execution dispatch.

```python
# flexlock/runner.py
import argparse
from omegaconf import OmegaConf, open_dict
from datetime import datetime
from pathlib import Path
from hydra.utils import instantiate
from .utils import load_python_defaults
from .parallel import ParallelExecutor
from .snapshot import snapshot

class FlexLockRunner:
    def __init__(self):
        self.parser = argparse.ArgumentParser()
        # ... add arguments (-d, -c, -s, -m, -o ...) ...

    def load_config(self, args):
        # 1. Base (Python Defaults)
        cfg = OmegaConf.create()
        if args.defaults:
            cfg = OmegaConf.create(load_python_defaults(args.defaults))
        
        # 2. Outer Overrides
        if args.config: cfg.merge_with(OmegaConf.load(args.config))
        if args.merge: cfg.merge_with(OmegaConf.load(args.merge))
        if args.overrides: cfg.merge_with(OmegaConf.from_dotlist(args.overrides))
        
        return cfg

    def _prepare_node(self, cfg, name="exp"):
        # Inject save_dir if missing
        if "save_dir" not in cfg:
             ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
             path = Path("outputs") / name / ts
             with open_dict(cfg):
                 cfg.save_dir = str(path)
        return cfg

    def run(self, cli_args=None):
        args = self.parser.parse_args(cli_args)
        root_cfg = self.load_config(args)
        
        # Extract tasks if sweeping
        tasks = []
        if args.sweep_from:
             tasks = OmegaConf.select(root_cfg, args.sweep_from)

        # Select Node
        node_cfg = root_cfg
        if args.select:
            node_cfg = OmegaConf.select(root_cfg, args.select)

        # Inner Overrides
        if args.merge_after_select: 
            node_cfg.merge_with(OmegaConf.load(args.merge_after_select))

        # Run
        node_cfg = self._prepare_node(node_cfg)
        
        if tasks:
            ParallelExecutor(instantiate, tasks, node_cfg, n_jobs=args.n_jobs).run()
        else:
            # Snapshot before run
            snapshot(node_cfg, repos={"main": "."}) 
            instantiate(node_cfg)
```

### 7. Interface (`flexlock/cli.py`)
Dual-mode decorator and CLI entry.

```python
# flexlock/cli.py
import sys
import functools
from .runner import FlexLockRunner

def flexcli(fn):
    """
    Decorator that allows a function to be:
    1. Imported and used programmatically (logic preserved).
    2. Run as a CLI entry point (FlexLockRunner invoked).
    """
    @functools.wraps(fn)
    def wrapper(cfg=None, **kwargs):
        # Mode 1: Programmatic
        if cfg is not None or kwargs:
            return fn(cfg, **kwargs)
        
        # Mode 2: CLI
        # We assume if no args passed, we are in CLI mode
        runner = FlexLockRunner()
        # In a real impl, you might want to map 'fn' to a default config logic here
        return runner.run()

    # Store original for py2cfg inspection
    wrapper._original_fn = fn
    return wrapper

def main():
    """Entry point for the 'flexlock' command."""
    FlexLockRunner().run()
```
