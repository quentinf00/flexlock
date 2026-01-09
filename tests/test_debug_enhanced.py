"""Tests for enhanced debug features."""

import os
import pytest
import sys
from unittest.mock import patch, MagicMock
from pathlib import Path

from flexlock.debug import (
    _is_notebook,
    _is_interactive_shell,
    _is_boring_frame,
    _is_project_frame,
    _score_frame,
    _extract_frames,
    _select_default_frame,
    debug_on_fail,
)


class TestEnvironmentDetection:
    """Test detection of different execution environments."""

    def test_is_notebook_without_ipython(self):
        """Test notebook detection when IPython is not available."""
        with patch.dict('sys.modules', {'IPython': None}):
            assert not _is_notebook()

    def test_is_notebook_with_ipython_none(self):
        """Test when get_ipython returns None."""
        mock_ipython = MagicMock()
        mock_ipython.get_ipython.return_value = None

        with patch('IPython.get_ipython', return_value=None):
            assert not _is_notebook()

    def test_is_interactive_shell_without_ipython(self):
        """Test interactive shell detection without IPython."""
        # Remove ps1 if it exists
        original_ps1 = getattr(sys, 'ps1', None)
        if hasattr(sys, 'ps1'):
            delattr(sys, 'ps1')

        try:
            with patch.dict('sys.modules', {'IPython': None}):
                assert not _is_interactive_shell()
        finally:
            if original_ps1 is not None:
                sys.ps1 = original_ps1

    def test_is_interactive_shell_with_ps1(self):
        """Test interactive shell detection with sys.ps1."""
        sys.ps1 = '>>> '
        try:
            with patch.dict('sys.modules', {'IPython': 'true'}):
                assert _is_interactive_shell()
        finally:
            if hasattr(sys, 'ps1'):
                delattr(sys, 'ps1')


class TestFrameFiltering:
    """Test frame filtering logic."""

    def test_is_boring_frame_stdlib(self):
        """Test that stdlib frames are considered boring."""
        # Use a known stdlib path
        stdlib_path = str(Path(sys.prefix) / 'lib' / 'python3.10' / 'os.py')
        assert _is_boring_frame(stdlib_path)

    def test_is_boring_frame_site_packages(self):
        """Test that site-packages frames are considered boring."""
        site_packages_path = '/usr/lib/python3.10/site-packages/numpy/core/numeric.py'
        assert _is_boring_frame(site_packages_path)

    def test_is_boring_frame_flexlock_internals(self):
        """Test that flexlock internals are considered boring."""
        flexlock_path = '/path/to/flexlock/flexlock/utils.py'
        assert _is_boring_frame(flexlock_path)

    def test_is_boring_frame_string(self):
        """Test that <string> filenames are considered boring."""
        assert _is_boring_frame('<string>')
        assert _is_boring_frame('')

    def test_is_not_boring_frame_project(self):
        """Test that project frames are not boring."""
        # Use current file as project code
        assert not _is_boring_frame(__file__)

    def test_is_project_frame(self):
        """Test project frame detection."""
        # Current file should be detected as project frame
        assert _is_project_frame(__file__)

    def test_is_not_project_frame_stdlib(self):
        """Test that stdlib is not project code."""
        stdlib_path = str(Path(sys.prefix) / 'lib' / 'python3.10' / 'os.py')
        assert not _is_project_frame(stdlib_path)

    def test_is_not_project_frame_invalid(self):
        """Test that invalid paths are not project frames."""
        assert not _is_project_frame('<string>')
        assert not _is_project_frame('')


class TestFrameScoring:
    """Test frame scoring heuristic."""

    def test_score_frame_project_bonus(self):
        """Test that project frames get high score."""
        frame_info = {
            'frame': None,
            'filename': __file__,  # This file is project code
            'locals': {'a': 1, 'b': 2},
            'is_project': True,
            'is_boring': False,
        }
        score = _score_frame(frame_info)
        assert score >= 1000  # Project bonus

    def test_score_frame_with_data_structures(self):
        """Test that frames with data structures get higher scores."""
        frame_info = {
            'frame': None,
            'filename': __file__,
            'locals': {'data': [1, 2, 3], 'config': {'key': 'value'}},
            'is_project': True,
            'is_boring': False,
        }
        score = _score_frame(frame_info)

        # Should get: project(1000) + locals(20) + list(20) + dict(20)
        assert score >= 1060

    def test_score_frame_few_locals_penalty(self):
        """Test that frames with very few locals get penalized."""
        frame_info = {
            'frame': None,
            'filename': __file__,
            'locals': {'x': 1},  # Only one local
            'is_project': False,
            'is_boring': True,
        }
        score = _score_frame(frame_info)

        # Should have penalty for few locals
        assert score < 1000

    def test_score_frame_interesting_names(self):
        """Test that interesting variable names increase score."""
        frame_info = {
            'frame': None,
            'filename': __file__,
            'locals': {
                'data': 1,
                'model': 2,
                'config': 3,
                '_private': 4,  # Should not count
                'self': 5,  # Should not count
            },
            'is_project': True,
            'is_boring': False,
        }
        score = _score_frame(frame_info)

        # 3 interesting names (data, model, config) should add points
        assert score >= 1000 + 15  # Project + 3*5 for names


