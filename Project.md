I want to develop the necessary tooling to improve my quality of life when developing ml experiments.

The requirements are:
- easy debugging when scripting
- no cost transition going from script to lib (function)
- easy exploration of different config
- lightweight config management
- automatic versioning of data and source code
- saving and restoring experiment
- browsing and comparing results across runs
- from simple case scripting to parallel execution (joblib or slurm)


I think I have an idea on how all this could be orchestrated, now I want to make it so that the usage is as light and painless as possible


# Easy debugging when scripting

Im quite happy with my current script to prod workflow:

I have the following skeleton:

```python
<my_stage.py>
from dataclass import dataclass
from omegaconf import OmegaConf
from pathlib import Path
from datetime import now

OmegaConf.register_resolver('now', lambda s: now().strftime(s), replace=True) # useful for automatic xp dir increment

@dataclass
class Config:
    save_dir = "results/<my_stage>/${now: %y%m%d-%H%M}"
    param = 1
    # All the parameters for the function goes here


def main(cfg: Config = OmegaConf.structured(Config()):
    try: 
        # %% the percent cell allows for interactive execution in IDEs like VSCode or jupyter console
        save_dir = Path(cfg.save_dir)
        save_dir.mkdir(parents=True, exist_ok=True)
        OmegaConf.resolve(cfg)
        OmegaConf.save(cfg, save_dir / 'config.yaml') # save config with

        # %%
        print(cfg.param)
        ...
    except Exception as e: #catch errors when executing full function
        import traceback
        print(traceback.exc_info()) # print traceback
    finally:
        return locals() # return locals state for further inspection in case or fail or success

if __name__ == '__main__':
    import my_stage
    import importlib as iml; iml.reload(my_stage) # reload in order not to restart the kernel at each iteration
    locals().update(my_stage.main()) # update kernel state with  latest execution locals
```

Using the above boilerplate, I can open a jupyter console, run the whole file, edit it, rerun, add configuration fields, use it (with autocomplete), when I get an error I can inspect the variables and run separate lines or  cells of the script progressively

Each run stores the config and relevant data in a different directory

Once I'm satisfied with my development, I know I have a function which I can configure.


## Having multiple config

Something that would be nice would be to be able to configure the script from the command line, a simple decorator like this could be considered:

```python
import argparse

def clicfg(fn):

    def wrapped():
        parser = argparse.ArgumentParser()
        parser.add_argument('--config', default=None)
        parser.add_argument('--experiment', default=None)
        parser.add_argument('--overrides_path', default=None)
        parser.add_argument('-o', '--overrides_dot', nargs='*', default=None)

        # if running in interactive window ignore sys.argv
        import sys
        if 'kernel/jupyter' in sys.argv[-1]: sys.argv.pop(-1)

        args = parser.parse_args()
        if args.config is not None:
            cfg = OmegaConf.load(args.config)
        if args.overrides_path is not None:
            overrides = OmegaConf.load(args.overrides_path)
            with OmegaConf.open_dict(cfg):
                cfg = OmegaConf.merge(cfg, overrides)
        if args.overrides_dot is not None: # TODO check
            overrides = OmegaConf.from_dotlist(args.overrides_dot)
            with OmegaConf.open_dict(cfg):
                cfg = OmegaConf.merge(cfg, overrides)

        if args.experiment is not None:
            cfg = OmegaConf.select(cfg, args.experiment)
        return fn(cfg)
    return wrapped
```

## Auto source versioning
The following function tracks the current repo, note that the 'results' directory should be gitignored to avoid versioning too much.
We should add an option to include/exclude files to be tracked (as glob pattern or regexp)

```python
import platform
from datetime import date

from git.repo import Repo as GitRepo
from git import IndexFile

def commit_cwd(branch, message, repo=None): # TODO add include and exclude and max size arguments
    repo = repo or GitRepo('.')
    index = IndexFile(repo)
    log_branch = getattr(repo.heads, branch, False) or repo.create_head(branch)

    to_add = (
                     set(repo.untracked_files)
                     | set([d.a_path or d.b_path for d in index.diff(None) if d.change_type != 'D'])
                     | set([d.a_path or d.b_path for d in index.diff(repo.head.commit) if d.change_type != 'A'])
             ) - set([d.a_path or d.b_path for d in index.diff(None) if d.change_type == 'D'])
    # TODO apply include and exlude filters
    # TODO add warning when adding file exceeding a certain size
    index.add(
        to_add,
        force=False,
        write=False,
        write_extension_data=True,
    )

    log_commit = index.commit(message, parent_commits=[log_branch.commit], head=False)
    log_branch.commit = log_commit
    return log_commit
```

then a decorator can run this checkpoint at each run

```python
def src(branch="run_logs", message="Checkpointing"): # add include exclude

    def decorator(fn):
        def wrapped():
            commit_cwd(branch, message)
            return fn()
        return wrapped
    return decorator
```

## Track data

Finally I want to be able to track when data changes from one experiment to the next.

Using a combination of 'dirhash' and 'xxhash' I can compute hashes for files and directory.

