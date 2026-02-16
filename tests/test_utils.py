"""Tests for utils module functions."""

import argparse
import dataclasses
from collections import namedtuple
from typing import Any
import pytest
from omegaconf import DictConfig, OmegaConf
import tempfile
from pathlib import Path
import functools

try:
    import attr

    ATTR_AVAILABLE = True
except ImportError:
    ATTR_AVAILABLE = False

from flexlock.utils import to_dictconfig, instantiate, py2cfg, log_to_file


# --- Test Cases for to_dictconfig function ---


def test_to_dictconfig_already_dictconfig():
    """Test that an already DictConfig object is returned as-is."""
    from omegaconf import OmegaConf

    existing_dictconfig = OmegaConf.create({"key": "value", "nested": {"x": 1}})
    result = to_dictconfig(existing_dictconfig)

    assert result == existing_dictconfig
    assert isinstance(result, DictConfig)


def test_to_dictconfig_dict():
    """Test conversion of dict to DictConfig."""
    input_dict = {"key": "value", "nested": {"x": 1, "y": [1, 2, 3]}}
    result = to_dictconfig(input_dict)

    assert isinstance(result, DictConfig)
    assert result.key == "value"
    assert result.nested.x == 1
    assert result.nested.y == [1, 2, 3]


def test_to_dictconfig_dataclass():
    """Test conversion of dataclass to DictConfig."""
    from dataclasses import dataclass

    @dataclass
    class TestDataclass:
        name: str
        value: int
        optional_field: str = "default"

    instance = TestDataclass(name="test", value=42)
    result = to_dictconfig(instance)

    assert isinstance(result, DictConfig)
    assert result.name == "test"
    assert result.value == 42
    assert result.optional_field == "default"


def test_to_dictconfig_plain_class():
    """Test conversion of plain class instance to DictConfig."""

    class TestClass:
        def __init__(self):
            self.name = "test"
            self.value = 42
            self.nested = {"x": 1, "y": [1, 2, 3]}
            self._private = "should_be_excluded"
            self.method = lambda: None  # Should be excluded

    instance = TestClass()
    result = to_dictconfig(instance)

    assert isinstance(result, DictConfig)
    assert result.name == "test"
    assert result.value == 42
    assert result.nested.x == 1
    assert result.nested.y == [1, 2, 3]
    assert "_private" not in result
    assert "method" not in result


def test_to_dictconfig_slots_class():
    """Test conversion of __slots__-based class instance to DictConfig."""

    class TestSlotsClass:
        __slots__ = ["name", "value", "nested"]

        def __init__(self):
            self.name = "test"
            self.value = 42
            self.nested = {"x": 1, "y": [1, 2, 3]}

    instance = TestSlotsClass()
    result = to_dictconfig(instance)

    assert isinstance(result, DictConfig)
    assert result.name == "test"
    assert result.value == 42
    assert result.nested.x == 1
    assert result.nested.y == [1, 2, 3]


def test_to_dictconfig_argparse_namespace():
    """Test conversion of argparse.Namespace to DictConfig."""
    args = argparse.Namespace()
    args.name = "test"
    args.value = 42
    args.flag = True
    args.list_value = [1, 2, 3]

    result = to_dictconfig(args)

    assert isinstance(result, DictConfig)
    assert result.name == "test"
    assert result.value == 42
    assert result.flag is True
    assert result.list_value == [1, 2, 3]


def test_to_dictconfig_typing_simple_namespace():
    """Test conversion of typing.SimpleNamespace to DictConfig."""
    from types import SimpleNamespace

    ns = SimpleNamespace()
    ns.name = "test"
    ns.value = 42

    result = to_dictconfig(ns)

    assert isinstance(result, DictConfig)
    assert result.name == "test"
    assert result.value == 42


def test_to_dictconfig_vanilla_class_attribute():
    """Test conversion of vanilla class (without dataclass, attrs, etc.) to DictConfig."""

    class VanillaClass:
        param1 = "value1"
        param2 = 123
        param3 = {"nested": "value"}

    instance = VanillaClass
    result = to_dictconfig(instance)

    assert isinstance(result, DictConfig)
    assert result.param1 == "value1"
    assert result.param2 == 123
    assert result.param3.nested == "value"


def test_to_dictconfig_vanilla_typed_class_attribute():
    """Test conversion of vanilla class (without dataclass, attrs, etc.) to DictConfig."""

    class VanillaClass:
        param1: str = "value1"
        param2: int = 123
        param3: dict = {"nested": "value"}

    instance = VanillaClass
    result = to_dictconfig(instance)

    assert isinstance(result, DictConfig)
    assert result.param1 == "value1"
    assert result.param2 == 123
    assert result.param3.nested == "value"


