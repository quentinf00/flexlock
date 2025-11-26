"""Slurm backend for FlexLock parallel execution."""

import cloudpickle, subprocess, os
from pathlib import Path
import secrets  # Better random for filenames
from .base import Backend, Job, JobEnvironment


class SlurmJob(Job):
    """Represents a Slurm job."""

    def __init__(self, job_id):
        self._id = job_id

    @property
    def job_id(self):
        return self._id


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
        return SlurmJob(job_id)

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
