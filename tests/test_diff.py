"""Tests for the RunDiff class."""

import pytest
from flexlock.diff import RunDiff
from omegaconf import OmegaConf


class TestRunDiff:
    """Test suite for RunDiff class."""

    def test_simple_value_comparison_match(self):
        """Test that identical simple values match."""
        current = {"config": {"lr": 0.01, "epochs": 10}}
        target = {"config": {"lr": 0.01, "epochs": 10}}

        diff = RunDiff(current, target)
        assert diff.compare_config() is True
        assert diff.diffs == {}

    def test_simple_value_comparison_mismatch(self):
        """Test that different simple values don't match."""
        current = {"config": {"lr": 0.01, "epochs": 10}}
        target = {"config": {"lr": 0.02, "epochs": 10}}

        diff = RunDiff(current, target)
        assert diff.compare_config() is False
        assert "config" in diff.diffs
        assert any("lr" in d for d in diff.diffs["config"])

    def test_nested_dict_comparison(self):
        """Test recursive comparison of nested dictionaries."""
        current = {
            "config": {
                "model": {
                    "type": "mlp",
                    "hidden_size": 128,
                    "activation": "relu"
                },
                "optimizer": {
                    "type": "adam",
                    "lr": 0.001
                }
            }
        }
        target = {
            "config": {
                "model": {
                    "type": "mlp",
                    "hidden_size": 128,
                    "activation": "relu"
                },
                "optimizer": {
                    "type": "adam",
                    "lr": 0.001
                }
            }
        }

        diff = RunDiff(current, target)
        assert diff.compare_config() is True

    def test_nested_dict_mismatch(self):
        """Test that nested differences are detected."""
        current = {
            "config": {
                "model": {
                    "type": "mlp",
                    "hidden_size": 128
                },
                "optimizer": {
                    "type": "adam",
                    "lr": 0.001
                }
            }
        }
        target = {
            "config": {
                "model": {
                    "type": "mlp",
                    "hidden_size": 256  # Different!
                },
                "optimizer": {
                    "type": "adam",
                    "lr": 0.001
                }
            }
        }

        diff = RunDiff(current, target)
        assert diff.compare_config() is False
        assert "config" in diff.diffs
        assert any("model.hidden_size" in d for d in diff.diffs["config"])

    def test_ignore_save_dir(self):
        """Test that save_dir is ignored during comparison."""
        current = {
            "config": {
                "lr": 0.01,
                "save_dir": "outputs/run_001"
            }
        }
        target = {
            "config": {
                "lr": 0.01,
                "save_dir": "outputs/run_999"
            }
        }

        diff = RunDiff(current, target)
        assert diff.compare_config() is True

    def test_ignore_timestamp(self):
        """Test that timestamp is ignored during comparison."""
        current = {
            "config": {
                "lr": 0.01,
                "timestamp": "2024-01-01T00:00:00"
            }
        }
        target = {
            "config": {
                "lr": 0.01,
                "timestamp": "2024-12-31T23:59:59"
            }
        }

        diff = RunDiff(current, target)
        assert diff.compare_config() is True

    def test_path_normalization(self):
        """Test that paths containing save_dir are normalized."""
        current = {
            "config": {
                "lr": 0.01,
                "save_dir": "outputs/run_001",
                "log_file": "outputs/run_001/train.log",
                "checkpoint": "outputs/run_001/model.pth"
            }
        }
        target = {
            "config": {
                "lr": 0.01,
                "save_dir": "outputs/run_999",
                "log_file": "outputs/run_999/train.log",
                "checkpoint": "outputs/run_999/model.pth"
            }
        }

        diff = RunDiff(
            current,
            target,
            current_save_dir="outputs/run_001",
            target_save_dir="outputs/run_999"
        )
        assert diff.compare_config() is True

    def test_path_normalization_with_mismatch(self):
        """Test that actual differences are still detected after normalization."""
        current = {
            "config": {
                "lr": 0.01,
                "save_dir": "outputs/run_001",
                "log_file": "outputs/run_001/train.log",
                "data_path": "/data/train.csv"  # Different!
            }
        }
        target = {
            "config": {
                "lr": 0.01,
                "save_dir": "outputs/run_999",
                "log_file": "outputs/run_999/train.log",
                "data_path": "/data/test.csv"  # Different!
            }
        }

        diff = RunDiff(
            current,
            target,
            current_save_dir="outputs/run_001",
            target_save_dir="outputs/run_999"
        )
        assert diff.compare_config() is False
        assert any("data_path" in d for d in diff.diffs["config"])

    def test_list_comparison_match(self):
        """Test that identical lists match."""
        current = {
            "config": {
                "layers": [128, 256, 512],
                "activations": ["relu", "relu", "softmax"]
            }
        }
        target = {
            "config": {
                "layers": [128, 256, 512],
                "activations": ["relu", "relu", "softmax"]
            }
        }

        diff = RunDiff(current, target)
        assert diff.compare_config() is True

    def test_list_comparison_mismatch(self):
        """Test that different lists are detected."""
        current = {
            "config": {
                "layers": [128, 256, 512]
            }
        }
        target = {
            "config": {
                "layers": [128, 512, 512]  # Different!
            }
        }

        diff = RunDiff(current, target)
        assert diff.compare_config() is False

    def test_list_length_mismatch(self):
        """Test that lists with different lengths are detected."""
        current = {
            "config": {
                "layers": [128, 256]
            }
        }
        target = {
            "config": {
                "layers": [128, 256, 512]
            }
        }

        diff = RunDiff(current, target)
        assert diff.compare_config() is False
        assert any("length mismatch" in d for d in diff.diffs["config"])

    def test_nested_list_of_dicts(self):
        """Test comparison of nested structures with lists of dicts."""
        current = {
            "config": {
                "experiments": [
                    {"lr": 0.01, "batch_size": 32},
                    {"lr": 0.001, "batch_size": 64}
                ]
            }
        }
        target = {
            "config": {
                "experiments": [
                    {"lr": 0.01, "batch_size": 32},
                    {"lr": 0.001, "batch_size": 64}
                ]
            }
        }

        diff = RunDiff(current, target)
        assert diff.compare_config() is True

    def test_missing_key(self):
        """Test that missing keys are detected."""
        current = {
            "config": {
                "lr": 0.01,
                "epochs": 10
            }
        }
        target = {
            "config": {
                "lr": 0.01,
                "epochs": 10,
                "batch_size": 32  # Extra key!
            }
        }

        diff = RunDiff(current, target)
        assert diff.compare_config() is False
        assert any("Missing in current" in d or "Extra in current" in d
                   for d in diff.diffs["config"])

    def test_custom_ignore_keys(self):
        """Test that custom ignore keys work."""
        current = {
            "config": {
                "lr": 0.01,
                "job_id": "job_123",
                "custom_field": "value_a"
            }
        }
        target = {
            "config": {
                "lr": 0.01,
                "job_id": "job_456",
                "custom_field": "value_b"
            }
        }

        diff = RunDiff(current, target, ignore_keys=["custom_field"])
        assert diff.compare_config() is True  # job_id and custom_field both ignored

    def test_git_comparison_match(self):
        """Test that git tree hashes are compared."""
        current = {
            "repos": {
                "main": {"tree": "abc123", "commit": "def456"}
            }
        }
        target = {
            "repos": {
                "main": {"tree": "abc123", "commit": "ghi789"}
            }
        }

        diff = RunDiff(current, target)
        assert diff.compare_git() is True  # Same tree hash

    def test_git_comparison_mismatch(self):
        """Test that different git tree hashes are detected."""
        current = {
            "repos": {
                "main": {"tree": "abc123"}
            }
        }
        target = {
            "repos": {
                "main": {"tree": "xyz789"}
            }
        }

        diff = RunDiff(current, target)
        assert diff.compare_git() is False
        assert "git" in diff.diffs

    def test_data_comparison_match(self):
        """Test that data hashes are compared."""
        current = {
            "data": {
                "train": "hash_abc",
                "test": "hash_def"
            }
        }
        target = {
            "data": {
                "train": "hash_abc",
                "test": "hash_def"
            }
        }

        diff = RunDiff(current, target)
        assert diff.compare_data() is True

    def test_data_comparison_mismatch(self):
        """Test that different data hashes are detected."""
        current = {
            "data": {
                "train": "hash_abc"
            }
        }
        target = {
            "data": {
                "train": "hash_xyz"
            }
        }

        diff = RunDiff(current, target)
        assert diff.compare_data() is False
        assert "data" in diff.diffs

    def test_is_match_all_pass(self):
        """Test that is_match returns True when all comparisons pass."""
        current = {
            "config": {"lr": 0.01},
            "repos": {"main": {"tree": "abc123"}},
            "data": {"train": "hash_abc"}
        }
        target = {
            "config": {"lr": 0.01},
            "repos": {"main": {"tree": "abc123"}},
            "data": {"train": "hash_abc"}
        }

        diff = RunDiff(current, target)
        assert diff.is_match() is True

    def test_is_match_config_fail(self):
        """Test that is_match returns False when config differs."""
        current = {
            "config": {"lr": 0.01},
            "repos": {"main": {"tree": "abc123"}},
            "data": {"train": "hash_abc"}
        }
        target = {
            "config": {"lr": 0.02},  # Different!
            "repos": {"main": {"tree": "abc123"}},
            "data": {"train": "hash_abc"}
        }

        diff = RunDiff(current, target)
        assert diff.is_match() is False

    def test_omegaconf_integration(self):
        """Test that OmegaConf DictConfig objects work correctly."""
        current_dict = OmegaConf.create({
            "config": {
                "model": {"type": "mlp", "size": 128},
                "lr": 0.01
            }
        })
        target_dict = OmegaConf.create({
            "config": {
                "model": {"type": "mlp", "size": 128},
                "lr": 0.01
            }
        })

        # Convert to container for comparison
        current = OmegaConf.to_container(current_dict)
        target = OmegaConf.to_container(target_dict)

        diff = RunDiff(current, target)
        assert diff.compare_config() is True

    def test_complex_real_world_scenario(self):
        """Test a realistic scenario with all features combined."""
        current = {
            "config": {
                "save_dir": "outputs/exp_001/run_001",
                "timestamp": "2024-01-01T00:00:00",
                "model": {
                    "type": "transformer",
                    "layers": [512, 512, 512],
                    "dropout": 0.1
                },
                "optimizer": {
                    "type": "adam",
                    "lr": 0.001,
                    "betas": [0.9, 0.999]
                },
                "data_path": "/data/train.csv",
                "log_file": "outputs/exp_001/run_001/training.log",
                "checkpoint_path": "outputs/exp_001/run_001/model.pth"
            },
            "repos": {
                "main": {"tree": "abc123def456"}
            },
            "data": {
                "train": "hash_train_123",
                "val": "hash_val_456"
            }
        }

        target = {
            "config": {
                "save_dir": "outputs/exp_001/run_999",
                "timestamp": "2024-12-31T23:59:59",
                "model": {
                    "type": "transformer",
                    "layers": [512, 512, 512],
                    "dropout": 0.1
                },
                "optimizer": {
                    "type": "adam",
                    "lr": 0.001,
                    "betas": [0.9, 0.999]
                },
                "data_path": "/data/train.csv",
                "log_file": "outputs/exp_001/run_999/training.log",
                "checkpoint_path": "outputs/exp_001/run_999/model.pth"
            },
            "repos": {
                "main": {"tree": "abc123def456"}
            },
            "data": {
                "train": "hash_train_123",
                "val": "hash_val_456"
            }
        }

        diff = RunDiff(
            current,
            target,
            current_save_dir="outputs/exp_001/run_001",
            target_save_dir="outputs/exp_001/run_999"
        )

        # Should match because:
        # - save_dir is ignored
        # - timestamp is ignored
        # - paths with save_dir are normalized
        # - all other config is identical
        # - git tree is identical
        # - data hashes are identical
        assert diff.is_match() is True


