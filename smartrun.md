This is the final piece of the puzzle. You are looking for **Memoization** (caching results based on input fingerprints).

In **FlexLock**, this should be implemented as a "Look-Before-You-Leap" check inside the `Project.submit` or `FlexLockRunner.run` logic.

Here is the design and implementation for the **Smart Run** feature.

### 1. The Strategy: "Fingerprint & Search"

To safely skip a run, we must prove that a previous run exists with:
1.  **Identical Code** (Git Tree Hash).
2.  **Identical Configuration** (Dictionary equality).
3.  **Identical Input Data** (Input file hashes).

We do **not** check the Output. We assume if Inputs + Logic are identical, the Output is identical (Deterministic assumption).

### 2. Implementation: `flexlock/smart.py`

We need a utility to generate a "Proposed Snapshot" (what the `run.lock` *would* look like) and compare it against existing `run.lock` files on disk.

```python
# flexlock/smart.py
from pathlib import Path
from loguru import logger
import yaml
from .snapshot import RunTracker
from .diff import RunDiff

class SmartCache:
    def __init__(self, search_dirs: list[str]):
        """
        search_dirs: List of directories to scan for previous runs 
                     (e.g. ["outputs/preprocess", "outputs/archive/preprocess"])
        """
        self.search_dirs = [Path(d) for d in search_dirs]

    def find_match(self, proposed_snapshot: dict):
        """
        Scans search_dirs for a run.lock that matches the proposed snapshot.
        Returns the Path to the matching run directory, or None.
        """
        for root in self.search_dirs:
            if not root.exists(): continue
            
            # Iterate over subdirectories (assuming 1 level deep: root/run_id)
            # You could make this recursive if needed
            for run_dir in root.iterdir():
                if not run_dir.is_dir(): continue
                
                lock_file = run_dir / "run.lock"
                if not lock_file.exists(): continue
                
                try:
                    # Load candidate
                    with open(lock_file, "r") as f:
                        candidate_snapshot = yaml.safe_load(f)
                    
                    # COMPARE using RunDiff
                    # We treat the proposed snapshot as "Current" and candidate as "Target"
                    # We pass None for directories because we assume snapshots contain all info needed
                    differ = RunDiff(
                        current_state=proposed_snapshot, 
                        target_state=candidate_snapshot
                    )
                    
                    if differ.is_match():
                        logger.success(f"⚡ Cache Hit! Found matching run at: {run_dir}")
                        return run_dir
                        
                except Exception as e:
                    logger.debug(f"Failed to read/compare {lock_file}: {e}")
                    continue
        
        return None

def generate_fingerprint(cfg, repos=None, data=None):
    """
    Generates the 'Proposed Snapshot' in memory without writing to disk.
    """
    # Use RunTracker in a 'dry-run' mode
    # We pass a dummy path because we won't save
    tracker = RunTracker(save_dir=Path("/dummy"))
    
    # 1. Config
    tracker.record_config(cfg)
    
    # 2. Env / Git (Calculates Tree Hashes)
    if repos: tracker.record_env(repos)
    
    # 3. Data (Calculates Hashes)
    if data: tracker.record_data(data)
    
    # We return the dict directly
    return tracker.finalize(cfg) # Assuming you implemented finalize() in RunTracker
```

### 3. Integration into `Project` API

This is where the user enables the feature.

```python
# flexlock/api.py
from .smart import SmartCache, generate_fingerprint

class Project:
    # ... init ...

    def submit(self, cfg, sweep=None, smart_run=False, cache_dirs=None, ...):
        
        # 1. Resolve Config & Paths (Standard)
        cfg = self._runner.prepare_node(cfg)
        repos, data, prevs = self._runner.extract_tracking_info(cfg)

        # --- SMART RUN LOGIC ---
        if smart_run:
            # Determine where to look. 
            # Default: Look in the parent directory of where we planned to save.
            # e.g. if save_dir is "outputs/preprocess/run_123", look in "outputs/preprocess"
            search_paths = cache_dirs or [Path(cfg.save_dir).parent]
            
            # Generate the "Fingerprint" (Heavy operation: Hashes data & git)
            fingerprint = generate_fingerprint(cfg, repos, data)
            
            cache = SmartCache(search_paths)
            match_dir = cache.find_match(fingerprint)
            
            if match_dir:
                # SKIP EXECUTION
                # Return a result object pointing to the EXISTING run
                return ExecutionResult(
                    save_dir=str(match_dir),
                    status="SKIPPED",
                    cfg=cfg # Return the config so we know what it was
                )

        # 2. Standard Execution (if no match or smart_run=False)
        snapshot(cfg, repos, data, prevs)
        return instantiate(cfg)
```

### 4. How to use it in your Pipeline

This completely solves the "Preprocess" use case.

```python
# pipeline.py
from flexlock import Project

def main():
    proj = Project(defaults="config.defaults")
    
    # --- STAGE 1: Preprocess ---
    # Goal: Don't re-run if we already did this exact preprocessing.
    
    preprocess_cfg = proj.get("preprocess")
    
    # smart_run=True will hash input data and check 'outputs/preprocess/*'
    prep_result = proj.submit(
        preprocess_cfg, 
        smart_run=True
    )
    
    print(f"Preprocessing used: {prep_result.save_dir}") 
    # ^ Points to OLD dir if cached, NEW dir if ran.

    # --- STAGE 2: Train ---
    # We link to the result of stage 1
    train_cfg = proj.get("train")
    train_cfg.data_dir = prep_result.save_dir
    
    proj.submit(train_cfg) # Maybe logic: always run training (smart_run=False)

```

### 5. Important Nuances

#### A. The "Save Dir" Dilemma
When `smart_run` finds a match, it returns the **Old Directory**.
*   **Advantage:** You don't duplicate data.
*   **Constraint:** Downstream stages must read from the returned path, not a predicted path.

#### B. The "Output" Assumption
`SmartRun` assumes that if a `run.lock` exists, the run finished successfully and the artifacts are valid.
*   **Refinement:** You might want to check for a `SUCCESS` file or a specific status in the `run.lock` (if you record status).
*   **Fix:**
    ```python
    # In find_match loop:
    if not (run_dir / ".SUCCESS").exists():
        continue # Run failed or didn't finish, don't use as cache
    ```

#### C. Performance
Calculating the fingerprint requires hashing the input data.
*   If your input is 1TB of images, this takes time.
*   **Mitigation:** This is why we implemented the **Tiered Hashing** (mtime/size check) in `data_hash.py`. It makes the fingerprint generation nearly instantaneous for large datasets that haven't been touched.

### Summary

The `smart_run` feature allows you to:
1.  **Generate a fingerprint** of a planned run (Code Tree + Config + Data Hash).
2.  **Scan previous output folders**.
3.  **Diff** the fingerprint against history.
4.  **Short-circuit** execution if a match is found.

This turns your `FlexLock` pipeline into a pseudo-build system (like Make/Bazel) where tasks only run if necessary.