```python
from dirhash import dirhash
import xxhash
from pathlib import Path

def hash_data(path, match=None, ignore=None, jobs=4, algorithm=xxhash.xxh3_64, chunk_size=2**18)
    if Path(path).is_file():
        with open(path, 'rb') as f:
            x = algo()
            while True:
                data = f.read(chunk_size)
                if data is None:
                    break
                x.update(data)
        return x.hexdigest()

    return dirhash(path, match=match, ignore=ignore, jobs=jobs, algorithm=algorithm, chunk_size=chunk_size)
```

I want to trigger this in a non blocking way when running my function on some specific path that can be configured.
A decorator can be used to specify which data path to hash. A cache system can be useful to avoid recomputing hashes for unmodified data.

## Previous stages

A common usecase is to load data generated from a previous run, in this case I want to be able to specify that a certain folder is a run where all this state has been tracked (src commit, data hashes, config)

A similar decorator can be implemented to register this information

##  Run.lock
 I think for each run the state should be stored in a file "run.lock" that can be a yaml:
- the config
- the commit hash and the blob hashes of different files of interests
- the hashes of the tracked data
- the "run.lock"s information of all the previous stages

## Experiment Logging
The above workflow allows for tracing all necessary information to ensure reproducibility, however, comparing and browsing past runs can be cumbersome if you need to find you way in the different files.
This is why in practice using a tool like mlflow or tensorboard is very useful.
A common issue I encounterd was to log the artifacts, plots etc... in the main() function, which always caused issues when I wanted to add a logging feature without rerunning the stage.


Therefore I think I should organize my logging as such:

```python
def main(cfg)
    try:
        OmegaConf.resolve(cfg)
        ...
    finally:
        return cfg, locals()

def log_run(cfg):
    run_id = get_run_id(cfg.save_dir)
    with mlflow.start_run(run_id) as run:
        # Log run state
        if (Path(cfg.save_dir) / 'run.lock').exists():
            mlflow.log_params(
                pd.json_normalize(
                    OmegaConf.to_container(
                        OmegaConf.load((Path(cfg.save_dir) / 'run.lock'))
                    ),
                    sep=".",
                ).to_dict(orient="records")[0]
            )
        else:
            mlflow.log_params(
                pd.json_normalize(
                    OmegaConf.to_container(
                        cfg
                    ),
                    sep=".",
                ).to_dict(orient="records")[0]
            )
        if (Path(cfg.save_dir) / 'run.log').exists():
            mlflow.log_artifact(Path(cfg.save_dir) / 'run.log')

        mlflow.log_metrics(...)
        mlflow.log_artifact(...)
        mlflow.log_model(...)
        log_stuff(run_id)
        
if __name__ == '__main__':
    cfg, locals = main()
    log_run(cfg)
    locals.update(locals())

```

All the initial part of the logging could be moved to a decorator that looks for common files and logs them.

A nice utils, would be to be able to update all the previous runs with the new logging function

```python
from my_stage import log_run
all_runs = Path('results').glob('my_stage*')
for run in all_runs:
    cfg = OmegaConf.load(run / 'config.yaml')
    log_run(cfg)
```

As a bonus, It would be very nice to be able to launch non blocking logging from the main. This way we could track the advancement



### Logging files
An utils that could be implemented as well would be to instantiate a logger, with nice formatting that writes to a file in the save_dir and output to std out

## Persisting and recovering (Push and pull) # TODO
Finally to complete the workflow I would like to chose a stage and store all the data and code used in the lineage of the experiment.
In the `run.lock` I have access to all past stages (and past stages of past stages)
and for all stages I know the commit of the source code that was used.
Therefore retrace the code history on a new branch, push it and tag it (I can potentially include the run.lock as tag or commit message or as a file in the commit)
For the data, I can just rclone all the `results/<stage>_<dates>` to a shared store
I would need the equivalent of rcloning back locally the `results/<stage>_<dates>` corresponding to a run.lock
A nice workflow if the shared store is a filesystem directory, would be to just symlink the folder in my repository


## From single exec to parallel
Usual workflow is script the process a single item and wanting to apply the processing to a listing of thousands of items
I would like to easily transition to the following workflow:
- 1) Single main (cfg = dict(input="...")) see above
- 2) local parallelization:
Below is just an Idea, the main crux is to potentially write only a single run.lock and not thousands and write the outputs in the same save_dir (this is not complicated)
The issue is how to access the wrapped main and feed it to parallel launcher
I'm open to suggestions on this

```python
def run_parallel(cfg, tasks, key=None):
    OmegaConf.resolve(cfg)
    def wrapped_main(task):
        if key is None
            with OmegaConf.open_dict(cfg)
            task_cfg = OmegaConf.merge(cfg, task)
        else:
            task_cfg = OmegaConf.update(cfg, key, task) 

        return main(task_cfg)
    with joblib.Parallel(n_jobs)(delayed(wrapped_main)(task) for task in tasks)
```
- 3) cluster parallelization
    - using submitit to launch parallel jobs that splits the task list in chunks and each slurm job processes a given chunk (using the joblib parallel as above)

- 4) Serial workers with  task pool, a final improvement that can be useful when encountering restricted usage limitations on the cluster, would be have each worker spawn a followup worker if they could not reach the end of their task lists. This can be done by managing a set of todo/done files for each task, and adding a timeout in the sbatch routine, but ideally requeuing the job should write in the same save_dir, meaning the same_dir should be shared across slurm jobs  (not sure how to do this)
