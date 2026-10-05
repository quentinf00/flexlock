"""Explicit live CPU acceptance: failed producer blocks an afterok consumer.

Run manually: python tests/slurm_failure_acceptance.py /jobscratch/qfebvre/NAME
Submits two one-CPU/1-GiB/one-minute jobs, cancels the blocked consumer, and
writes accounting evidence. This is deliberately outside automatic pytest.
"""

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from flexlock.backends.slurm import SlurmBackend
from flexlock.taskdb import get_all_tasks, queue_tasks
from flexlock.worker import worker_loop


def fail_stage(cfg):
    raise RuntimeError("live acceptance injected producer failure")


def consume(marker):
    Path(marker).touch()


def main():
    scratch = Path(sys.argv[1]).resolve()
    scratch.mkdir(parents=True, exist_ok=False)
    db = scratch / "producer.tasks.db"
    queue_tasks(db, [{"_stages_": [{"save_dir": str(scratch / "producer"),
                                   "_snapshot_": {"repos": {}}}]}])
    startup = ["#SBATCH --partition=cpu", "#SBATCH --cpus-per-task=1",
               "#SBATCH --mem=1G", "#SBATCH --time=00:01:00",
               f"cd {ROOT}", f"export PYTHONPATH={ROOT}",
               "export OMP_NUM_THREADS=1", "export OPENBLAS_NUM_THREADS=1"]
    marker = scratch / "consumer-executed"
    jobs = []
    evidence = {}
    try:
        producer = SlurmBackend(scratch / "producer-job", startup, python_exe=sys.executable).submit(
            worker_loop, fail_stage, {}, None, db,
        )
        jobs.append(producer.job_id)
        consumer = SlurmBackend(scratch / "consumer-job", startup, python_exe=sys.executable,
                                after=[producer.job_id]).submit(consume, str(marker))
        jobs.append(consumer.job_id)
        evidence["jobs"] = {"producer": producer.job_id, "consumer": consumer.job_id}
        (scratch / "acceptance.json").write_text(json.dumps(evidence, indent=2))
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            accounting = subprocess.check_output([
                "sacct", "-j", producer.job_id, "--noheader", "--parsable2",
                "--format=JobIDRaw,State,ExitCode"], text=True)
            evidence["producer_accounting"] = accounting
            evidence["producer_queue"] = subprocess.check_output([
                "squeue", "-j", producer.job_id, "--noheader", "--format=%T|%r"], text=True)
            if any(line.startswith(producer.job_id + "|FAILED|") for line in accounting.splitlines()):
                break
            time.sleep(3)
        else:
            raise RuntimeError("Producer did not reach FAILED within 180 seconds")
        evidence["consumer_queue"] = subprocess.check_output([
            "squeue", "-j", consumer.job_id, "--noheader", "--format=%T|%r"], text=True)
        evidence["consumer_accounting"] = subprocess.check_output([
            "sacct", "-j", consumer.job_id, "--noheader", "--parsable2",
            "--format=JobIDRaw,State,ExitCode"], text=True)
        evidence["task_status"] = get_all_tasks(db)[0]["status"]
        producer_row = next(line for line in accounting.splitlines()
                            if line.startswith(producer.job_id + "|"))
        assert producer_row.split("|")[2].split(":")[0] != "0", producer_row
        assert evidence["task_status"] == "failed"
        assert not marker.exists(), "Dependent consumer executed despite producer failure"
        assert ("Dependency" in evidence["consumer_queue"] or
                "CANCELLED" in evidence["consumer_accounting"]), evidence
        evidence["passed"] = True
    except BaseException as exc:
        evidence["error"] = str(exc)
        evidence["passed"] = False
        raise
    finally:
        for job_id in jobs:
            subprocess.run(["scancel", job_id], check=False, capture_output=True)
        evidence["consumer_executed"] = marker.exists()
        (scratch / "acceptance.json").write_text(json.dumps(evidence, indent=2))
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