def test_to_dictconfig_vanilla_class():
    """Test conversion of vanilla class (without dataclass, attrs, etc.) to DictConfig."""

    class VanillaClass:
        def __init__(self):
            self.param1 = "value1"
            self.param2 = 123
            self.param3 = {"nested": "value"}

    instance = VanillaClass()
    result = to_dictconfig(instance)

    assert isinstance(result, DictConfig)
    assert result.param1 == "value1"
    assert result.param2 == 123
    assert result.param3.nested == "value"


def test_to_dictconfig_attrs_class():
    """Test conversion of attrs.define class to DictConfig."""

    @attr.define
    class AttrsClass:
        name: str = attr.field()
        value: int = attr.field()
        default_value: str = "default"

    instance = AttrsClass(name="test", value=42)
    result = to_dictconfig(instance)

    assert isinstance(result, DictConfig)
    assert result.name == "test"
    assert result.value == 42
    assert result.default_value == "default"


# Additional test for edge cases
def test_to_dictconfig_empty_dict():
    """Test conversion of empty dict."""
    result = to_dictconfig({})
    assert isinstance(result, DictConfig)
    assert len(result) == 0


def test_to_dictconfig_nested_structures():
    """Test handling of complex nested structures."""
    complex_input = {
        "level1": {
            "level2": {"value": "deep_value", "list": [1, 2, {"nested_dict": "value"}]},
            "simple_value": 42,
        },
        "top_level_list": [{"item1": "val1"}, {"item2": "val2"}],
    }

    result = to_dictconfig(complex_input)
    assert isinstance(result, DictConfig)
    assert result.level1.level2.value == "deep_value"
    assert result.level1.level2.list[0] == 1
    assert result.level1.level2.list[1] == 2
    assert result.level1.level2.list[2].nested_dict == "value"
    assert result.level1.simple_value == 42
    assert result.top_level_list[0].item1 == "val1"
    assert result.top_level_list[1].item2 == "val2"


# --- Test Cases for instantiate function ---

class TestInstantiationClass:
    """Helper class for testing instantiate function."""
    def __init__(self, param1="default", param2=42):
        self.param1 = param1
        self.param2 = param2


class TestClassWithPositionalArgs:
    """Helper class for testing positional args functionality."""
    def __init__(self, a, b, c=None):
        self.a = a
        self.b = b
        self.c = c


def test_instantiate_simple_class():
    """Test instantiating a simple class via config."""
    config = OmegaConf.create({
        "_target_": "tests.test_utils.TestInstantiationClass",
        "param1": "test_value",
        "param2": 100
    })

    result = instantiate(config)
    assert result.__class__.__name__ == 'TestInstantiationClass'
    assert result.param1 == "test_value"
    assert result.param2 == 100


def test_instantiate_with_actual_import():
    """Test instantiate with a class that can be imported."""
    from argparse import Namespace

    config = OmegaConf.create({
        "_target_": "argparse.Namespace",
        "name": "test",
        "value": 42
    })

    result = instantiate(config)
    assert isinstance(result, Namespace)
    assert result.name == "test"
    assert result.value == 42


def test_instantiate_with_list():
    """Test instantiate with list containing target objects."""
    from argparse import Namespace

    config = OmegaConf.create([
        {
            "_target_": "argparse.Namespace",
            "name": "test1",
            "value": 1
        },
        {
            "_target_": "argparse.Namespace",
            "name": "test2",
            "value": 2
        }
    ])

    result = instantiate(config)
    assert isinstance(result, list)
    assert len(result) == 2
    assert isinstance(result[0], Namespace)
    assert result[0].name == "test1"
    assert result[0].value == 1
    assert isinstance(result[1], Namespace)
    assert result[1].name == "test2"
    assert result[1].value == 2


def test_instantiate_nested_config():
    """Test instantiate with nested config containing targets."""
    from argparse import Namespace

    config = OmegaConf.create({
        "namespace": {
            "_target_": "argparse.Namespace",
            "name": "nested",
            "value": 99
        },
        "simple": "value",
        "list": [1, 2, 3]
    })

    result = instantiate(config)
    assert isinstance(result, dict)
    assert isinstance(result["namespace"], Namespace)
    assert result["namespace"].name == "nested"
    assert result["namespace"].value == 99
    assert result["simple"] == "value"
    assert result["list"] == [1, 2, 3]


