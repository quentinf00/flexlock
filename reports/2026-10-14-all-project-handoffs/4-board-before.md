Here is a proposed structure for your Cookiecutter template examples, broken down by complexity and feature set.

### Directory Structure Proposal

```text
{{cookiecutter.project_slug}}/
├── 01_basics/
│   ├── simple_script.py          # The self-contained script
│   └── grids.yaml                # For external sweep demo
├── 02_reproducibility/
│   ├── train_model.py            # Script with snapshot config
│   └── data/                     # Dummy data folder
├── 03_yaml_config/
│   ├── main.py                   # Entry point
│   ├── config.yaml               # Multistage YAML
│   └── overrides.yaml            # For file merging demo
├── 04_python_config/
│   ├── main.py                   # Entry point
│   ├── config.py                 # py2cfg definitions
│   └── components.py             # Functions/Classes
└── 05_pipeline/
    ├── pipeline.py               # The Orchestrator (Project API)
    ├── stages.py                 # The stage functions
    └── configs.py                # The definitions
```

---

### 1. The "Script" (Basics)
**File:** `01_basics/simple_script.py`
**Focus:** `@flexcli` decorator, CLI arguments, and simple sweeps.

*   **Code:** A function `train(lr=0.01, batch_size=32)` decorated with `@flexcli`.
*   **Demo Scenarios (E2E Tests):**
    1.  **Default Run:** `python simple_script.py`
        *   *Check:* Runs with defaults.
    2.  **Param Override:** `python simple_script.py lr=0.1`
        *   *Check:* `lr` changes.
    3.  **CLI Sweep:** `python simple_script.py --sweep "lr=0.01,lr=0.05" --n_jobs 2`
        *   *Check:* Runs 2 jobs in parallel.
    4.  **File Sweep:** `python simple_script.py --sweep-file grids.yaml`
        *   *Check:* Loads sweep list from YAML and executes.

---

### 2. The "Scientist" (Reproducibility & Lineage)
**File:** `02_reproducibility/train_model.py`
**Focus:** Snapshotting, Data Hashing, Git Patching, and Diffing.

*   **Code:**
    *   Decorator uses `snapshot_config={...}`.
    *   Interpolation: `"data": {"raw": "${data_path}"}`.
*   **Demo Scenarios:**
    1.  **Snapshot Generation:** `python train_model.py data_path=./data/raw`
        *   *Check:* `outputs/.../run.lock` is created. `run.lock` contains `repos` (tree hash) and `data` (file hash).
    2.  **Diffing (Identical):** Run the command again.
        *   *Check:* Use `flexlock diff` on the two output folders. result: "Identical".
    3.  **Diffing (Code Change):** Add a comment or print statement to the script. Run again.
        *   *Check:* `flexlock diff` shows "Git Tree Mismatch".
    4.  **Diffing (Data Change):** Modify a file in `./data/raw`. Run again.
        *   *Check:* `flexlock diff` shows "Data Hash Mismatch".

---

### 3. The "Engineer" (Multistage YAML)
**File:** `03_yaml_config/config.yaml` & `main.py`
**Focus:** Structure, Selection, Interpolation, and Complex Overrides.

*   **Code:** `main.py` is a dumb entry point. `config.yaml` has `global_params`, `stage_A`, `stage_B`. `stage_B` uses `${stage_A.output_dir}`.
*   **Demo Scenarios:**
    1.  **Selection & Interpolation:** `flexlock -c config.yaml -s stage_B`
        *   *Check:* `stage_B` runs, accessing `global_params` successfully (context preservation).
    2.  **Outer Override (Global):** `flexlock -c config.yaml -s stage_B -o "global_params.seed=99"`
        *   *Check:* `stage_B` sees the new seed via interpolation.
    3.  **Inner Override (Local):** `flexlock -c config.yaml -s stage_B -O "lr=0.5"`
        *   *Check:* `stage_B` specific parameter updates.
    4.  **Sweep from Key:** `flexlock -c config.yaml -s stage_A --sweep-from experiments.grid_search`
        *   *Check:* `experiments.grid_search` list defined in YAML is executed.

---

### 4. The "Developer" (Python Defaults)
**File:** `04_python_config/config.py`
**Focus:** `py2cfg`, Classes, and Mutable Defaults handling.

*   **Code:**
    *   `components.py`: `def train(opt=None)` (None default pattern).
    *   `config.py`: `py2cfg(train, opt=py2cfg(Adam, lr=1e-3))`.
*   **Demo Scenarios:**
    1.  **Defaults Loading:** `flexlock -d 04_python_config.config.defaults -s train`
        *   *Check:* The `Adam` optimizer is correctly instantiated and passed to the function.
    2.  **Deep Override:** `flexlock -d ... -s train -O "opt.lr=0.05"`
        *   *Check:* The nested object property is updated.
    3.  **Swapping Classes:** `flexlock -d ... -s train -O "opt={_target_: torch.optim.SGD, lr: 0.1}"`
        *   *Check:* The function receives an SGD instance instead of Adam.

---

### 5. The "Orchestrator" (Pipeline & API)
**File:** `05_pipeline/pipeline.py`
**Focus:** `Project` API, dependencies, and memoization.

*   **Code:** A Python script using `Project` to load configs from `04_python_config`.
*   **Demo Scenarios:**
    1.  **Full Pipeline:** `python pipeline.py`
        *   *Logic:*
            1.  `proj.submit(train_cfg, sweep=grid, wait=True)`
            2.  Iterate results, pick best `save_dir`.
            3.  `eval_cfg.ckpt = best_dir`.
            4.  `proj.submit(eval_cfg)`.
        *   *Check:* Verify that Stage 2 (eval) points to the output of one of the Stage 1 tasks.
    2.  **Smart Resume:** Run `python pipeline.py` again.
        *   *Logic:* Use `proj.exists(cfg)` (wrapping `RunDiff`) before submitting.
        *   *Check:* The script prints "Skipping Training (Exists)" and moves immediately to Eval.

---

### Summary Table for Documentation

| Example | Key Concepts | FlexLock Features Tested |
| :--- | :--- | :--- |
| **01_Basics** | CLI, Scripts | `@flexcli`, `py2cfg` (implicit), `--sweep` (CLI/File) |
| **02_Repro** | State, Git, Data | `snapshot_config`, `run.lock`, `diff`, Data Hashing |
| **03_YAML** | Config Hierarchy | `-c`, `-s`, `-o` vs `-O`, Interpolation, `--sweep-from` |
| **04_Python** | Types, Objects | `-d`, `py2cfg` (nested), `instantiate`, Mutable Defaults |
| **05_Pipeline** | Workflow, DAG | `Project`, `submit()`, `wait=True`, Lineage passing |

