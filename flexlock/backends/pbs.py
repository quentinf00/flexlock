"""PBS backend for FlexLock parallel execution."""

import cloudpickle, subprocess, os
from pathlib import Path
import secrets
import time
from .base import Backend, Job, JobEnvironment
from loguru import logger


class PBSJob(Job):
    """Represents a PBS job."""

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


class PBSBackend(Backend):
    """Implements the FlexLock backend for PBS (Portable Batch System) job submission."""

    def __init__(
        self,
        folder: Path,
        startup_lines: list[str],
        configure_logging: bool = True,
        configure_name: bool = True,
        python_exe: str = "python",
    ):
        self.folder = folder
        self.folder.mkdir(parents=True, exist_ok=True)
        self.startup_lines = startup_lines
        self.configure_logging = configure_logging
        self.configure_name = configure_name
        self.python_exe = python_exe

    def _make_script(self, pickled_path: Path) -> str:
        """Generates the PBS submission script content."""
        lines = ["#!/bin/bash"]

        if self.configure_name:
            lines.extend(
                [
                    f"#PBS -N {self.folder.parent.stem}",
                ]
            )
        if self.configure_logging:
            lines.extend(
                [
                    f"#PBS -o {self.folder.absolute() / 'pbs.out'}",
                    f"#PBS -e {self.folder.absolute() / 'pbs.err'}",
                ]
            )
        lines.extend(self.startup_lines)
        python_script = [
            "import cloudpickle, sys, os",
            f"with open('{pickled_path}', 'rb') as f:",
            "    fn, a, kw = cloudpickle.load(f)",
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
        """Submits a single function for execution as a PBS job."""
        data = (fn, args, kwargs)
        pkl_path = self.folder / f"task_{secrets.token_hex(4)}.pkl"
        with open(pkl_path, "wb") as f:
            cloudpickle.dump(data, f)

        script_path = self.folder / f"job_{secrets.token_hex(4)}.pbs"
        script_path.write_text(self._make_script(pkl_path))

        out = subprocess.check_output(["qsub", str(script_path)], text=True).strip()
        job_id = out
        return PBSJob(job_id, backend=self)

    def check_status(self, job_id: str) -> str:
        """
        Check the status of a PBS job.

        Returns:
            Status string: 'Q' (queued), 'R' (running), 'C' (completed), 'E' (exiting), 'H' (held), or 'unknown'
        """
        try:
            # Use qstat -x to get info about finished jobs too
            out = subprocess.check_output(
                ["qstat", "-x", job_id], text=True, stderr=subprocess.DEVNULL
            )
            lines = out.strip().split("\n")
            if len(lines) > 2:  # Header + job line
                # Parse the status from qstat output
                job_line = lines[2]  # Skip two header lines
                parts = job_line.split()
                if len(parts) >= 10:
                    return parts[9]  # Job state is usually the 10th column
        except subprocess.CalledProcessError:
            # Job not found, likely completed and cleaned up
            return "C"
        except Exception as e:
            logger.warning(f"Failed to check PBS job status for {job_id}: {e}")
        return "unknown"

    def wait_for_job(self, job_id: str, timeout=None, poll_interval=5) -> bool:
        """
        Wait for a PBS job to complete.

        Args:
            job_id: PBS job identifier
            timeout: Maximum time to wait in seconds (None for no timeout)
            poll_interval: Time between status checks in seconds

        Returns:
            True if job completed successfully, False otherwise
        """
        start_time = time.time()
        logger.info(f"Waiting for PBS job {job_id} to complete...")

        while True:
            status = self.check_status(job_id)

            # Completed states
            if status in ["C", "completed"]:
                logger.info(f"PBS job {job_id} completed")
                return True

            # Failed states
            if status in ["E", "F", "failed"]:
                logger.error(f"PBS job {job_id} failed with status: {status}")
                return False

            # Check timeout
            if timeout and (time.time() - start_time) > timeout:
                logger.error(f"PBS job {job_id} timed out after {timeout}s")
                return False

            # Still running or queued
            if status in ["Q", "R", "H"]:
                logger.debug(f"PBS job {job_id} status: {status}")
            else:
                logger.debug(f"PBS job {job_id} unknown status: {status}")

            time.sleep(poll_interval)

    def cancel_job(self, job_id: str) -> bool:
        """
        Cancel a PBS job.

        Args:
            job_id: PBS job identifier

        Returns:
            True if cancellation succeeded, False otherwise
        """
        try:
            subprocess.check_call(["qdel", job_id], stderr=subprocess.DEVNULL)
            logger.info(f"Cancelled PBS job {job_id}")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to cancel PBS job {job_id}: {e}")
            return False

    def environment(self):
        """Returns a JobEnvironment object providing PBS-specific environment variables."""

        class Env(JobEnvironment):
            @property
            def global_rank(self):
                return int(os.getenv("OMPI_COMM_WORLD_RANK", 0))

            @property
            def world_size(self):
                return int(os.getenv("OMPI_COMM_WORLD_SIZE", 1))

        return Env()
