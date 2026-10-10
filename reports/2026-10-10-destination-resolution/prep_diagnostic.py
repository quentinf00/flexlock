"""Instrumented preparation diagnostic; excluded from benchmark medians."""
from pathlib import Path
import runpy
import sys
from context import install_baseline
from benchmarks.thousand_items import measure
if '--baseline' in sys.argv:
    sys.argv.remove('--baseline')
    install_baseline()
original = measure.run
def diagnostic(args):
    args.profile = True
    return original(args)
measure.run = diagnostic
runpy.run_path(str(Path(__file__).resolve().parents[1]/'2026-10-08-process-preparation'/'case.py'))['main']()
