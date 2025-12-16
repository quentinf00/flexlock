This enhancement makes `FlexLock` much more versatile for quick experiments (e.g., sweeping a learning rate directly from the command line) without needing to modify Python or YAML files.

Here is the implementation plan and code for **Step 2 (The Runner Logic)** and **Step 4 (CLI Arguments)**.

### 1. Strategy

We will introduce three mutually exclusive flags to define the **Source** of the sweep, and one flag to define the **Target** (where to inject).

**The Source Flags:**
1.  `--sweep-key`: (Old behavior) Loads a list/dict from the loaded config.
2.  `--sweep-file`: Loads a list from a `.yaml`, `.json`, or `.txt` file.
3.  **`--sweep` (New)**: Parses a comma-separated string from the CLI.

**The Target Flag:**
*   `--sweep-target`:
    *   If **Provided**: The sweep values (primitives or dicts) are nested under this key.
    *   If **Missing**: The sweep values *must* be dictionaries and are merged at the root of the node.

---

### 2. Implementation: `flexlock/runner.py`

I will add a `_load_sweep_tasks` method to the runner to handle the parsing logic.

```python
# flexlock/runner.py

import sys
import argparse
import json
import csv
from pathlib import Path
from typing import List, Any, Dict

from omegaconf import OmegaConf, DictConfig, ListConfig, open_dict
from hydra.utils import instantiate
from loguru import logger

# ... previous imports (utils, parallel, snapshot) ...

class FlexLockRunner:
    def __init__(self):
        self.parser = self._build_parser()

    def _build_parser(self):
        parser = argparse.ArgumentParser(description="FlexLock Execution Manager")

        # ... Existing Config/Select args ...
        parser.add_argument("--defaults", "-d", help="Python import path for default config")
        parser.add_argument("--config", "-c", help="Path to base YAML config file")
        parser.add_argument("--select", "-s", help="Dot-separated key to select the node to run")
        
        # ... Existing Override args (-m, -o, -M, -O) ...
        parser.add_argument("--merge", "-m", help="Merge file into Root config")
        parser.add_argument("--overrides", "-o", nargs="*", default=[], help="Dot-list overrides for Root")
        parser.add_argument("--merge-after-select", "-M", help="Merge file into Selected config")
        parser.add_argument("--overrides-after-select", "-O", nargs="*", default=[], help="Dot-list overrides for Selected")

        # --- NEW SWEEP ARGUMENTS ---
        sweep_group = parser.add_argument_group("Sweep Configuration")
        
        # Source (Mutually Exclusive)
        source = sweep_group.add_mutually_exclusive_group()
        source.add_argument("--sweep-key", help="Key in config containing the sweep list (e.g. 'experiments.grid')")
        source.add_argument("--sweep-file", help="Path to a file (yaml, json, txt) containing the sweep list")
        source.add_argument("--sweep", help="Comma-separated values (e.g. '0.01,0.02' or 'lr=0.1,lr=0.2')")

        # Injection Target
        sweep_group.add_argument(
            "--sweep-target", 
            help="Dot-path key to inject the sweep value into (e.g. 'optimizer.lr'). "
                 "If omitted, sweep items are merged at the root."
        )

        # Execution
        parser.add_argument("--n_jobs", type=int, default=1, help="Number of parallel jobs")
        
        return parser

    def _parse_cli_sweep(self, sweep_str: str) -> List[Any]:
        """Parses a comma-separated string into a list of values or dicts."""
        # Use csv reader to handle quoted strings correctly
        reader = csv.reader([sweep_str], skipinitialspace=True)
        items = next(reader)
        
        parsed_items = []
        for item in items:
            # Check for "key=value" format to support simple dict overrides
            if "=" in item:
                # This returns a DictConfig
                try:
                    conf = OmegaConf.from_dotlist([item])
                    # Convert to primitive dict
                    parsed_items.append(OmegaConf.to_container(conf))
                except Exception:
                    # Fallback to string if parsing fails
                    parsed_items.append(item)
            else:
                # Try to cast to int/float/bool, fallback to string
                try:
                    # YAML safe load handles typing (1 -> int, 1.0 -> float, true -> bool)
                    val = yaml.safe_load(item)
                    parsed_items.append(val)
                except Exception:
                    parsed_items.append(item)
        return parsed_items

    def _load_sweep_tasks(self, args, root_cfg) -> List[Dict]:
        """
        Extracts and normalizes the sweep list based on CLI arguments.
        Returns a list of Dictionaries (Tasks).
        """
        raw_tasks = None

        # 1. Determine Source
        if args.sweep_key:
            raw_tasks = OmegaConf.select(root_cfg, args.sweep_key)
            if raw_tasks is None:
                logger.error(f"Sweep key '{args.sweep_key}' not found in config.")
                sys.exit(1)
            # Convert ListConfig to primitive list
            if isinstance(raw_tasks, (ListConfig, DictConfig)):
                raw_tasks = OmegaConf.to_container(raw_tasks, resolve=True)

        elif args.sweep_file:
            fpath = Path(args.sweep_file)
            if not fpath.exists():
                logger.error(f"Sweep file '{fpath}' not found.")
                sys.exit(1)
            
            if fpath.suffix in ['.yaml', '.yml']:
                raw_tasks = OmegaConf.to_container(OmegaConf.load(fpath), resolve=True)
            elif fpath.suffix == '.json':
                with open(fpath) as f:
                    raw_tasks = json.load(f)
            else:
                # Text file: Assume one value per line
                with open(fpath) as f:
                    # strip whitespace and skip empty lines
                    raw_tasks = [line.strip() for line in f if line.strip()]
                    # Attempt type conversion via YAML
                    raw_tasks = [yaml.safe_load(t) for t in raw_tasks]

        elif args.sweep:
            raw_tasks = self._parse_cli_sweep(args.sweep)

        if raw_tasks is None:
            return []

        # Ensure raw_tasks is a list (handle single dict/value case if user messed up config)
        if not isinstance(raw_tasks, list):
            raw_tasks = [raw_tasks]

        # 2. Normalize based on Target
        final_tasks = []
        
        if args.sweep_target:
            # Injection Mode: Wrap value into {target: value}
            for val in raw_tasks:
                # Create a structure: e.g., target="opt.lr", val=0.01 -> {"opt": {"lr": 0.01}}
                # OmegaConf.from_dotlist expects "key=value", but we have the value object.
                # Simplest way: create a dummy config and merge
                
                # Check if val is already a dict (ambiguous case, but allowed)
                # e.g. sweep-target="opt", val={"lr": 0.1} -> opt.lr = 0.1
                
                # We construct the nested dict manually or via OmegaConf
                wrapper = OmegaConf.create()
                OmegaConf.update(wrapper, args.sweep_target, val)
                final_tasks.append(OmegaConf.to_container(wrapper))
        else:
            # Root Merge Mode: Values MUST be dicts
            for i, task in enumerate(raw_tasks):
                if not isinstance(task, dict):
                    logger.error(
                        f"Sweep item #{i} ({task}) is not a dictionary. "
                        f"You must provide --sweep-target to inject primitive values."
                    )
                    sys.exit(1)
                final_tasks.append(task)

        return final_tasks

    def run(self, cli_args=None, base_cfg=None):
        args = self.parser.parse_args(cli_args)
        
        # ... (Load Root Config Logic) ...
        root_cfg = self.load_config(args, base_cfg)

        # ... (Selection Logic) ...
        node_cfg = root_cfg
        if args.select:
            node_cfg = OmegaConf.select(root_cfg, args.select)
            if node_cfg is None:
                logger.error(f"Selection '{args.select}' returned None.")
                sys.exit(1)

        # ... (Inner Overrides Logic) ...
        if args.merge_after_select: 
            node_cfg.merge_with(OmegaConf.load(args.merge_after_select))
        if args.overrides_after_select: 
            node_cfg.merge_with(OmegaConf.from_dotlist(args.overrides_after_select))

        # --- SWEEP HANDLING ---
        tasks = self._load_sweep_tasks(args, root_cfg)

        # Prepare node (save_dir injection)
        node_cfg = self._prepare_node(node_cfg)

        if tasks:
            logger.info(f"Running sweep with {len(tasks)} tasks.")
            # Note: We pass node_cfg as the template. 
            # tasks are merged into it by the executor.
            executor = ParallelExecutor(
                func=instantiate, 
                tasks=tasks, 
                cfg=node_cfg, 
                n_jobs=args.n_jobs
            )
            executor.run()
        else:
            # Single run
            snapshot(node_cfg, repos={"main": "."}) 
            instantiate(node_cfg)

```

