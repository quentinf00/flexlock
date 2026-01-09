"""Tests for flexcli Jupyter/interactive window support."""

import pytest
import sys
from unittest.mock import patch, MagicMock
from flexlock.flexcli import _is_jupyter_or_interactive, _should_use_cli_mode, flexcli


class TestJupyterDetection:
    """Test detection of Jupyter/interactive environments."""

    def test_is_jupyter_without_ipython(self):
        """Test when IPython is not available."""
        with patch.dict('sys.modules', {'IPython': None}):
            assert not _is_jupyter_or_interactive()

    def test_is_jupyter_with_ipython_kernel(self):
        """Test when IPython kernel is running."""
        mock_ipython = MagicMock()
        mock_ipython.config = {'IPKernelApp': {}}

        with patch('IPython.get_ipython', return_value=mock_ipython):
            assert _is_jupyter_or_interactive()

    def test_is_jupyter_with_none_ipython(self):
        """Test when get_ipython returns None."""
        with patch('IPython.get_ipython', return_value=None):
            assert not _is_jupyter_or_interactive()

    def test_is_interactive_with_ps1(self):
        """Test detection with sys.ps1 (python -i)."""
        sys.ps1 = '>>> '
        try:
            assert _is_jupyter_or_interactive()
        finally:
            if hasattr(sys, 'ps1'):
                delattr(sys, 'ps1')


class TestCLIModeDetection:
    """Test CLI mode detection logic."""

    def test_should_use_cli_normal_script(self):
        """Test CLI mode for normal script execution."""
        with patch.object(sys, 'argv', ['script.py', '-o', 'param=2']):
            with patch('flexlock.flexcli._is_jupyter_or_interactive', return_value=False):
                assert _should_use_cli_mode()

    def test_should_not_use_cli_ipykernel_launcher(self):
        """Test that ipykernel_launcher is detected and CLI is disabled."""
        with patch.object(sys, 'argv', ['ipykernel_launcher.py', '--f=/path/to/kernel.json']):
            assert not _should_use_cli_mode()

    def test_should_not_use_cli_kernel_args_with_dash_f(self):
        """Test detection of kernel args with -f."""
        with patch.object(sys, 'argv', ['python', '-f', '/tmp/kernel-123.json']):
            assert not _should_use_cli_mode()

    def test_should_not_use_cli_kernel_args_with_double_dash_f(self):
        """Test detection of kernel args with --f=."""
        with patch.object(sys, 'argv', ['python', '--f=/tmp/kernel-456.json']):
            assert not _should_use_cli_mode()

    def test_should_use_cli_with_ipython_run(self):
        """Test that %run in IPython still parses CLI args."""
        # When using %run script.py -o param=2, sys.argv is ['script.py', '-o', 'param=2']
        with patch.object(sys, 'argv', ['test_script.py', '-o', 'param=2']):
            # Even if in interactive, no kernel args → should parse
            assert _should_use_cli_mode()

    def test_should_use_cli_with_normal_dash_f_arg(self):
        """Test that non-kernel -f arguments don't trigger detection."""
        # User might have -f flag for something else (not .json file)
        with patch.object(sys, 'argv', ['script.py', '-f', 'output.txt']):
            # No .json in the argument, should parse
            assert _should_use_cli_mode()


class TestFlexcliJupyterIntegration:
    """Test flexcli behavior in different environments."""

    def test_flexcli_direct_call_with_args(self):
        """Test direct function call with arguments always executes."""

        @flexcli
        def train(lr=0.01, epochs=10):
            return {"lr": lr, "epochs": epochs}

        # Direct call with args - should execute regardless of environment
        result = train(lr=0.1, epochs=20)
        assert result['lr'] == 0.1
        assert result['epochs'] == 20

    @patch('flexlock.flexcli._should_use_cli_mode', return_value=False)
    @patch('flexlock.flexcli._is_jupyter_or_interactive', return_value=True)
    def test_flexcli_jupyter_no_args_uses_defaults(self, mock_interactive, mock_cli_mode):
        """Test that calling with no args in Jupyter uses defaults."""

        @flexcli(lr=0.01, epochs=10)
        def train(lr=0.01, epochs=10):
            return {"lr": lr, "epochs": epochs}

        # In Jupyter, calling train() should use defaults
        result = train()
        assert result['lr'] == 0.01
        assert result['epochs'] == 10

    @patch.object(sys, 'argv', ['ipykernel_launcher.py', '--f=/tmp/kernel.json'])
    @patch('flexlock.flexcli._is_jupyter_or_interactive', return_value=True)
    def test_flexcli_ignores_kernel_args(self, mock_interactive):
        """Test that kernel args don't cause parser errors."""

        @flexcli(param=5)
        def process(param=1):
            return param * 2

        # Should not try to parse kernel args, just use defaults
        result = process()
        assert result == 10  # param=5 * 2

    @patch.object(sys, 'argv', ['test_script.py', '-o', 'param=3'])
    @patch('flexlock.flexcli._is_jupyter_or_interactive', return_value=True)
    @patch('flexlock.flexcli.FlexLockRunner')
    def test_flexcli_ipython_run_parses_args(self, mock_runner, mock_interactive):
        """Test that %run script.py -o param=3 still works."""

        mock_runner_instance = MagicMock()
        mock_runner.return_value = mock_runner_instance
        mock_runner_instance.run.return_value = "success"

        @flexcli(param=1)
        def process(param=1):
            return param * 2

        # Should parse CLI args from %run
        result = process()

        # Runner should be called (CLI parsing happens)
        assert mock_runner.called
        assert mock_runner_instance.run.called

    @patch('flexlock.flexcli._should_use_cli_mode', return_value=True)
    @patch('flexlock.flexcli.FlexLockRunner')
    def test_flexcli_normal_script_uses_runner(self, mock_runner, mock_cli_mode):
        """Test normal script execution uses FlexLockRunner."""

        mock_runner_instance = MagicMock()
        mock_runner.return_value = mock_runner_instance
        mock_runner_instance.run.return_value = {"result": "success"}

        @flexcli(param=1)
        def process(param=1):
            return param

        # In normal script mode, should use runner
        result = process()

        # Verify runner was used
        assert mock_runner.called
        assert mock_runner_instance.run.called


class TestEdgeCases:
    """Test edge cases and corner scenarios."""

    def test_vscode_interactive_window_args(self):
        """Test VSCode interactive window specific argv pattern."""
        # VSCode uses similar pattern to Jupyter
        with patch.object(sys, 'argv', [
            'ipykernel_launcher.py',
            '-f',
            '/path/to/vscode-kernel-123.json'
        ]):
            assert not _should_use_cli_mode()

    def test_empty_argv(self):
        """Test behavior with empty argv."""
        with patch.object(sys, 'argv', []):
            # Should not crash, default to interactive mode
            assert not _should_use_cli_mode()

    def test_argv_with_only_script_name(self):
        """Test argv with just script name."""
        with patch.object(sys, 'argv', ['script.py']):
            assert _should_use_cli_mode()

    def test_dash_f_with_non_json_file(self):
        """Test -f with non-JSON file doesn't trigger kernel detection."""
        with patch.object(sys, 'argv', ['script.py', '-f', 'data.csv']):
            # Not a kernel arg (no .json), should parse
            assert _should_use_cli_mode()

    def test_dash_f_in_middle_of_args(self):
        """Test -f argument in middle doesn't trigger if not kernel."""
        with patch.object(sys, 'argv', ['script.py', '-o', 'param=1', '-f', 'output.txt']):
            # No .json file, should parse normally
            assert _should_use_cli_mode()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
