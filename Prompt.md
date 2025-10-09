Documentation:


Items

## Quickstart:

Starting point:

```python
class Config:
    param = 1
    input_path = 'data/preprocess/input.csv'
    save_dir = 'results/process'

def process(cfg: Config=Config()):
    print(cfg.param)
    with open('results/process/out.txt', 'w') as f:
        for _ in range(cfg.param):
            f.write(Path(cfg.input_path).read_text())
```



### runlock:
```python
class Config:
    param = 1
    input_path = 'data/input.csv'

def main(cfg: Config=Config()):
    runlock( # writes run.lock the run sheet containing:
        config=cfg, #  config 
        repos=['.'], #  version of the code
        data=[cfg.input_path], # hash of the input data
        prevs=[Path(input_path.parent)] # run.lock of previous runs 
        runlock_path= Path(cfg.save_dir) / 'run.lock' # (default if save_dir is in config) path to save the runs 
    )
    ...
```

### mlflow_lock:
```python

class Config:
    ...

def main(cfg):
    ...

def log_run(save_dir):
    with mlflow_lock(save_dir) as run: 
        # creates a new run with logical_run_id  save_dir
        # deprecates older runs with same logical run_id
        # logs the run.lock data

        # You can log whatever more  you need about the run:
        mlflow.log_artifact('results/process/out.txt')
        ...
```

In the philosophy, this is separate from the  `main()`. You can run the logging function multiple times and iterate on it. And then by filtering on the `active` status, you only have access to the most recent one.

One thing this solves, is when you have trained multiple models and you want to add a  diagnosis, you can update the log_run function and rerun it for the training each training directory of the model

### clicfg

```python
# process.py

class Config:
    ...

@clicfg(config_class=Config)
def main(cfg):
    ...

def log_run(save_dir):
        ...

if __name__ == '__main__':
    main(Config())
```

this allows the following usage:

```
# default run
python process.py

# other config file (can only override some parameter)
python process.py --config conf/new_conf.yml

# load config from key 
python process.py --config conf/multi_stage.yml --experiment process

# change specific param
python process.py -o param 10

# run multiple configs
echo "1\n2\n3\n4\n5" >> tasks.txt 
python process.py --tasks list.txt --task_to param 

## with local parallelisation
python process.py --tasks list.txt --task_to param  --n_jobs=10

## with slurm parallelisation
python process.py --tasks list.txt --task_to param  --slurm_config=slurm.yaml
```


## Proposed development workflow

When writing up the code, the REPL,  cell-based jupyterlike workflow when we can investigate each variable and statement is often a useful/necessary stepping stone to the final processing function/module. But a notebook can quickly become a nightmarish tangles of cell which never ends up being refactored into "cleaner code"

To mitigate this, I developped a helper and came up with a workflow I like:


Given the following skeleton

```python
# process.py

class Config:
    ...

@clicfg(config_class=Config)
def main(cfg):
    a =  0
    1/a
    ...

def log_run(save_dir):
        ...

if __name__ == '__main__':
    main(Config())
```
Running this file will fail bu we loos the local context making it difficult to know what happened  
```IPython/Jupyter Console /Notebook
>>> import process; process.main()
Exception ...
>>> a
a undefined
```


By adding the `unsafe_debug` decorator:
```python
@unsafe_debug
@clicfg(config_class=Config)
def main(cfg):
    a =  0
    1/a
    ...

```IPython (env FLEXLOCK_DEBUG=1)
>>> import process; process.main()
Exception ...
>>> a
0
```

NB the autoreload / run magic commands are your friends


# Next steps:

## Advanced: Resolver workflow
Specifying run lock directly from the config with 
'${runlock_data:data/preprocess/input.csv}'
'${runlock_prev:data/preprocess}'

## Persisting runs push/pull:
- Having a script that given a run.lock or (set of run.lock s):
    - compile all necessary commit on a clean branch, push it to the repo (tags it)
    - copy (rclone) all the data from previous stages to a remote under the same tag (as the git)

- Having a script given the github repos, remotes, and a given tag, pulls the code and copy the data (or possibly symlink it if on same filesystem)


