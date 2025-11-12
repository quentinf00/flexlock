"""PBS backend for FlexLock parallel execution."""

import cloudpickle, subprocess, os
from pathlib import Path
import secrets
from .base import Backend, Job
from loguru import logger

class PBSJob(Job):
    """Represents a PBS job."""
    def __init__(self, job_id): self._id = job_id
    @property
    def job_id(self): return self._id

class PBSBackend(Backend):
    """Implements the FlexLock backend for PBS (Portable Batch System) job submission."""

    def __init__(
        self,
        folder: Path,
        startup_lines: list[str],
        configure_logging: bool = True,
        containerization: str | None = None,
        container_image: str | None = None,
        bind_mounts: list[str] | None = None,
    ):
        self.folder = folder
        self.folder.mkdir(parents=True, exist_ok=True)
        self.startup_lines = startup_lines
        self.configure_logging = configure_logging
        self.containerization = containerization
        self.container_image = container_image
        self.bind_mounts = bind_mounts or []

    def _make_script(
        self, pickled_path: Path
    ) -> str:
        """Generates the PBS submission script content."""
        lines = ["#!/bin/bash"]
        lines.extend(self.startup_lines)

        if self.configure_logging:
            lines.extend(
                [
                    f"#PBS -o {self.folder.absolute() / 'pbs.out'}",
                    f"#PBS -e {self.folder.absolute() / 'pbs.err'}",
                ]
            )
        python_script = [
            "import cloudpickle, sys, os",
            f"with open('{pickled_path}', 'rb') as f:",
            "    fn, a, kw = cloudpickle.load(f)",
            "fn(*a, **kw)",
        ]
        python_code = "\n".join(python_script)

        # Always bind the folder containing the pickled task
        all_bind_mounts = list(set([str(self.folder.absolute())] + self.bind_mounts))
        bind_str = " ".join(f"--bind {p}" for p in all_bind_mounts)

        if self.containerization == "singularity":
            lines.append(
                f"singularity exec {bind_str} {self.container_image} python - <<'PY'\n{python_code}\nPY"
            )
        elif self.containerization == "docker":
            bind_str = " ".join(f"-v {p}:{p}" for p in all_bind_mounts)
            lines.append(
                f"docker exec {bind_str} {self.container_image} python - <<'PY'\n{python_code}\nPY"
            )
        else:
            lines.extend(
                [
                    f"python - <<'PY'\n{python_code}\nPY",
                ]
            )

        return "\n".join(lines)

    def submit(self, fn, *args, **kwargs):
        """Submits a single function for execution as a PBS job."""
        data = (fn, args, kwargs)
        pkl_path = self.folder / f"task_{secrets.token_hex(4)}.pkl"
        with open(pkl_path, 'wb') as f:
            cloudpickle.dump(data, f)

        script_path = self.folder / f"job_{secrets.token_hex(4)}.pbs"
        script_path.write_text(self._make_script(pkl_path))

        out = subprocess.check_output(["qsub", str(script_path)], text=True).strip()
        job_id = out
        return PBSJob(job_id)

    def environment(self):
        """Returns a JobEnvironment object providing PBS-specific environment variables."""
        class Env:
            @property
            def global_rank(self): return int(os.getenv("OMPI_COMM_WORLD_RANK", 0))
            @property
            def world_size(self): return int(os.getenv("OMPI_COMM_WORLD_SIZE", 1))
        return Env()
