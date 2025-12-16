#!/usr/bin/env python3

"""Test script for the snapshot implementation."""

import os
import tempfile
import shutil
from pathlib import Path
from flexlock.runner import FlexLockRunner
from flexlock.flexcli import flexcli
from flexlock.utils import py2cfg
from omegaconf import OmegaConf
import yaml


def simple_train(data_path, save_dir=None):
    """Simple training function for testing."""
    print(f"Training on {data_path}")
    if save_dir:
        print(f"Save directory: {save_dir}")
    return f"Training completed with data from {data_path}"

def test_yaml_config():
    """Test snapshot functionality with YAML configuration."""
    print("=== Testing YAML Configuration ===")
    
    # Create a temporary directory structure
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create data directory
        data_dir = temp_path / "data" / "raw"
        data_dir.mkdir(parents=True)
        
        # Create a dummy data file
        dummy_data = data_dir / "images.txt"
        dummy_data.write_text("dummy image data")
        
        # Create YAML config
        config_content = f"""
stage1:
  _target_: test_snapshot_implementation.simple_train
  data_path: "{dummy_data}"
  _snapshot_:
    data:
      raw_images: ${{stage1.data_path}}
"""
        config_file = temp_path / "config.yaml"
        config_file.write_text(config_content)
        
        # Run with FlexLock
        runner = FlexLockRunner()
        result = runner.run(["--config", str(config_file), "--select", "stage1"])
        
        print(f"Result: {result}")
        
        # Check if run.lock was created
        # The save_dir should be outputs/stage1/<timestamp>
        outputs_dir = temp_path / "outputs" / "stage1"
        if outputs_dir.exists():
            run_dirs = list(outputs_dir.iterdir())
            if run_dirs:
                run_dir = run_dirs[0]
                lock_file = run_dir / "run.lock"
                if lock_file.exists():
                    with open(lock_file, 'r') as f:
                        lock_data = yaml.safe_load(f)
                    print(f"run.lock created successfully: {lock_data}")
                    
                    # Check if data was hashed
                    if "data" in lock_data:
                        print(f"Data hashed: {lock_data['data']}")
                    else:
                        print("No data found in run.lock")
                else:
                    print("run.lock not found")
            else:
                print("No run directories found")
        else:
            print("Outputs directory not created")

def _traindec(data_path, save_dir=None):
    print(f"Training on {data_path}")
    if save_dir:
        print(f"Save directory: {save_dir}")
    return "Training completed"
def test_decorator_config():
    """Test snapshot functionality with decorator configuration."""
    print("\n=== Testing Decorator Configuration ===")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create data directory
        data_dir = temp_path / "data" / "mnist"
        data_dir.mkdir(parents=True)
        
        # Create a dummy data file
        dummy_data = data_dir / "train.csv"
        dummy_data.write_text("dummy mnist data")
        
        traindec=flexcli(
            data_path=str(dummy_data),
            snapshot_config={
                "repos": {"main": os.getcwd()},
                "data": {"input_dataset": "${data_path}"}
            }
        )(_traindec)
        
        # Change to temp directory for the test
        original_cwd = os.getcwd()
        try:
            os.chdir(temp_path)
            result = traindec()
            print(f"Training result: {result}")
            
            # Check if run.lock was created
            # The save_dir should be outputs/train/<timestamp>
            outputs_dir = temp_path / "outputs" / "train"
            if outputs_dir.exists():
                run_dirs = list(outputs_dir.iterdir())
                if run_dirs:
                    run_dir = run_dirs[0]
                    lock_file = run_dir / "run.lock"
                    if lock_file.exists():
                        with open(lock_file, 'r') as f:
                            lock_data = yaml.safe_load(f)
                        print(f"run.lock created successfully: {lock_data}")
                        
                        # Check if data was hashed
                        if "data" in lock_data:
                            print(f"Data hashed: {lock_data['data']}")
                        else:
                            print("No data found in run.lock")
                    else:
                        print("run.lock not found")
                else:
                    print("No run directories found")
            else:
                print("Outputs directory not created")
        finally:
            os.chdir(original_cwd)

def train_fn2(data_path, epochs=10, save_dir=None):
    print(f"Training on {data_path} for {epochs} epochs")
    if save_dir:
        print(f"Save directory: {save_dir}")
    return "Training completed"

def test_py2cfg_config():
    """Test snapshot functionality with py2cfg configuration."""
    print("\n=== Testing py2cfg Configuration ===")
    
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create data directory
        data_dir = temp_path / "data" / "raw"
        data_dir.mkdir(parents=True)
        
        # Create a dummy data file
        dummy_data = data_dir / "data.zip"
        dummy_data.write_text("dummy zip data")
        
        # Create config using py2cfg
        config = {
            "experiment_1": py2cfg(
                train_fn2,
                epochs=20,
                data_path=str(dummy_data),
                _snapshot_={
                    "repos": {"main": "."},
                    "data": {"raw": str(dummy_data)}
                }
            )
        }
        
        # Save config to file
        config_file = temp_path / "config.py"
        with open(config_file, 'w') as f:
            f.write(f"config = {config}")
        
        # Run with FlexLock
        runner = FlexLockRunner()
        result = runner.run(["--defaults", str(config_file), "--select", "experiment_1"])
        
        print(f"Result: {result}")
        
        # Check if run.lock was created
        outputs_dir = temp_path / "outputs" / "experiment_1"
        if outputs_dir.exists():
            run_dirs = list(outputs_dir.iterdir())
            if run_dirs:
                run_dir = run_dirs[0]
                lock_file = run_dir / "run.lock"
                if lock_file.exists():
                    with open(lock_file, 'r') as f:
                        lock_data = yaml.safe_load(f)
                    print(f"run.lock created successfully: {lock_data}")
                    
                    # Check if data was hashed
                    if "data" in lock_data:
                        print(f"Data hashed: {lock_data['data']}")
                    else:
                        print("No data found in run.lock")
                else:
                    print("run.lock not found")
            else:
                print("No run directories found")
        else:
            print("Outputs directory not created")

if __name__ == "__main__":
    print("Testing FlexLock Snapshot Implementation")
    
    try:
        test_yaml_config()
        test_decorator_config()
        test_py2cfg_config()
        print("\n=== All tests completed ===")
    except Exception as e:
        print(f"Test failed with error: {e}")
        import traceback
        traceback.print_exc()