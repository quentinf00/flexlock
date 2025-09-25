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
- [x] Implement the data hashing utility
    - [x] Create a `hash_data` function for files and directories
    - [ ] Implement a caching mechanism to avoid re-hashing
    - [x] Write tests for hashing and cache correctness
    - [ ] Implement non blocking data hashing (spawn process that perform the hashing and update the run.lock)

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

### Phase 5.2: Parallel
- [ ] Implement local parallel execution with `joblib`
    - [ ] Create a `run_parallel` function or similar wrapper
    - [ ] Ensure decorators and config handling are compatible with parallel execution
- [ ] Implement cluster parallel execution with `submitit`
    - [ ] Design a wrapper to submit `joblib` chunks to a SLURM cluster
    - [ ] Ensure decorators and config handling are compatible with parallel execution
- [ ] Implement job requeue in case the tasks list are not finished

### Phase 5.3: Debugging
- [x] Integrate `unsafe_debug` decorator
- [x] Make decorator conditional on `NAGA_DEBUG` environment variable
- [x] Add tests for the debug decorator
- [x] Document the debug decorator

## Phase 6: Documentation & Refinement
- [ ] Write user documentation and examples for each feature
- [ ] Create a comprehensive `README.md`
- [ ] Refine the API based on usage to ensure it is "light and painless"

## Phase 7: Package and deploy
- [ ] build pixi package

## Document interfaces
- [ ] Specify that configs must have save_dir (interface)
    - [ ] Add explicit run time checks and messages when no save dir is specified
- [ ] Specify that parallel must have tasks 

## Misc:
- Add flexibility to track data from config keys or from explicit path

