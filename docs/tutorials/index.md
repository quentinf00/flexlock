# Tutorials

Learn FlexLock through hands-on examples, progressing from simple scripts to complex multi-stage pipelines.

## Tutorial Series

### 📘 Beginner

#### [01. Basics: Your First FlexLock Script](./01_basics.md)
**Time:** 10 minutes
**What you'll learn:**
- Using `@flexcli` decorator
- Command-line parameter overrides
- Running parameter sweeps
- Automatic result tracking

**Perfect for:** Getting started with FlexLock

---

#### [02. Reproducibility: Tracking Everything](./02_reproducibility.md)
**Time:** 15 minutes
**What you'll learn:**
- Automatic snapshot generation
- Git tree hashing for code tracking
- Data fingerprinting
- Comparing runs with `flexlock diff`

**Perfect for:** Ensuring reproducible experiments

---

### 📗 Intermediate

#### [03. YAML Configs: Declarative Configuration](./03_yaml_config.md)
**Time:** 20 minutes
**What you'll learn:**
- Multi-stage YAML configurations
- Configuration selection and interpolation
- Nested overrides (outer vs inner)
- Sweep definitions in YAML

**Perfect for:** Managing complex configurations

---

#### [04. Python Configs: Type-Safe Configuration](./04_python_config.md)
**Time:** 25 minutes
**What you'll learn:**
- Using `py2cfg` for Python-based configs
- Handling nested objects and mutable defaults
- Deep parameter overrides
- Swapping classes at runtime

**Perfect for:** Building reusable configuration systems

---

### 📙 Advanced

#### [05. Pipelines: Multi-Stage Workflows](./05_pipeline.md)
**Time:** 30 minutes
**What you'll learn:**
- Using the `Project` API
- Building dependency-aware pipelines
- Smart resume with automatic caching
- Hyperparameter sweeps with best model selection
- Passing results between stages

**Perfect for:** Complex research workflows

---

#### [06. Interactive Debugging: State Preservation](./06_debugging.md)
**Time:** 20 minutes
**What you'll learn:**
- Using `@debug_on_fail` for variable capture
- Environment-based activation with `FLEXLOCK_DEBUG`
- Integration with `@flexcli` decorator
- Preserving expensive computation state
- Interactive debugging workflows

**Perfect for:** Debugging long-running experiments

---

## Learning Paths

### 🎯 Quick Start Path
For rapid prototyping and experimentation:
1. [01. Basics](./01_basics.md) → Understand `@flexcli`
2. [02. Reproducibility](./02_reproducibility.md) → Add tracking
3. Done! You can now run reproducible experiments

### 🔬 Research Scientist Path
For ML research and experimentation:
1. [01. Basics](./01_basics.md)
2. [02. Reproducibility](./02_reproducibility.md)
3. [04. Python Configs](./04_python_config.md) → Manage complex model configs
4. [06. Interactive Debugging](./06_debugging.md) → Debug long experiments efficiently
5. [05. Pipelines](./05_pipeline.md) → Build multi-stage workflows

### 🏗️ ML Engineer Path
For production-ready pipelines:
1. [03. YAML Configs](./03_yaml_config.md) → Declarative configs
2. [05. Pipelines](./05_pipeline.md) → Build robust workflows
3. [Parallel Execution](../parallel.md) → Scale to clusters

## Prerequisites

All tutorials assume:
- Python 3.8+
- FlexLock installed (`pip install flexlock`)
- Basic Python knowledge
- Familiarity with command line

## Tutorial Structure

Each tutorial follows this format:

1. **Overview**: What you'll learn
2. **Files**: What's included in the example
3. **Demo Scenarios**: Step-by-step walkthroughs
4. **Concepts**: Deep dive into features
5. **Exercises**: Try it yourself
6. **Next Steps**: Where to go from here

## Getting the Examples

All tutorial code is available in the `examples/` directory:

```bash
git clone https://github.com/quentinf00/flexlock.git
cd flexlock/examples/my_awesome_project
```

Or download just the examples:

```bash
# Download specific example
wget https://raw.githubusercontent.com/quentinf00/flexlock/main/examples/my_awesome_project/01_basics/simple_script.py
```

## Need Help?

- **Stuck?** Check the [FAQ](../faq.md)
- **Bug?** [Report it](https://github.com/quentinf00/flexlock/issues)
- **Question?** [Ask on Discussions](https://github.com/quentinf00/flexlock/discussions)

Ready to start? Begin with **[Tutorial 01: Basics](./01_basics.md)**!
