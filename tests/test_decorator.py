import os
from unittest.mock import patch
import pytest
from omegaconf import OmegaConf
from dataclasses import dataclass

from naga import naga

# Define a simple config for testing
@dataclass
class SimpleConfig:
    param: int = 1
    data_path: str = "fake/path"

# Keep track of calls
mock_calls = {}

# Mock the decorators to test the chaining
def mock_decorator(name, **params):
    def decorator(fn):
        mock_calls.setdefault(name, []).append(params)
        def wrapper(*args, **kwargs):
            return fn(*args, **kwargs)
        return wrapper
    return decorator

patch('naga.decorator.clicfg', lambda fn: mock_decorator('clicfg')(fn)).start()
patch('naga.decorator.snapshot', lambda **kwargs: mock_decorator('snapshot', **kwargs)).start()
patch('naga.decorator.track_data', lambda *args: mock_decorator('track_data', keys=args)).start()
patch('naga.decorator.load_stage', lambda *args: mock_decorator('load_stage', keys=args)).start()
patch('naga.decorator.runlock', lambda fn: mock_decorator('runlock')(fn)).start()
patch('naga.decorator.unsafe_debug', lambda fn: mock_decorator('unsafe_debug')(fn)).start()


@pytest.fixture(autouse=True)
def reset_mocks():
    mock_calls.clear()

def test_naga_decorator_defaults():
    """Test that @naga applies default decorators."""

    @naga()
    def main(cfg=OmegaConf.structured(SimpleConfig)):
        pass
    
    main()

    assert 'clicfg' in mock_calls
    assert 'runlock' in mock_calls
    assert 'unsafe_debug' in mock_calls
    assert 'snapshot' not in mock_calls  # No params, so not called
    assert 'track_data' not in mock_calls
    assert 'load_stage' not in mock_calls

def test_naga_decorator_all_params():
    """Test that @naga correctly passes parameters to underlying decorators."""

    snapshot_args = {'branch': 'test', 'message': 'A test'}
    track_data_args = ['data_path']
    load_stage_args = ['prev_stage']

    @naga(
        snapshot_params=snapshot_args,
        track_data_params=track_data_args,
        load_stage_params=load_stage_args
    )
    def main(cfg=OmegaConf.structured(SimpleConfig)):
        pass

    main()

    assert 'snapshot' in mock_calls
    assert mock_calls['snapshot'][0] == snapshot_args

    assert 'track_data' in mock_calls
    assert mock_calls['track_data'][0]['keys'] == tuple(track_data_args)

    assert 'load_stage' in mock_calls
    assert mock_calls['load_stage'][0]['keys'] == tuple(load_stage_args)

def test_naga_decorator_disable_flags():
    """Test that boolean flags can disable decorators."""

    @naga(
        use_clicfg=False,
        use_runlock=False,
        use_debug=False
    )
    def main(cfg=OmegaConf.structured(SimpleConfig)):
        pass

    main()

    assert 'clicfg' not in mock_calls
    assert 'runlock' not in mock_calls
    assert 'unsafe_debug' not in mock_calls
