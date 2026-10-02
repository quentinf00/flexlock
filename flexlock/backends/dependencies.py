"""Normalize scheduler dependencies shared by Slurm, PBS, and the API."""

import re

from ..exceptions import FlexLockValidationError


def normalize_after(after):
    """Return distinct job IDs from a sequence or colon-separated string."""
    if after is None:
        return []
    values = after.split(":") if isinstance(after, str) else after
    if isinstance(values, int):
        values = [values]
    ids = []
    for value in values:
        job_id = str(value).strip()
        if not re.fullmatch(r"\d+(?:_\d+)?(?:\[\d*\])?(?:\.[A-Za-z0-9_.-]+)?", job_id):
            raise FlexLockValidationError(f"Invalid scheduler job ID in after: {value!r}")
        if job_id not in ids:
            ids.append(job_id)
    return ids


def validate_after(after, slurm_config, pbs_config):
    ids = normalize_after(after)
    if ids and not (slurm_config or pbs_config):
        raise FlexLockValidationError("after/--after requires a Slurm or PBS backend.")
    if slurm_config and any(not re.fullmatch(r"\d+(?:_\d+)?", job_id) for job_id in ids):
        raise FlexLockValidationError("Slurm dependencies require numeric job IDs.")
    return ids
