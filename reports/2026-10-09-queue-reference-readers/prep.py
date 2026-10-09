"""Full preparation with baseline/current reader implementation, mocked sbatch."""
from pathlib import Path
import runpy
import sys
from context import install_baseline


if __name__ == '__main__':
    if '--baseline' in sys.argv:
        sys.argv.remove('--baseline')
        install_baseline()
    driver = Path(__file__).resolve().parents[1]/'2026-10-08-process-preparation'/'case.py'
    runpy.run_path(str(driver))['main']()