def test_instantiate_partial():
    """Test instantiate with _partial_ flag."""
    config = OmegaConf.create({
        "_target_": "builtins.dict",
        "_partial_": True,
        "param1": "test_value"
    })

    partial_func = instantiate(config)
    assert isinstance(partial_func, functools.partial)

    # Call the partial to get the actual result
    result = partial_func(param2=200)
    assert isinstance(result, dict)
    assert result["param1"] == "test_value"
    assert result["param2"] == 200


def test_instantiate_with_positional_args():
    """Test instantiate with positional arguments via _args_."""

    config = OmegaConf.create({
        "_target_": "builtins.tuple",
        "_args_": [[1, 2, 3]]
    })

    result = instantiate(config)
    assert result == (1, 2, 3)
    assert isinstance(result, tuple)


def test_instantiate_with_args_and_kwargs():
    """Test instantiate with both positional and keyword arguments."""

    config = OmegaConf.create({
        "_target_": "tests.test_utils.TestClassWithPositionalArgs",
        "_args_": [10, 20],
        "c": "keyword_value"
    })

    result = instantiate(config)
    assert result.__class__.__name__ ==  'TestClassWithPositionalArgs'
    assert result.a == 10
    assert result.b == 20
    assert result.c == "keyword_value"


def test_instantiate_with_args_and_runtime_args():
    """Test instantiate with _args_ from config and runtime args."""

    config = OmegaConf.create({
        "_target_": "builtins.sum",
        "_args_": [[1, 2, 3]]  # Sum of [1, 2, 3] should be 6
    })

    result = instantiate(config)
    assert result == 6


def test_instantiate_with_runtime_args():
    """Test instantiate with runtime arguments overriding config."""
    config = OmegaConf.create({
        "_target_": "builtins.dict",
        "param1": "original",
        "param2": "to_override"
    })

    result = instantiate(config, param2="new_value", param3="added")
    assert isinstance(result, dict)
    assert result["param1"] == "original"
    assert result["param2"] == "new_value"  # Overridden by runtime arg
    assert result["param3"] == "added"      # Added at runtime


# --- Test Cases for py2cfg function ---

def py2cfg_test_func(x=10, y="hello"):
    """Test function for py2cfg."""
    return f"x={x}, y={y}"


class Py2CfgTestClass:
    """Test class for py2cfg."""
    def __init__(self, param1="default", param2=42):
        self.param1 = param1
        self.param2 = param2


def test_py2cfg_simple_function():
    """Test converting a simple function to config."""

    config = py2cfg(py2cfg_test_func)

    assert "_target_" in config
    assert config["_target_"] == "test_utils.py2cfg_test_func"
    assert "x" in config
    assert "y" in config
    assert config["x"] == 10
    assert config["y"] == "hello"


def test_py2cfg_simple_class():
    """Test converting a simple class to config."""

    config = py2cfg(Py2CfgTestClass)

    assert "_target_" in config
    assert config["_target_"] == "test_utils.Py2CfgTestClass"
    assert "param1" in config
    assert "param2" in config
    assert config["param1"] == "default"
    assert config["param2"] == 42


def test_py2cfg_with_overrides():
    """Test py2cfg with override parameters."""

    def simple_func(x=10, y="hello"):
        return f"x={x}, y={y}"

    config = py2cfg(simple_func, x=99, new_param="new_value")

    assert config["x"] == 99  # Overridden
    assert config["y"] == "hello"  # Default preserved
    assert config["new_param"] == "new_value"  # New param added


def py2cfg_args_test_func(a, b, c=None):
    """Test function for args py2cfg."""
    return a, b, c


def py2cfg_partial_test_func(x, y=10):
    """Test function for partial py2cfg."""
    return x + y


def test_py2cfg_partial_function():
    """Test converting a partial function to config."""

    partial_func = functools.partial(py2cfg_partial_test_func, x=5)
    config = py2cfg(partial_func)

    assert "_target_" in config
    assert config["_target_"] == "test_utils.py2cfg_partial_test_func"
    assert "_partial_" in config
    assert config["_partial_"] is True
    assert config["x"] == 5  # Partial's fixed argument
    assert config["y"] == 10  # Default preserved


def test_py2cfg_no_signature():
    """Test py2cfg with object that has no signature."""
    # Using built-in functions that might not have inspectable signatures
    import math

    config = py2cfg(math.ceil)
    assert "_target_" in config
    assert config["_target_"] == "math.ceil"
    # Should not crash even if signature inspection fails

class CallableClass:
    def __init__(self, default_value=42):
        self.default_value = default_value

    def __call__(self, x):
        return x + self.default_value