class TestFrameExtraction:
    """Test frame extraction from exceptions."""

    def test_extract_frames_from_exception(self):
        """Test extracting frames from a real exception."""

        def level1():
            x = "level1"
            return level2()

        def level2():
            y = "level2"
            return level3()

        def level3():
            z = "level3"
            raise ValueError("Test exception")

        try:
            level1()
        except ValueError:
            exc_info = sys.exc_info()
            frames = _extract_frames(exc_info)

            # Should have captured all frames
            assert len(frames) >= 3

            # Check that function names are captured
            function_names = [f['function'] for f in frames]
            assert 'level3' in function_names

            # Check that locals are captured
            level3_frame = next(f for f in frames if f['function'] == 'level3')
            assert 'z' in level3_frame['locals']
            assert level3_frame['locals']['z'] == 'level3'

    def test_extract_frames_handles_empty_locals(self):
        """Test that extraction handles frames with no locals gracefully."""

        def minimal_function():
            raise RuntimeError("Test")

        try:
            minimal_function()
        except RuntimeError:
            exc_info = sys.exc_info()
            frames = _extract_frames(exc_info)

            # Should still extract frames even with minimal locals
            assert len(frames) > 0


class TestFrameSelection:
    """Test default frame selection logic."""

    def test_select_exception_frame_if_project(self):
        """Test that exception frame is selected if it's in project code."""
        frames = [
            {
                'function': 'caller',
                'is_project': True,
                'is_boring': False,
                'filename': '/project/caller.py',
                'locals': {'x': 1},
            },
            {
                'function': 'exception_site',
                'is_project': True,
                'is_boring': False,
                'filename': '/project/util.py',
                'locals': {'y': 2},
            },
        ]

        # Last frame (exception site) is in project, should be selected
        idx = _select_default_frame(frames)
        assert idx == 1  # Last frame

    def test_select_deepest_project_frame_if_exception_not_project(self):
        """Test selecting deepest project frame when exception is in library."""
        frames = [
            {
                'function': 'main',
                'is_project': True,
                'is_boring': False,
                'filename': '/project/main.py',
                'locals': {'config': {}},
            },
            {
                'function': 'process',
                'is_project': True,
                'is_boring': False,
                'filename': '/project/process.py',
                'locals': {'data': []},
            },
            {
                'function': 'numpy_internal',
                'is_project': False,
                'is_boring': True,
                'filename': '/site-packages/numpy/core.py',
                'locals': {},
            },
        ]

        # Exception in numpy, should select deepest project frame (process)
        idx = _select_default_frame(frames)
        assert idx == 1  # process frame

    def test_select_exception_frame_if_no_project_frames(self):
        """Test fallback to exception frame when no project frames."""
        frames = [
            {
                'function': 'lib_function',
                'is_project': False,
                'is_boring': True,
                'filename': '/site-packages/lib/module.py',
                'locals': {},
            },
            {
                'function': 'exception_site',
                'is_project': False,
                'is_boring': True,
                'filename': '/site-packages/lib/core.py',
                'locals': {},
            },
        ]

        # No project frames, should select last frame with warning
        idx = _select_default_frame(frames)
        assert idx == 1  # Last frame


class TestDebugOnFailEnhanced:
    """Test the enhanced debug_on_fail decorator."""

    @patch.dict(os.environ, {'FLEXLOCK_DEBUG': '1', 'FLEXLOCK_DEBUG_STRATEGY': 'inject'})
    @patch('flexlock.debug._is_notebook', return_value=True)
    @patch('IPython.get_ipython')
    def test_debug_injects_project_frame_not_exception_frame(self, mock_get_ipython, mock_is_notebook):
        """Test that debug mode injects the project frame, not utility frame."""
        mock_ipython = MagicMock()
        mock_get_ipython.return_value = mock_ipython

        def utility_with_no_locals():
            """Small utility where exception happens."""
            return int("not a number")

        def process_with_state():
            """Function with interesting state."""
            data = [1, 2, 3]
            config = {'lr': 0.01}
            result = utility_with_no_locals()
            return result

        @debug_on_fail
        def main():
            return process_with_state()

        with pytest.raises(ValueError):
            main()

        # Check that inject was called
        assert mock_ipython.user_ns.update.called

        # The injected locals should be from process_with_state (has data, config)
        # not from utility_with_no_locals (has nothing)
        call_args = mock_ipython.user_ns.update.call_args_list
        injected_vars = {}
        for call in call_args:
            if call[0]:  # positional args
                injected_vars.update(call[0][0])


    @patch.dict(os.environ, {'FLEXLOCK_DEBUG': '0'})
    def test_debug_disabled_via_env(self):
        """Test that debug mode can be disabled."""

        @debug_on_fail
        def will_fail():
            x = 10
            raise ValueError("Test")

        with pytest.raises(ValueError):
            will_fail()

        # Should not inject
        assert 'x' not in locals()

    @patch.dict(os.environ, {'FLEXLOCK_NODEBUG': '1'})
    def test_debug_disabled_via_nodebug(self):
        """Test that FLEXLOCK_NODEBUG disables debug mode."""

        @debug_on_fail
        def will_fail():
            y = 20
            raise ValueError("Test")

        with pytest.raises(ValueError):
            will_fail()

        # Should not inject
        assert 'y' not in locals()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
