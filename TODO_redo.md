# Naga Refactoring Plan (Redo)

This document outlines the plan to refactor the Naga library into a more modular, explicit, and composable set of tools, based on the design in `NagaRedo.md`. The goal is to move away from a single, complex decorator to a series of standalone functions and context managers that are orchestrated explicitly in the user's script.

The new core components will be:
- `naga.clicfg()`: A flexible decorator for handling configuration from both CLI and programmatic calls.
- `naga.runlock()`: An explicit function to generate the `run.lock` file.
- `naga.mlflow_lock()`: A context manager to handle the MLflow run lifecycle.

---

## Phase 1: Core Component Implementation

### 1.1. Implement `naga.runlock()` Function
- **Location:** `naga/runlock.py`
- **Action:** Refactor the existing `@runlock` decorator and related logic into a standalone function.
- **Details:**
    - **Signature:** `runlock(config, repos=None, data=None, prevs=None, runlock_path=None, merge=False)`
    - **Functionality:**
        - **`config`**: The final, resolved OmegaConf object for the run.
        - **`repos` (dict):** A dictionary mapping a name to a git repository path (e.g., `{'main_repo': '.'}`). A helper `naga.snapshot.get_git_commit(path)` will be created.
        - **`data` (dict):** A dictionary mapping a name to a data path to be hashed (e.g., `{'raw_data': 'path/to/data'}`). Uses the existing `naga.data_hash.hash_data`.
        - **`prevs` (list):** A list of paths to previous stage directories to be included. Uses the existing `naga.load_stage.load_stage_from_path`.
        - **`runlock_path` (str or callable):** If not provided, defaults to `Path(config.save_dir) / 'run.lock'`.
        - **`merge` (bool):** If `True` and a `run.lock` file already exists, it will be read, updated with the new information, and written back.
        - The function will be responsible for atomically writing the final `run.lock` YAML file.

### 1.2. Implement `naga.mlflow_lock()` Context Manager
- **Location:** `naga/mlflow_log.py`
- **Action:** Refactor the `@mlflow_log_run` decorator into a context manager.
- **Details:**
    - **Signature:** `naga.mlflow_lock(path, runlock_file='run.lock')`
    - **`__enter__`:**
        - Uses `path` as the `logical_run_id` to search for previous active MLflow runs.
        - Starts a new MLflow run (`mlflow.start_run`).
        - Sets the appropriate tags (`naga.logical_run_id`, `naga.run_status='active'`).
        - Returns the active MLflow `run` object.
    - **`__exit__`:**
        - Upon exiting the `with` block, it logs the `run.lock` and `experiment.log` from the `path` directory as artifacts.
        - It correctly handles exceptions.
        - It finalizes the MLflow run.
        - It finds the previous active run (if any) and updates its tags to `naga.run_status='deprecated'` and `naga.superseded_by_run_id=...`.

### 1.3. Refactor `naga.clicfg()` Decorator
- **Location:** `naga/clicfg.py`
- **Action:** Enhance the decorator to support both CLI and programmatic calls.
- **Details:**
    - The decorator will inspect how the wrapped function is called.
    - **CLI Call (`python main.py --arg value`):** Behavior remains as is, parsing `sys.argv`.
    - **Programmatic Call (`main(arg='value')`):**
        - It will convert the `kwargs` into an OmegaConf dot-list (`['arg=value']`).
        - This list will be used as the final override layer on top of default and file-based configurations.
        - This allows for a seamless and identical configuration logic regardless of the calling method.

---

## Phase 2: Integration and Cleanup

### 2.1. Update OmegaConf Resolvers
- **Location:** `naga/resolvers.py`
- **Action:** Modify the resolvers to work with the new `runlock` function.
- **Details:**
    - The `track` and `stage` resolvers will no longer directly modify a global context.
    - They will now call `naga.runlock(config=cfg, ..., merge=True)` to incrementally add their information to the `run.lock` file as the configuration is being resolved. This makes their behavior more explicit.

### 2.2. Deprecate and Remove Old Components
- **Action:** Remove obsolete decorators to avoid confusion and code duplication.
- **Details:**
    - Remove the master `@naga.naga` decorator (`naga/decorator.py`).
    - Remove the individual decorators: `@snapshot`, `@track_data`, `@load_stage`, and `@runlock`. Their logic will now reside within the new `runlock` function or helper utilities.
    - The file `naga/decorator.py` will be deleted.

### 2.3. Create Helper Utilities
- **Action:** Consolidate scattered logic into reusable helper functions.
- **Details:**
    - `naga.snapshot.py`: Create `get_git_commit(path)` to return the commit hash of a given repo path.
    - `naga.data_hash.py`: Ensure `hash_data(path)` is robust and accessible.
    - `naga.load_stage.py`: Ensure `load_stage_from_path(path)` is suitable for use by `runlock`.

---

## Phase 3: Documentation

### 3.1. Update `README.md` and `GEMINI.md`
- **Action:** Rewrite the main documentation and philosophy to reflect the new design.
- **Details:**
    - Provide a clear, simple example of the new recommended workflow (`clicfg` -> `mlflow_lock` -> `core_logic` -> `runlock`).
    - Explain the benefits of the new explicit, composable approach.

### 3.2. Update All Docstrings
- **Action:** Ensure all public functions and classes have clear, up-to-date docstrings.

---
