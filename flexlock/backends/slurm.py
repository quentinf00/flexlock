"""Slurm backend for FlexLock parallel execution."""

import cloudpickle, subprocess, os
import re
from pathlib import Path
import secrets  # Better random for filenames
import time
from .base import Backend, Job, JobEnvironment
from loguru import logger
from .dependencies import validate_after


# Heuristics for recognising environment-activation lines in startup_lines.
# These commands prepare the compute-node shell (PATH, libs, interpreters)
# before the pickled task runs. Missing them is the wiki's most common
# silent-failure mode ("import fails on node, looks fine locally").
_ENV_ACTIVATION_PATTERNS = (
    re.compile(r"\beval\s"),                   # eval "$(...)" — pixi shell-hook, conda hook
    re.compile(r"\bsource\s"),                 # source venv/bin/activate
    re.compile(r"\bconda\s+activate\b"),
    re.compile(r"\bmamba\s+activate\b"),
    re.compile(r"\bmodule\s+(load|add)\b"),    # HPC module systems
    re.compile(r"\bpixi\s+(run|shell)\b"),
    re.compile(r"\bspack\s+load\b"),
)


def validate_slurm_script(
    script: str, *, expects_gpu: bool = False
) -> list[str]:
    """Return a list of human-readable warning strings for a Slurm script.

    Empty list means no concerns. Each warning is independent — callers
    decide whether to log or print. Validation is intentionally lenient
    (warn, never fail) because power-user setups may intentionally omit
    pieces this function expects.
    """
    warnings: list[str] = []

    sbatch_lines = [
        ln.strip() for ln in script.splitlines() if ln.strip().startswith("#SBATCH")
    ]
    body_lines = [
        ln for ln in script.splitlines()
        if ln.strip() and not ln.strip().startswith(("#!", "#SBATCH"))
    ]

    # 1. --partition is the most common forgotten directive — jobs land on
    #    the default queue, often a CPU one when a GPU was wanted.
    if not any("--partition" in ln or "-p " in ln for ln in sbatch_lines):
        warnings.append(
            "No --partition directive found. The job will land on the "
            "cluster's default queue, which may not be the one you want."
        )

    # 2. cd to the submission dir keeps relative paths in user code working
    #    from the compute node.
    if not any(re.search(r"\bcd\b", ln) for ln in body_lines):
        warnings.append(
            "No 'cd' command in startup_lines. Relative paths in your "
            "code will resolve against the compute node's HOME, not the "
            "submission directory. Add 'cd $SLURM_SUBMIT_DIR' to "
            "startup_lines."
        )

    # 3. Some form of env activation is almost always needed.
    if not any(p.search(ln) for ln in body_lines for p in _ENV_ACTIVATION_PATTERNS):
        warnings.append(
            "No environment-activation command detected in startup_lines "
            "(eval, source, conda/mamba activate, module load, pixi run/shell). "
            "Python imports may fail on the compute node."
        )

    # 4. If the caller flagged this as a GPU config but the script doesn't
    #    request a GPU, surface it.
    if expects_gpu and not any(
        "--gres" in ln or "--gpus" in ln for ln in sbatch_lines
    ):
        warnings.append(
            "GPU config requested but no --gres or --gpus directive in "
            "startup_lines. The job will run on CPU silently."
        )

    return warnings


class SlurmJob(Job):
    """Represents a Slurm job."""

    def __init__(self, job_id, backend=None):
        self._id = job_id
        self._backend = backend

    @property
    def job_id(self):
        return self._id

    def status(self):
        """Get current job status."""
        if self._backend:
            return self._backend.check_status(self._id)
        return "unknown"

    def wait(self, timeout=None, poll_interval=5):
        """Wait for job to complete."""
        if self._backend:
            return self._backend.wait_for_job(self._id, timeout, poll_interval)
        return False

    def cancel(self):
        """Cancel the job."""
        if self._backend:
            return self._backend.cancel_job(self._id)
        return False


