"""Tests for utils module functions."""

import argparse
import dataclasses
from collections import namedtuple
from typing import Any
import pytest
from omegaconf import DictConfig

try:
    import attr

    ATTR_AVAILABLE = True
except ImportError:
    ATTR_AVAILABLE = False

from flexlock.utils import to_dictconfig


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
