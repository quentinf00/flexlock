# Naga Development Plan

## Phase 1: Core Setup & Configuration
- [x] Initialize project structure (`naga` package, `tests` directory)
- [x] Finalize and add all initial dependencies to `pixi.toml`
- [x] Implement the `clicfg` decorator for configuration
    - [x] Add support for loading from file, path overrides, and dotlist overrides
    - [x] Write comprehensive unit tests for all configuration scenarios

## Phase 2: Versioning & Hashing
- [x] Implement the `src` decorator for source code versioning (renamed to `snapshot`)
    - [x] Implement `commit_cwd` with `include` and `exclude` patterns
    - [x] Add tests for git tracking logic
    - [ ] handling mutli repo tracking: one stage may require modification to multiple project, I want to be able to specify multiple repo path to snashot
- [x] Implement the data hashing utility
    - [x] Create a `hash_data` function for files and directories
    - [ ] Implement a caching mechanism to avoid re-hashing
    - [x] Write tests for hashing and cache correctness
    - [ ] Implement non blocking data hashing (spawn process that perform the hashing and update the run.lock)
    - [ ] Add flexibility to track data from config keys or from explicit path

## Phase 3: State Management
- [x] Define the final `run.lock` YAML schema
    - [x] Include sections for config, source commit, data hashes, and previous stages
- [x] Create a decorator to manage the `run.lock`
    - [x] It should gather information from other decorators/sources
    - [ ] It should write the `run.lock` file atomically
- [x] Implement the "previous stage" decorator
    - [x] It should load a `run.lock` from a previous run and store its info
- [x] Write tests for `run.lock` creation, validation, and loading

## Phase 4: Logging & Monitoring
- [x] Create a utility for standardized file and console logging
- [x] Implement a decorator for MLflow integration
    - [x] Log parameters from `run.lock`
    - [x] Log logfile if exists
    - [x] Resume/Update previous MLFlow log entry if exists
- [x] Create a script/utility to update MLFlow logs for past runs
- [ ] Explore and implement non-blocking logging for in-progress runs


## Phase 5: Advanced Features

### Phase 5.1: Push Pull
- [ ] Implement Git Push/Pull functionality
    - [ ] Design the git utils that create a new branch and apply all commits of past stages
- [ ] Implement Data Push/Pull functionality
    - [ ] Design the `rclone` wrapper/strategy
    - [ ] Create commands or functions to `push` and `pull` experiment results
- [ ] Expose  Push/Pull with a command (with args)

### Phase 5.2: Parallel Execution
- [x] Redesign parallel execution feature
    - [x] Add `--task-to` argument to specify where in the config to inject task items.
    - [x] Add `--n_jobs` argument to control the number of workers for `joblib`.
    - [x] Add `--slurm_config` argument to point to a Slurm configuration file for `submitit`.
    - [x] Wrap the main function in a class with a `checkpoint` method for requeueing undone tasks.
    - [x] Decide on implementation location: `naga/clicfg.py` or a new dedicated file (e.g., `naga/parallel.py`).
    - [x] Implement local parallelization with `joblib`.
    - [x] Implement cluster parallelization with `submitit`.
    - [x] Implement serial workers with task pool and requeueing mechanism.

### Phase 5.3: Debugging
- [x] Integrate `unsafe_debug` decorator
- [x] Make decorator conditional on `NAGA_DEBUG` environment variable
- [x] Add tests for the debug decorator
- [x] Document the debug decorator

### Phase 5.4: Additionnal interfaces
- [ ] context manager based workflow:
    - [ ] the hashing, versioning, previous stage snapshoting could be done in a context manager


## Phase 6: Documentation & Refinement
- [x] Write user documentation and examples for each feature
- [x] Create a comprehensive `README.md`
- [x] Refine the API based on usage to ensure it is "light and painless"

## Phase 7: Package and deploy
- [x] build pixi package

## Document interfaces
- [ ] Specify that configs must have save_dir (interface)
    - [ ] Add explicit run time checks and messages when no save dir is specified
- [ ] Specify that parallel must have tasks 

## MIsc Improvements
- [ ] The naga decorator with default arguments should do the snapshot 
- [ ] The naga decorator with default arguments should do some  mlflow logging (logging the runlock, config and log files but after the function call)
- [ ] Resolver based workflow: add omegaconf resolver to populate the run context while resolving the config 
    - [ ] resolver for tracking data
    - [ ] resolver for flagging previous stages
