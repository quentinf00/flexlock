"""Refuse personal filesystem paths in public documentation and shipped skills."""
import re
from pathlib import Path
root = Path(__file__).resolve().parents[2]
paths = [root / "README.md", * (root / "docs").rglob("*.md"),
         *(root / "docs").rglob("*.rst"), *(root / "flexlock/skills").rglob("*.md")]
bad = []
for path in paths:
    if "_build" in path.parts:
        continue
    for number, line in enumerate(path.read_text().splitlines(), 1):
        if re.search(r"/(?:ontap|scale|home|jobscratch)/", line):
            bad.append(f"{path.relative_to(root)}:{number}")
if bad:
    raise SystemExit("Personal filesystem paths in public docs: " + ", ".join(bad))
print("Public documentation path check passed")
