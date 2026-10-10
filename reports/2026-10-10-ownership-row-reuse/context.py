"""Load retained old guard behavior for valid-locator comparison fixtures."""
import importlib.util
from pathlib import Path


def install_baseline():
    from flexlock import destination_guard
    path = Path(__file__).with_name('baseline_guard.py')
    spec = importlib.util.spec_from_file_location('flexlock._reference_baseline', path)
    baseline = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(baseline)
    destination_guard.has_active_destination = baseline.has_active_destination
    destination_guard.guard_destinations = baseline.guard_destinations
    destination_guard._product_databases = baseline._product_databases
