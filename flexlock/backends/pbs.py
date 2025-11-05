# flexlock/backends/pbs.py
import cloudpickle, subprocess, os
from pathlib import Path
import secrets
from .base import Backend, Job

class PBSJob(Job):
    def __init__(self, job_id): self._id = job_id
    @property
    def job_id(self): return self._id

class PBSBackend(Backend):
    def __init__(self, folder: Path, **pbs_kwargs):
        self.folder = folder
        self.folder.mkdir(parents=True, exist_ok=True)
        self.kwargs = pbs_kwargs

    def _make_script(self, pickled_path: Path, is_array: bool = False, array_size: int = 0) -> str:
        lines = [
            "#!/bin/bash",
            f"#PBS -N flexlock",
            f"#PBS -l nodes=1",
            f"#PBS -l ncpus={self.kwargs.get('num_cpus',1)}",
            f"#PBS -l walltime={self.kwargs.get('time','01:00:00')}",
            f"#PBS -q {self.kwargs.get('queue','batch')}",
        ]
        # Add extra directives if provided
        extra_directives = self.kwargs.get('extra_directives', [])
        if isinstance(extra_directives, str):
            extra_directives = [extra_directives]
        lines.extend(extra_directives)

        if is_array and array_size > 1:
            lines.append(f"#PBS -J 0-{array_size-1}")

        lines += [
            "module load python 2>/dev/null || true",
            f"python - <<'PY'\nimport cloudpickle, sys, os\n"
            f"with open('{pickled_path}', 'rb') as f:\n"
            f"    data = cloudpickle.load(f)\n"
            f"if isinstance(data, list):\n"
            f"    all_same = all(d == data[0] for d in data) if len(data) > 1 else True\n"
            f"    idx = int(os.getenv('PBS_ARRAY_INDEX', 0))\n"
            f"    fn, a, kw = data[0] if all_same else data[idx]\n"
            f"else:\n"
            f"    fn, a, kw = data\n"
            f"fn(*a, **kw)\nPY",
        ]
        return "\n".join(lines)

    def submit(self, fn, *args, **kwargs):
        data = (fn, args, kwargs)
        pkl_path = self.folder / f"task_{secrets.token_hex(4)}.pkl"
        with open(pkl_path, 'wb') as f:
            cloudpickle.dump(data, f)

        script_path = self.folder / f"job_{secrets.token_hex(4)}.pbs"
        script_path.write_text(self._make_script(pkl_path))

        out = subprocess.check_output(["qsub", str(script_path)], text=True).strip()
        job_id = out
        return PBSJob(job_id)

    def map_array(self, fn, params_list: list):
        data = [(fn, p if isinstance(p, tuple) else (p,), {}) for p in params_list]
        pkl_path = self.folder / f"array_{secrets.token_hex(4)}.pkl"
        with open(pkl_path, 'wb') as f:
            cloudpickle.dump(data, f)

        script_path = self.folder / f"array_job_{secrets.token_hex(4)}.pbs"
        script_path.write_text(self._make_script(pkl_path, is_array=True, array_size=len(params_list)))

        out = subprocess.check_output(["qsub", str(script_path)], text=True).strip()
        job_id = out  # e.g., "12345[]"
        return [PBSJob(f"{job_id}[{i}]") for i in range(len(params_list))]

    def environment(self):
        class Env:
            @property
            def global_rank(self): return int(os.getenv("OMPI_COMM_WORLD_RANK", 0))
            @property
            def world_size(self): return int(os.getenv("OMPI_COMM_WORLD_SIZE", 1))
        return Env()
