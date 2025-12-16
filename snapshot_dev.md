Here is the breakdown of why you should do it, the trade-offs, and the implementation.

### 1. The Pros & Cons

| Feature | File-Based (`run.lock`) | DB-Based (`sqlite`) |
| :--- | :--- | :--- |
| **Filesystem Health** | ❌ **Poor**. 10k tasks = 10k files. | ✅ **Excellent**. 1 file (`tasks.db`). |
| **Queryability** | ❌ **Hard**. Need to parse thousands of YAMLs to find "lr > 0.1". | ✅ **Instant**. `SELECT * FROM tasks WHERE json_extract(snapshot, '$.config.lr') > 0.1`. |
| **Atomic Transfer** | ✅ **Easy**. Zip the folder, send to colleague. | ⚠️ **Hard**. Need to export metadata from DB to send along with data. |
| **Lineage** | ✅ **Standard**. Recursive file search works. | ⚠️ **Complex**. Requires DB lookup to verify upstream dependencies. |
| **Visualization** | ❌ **Manual**. | ✅ **Easy**. Connect generic tools (Datasette, Streamlit) to the DB. |

### 2. The Verdict

**Go for a "Hybrid" approach:**
1.  **Primary Storage**: Store the full JSON snapshot in the SQLite DB. This is used for execution logic, diffing, and analysis.
2.  **Lineage Anchor (Optional)**: Write a *minimal* marker file in the task directory (e.g., `.task_id`) or a full `run.lock` **only if** you expect to use that specific folder as an input for a future pipeline stage.

If your workflow is strictly "Sweep -> Aggregate Results", you don't need individual lock files. The DB is enough.

---

### 3. Implementation Plan

#### A. Database Schema Update

You need a column to store the snapshot JSON blob.

```sql
CREATE TABLE tasks (
    id INTEGER PRIMARY KEY,
    status TEXT DEFAULT 'PENDING',
    config JSON,         -- The input configuration (merged)
    snapshot JSON,       -- The runtime state (Git + Data + Config + Lineage)
    worker_id TEXT,
    started_at TIMESTAMP,
    finished_at TIMESTAMP
);
```

#### B. `RunTracker` Modification

We modify `snapshot()` to **return the dictionary** instead of strictly writing to a file. The caller decides where to put it.

```python
# flexlock/snapshot.py

class RunTracker:
    # ... existing init ...

    def finalize(self, config):
        """Prepares the final snapshot dict but does not write it."""
        self.run_data["config"] = OmegaConf.to_container(config, resolve=True)
        # ... logic for repos, data, lineage ...
        return self.run_data

    def save_to_file(self, config):
        """Original behavior."""
        data = self.finalize(config)
        # ... atomic write logic ...

# flexlock/snapshot.py (Utility)
def snapshot(cfg, repos=None, data=None, prevs=None, parent_lock=None, return_only=False):
    tracker = RunTracker(cfg.save_dir, parent_lock)
    # ... record env/data ...
    
    if return_only:
        return tracker.finalize(cfg)
    else:
        tracker.save_to_file(cfg)
```

#### C. Worker Logic (Writing to DB)

In your `ParallelExecutor` worker loop:

```python
    def _worker_entry(self, task_id, task_overrides, root_dir, db_path):
        # 1. Setup Config & Directories
        # ...
        
        # 2. Generate Snapshot (In-Memory)
        # Note: We rely on the Master Lock (parent_lock) for heavy git info
        snapshot_data = snapshot(
            task_cfg,
            data=data,
            prevs=prevs,
            parent_lock=root_dir / "run.lock",
            return_only=True  # <--- Do not write file
        )
        
        # 3. Write to DB
        import sqlite3
        import json
        
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "UPDATE tasks SET status='RUNNING', snapshot=?, started_at=CURRENT_TIMESTAMP WHERE id=?",
                (json.dumps(snapshot_data), task_id)
            )
            
        # 4. Execute
        try:
            instantiate(task_cfg)
            # Update DB on success...
        except Exception:
            # Update DB on fail...
```

#### D. The "Virtual" Diff

Since the snapshots are in the DB, `flexlock diff` needs to be able to read them.

**CLI Update:**
```bash
# Diff two directory-based runs (standard)
flexlock diff outputs/run_A outputs/run_B

# Diff two tasks within a sweep (DB-based)
flexlock diff --db outputs/sweep_X/tasks.db 1 5
```

### 4. Handling Lineage (The Tricky Part)

If `Task 2` depends on `Task 1`, and `Task 1` has no `run.lock` file, the recursive search `_find_snapshot_dir` will fail.

**Solution:**
Since you are using `Project` and `ParallelExecutor`, you likely handle dependencies at the **Stage** level, not the **Task** level.
*   Stage 2 usually depends on the **Aggregated Output** of Stage 1 (the whole folder), or specific files.

If you strictly need file-level lineage (e.g., Stage 2 reads `outputs/sweep/task_01/model.pt`), you have two options:

1.  **The "Marker" File:**
    When the worker starts, write a tiny file `outputs/sweep/task_01/.flexlock_id` containing `{"db": "../../tasks.db", "id": 1}`.
    Update `_find_snapshot_dir` to recognize this marker, open the DB, and fetch the snapshot.

2.  **Explicit Config:**
    In Stage 2's config, you explicitly point to the DB.
    ```yaml
    # Stage 2 Config
    data:
      model: "outputs/sweep/task_01/model.pt"
    _snapshot_:
      lineage_source: "outputs/sweep/tasks.db" # Hint to the runner
    ```

### Recommendation

**Store the full content in the DB.**

It aligns perfectly with your architecture (using SQLite for task management). It makes your experiment analysis incredibly powerful (SQL over hyperparameters).

If you need to share a specific task result with someone, write a simple CLI command:
`flexlock export-task --db tasks.db --id 1 --out outputs/extracted_task_1/run.lock`
