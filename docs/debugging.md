# `debug_on_fail`: Interactive Debugging

The `@debug_on_fail` decorator is a development tool designed to bridge the gap between interactive, exploratory programming (like in a Jupyter notebook) and robust, script-based execution. When an exception occurs in a decorated function, instead of crashing, it drops you into an interactive IPython debugger with the full state of your program preserved.

## The Problem

When you are developing a complex data processing or machine learning script, it is common for errors to occur. When a script fails, you typically get a traceback, but you lose the entire local context of the function. This makes it difficult to inspect the variables and understand what went wrong.

```python
def main():
    a = 1
    b = 0
    c = a / b  # Raises ZeroDivisionError

if __name__ == '__main__':
    main()

# Script crashes, and you can't inspect the values of a and b.
```

## The Solution: `@debug_on_fail`

By adding the `@debug_on_fail` decorator and running your script with the `FLEXLOCK_DEBUG=1` environment variable, you can seamlessly transition from execution to debugging.

```python
from flexlock import debug_on_fail

@debug_on_fail
def main():
    a = 1
    b = 0
    c = a / b

if __name__ == '__main__':
    main()
```

Now, run the script from your terminal:

```bash
FLEXLOCK_DEBUG=1 python your_script.py
```

When the `ZeroDivisionError` occurs, you will be dropped into an IPython post-mortem debugger.

```
ZeroDivisionError: division by zero
> /path/to/your_script.py(7)main()
      5     a = 1
      6     b = 0
----> 7     c = a / b

Dropping into an interactive shell.
The current context is available in the `ctx` dictionary.
For example, access a with `ctx['a']`.

ipdb> a
1
ipdb> b
0
ipdb> # You can now inspect variables, run code, and debug interactively.
```

## Best Practices

- **Development Only**: As the name implies, `@debug_on_fail` is for development. It should not be used in production code.
- **Combine with `@flexcli`**: `@debug_on_fail` is particularly powerful when combined with `@flexcli`. Place it *above* `@flexcli`.

  ```python
  from flexlock import flexcli, debug_on_fail

  class Config:
      ...

  @debug_on_fail
  @flexcli(config_class=Config)
  def main(cfg: Config):
      # Your code here
      ...
  ```
- **Autoreload**: For an even more seamless workflow, use an autoreload tool in your interactive shell (e.g., the `%autoreload` magic in IPython). This allows you to edit your code in your editor and have the changes automatically reflected in your debugging session.