def test_py2cfg_callable_object():
    """Test py2cfg with a callable object."""

    config = py2cfg(CallableClass.__call__, self=py2cfg(CallableClass, default_value=10))

    assert "_target_" in config


def test_py2cfg_partial_with_positional_args():
    """Test py2cfg with a partial function that has positional arguments."""

    def test_func(a, b, c=None):
        return a + b if c is None else a + b + c

    partial_func = functools.partial(test_func, 5, 10)  # (a=5, b=10)
    config = py2cfg(partial_func)

    assert "_target_" in config
    assert config["_target_"] == "test_utils.test_py2cfg_partial_with_positional_args.<locals>.test_func"
    assert "_partial_" in config
    assert config["_partial_"] is True
    assert "_args_" in config
    assert config["_args_"] == [5, 10]  # Positional args should be captured


# --- Test Cases for log_to_file function ---

def test_log_to_file_context_manager():
    """Test the log_to_file context manager functionality."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
        log_path = f.name

    try:
        # Use the context manager
        with log_to_file(log_path):
            from loguru import logger
            logger.info("Test message 1")
            logger.debug("Test message 2")

        # Check that the log file contains the messages
        with open(log_path, 'r') as f:
            log_content = f.read()

        assert "Test message 1" in log_content
        assert "Test message 2" in log_content
        assert "INFO" in log_content
        assert "DEBUG" in log_content

    finally:
        # Clean up the temporary file
        if Path(log_path).exists():
            Path(log_path).unlink()


def test_log_to_file_with_multiple_logs():
    """Test logging to file with multiple context entries."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
        log_path = f.name

    try:
        # Log something
        with log_to_file(log_path):
            from loguru import logger
            logger.info("First message")

        # Log something else to same file
        with log_to_file(log_path):
            from loguru import logger
            logger.warning("Second message")

        # Check that both messages are in the file
        with open(log_path, 'r') as f:
            log_content = f.read()

        assert "First message" in log_content
        assert "Second message" in log_content
        assert "INFO" in log_content
        assert "WARNING" in log_content

    finally:
        # Clean up the temporary file
        if Path(log_path).exists():
            Path(log_path).unlink()


