"""Required output contracts, checked at completion and before reuse.

Paths are relative to the run directory unless absolute. Hashing is opt-in;
schema/count validation belongs to a project callable receiving ``path``.
"""

import hashlib
import json
from pathlib import Path

from omegaconf import OmegaConf

from .exceptions import FlexLockValidationError
from .run_record import _atomic_write

MANIFEST = "run.outputs.json"


def _contracts(cfg, save_dir):
    raw = cfg.get("_outputs_")
    if raw is None:
        return {}
    if OmegaConf.is_config(raw):
        raw = OmegaConf.to_container(raw, resolve=True)
    if isinstance(raw, list):
        raw = {str(i): path for i, path in enumerate(raw)}
    if not isinstance(raw, dict):
        raise FlexLockValidationError("_outputs_ must be a list of paths or a name→contract mapping")
    contracts = {}
    original_root = Path(str(cfg.get("save_dir", save_dir))).absolute()
    for name, value in raw.items():
        spec = {"path": value} if isinstance(value, str) else value
        if not isinstance(spec, dict) or not isinstance(spec.get("path"), str):
            raise FlexLockValidationError(f"Output {name!r} requires a string path")
        unknown = set(spec) - {"path", "sha256", "validator"}
        if unknown or not isinstance(spec.get("sha256", False), bool):
            raise FlexLockValidationError(f"Invalid output contract {name!r}: {spec}")
        path = Path(spec["path"])
        if path.is_absolute():
            # A cache candidate can live at another save_dir. Rebase only
            # outputs inside the proposed run root; external paths stay exact.
            try:
                path = path.relative_to(original_root)
            except ValueError:
                pass
        else:
            # Already-resolved '${save_dir}/file' may be relative to cwd.
            try:
                path = path.absolute().relative_to(original_root)
            except ValueError:
                pass
        if not path.is_absolute():
            path = Path(save_dir) / path
        contracts[str(name)] = (path, spec)
    return contracts


def _digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_outputs(cfg, save_dir=None, *, completing=False, record_dir=None):
    """Raise on unhealthy outputs; persist checksums only on completion.

    Existing runs without contracts keep their original behavior. A checksum
    contract requires a completion manifest, so old runs cannot silently
    establish a new baseline during reuse.
    """
    save_dir = Path(save_dir if save_dir is not None else cfg.get("save_dir", "."))
    contracts = _contracts(cfg, save_dir)
    if not contracts:
        return
    previous = {}
    # Shared product roots have independent per-item completion baselines.
    manifest_path = Path(record_dir) / MANIFEST if record_dir is not None else save_dir / MANIFEST
    if not completing and manifest_path.exists():
        try:
            previous = json.loads(manifest_path.read_text())["outputs"]
        except (ValueError, KeyError, TypeError) as exc:
            raise FlexLockValidationError(f"Invalid output manifest at {manifest_path}: {exc}") from exc
    outputs = {}
    for name, (path, spec) in contracts.items():
        try:
            if not path.exists():
                raise ValueError("required path is missing")
            entry = {"path": str(path.absolute())}
            if spec.get("sha256", False):
                digest = _digest(path)
                if not completing and previous.get(name, {}).get("sha256") != digest:
                    raise ValueError("SHA256 differs from completion record or baseline is missing")
                entry["sha256"] = digest
            validator = spec.get("validator")
            if validator is not None:
                from .utils import instantiate

                if not isinstance(validator, dict) or "_target_" not in validator:
                    raise ValueError("validator requires an _target_ callable")
                if "path" in validator:
                    raise ValueError("validator path is supplied by the output contract")
                if instantiate(OmegaConf.create({**validator, "path": str(path)})) is False:
                    raise ValueError("validator returned False")
            outputs[name] = entry
        except Exception as exc:
            raise FlexLockValidationError(
                f"Output {name!r} at {path} failed integrity check: {exc}"
            ) from exc
    if completing:
        _atomic_write(manifest_path, json.dumps({"version": 1, "outputs": outputs}, indent=2))
