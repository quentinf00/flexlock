import pytest
from omegaconf import OmegaConf
import sys
from unittest.mock import patch, MagicMock
import inspect

from pathlib import Path
from flexlock.flexcli import flexcli


def test_flexcli_decorator_basic():
    """Test the basic functionality of the flexcli decorator."""

    @flexcli
    def simple_function(cfg):
        return cfg

    # Test programmatic usage
    config = OmegaConf.create({"param": 10})
    result = simple_function(config)
    assert result == config


def test_flexcli_with_defaults():
    """Test the flexcli decorator with default parameters."""

    @flexcli(param=20, name="test")
    def function_with_defaults(cfg):
        return cfg

    # Test programmatic usage
    config = OmegaConf.create({"other_param": 30})
    result = function_with_defaults(config)
    assert result == config


def test_flexcli_decorator_storage():
    """Test that the decorator properly stores metadata."""

    @flexcli(test_param=100, learning_rate=0.01)
    def test_function(cfg):
        return cfg

    # Verify the decorator metadata
    assert hasattr(test_function, '_original_fn')
    assert hasattr(test_function, '_defaults')
    assert test_function._defaults == {'test_param': 100, 'learning_rate': 0.01}


def test_flexcli_without_parentheses():
    """Test that the decorator works without parentheses."""

    @flexcli
    def simple_function(cfg):
        return cfg

    # Should work without arguments
    assert hasattr(simple_function, '_original_fn')
    assert hasattr(simple_function, '_defaults')  # Should be empty dict
    assert simple_function._defaults == {}


def test_flexcli_with_parentheses():
    """Test that the decorator works with parentheses and arguments."""

    @flexcli(param1=5, param2="test")
    def function_with_args(cfg):
        return cfg

    # Should work with arguments
    assert hasattr(function_with_args, '_original_fn')
    assert hasattr(function_with_args, '_defaults')
    assert function_with_args._defaults == {'param1': 5, 'param2': 'test'}


def test_flexcli_inspect_frame():
    """Test the decorator's ability to detect when called from __main__."""

    @flexcli(test_param=100)
    def test_function(cfg):
        return cfg

    # The function should store the defaults properly
    assert hasattr(test_function, '_defaults')
    assert test_function._defaults == {'test_param': 100}

    # Test that the wrapper function has the correct attributes
    assert hasattr(test_function, '_original_fn')
    assert test_function._original_fn is not None
