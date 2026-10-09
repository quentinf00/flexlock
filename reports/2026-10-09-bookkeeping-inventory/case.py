"""File-saving prototype only. Its ownership reader gap is intentionally retained."""
from pathlib import Path
import runpy
import sys

from flexlock import destination_guard


def main():
    prototype = '--omit-nested-pointers' in sys.argv
    if prototype:
        sys.argv.remove('--omit-nested-pointers')
        original = destination_guard.reserve_queue

        def reserve_external(paths, db_path):
            root = Path(db_path).resolve().parent
            external = [p for p in paths if not Path(p).resolve().is_relative_to(root)]
            return original(external, db_path)
        destination_guard.reserve_queue = reserve_external
    driver = Path(__file__).resolve().parents[1]/'2026-10-08-process-preparation'/'case.py'
    runpy.run_path(str(driver))['main']()


if __name__ == '__main__':
    main()
