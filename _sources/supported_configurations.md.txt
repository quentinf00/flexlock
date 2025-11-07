# Supported Configuration Formats

FlexLock's `@flexcli` decorator and underlying `to_dictconfig` utility support multiple configuration formats for maximum flexibility:


### 1. Dictionary
- Standard Python dictionaries.
- Supports nested structures and all Python data types.

```python
config = {
    "param": 42,
    "name": "example",
    "nested": {
        "value": "test"
    }
}
```
### 2. Vanilla Python Classes
- Regular Python classes with attributes.
- Attributes that don't start with `_` and are not callable will be included.

```python
class Config:
    def __init__(self):
        self.param = 42
        self.name = "example"
```
## 3. Dataclasses
- **Require type annotations** for all fields to be properly recognized.
- Fields without type hints will generate will be ignored by OmegaConf.
- Supports default values and nested structures.

```python
from dataclasses import dataclass

@dataclass
class Config:
    param: int  # Type annotation required
    name: str   # Type annotation required
    optional: str = "default"
```

### 4. argparse.Namespace
- Compatible with argparse-generated namespace objects.
- All attributes become configuration keys.

```python
import argparse

args = argparse.Namespace(param=42, name="example")
```

## 5. attrs.define Classes
- **Do not require type annotations** .
- Automatically converts to DictConfig format.
- Supports defaults and validation.

```python
import attr

@attr.define
class Config:
    param = 1
    name = 2
    optional = "default"
```



### 6. __slots__ Classes
- Classes that define `__slots__`.
- All slot attributes are converted to config values.

```python
class Config:
    __slots__ = ["param", "name"]
    
    def __init__(self):
        self.param = 42
        self.name = "example"
```

### Important Notes:
- For **dataclasses**, type annotations are required for all fields to ensure proper conversion.
- For **attrs.define** classes, type annotations are recommended but not strictly required.

