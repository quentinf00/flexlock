def collect_task_repos(cfg, tasks, task_to=None) -> Dict:
    """Repos to record in a sweep master's run.lock, including the tasks' own.

    ``extract_tracking_info(cfg)`` only sees the base config. When ``_target_``
    (or ``_snapshot_.repos``) lives in the tasks instead (a single HPC run, or
    ``--sweep-file`` of full configs), the base yields nothing, and since
    workers record tasks as deltas against the master, no code state would be
    recorded at all. Tasks are grouped by their ``_target_``/``_snapshot_``
    so the cost is one merge per distinct target, not per task.
    """
    repos, _, _ = extract_tracking_info(cfg)
    seen = set()
    expanded = []
    for task in tasks:
        if isinstance(task, (dict, DictConfig)) and "_stages_" in task:
            expanded.extend((stage, None) for stage in task["_stages_"])
        else:
            expanded.append((task, task_to))
    for task, target_path in expanded:
        node = task
        if target_path and isinstance(task, (dict, DictConfig)):
            node = OmegaConf.select(OmegaConf.create(task), target_path)
        if not isinstance(node, (dict, DictConfig)):
            continue
        target = node.get("_target_")
        snap = node.get("_snapshot_")
        if target is None and snap is None:
            continue
        key = (str(target), str(snap))
        if key in seen:
            continue
        seen.add(key)
        try:
            merged = merge_task_into_cfg(cfg, task, target_path)
            # Only repositories belong in the master's code snapshot. Future
            # task inputs and lineage are resolved and recorded by the worker.
            from .presets import controller_snapshot
            merged["_snapshot_"] = controller_snapshot(merged, defer_inputs=True)
            task_repos, _, _ = extract_tracking_info(merged)
        except Exception as exc:
            logger.debug(f"Could not extract repos from task {target}: {exc}")
            continue
        for name, info in task_repos.items():
            repos.setdefault(name, info)
    return repos