def test_log_to_file_different_files():
    """Test logging to different files."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f1:
        log_path1 = f1.name
    with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f2:
        log_path2 = f2.name

    try:
        # Log to first file
        with log_to_file(log_path1):
            from loguru import logger
            logger.info("Message for file 1")

        # Log to second file
        with log_to_file(log_path2):
            from loguru import logger
            logger.info("Message for file 2")

        # Check that each file has its own message
        with open(log_path1, 'r') as f:
            content1 = f.read()
        with open(log_path2, 'r') as f:
            content2 = f.read()

        assert "Message for file 1" in content1
        assert "Message for file 2" not in content1
        assert "Message for file 2" in content2
        assert "Message for file 1" not in content2

    finally:
        # Clean up the temporary files
        for path in [log_path1, log_path2]:
            if Path(path).exists():
                Path(path).unlink()

# --- Test Cases for extract_tracking_info function ---


def test_extract_tracking_info_basic():
    """Test extract_tracking_info with basic repos and data."""
    from flexlock.utils import extract_tracking_info
    
    cfg = OmegaConf.create({
        '_snapshot_': {
            'repos': {'main': '.', 'lib': './lib'},
            'data': {'input': 'data/train.csv', 'model': 'models/best.pt'}
        }
    })
    
    repos, data, prevs = extract_tracking_info(cfg)

    assert repos['main']['path'] == '.'
    assert repos['lib']['path'] == './lib'
    assert data == {'input': 'data/train.csv', 'model': 'models/best.pt'}
    # prevs should include data paths
    assert 'data/train.csv' in prevs
    assert 'models/best.pt' in prevs


def test_extract_tracking_info_no_snapshot():
    """Test extract_tracking_info when _snapshot_ is missing."""
    from flexlock.utils import extract_tracking_info
    
    cfg = OmegaConf.create({'model': 'resnet', 'lr': 0.001})
    
    repos, data, prevs = extract_tracking_info(cfg)
    
    assert repos == {}
    assert data == {}
    assert prevs == []


def test_extract_tracking_info_with_prevs():
    """Test extract_tracking_info with explicit prevs."""
    from flexlock.utils import extract_tracking_info
    
    cfg = OmegaConf.create({
        '_snapshot_': {
            'repos': {'main': '.'},
            'data': {'input': 'data/train.csv'},
            'prevs': ['outputs/exp1/run.lock', 'outputs/exp2/run.lock']
        }
    })
    
    repos, data, prevs = extract_tracking_info(cfg)

    assert repos['main']['path'] == '.'
    assert data == {'input': 'data/train.csv'}
    # prevs should include both explicit prevs and data paths
    assert 'outputs/exp1/run.lock' in prevs
    assert 'outputs/exp2/run.lock' in prevs
    assert 'data/train.csv' in prevs


def test_extract_tracking_info_singular_repo_raises_error():
    """Test that using 'repo' (singular) raises FlexLockConfigError."""
    from flexlock.utils import extract_tracking_info
    from flexlock.exceptions import FlexLockConfigError
    
    cfg = OmegaConf.create({
        '_snapshot_': {
            'repo': '.',  # Using singular 'repo' - should raise error
            'data': {'input': 'data/train.csv'}
        }
    })
    
    with pytest.raises(FlexLockConfigError, match="Found 'repo' \\(singular\\)"):
        extract_tracking_info(cfg)


def test_extract_tracking_info_module_repo():
    """Test extract_tracking_info with module-based repo spec."""
    from flexlock.utils import extract_tracking_info
    from unittest.mock import patch

    cfg = OmegaConf.create({
        '_snapshot_': {
            'repos': {
                'my_pkg': {'module': 'my_pkg'},
            }
        }
    })

    with patch('flexlock.utils.resolve_module_to_repo_path', return_value='/resolved/path'):
        repos, data, prevs = extract_tracking_info(cfg)

    assert repos['my_pkg']['path'] == '/resolved/path'
    assert repos['my_pkg']['module'] == 'my_pkg'


def test_extract_tracking_info_module_with_include():
    """Test module-based repo with include/exclude filters."""
    from flexlock.utils import extract_tracking_info
    from unittest.mock import patch

    cfg = OmegaConf.create({
        '_snapshot_': {
            'repos': {
                'my_pkg': {'module': 'my_pkg', 'include': ['src/**'], 'exclude': ['*.pyc']},
            }
        }
    })

    with patch('flexlock.utils.resolve_module_to_repo_path', return_value='/resolved/path'):
        repos, data, prevs = extract_tracking_info(cfg)

    assert repos['my_pkg']['path'] == '/resolved/path'
    assert repos['my_pkg']['include'] == ['src/**']
    assert repos['my_pkg']['exclude'] == ['*.pyc']


def test_extract_tracking_info_both_path_and_module():
    """Test that path takes precedence when both are provided."""
    from flexlock.utils import extract_tracking_info

    cfg = OmegaConf.create({
        '_snapshot_': {
            'repos': {
                'my_pkg': {'path': '/explicit/path', 'module': 'my_pkg'},
            }
        }
    })

    repos, data, prevs = extract_tracking_info(cfg)

    assert repos['my_pkg']['path'] == '/explicit/path'
    assert repos['my_pkg']['module'] == 'my_pkg'


def test_extract_tracking_info_neither_path_nor_module():
    """Test that neither path nor module raises error."""
    from flexlock.utils import extract_tracking_info
    from flexlock.exceptions import FlexLockConfigError

    cfg = OmegaConf.create({
        '_snapshot_': {
            'repos': {
                'my_pkg': {'include': ['*.py']},
            }
        }
    })

    with pytest.raises(FlexLockConfigError, match="must specify either 'path' or 'module'"):
        extract_tracking_info(cfg)


def test_extract_tracking_info_auto_detect_uses_module_name():
    """Test that auto-detection names the repo after the top-level module."""
    from flexlock.utils import extract_tracking_info
    from unittest.mock import patch

    cfg = OmegaConf.create({
        '_target_': 'my_pkg.trainer.Trainer',
    })

    with patch('flexlock.utils.resolve_module_to_repo_path', return_value='/some/repo'):
        repos, data, prevs = extract_tracking_info(cfg)

    assert 'my_pkg' in repos
    assert repos['my_pkg']['path'] == '/some/repo'
    assert repos['my_pkg']['module'] == 'my_pkg'
    assert 'main' not in repos


def test_extract_tracking_info_auto_detect_skips_if_exists():
    """Test that auto-detection doesn't override an explicitly set repo."""
    from flexlock.utils import extract_tracking_info
    from unittest.mock import patch

    cfg = OmegaConf.create({
        '_target_': 'my_pkg.trainer.Trainer',
        '_snapshot_': {
            'repos': {
                'my_pkg': '/explicit/path',
            }
        }
    })

    with patch('flexlock.utils.resolve_module_to_repo_path') as mock_resolve:
        repos, data, prevs = extract_tracking_info(cfg)

    assert repos['my_pkg']['path'] == '/explicit/path'
    mock_resolve.assert_not_called()