class SlurmBackend(Backend):
    """Implements the FlexLock backend for Slurm job submission."""

    def __init__(
        self,
        folder: Path,
        startup_lines: list[str],
        configure_logging: bool = True,
        python_exe="python",
        after=None,
    ):
        self.folder = folder
        self.folder.mkdir(parents=True, exist_ok=True)
        self.startup_lines = startup_lines
        self.configure_logging = configure_logging
        self.python_exe = python_exe
        self.after = validate_after(after, True, False)
        if self.after and any(
            re.search(r"^\s*#SBATCH\s+.*(?:--dependency(?:[=\s])|-d\s)", line)
            for line in startup_lines
        ):
            from ..exceptions import FlexLockValidationError

            raise FlexLockValidationError(
                "Specify dependencies with after/--after or startup_lines, not both."
            )

    def render_script(self, pickled_path: "Path | str | None" = None) -> str:
        """Render the would-be Slurm script without submitting.

        ``pickled_path`` defaults to a placeholder path so users can preview
        the script (e.g. via ``dry_run=True``) before any pickling happens.
        """
        return self._make_script(Path(pickled_path or "<pickled-task.pkl>"))

    def _make_script(self, pickled_path: Path) -> str:
        """Generates the Slurm submission script content."""
        lines = ["#!/bin/bash"]
        if self.after:
            lines.append(f"#SBATCH --dependency=afterok:{':'.join(self.after)}")
        # SBATCH directives must all come before any shell commands —
        # Slurm stops parsing directives at the first non-comment, non-blank line.
        if self.configure_logging:
            lines.extend(
                [
                    f"#SBATCH --output={self.folder.absolute() / 'slurm.out'}",
                    f"#SBATCH --error={self.folder.absolute() / 'slurm.err'}",
                ]
            )
        lines.extend(self.startup_lines)

        python_script = [
            "import cloudpickle, sys, os",
            # Make the submission directory importable so that _target_ strings
            # like 'train.main' resolve in the worker as they do on the
            # submitting machine. Append (not insert-at-0): cwd is a fallback
            # only — it must never shadow installed packages, or a local file
            # colliding with a dependency torch/lightning imports lazily during
            # CUDA init can break the GPU stack in confusing ways.
            f"sys.path.append({str(Path.cwd().resolve())!r})",
            # The __main__ guard is mandatory: with the `spawn`/`forkserver`
            # multiprocessing start methods (e.g. torch DataLoader workers),
            # the child re-imports this bootstrap as `__mp_main__`. Without the
            # guard the task fn would run again in every worker.
            "def _flexlock_run():",
            f"    with open({str(pickled_path)!r}, 'rb') as f:",
            "        fn, a, kw = cloudpickle.load(f)",
            "    fn(*a, **kw)",
            "if __name__ == '__main__':",
            "    _flexlock_run()",
        ]
        python_code = "\n".join(python_script)
        # Write the bootstrap to a real file (not stdin). Running via a heredoc
        # pipe (`python - <<PY`) leaves __main__.__file__ == '<stdin>', which
        # `spawn`/`forkserver` workers cannot re-import (FileNotFoundError on
        # '<stdin>'). A concrete path makes the main module importable.
        bootstrap_path = f"{pickled_path}.main.py"
        lines.extend(
            [
                f"cat > {bootstrap_path} <<'PY'\n{python_code}\nPY",
                f"{self.python_exe} {bootstrap_path}",
            ]
        )
        return "\n".join(lines)

    def submit(self, fn, *args, **kwargs):
        """Submits a single function for execution as a Slurm job."""
        data = (fn, args, kwargs)
        pkl_path = self.folder / f"task_{secrets.token_hex(4)}.pkl"
        with open(pkl_path, "wb") as f:
            cloudpickle.dump(data, f)

        script_path = self.folder / f"job_{secrets.token_hex(4)}.slurm"
        script = self._make_script(pkl_path)
        script_path.write_text(script)

        for w in validate_slurm_script(script):
            logger.warning(f"Slurm config: {w}")

        out = subprocess.check_output(["sbatch", str(script_path)], text=True).strip()
        job_id = out.split()[-1]
        return SlurmJob(job_id, backend=self)

    def check_status(self, job_id: str) -> str:
        """
        Check the status of a Slurm job.

        Returns:
            Status string: 'PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED', or 'unknown'
        """
        try:
            # Use squeue for running/pending jobs
            out = subprocess.check_output(
                ["squeue", "-j", job_id, "-h", "-o", "%T"],
                text=True,
                stderr=subprocess.DEVNULL,
            )
            status = out.strip()
            if status:
                return status
        except subprocess.CalledProcessError:
            pass  # Job not in queue, check sacct

        try:
            # Use sacct for completed jobs
            out = subprocess.check_output(
                ["sacct", "-j", job_id, "-n", "-o", "State"],
                text=True,
                stderr=subprocess.DEVNULL,
            )
            status = out.strip().split("\n")[0].strip()
            if status:
                return status
        except subprocess.CalledProcessError:
            pass

        logger.warning(f"Could not determine status for Slurm job {job_id}")
        return "unknown"

    # States that mean the job has definitively ended. Anything else —
    # active (PENDING/RUNNING/...) OR ambiguous ("unknown") — is NOT terminal.
    TERMINAL_STATES = frozenset({
        "COMPLETED", "FAILED", "TIMEOUT", "CANCELLED", "NODE_FAIL",
        "PREEMPTED", "OUT_OF_MEMORY", "BOOT_FAIL", "DEADLINE", "REVOKED",
        "SPECIAL_EXIT",
    })

    def is_terminal(self, job_id: str) -> bool:
        """Return True only when the scheduler confirms the job has ended.

        Used by the controller to decide whether tasks still marked
        ``running``/``pending`` have been orphaned by a dead job. This is
        deliberately conservative: ``unknown`` (e.g. ``squeue`` doesn't list a
        just-submitted job yet and ``sacct`` hasn't recorded it) and all
        active states return ``False``, so a transient/racy status read never
        causes a healthy job to be reconciled away.
        """
        raw = self.check_status(job_id).strip()
        if not raw:
            return False
        # Normalize forms like "CANCELLED by 12345" / "CANCELLED+".
        token = raw.upper().split()[0].rstrip("+")
        return token in self.TERMINAL_STATES

    def wait_for_job(self, job_id: str, timeout=None, poll_interval=5) -> bool:
        """
        Wait for a Slurm job to complete.

        Args:
            job_id: Slurm job identifier
            timeout: Maximum time to wait in seconds (None for no timeout)
            poll_interval: Time between status checks in seconds

        Returns:
            True if job completed successfully, False otherwise
        """
        start_time = time.time()
        logger.info(f"Waiting for Slurm job {job_id} to complete...")

        while True:
            status = self.check_status(job_id)

            # Completed states
            if status in ["COMPLETED", "completed"]:
                logger.info(f"Slurm job {job_id} completed")
                return True

            # Failed states
            if status in [
                "FAILED",
                "TIMEOUT",
                "CANCELLED",
                "NODE_FAIL",
                "PREEMPTED",
                "OUT_OF_MEMORY",
            ]:
                logger.error(f"Slurm job {job_id} failed with status: {status}")
                return False

            # Check timeout
            if timeout and (time.time() - start_time) > timeout:
                logger.error(f"Slurm job {job_id} timed out after {timeout}s")
                return False

            # Still running or pending
            if status in ["PENDING", "RUNNING", "CONFIGURING"]:
                logger.debug(f"Slurm job {job_id} status: {status}")
            else:
                logger.debug(f"Slurm job {job_id} unknown status: {status}")

            time.sleep(poll_interval)

    def cancel_job(self, job_id: str) -> bool:
        """
        Cancel a Slurm job.

        Args:
            job_id: Slurm job identifier

        Returns:
            True if cancellation succeeded, False otherwise
        """
        try:
            subprocess.check_call(["scancel", job_id], stderr=subprocess.DEVNULL)
            logger.info(f"Cancelled Slurm job {job_id}")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to cancel Slurm job {job_id}: {e}")
            return False

    def environment(self):
        """Returns a JobEnvironment object providing Slurm-specific environment variables."""

        class Env(JobEnvironment):
            @property
            def global_rank(self):
                return int(os.getenv("SLURM_PROCID", 0))

            @property
            def world_size(self):
                return int(os.getenv("SLURM_NTASKS", 1))

        return Env()
