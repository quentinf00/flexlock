# Agent Guidance: sample_project

## Project Structure
- `src/sample_project/`: Core implementation.
    - `cnf/`: Conditional Neural Field components.
    - `diffusion/`: Latent diffusion models.
    - `data/`: Preprocessing and data loading.
    - `evaluate/`: Reconstruction and assimilation scripts.
- `outputs/`: Training artifacts and results.
- `configs/`: Execution configurations.

## Project Objective

Reproduce the ConFiLD (see docs/confild.md when necessary) experiment on a NATL60 ssh (available here /scale/user/qfebvre/projects/251023_perceiver_da/2020a_SSH_mapping_NATL60/dc_ref):

see docs/project_steps.md
the original ConfilD implementation is here /scale/user/qfebvre/projects/260506_hafs/CoNFiLD

## Flexlock

You must use the flexlock library to configure/run/distribute/orchestrate  the different stages/experiments of the project

You are a beta tester, 
- you should refer first to the documentation: ../flexlock/docs and only inspect the code when you encounter an error
- Maintain a flexlock wiki  `flexlock_wiki/` with:
    - Use cases (should be framed as user stories): with best solution so far
    - Fail cases: failed command, misunderstood doc, unintuitive interface, code bug
    - Improvements:
        - doc updates
        - bug fixes
        - missing features
- Refer to the wiki to check if the intended usage already is in it with a adequate solution.

## Environment
The project uses pixi to manage dependencies
You have access to a slurm cluster, and to 2 gpus locally








## Key Constraints
- **CNF Architecture**: Currently supports both standard MLP and FiLM conditioning.
- **Diffusion**: Operates on latent vectors $z$ produced by the CNF stage, using temporal windowing to learn sequence structure.

## Verification
- No dedicated test suite is currently defined in `pyproject.toml`. Verification should be done via `run_*.py` scripts and inspecting `outputs/`.