class TestRunDiffCorrectness:
    """Regression tests for issues 7, 8, 9."""

    def test_nested_user_key_not_ignored(self):
        """A user hyperparameter named 'time' nested in config must count (issue 7)."""
        current = {"config": {"train": {"time": 100}}}
        target = {"config": {"train": {"time": 200}}}
        diff = RunDiff(current, target)
        assert diff.compare_config() is False

    def test_toplevel_metadata_still_ignored(self):
        """Injected metadata at the config top level stays ignored."""
        current = {"config": {"time": "2024-01-01", "lr": 0.1}}
        target = {"config": {"time": "2024-12-31", "lr": 0.1}}
        diff = RunDiff(current, target)
        assert diff.compare_config() is True

    def test_normalization_is_prefix_only(self):
        """Only exact/path-prefix matches are normalized, not substrings (issue 8)."""
        diff = RunDiff({}, {})
        root = "outputs/run_001"
        # A sibling dir that merely shares the string prefix (next char is not a
        # separator) must be left intact — the old substring replace corrupted it.
        assert diff._normalize_val("outputs/run_001_backup/x", root) == (
            "outputs/run_001_backup/x"
        )
        # Genuine path prefix and exact match are normalized.
        assert diff._normalize_val("outputs/run_001/model.pth", root) == (
            "<SAVE_DIR>/model.pth"
        )
        assert diff._normalize_val(root, root) == "<SAVE_DIR>"

    def test_git_repo_only_in_target_flagged(self):
        """A repo present only in target is flagged (issue 9, symmetry)."""
        current = {"repos": {"a": {"tree": "x"}}}
        target = {"repos": {"a": {"tree": "x"}, "b": {"tree": "y"}}}
        diff = RunDiff(current, target)
        assert diff.compare_git() is False
        assert any("only in target" in m for m in diff.diffs["git"])

    def test_data_diff_names_the_key(self):
        """compare_data reports which key differs (issue 9)."""
        current = {"data": {"train": "h1", "val": "hv"}}
        target = {"data": {"train": "h2", "val": "hv"}}
        diff = RunDiff(current, target)
        assert diff.compare_data() is False
        assert any("train" in m for m in diff.diffs["data"])
        assert not any("val" in m for m in diff.diffs["data"])

    def test_note_only_difference_is_match(self):
        """Snapshots differing only in the top-level note still match."""
        current = {"note": "run A", "config": {"lr": 0.01}}
        target = {"note": "run B", "config": {"lr": 0.01}}
        diff = RunDiff(current, target)
        assert diff.is_match() is True

    def test_top_level_note_key_ignored_in_config(self):
        """A ``note`` key at the config top level is ignored (defensive)."""
        current = {"config": {"note": "x", "lr": 0.01}}
        target = {"config": {"note": "y", "lr": 0.01}}
        diff = RunDiff(current, target)
        assert diff.compare_config() is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
