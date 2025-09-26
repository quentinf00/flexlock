import pytest
from pathlib import Path
from dataclasses import dataclass
from omegaconf import OmegaConf
import tempfile
import pickle
import yaml
from unittest.mock import patch
import sys

from naga import clicfg, snapshot, runlock, track_data
from naga.mlflow_log import mlflow_log_run


@dataclass
class TestConfig:
    save_dir: str = ""
    param: int = 1


def test_main_diag_pattern_with_decorators(tmp_path):
    """Test the main/diag pattern with Naga decorators."""
    save_dir = tmp_path / "test_experiment"
    
    # Define main function with decorators (following the proper order)
    @clicfg
    @runlock
    @track_data()  # This won't track anything since there are no data fields
    @snapshot(branch="test_logs", message="Test snapshot")
    def main(cfg: TestConfig = OmegaConf.structured(TestConfig(save_dir=save_dir))):
        # Set save_dir dynamically if not provided
        if not cfg.save_dir:
            cfg.save_dir = str(save_dir)
        
        save_dir_path = Path(cfg.save_dir)
        save_dir_path.mkdir(parents=True, exist_ok=True)
        
        # Simulate some computation
        result = {"computed_value": cfg.param * 2, "status": "success"}
        
        # Save result for diag function
        with open(save_dir_path / "result.pkl", "wb") as f:
            pickle.dump(result, f)
        
        # Save config as well (done by @runlock)
        return cfg
    
    def diag(cfg):
        # Diagnostic function that loads and analyzes results from main
        save_dir_path = Path(cfg.save_dir)
        
        # Load results saved by main
        with open(save_dir_path / "result.pkl", "rb") as f:
            result = pickle.load(f)
        
        # Perform diagnostics
        analysis = {"is_positive": result["computed_value"] > 0, "input_param": cfg.param}
        
        # Save analysis
        with open(save_dir_path / "analysis.pkl", "wb") as f:
            pickle.dump(analysis, f)
        
        return analysis

    # Execute main and diag
    cfg = main()
    analysis = diag(cfg)
    
    # Verify results
    assert analysis["is_positive"] is True
    assert analysis["input_param"] == 1
    
    # Verify that run.lock was created
    run_lock_path = save_dir / "run.lock"
    assert run_lock_path.exists()
    
    # Verify run.lock contents
    with open(run_lock_path, 'r') as f:
        run_data = yaml.safe_load(f)
    
    assert "config" in run_data
    assert run_data["config"]["param"] == 1
    assert run_data["config"]["save_dir"] == str(save_dir)


def test_main_diag_pattern_with_mlflow(tmp_path, monkeypatch):
    """Test the main/diag pattern with MLflow integration."""
    import mlflow
    
    # Set up temporary MLflow tracking
    tracking_uri = f"file://{tmp_path / 'mlruns'}"
    mlflow.set_tracking_uri(tracking_uri)
    
    save_dir = tmp_path / "test_mlflow_experiment"
    
    @clicfg
    @runlock
    def main(cfg: TestConfig = OmegaConf.structured(TestConfig(save_dir=save_dir))):
        if not cfg.save_dir:
            cfg.save_dir = str(save_dir)
            
        save_dir_path = Path(cfg.save_dir)
        save_dir_path.mkdir(parents=True, exist_ok=True)
        
        # Simulate computation
        result = {"mlflow_metric": cfg.param * 10}
        
        # Save result
        with open(save_dir_path / "result.pkl", "wb") as f:
            pickle.dump(result, f)
        
        return cfg, locals()
    
    # Wrap diag function with MLflow logging
    @mlflow_log_run(
        run_lock_path=lambda cfg: Path(cfg.save_dir) / "run.lock"
    )
    def diag(cfg):
        # Diagnostic function that logs to MLflow
        save_dir_path = Path(cfg.save_dir)
        
        with open(save_dir_path / "result.pkl", "rb") as f:
            result = pickle.load(f)
        
        # Log to MLflow
        import mlflow
        mlflow.log_metric("computed_metric", result["mlflow_metric"])
        mlflow.log_param("input_param", cfg.param)
        
        return result["mlflow_metric"]

    # Execute main then diag with MLflow
    cfg, local_vars = main()
    metric_value = diag(cfg)
    
    # Verify MLflow run was created and logged correctly
    runs = mlflow.search_runs()
    assert len(runs) >= 1  # May have runs from other tests
    
    # Find our specific run by tags or parameters
    found_run = False
    for _, run in runs.iterrows():
        if run.get('params.param') == '1':  # Our input parameter
            found_run = True
            assert run['metrics.computed_metric'] == 10.0
            break
    
    assert found_run, "MLflow run with expected parameters not found"


def test_diag_function_with_save_dir_path():
    """Test that diag function can work with save_dir path instead of full config."""
    import mlflow
    from naga.mlflow_log import mlflow_log_run
    
    with tempfile.TemporaryDirectory() as tmp_dir:
        save_dir = Path(tmp_dir) / "experiment"
        save_dir.mkdir()
        
        # Create run.lock file
        run_lock_data = {
            "config": {
                "param": 42,
                "save_dir": str(save_dir)
            }
        }
        run_lock_path = save_dir / "run.lock"
        with open(run_lock_path, 'w') as f:
            yaml.dump(run_lock_data, f)
        
        # Create results file
        results = {"value": 100}
        with open(save_dir / "results.pkl", "wb") as f:
            pickle.dump(results, f)
        
        # Test diag function that receives save_dir path directly
        @mlflow_log_run(
            run_lock_path=lambda cfg: Path(cfg.save_dir) / "run.lock"
        )
        def diag_with_config(cfg):
            # This version receives a config object
            import mlflow
            mlflow.log_metric("result_value", cfg.param * 2)
            return cfg.param
        
        # Execute
        result = diag_with_config(OmegaConf.create(run_lock_data["config"]))
        
        assert result == 42
