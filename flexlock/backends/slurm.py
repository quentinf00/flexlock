"""Slurm backend for FlexLock parallel execution."""

import cloudpickle, subprocess, os
from pathlib import Path
import secrets  # Better random for filenames
import time
from .base import Backend, Job, JobEnvironment
from loguru import logger


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
    ):
        self.folder = folder
        self.folder.mkdir(parents=True, exist_ok=True)
        self.startup_lines = startup_lines
        self.configure_logging = configure_logging
        self.python_exe = python_exe

    def _make_script(self, pickled_path: Path) -> str:
        """Generates the Slurm submission script content."""
        lines = ["#!/bin/bash"]
        lines.extend(self.startup_lines)

        if self.configure_logging:
            lines.extend(
                [
                    f"#SBATCH --output={self.folder.absolute() / 'slurm.out'}",
                    f"#SBATCH --error={self.folder.absolute() / 'slurm.err'}",
                ]
            )

        python_script = [
            "import cloudpickle, sys, os",
            f"with open('{pickled_path}', 'rb') as f:",
            "    data = cloudpickle.load(f)",
            "    fn, a, kw = data",
            "fn(*a, **kw)",
        ]
        python_code = "\n".join(python_script)
        lines.extend(
            [
                f"{self.python_exe} - <<'PY'\n{python_code}\nPY",
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
        script_path.write_text(self._make_script(pkl_path))

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
                stderr=subprocess.DEVNULL
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
                stderr=subprocess.DEVNULL
            )
            status = out.strip().split('\n')[0].strip()
            if status:
                return status
        except subprocess.CalledProcessError:
            pass

        logger.warning(f"Could not determine status for Slurm job {job_id}")
        return 'unknown'

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
            if status in ['COMPLETED', 'completed']:
                logger.info(f"Slurm job {job_id} completed")
                return True

            # Failed states
            if status in ['FAILED', 'TIMEOUT', 'CANCELLED', 'NODE_FAIL', 'PREEMPTED', 'OUT_OF_MEMORY']:
                logger.error(f"Slurm job {job_id} failed with status: {status}")
                return False

            # Check timeout
            if timeout and (time.time() - start_time) > timeout:
                logger.error(f"Slurm job {job_id} timed out after {timeout}s")
                return False

            # Still running or pending
            if status in ['PENDING', 'RUNNING', 'CONFIGURING']:
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
