import os
import pytest
from unittest.mock import patch

from naga import unsafe_debug

def test_debug_decorator_inactive_by_default():
    """Verify the decorator does nothing when NAGA_DEBUG is not set."""

    @unsafe_debug
    def failing_function():
        x = 1
        y = 0
        z = x / y
        return z

    with pytest.raises(ZeroDivisionError):
        failing_function()

    assert 'x' not in locals(), "Variable 'x' should not be injected when decorator is inactive"
    assert 'y' not in locals(), "Variable 'y' should not be injected when decorator is inactive"

@patch.dict(os.environ, {"NAGA_DEBUG": "0"})
def test_debug_decorator_explicitly_inactive():
    """Verify the decorator does nothing when NAGA_DEBUG is '0'."""

    @unsafe_debug
    def failing_function():
        x = 1
        y = 0
        z = x / y
        return z

    with pytest.raises(ZeroDivisionError):
        failing_function()

    assert 'x' not in locals(), "Variable 'x' should not be injected when NAGA_DEBUG='0'"
    assert 'y' not in locals(), "Variable 'y' should not be injected when NAGA_DEBUG='0'"

@patch.dict(os.environ, {"NAGA_DEBUG": "1"})
def test_debug_decorator_active_and_injects_on_exception():
    """Verify the decorator injects local variables into the caller's frame when NAGA_DEBUG='1'."""

    @unsafe_debug
    def failing_function():
        a = 100
        b = 0
        c = a / b
        return c

    with pytest.raises(ZeroDivisionError):
        failing_function()

    assert 'a' in locals(), "Variable 'a' should have been injected by the debug decorator"
    assert 'b' in locals(), "Variable 'b' should have been injected by the debug decorator"
    assert locals()['a'] == 100, "Injected variable 'a' should have the correct value"
    assert locals()['b'] == 0, "Injected variable 'b' should have the correct value"

@patch.dict(os.environ, {"NAGA_DEBUG": "true"})
def test_debug_decorator_active_with_true_string():
    """Verify the decorator activates when NAGA_DEBUG='true'."""

    @unsafe_debug
    def failing_function():
        text_var = "hello"
        raise RuntimeError("A test error")

    with pytest.raises(RuntimeError):
        failing_function()

    assert 'text_var' in locals(), "Variable should be injected when NAGA_DEBUG='true'"
    assert locals()['text_var'] == "hello", "Injected variable should have the correct value"