### 3. Usage Examples

Here is how the new functionality looks in practice.

#### Scenario A: Simple Primitive Sweep (CLI)
You want to sweep the `p` parameter of the selected node.

```bash
# Injects p=10, then p=20 into 'stage1' config
flexlock -s stage1 --sweep "10,20" --sweep-target p
```

#### Scenario B: File-based Sweep (Text File)
You have a `seeds.txt` containing a list of integers.

```bash
# seeds.txt content:
# 42
# 101
# 999

# Injects global.seed=42, etc.
flexlock -s stage1 --sweep-file seeds.txt --sweep-target global.seed
```

#### Scenario C: Complex Dictionary Sweep (CLI)
You want to change multiple parameters at once without a config file.

```bash
# Runs 2 jobs:
# 1. {optimizer: {lr: 0.01}, batch_size: 32}
# 2. {optimizer: {lr: 0.05}, batch_size: 64}
# Note: No --sweep-target needed because items are implicit key-values.

flexlock -s stage1 --sweep "optimizer.lr=0.01,optimizer.lr=0.05" \
         --overrides-after-select "batch_size=32" # Applies to both
```
*Correction on Scenario C:* My parsing logic above handles `key=value` strings in the CLI CSV. However, comma splitting is tricky if the value contains commas.
*   Input: `optimizer.lr=0.01,batch=32` -> This is parsed as **two items** in the sweep list:
    1. `{'optimizer': {'lr': 0.01}}`
    2. `{'batch': 32}`
    This creates 2 jobs, one setting LR, one setting Batch. It does **not** create one job with both.
*   **To do complex overrides per job via CLI**, users should use `--sweep-key` (YAML list defined in config) or `--sweep-file` (YAML/JSON file). The CLI `--sweep` is best reserved for single-variable lists or simple override lists.

#### Scenario D: Targeting a specific sub-node
If your config has a deeply nested object that you want to replace entirely.

```bash
# Injects the dictionary into the 'optimizer' key
flexlock -s stage1 \
         --sweep "{'_target_': 'Adam', 'lr': 1e-3},{'_target_': 'SGD', 'lr': 0.1}" \
         --sweep-target optimizer
```

### 4. Implementation Details (Dependencies)

*   **`csv`**: Used to parse the `--sweep` string properly (handling quotes ` "a,b",c `).
*   **`yaml.safe_load`**: Used to auto-cast strings ("10" -> 10, "true" -> True) so users don't end up with string types for integer hyperparameters.
*   **`OmegaConf.update`**: Used in `_load_sweep_tasks` to create the nested structure when `--sweep-target` is used.

This enhancement fulfills your requirements for **flexible sources** (CLI, File, Config) and **controlled injection** (Root vs Target Key).
