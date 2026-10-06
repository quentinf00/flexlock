"""Explicit project index setup and read-only discovery diagnostics."""
import json
import os
from pathlib import Path
import uuid

from .index import INDEX_DIRNAME, INDEX_FILENAME, _connect, resolve_index_path


def initialize(root='.') -> dict:
    """Initialize the requested project without moving existing nested indexes."""
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError(f'Project root must be an existing directory: {root}')
    index_path = root / INDEX_DIRNAME / INDEX_FILENAME
    override = os.environ.get('FLEXLOCK_INDEX')
    if override and Path(override).resolve() != index_path:
        raise ValueError(f'FLEXLOCK_INDEX selects {Path(override).resolve()}, not {index_path}; '
                         'unset it or initialize the matching project root')
    directory = index_path.parent
    directory.mkdir(exist_ok=True)
    metadata_path = directory / 'project.json'
    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text())
        if metadata.get('version') != 1 or not metadata.get('project_id'):
            raise ValueError(f'Invalid project metadata: {metadata_path}')
    else:
        metadata = dict(version=1, project_id=uuid.uuid4().hex)
        try:
            with metadata_path.open('x') as stream:
                json.dump(metadata, stream, indent=2)
                stream.write('\n')
        except FileExistsError:
            metadata = json.loads(metadata_path.read_text())
    _connect(index_path).close()
    (directory / 'presets').mkdir(exist_ok=True)
    return diagnose(root)


def diagnose(start='.') -> dict:
    """Explain effective scope without creating or changing files/databases."""
    from .presets import presets_roots

    start = Path(start).resolve()
    index_path = resolve_index_path(start).resolve()
    metadata_path = index_path.parent / 'project.json'
    metadata, errors = None, []
    if metadata_path.exists():
        try:
            metadata = json.loads(metadata_path.read_text())
        except (OSError, ValueError) as exc:
            errors.append(f'Cannot read {metadata_path}: {exc}')
    expected = index_path.parent / 'presets'
    roots = list(dict.fromkeys(map(str, [expected, *presets_roots(start)])))
    if not index_path.exists():
        errors.append('No fingerprint index exists at the effective path; run flexlock init '
                      'at the intended project root before launching, or reindex historical runs.')
    if metadata is None:
        errors.append('No explicit project identity; legacy .flexlock directory discovery still applies.')
    return dict(start=str(start), index_path=str(index_path),
                index_exists=index_path.is_file(),
                source='FLEXLOCK_INDEX' if os.environ.get('FLEXLOCK_INDEX') else
                       ('project-directory' if index_path.parent.is_dir() else 'fallback'),
                project=metadata, presets_roots=roots, diagnostics=errors)
