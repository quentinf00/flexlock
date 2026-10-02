"""Check that the version declarations agree (and match the tag, if given).

The wheel version comes from ``flexlock/__init__.py`` (hatch dynamic version);
the conda package version from ``[tool.pixi.package] version`` in
pyproject.toml. Usage: ``python .github/scripts/check_version.py [vX.Y.Z]``.
"""

import re
import sys
import tomllib
from pathlib import Path

root = Path(__file__).resolve().parents[2]
init = (root / "flexlock" / "__init__.py").read_text()
m = re.search(r'^__version__\s*=\s*"([^"]+)"', init, re.M)
if not m:
    sys.exit("could not find __version__ in flexlock/__init__.py")
py_version = m.group(1)

pixi_version = tomllib.loads((root / "pyproject.toml").read_text())["tool"]["pixi"]["package"]["version"]

errors = []
if py_version != pixi_version:
    errors.append(
        f"flexlock/__init__.py __version__={py_version!r} != "
        f"[tool.pixi.package] version={pixi_version!r}"
    )
if len(sys.argv) > 1:
    tag = sys.argv[1].removeprefix("refs/tags/")
    if tag != f"v{py_version}":
        errors.append(f"tag {tag!r} does not match package version v{py_version}")

if errors:
    sys.exit("\n".join(errors))
print(f"version OK: {py_version}")
