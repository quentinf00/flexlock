# Installation

## Requirements

FlexLock requires Python 3.11 or later.

## Conda Installation

The library is shipped as a conda package from the channel quentinf00. You can install it using conda, micromamba, or pixi.

```bash
# Using conda
conda install -c quentinf00 flexlock

# Using micromamba
micromamba install -c quentinf00 flexlock

# Using pixi
pixi add flexlock -c quentinf00
```

### Optional Dependencies

If you would like to benefit from the MLflow integration, please install it separately:

```bash
conda install mlflow
```

---

## Development Installation

For contributors and developers who want to modify FlexLock:

### Using pixi (Recommended)

[pixi](https://pixi.sh/) is a fast package manager that handles both dependencies and virtual environments.

```bash
# Clone the repository
git clone https://github.com/quentinf00/flexlock.git
cd flexlock

# Install dependencies and create environment
pixi install

# Activate the environment
pixi shell
```

### Using pip (Editable Install)

If you prefer to use pip for development:

```bash
# Clone the repository
git clone https://github.com/quentinf00/flexlock.git
cd flexlock

# Install in editable mode
pip install -e .

# Install development dependencies (if needed)
pip install -e ".[dev]"
```

### Running Tests

After installing in development mode, you can run the test suite:

```bash
# Using pixi
pixi run test

# Using pytest directly
pytest
```

---

## Verifying Installation

After installation, verify that FlexLock is working correctly:

```bash
# Check the installed version
python -c "import flexlock; print(flexlock.__version__)"

# Verify CLI tools are available
flexlock-diff --help
flexlock-export --help
flexlock-run --help
```

If all commands complete without errors, FlexLock is successfully installed!

---

## Troubleshooting

### Command not found: flexlock-diff

If the CLI tools are not found in your PATH, ensure that your conda/pip bin directory is in your PATH:

```bash
# Check where flexlock is installed
python -c "import flexlock; print(flexlock.__file__)"

# For conda environments
echo $CONDA_PREFIX/bin

# Add to PATH if needed
export PATH="$CONDA_PREFIX/bin:$PATH"
```

### Import Error

If you get import errors, ensure you're using Python 3.11 or later:

```bash
python --version
```

If you need to upgrade Python, create a new conda environment:

```bash
conda create -n flexlock-env python=3.11
conda activate flexlock-env
conda install -c quentinf00 flexlock
```
