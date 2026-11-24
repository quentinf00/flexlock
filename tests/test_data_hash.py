import pytest
from pathlib import Path
from omegaconf import OmegaConf
from dataclasses import dataclass
import time
import os
import sqlite3
from unittest.mock import patch, call

from flexlock.data_hash import hash_data, _get_db
from flexlock.context import run_context

# --- Fixtures ---


@pytest.fixture(autouse=True)
def clear_cache_before_each_test(tmp_path):
    """Fixture to ensure the cache is clear and isolated for each test."""
    cache_dir = tmp_path / ".cache" / "flexlock"
    Path(cache_dir).mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / "hashes.db"

    # Mock the CACHE_DB path
    with patch("flexlock.data_hash.CACHE_DB", cache_file):
        if cache_file.exists():
            os.remove(cache_file)
        yield
        if cache_file.exists():
            os.remove(cache_file)


@pytest.fixture
def test_data(tmp_path):
    """Create a standard small test directory."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "file1.txt").write_text("hello")
    sub_dir = data_dir / "sub"
    sub_dir.mkdir()
    (sub_dir / "file2.log").write_text("world")
    return data_dir


# --- Basic Tests ---


def test_hash_data_file(test_data):
    """Test hashing a single file."""
    file_path = test_data / "file1.txt"
    file_hash = hash_data(file_path)
    assert isinstance(file_hash, str) and len(file_hash) == 16


def test_hash_data_directory(test_data):
    """Test hashing a directory and that it changes on modification."""
    dir_hash1 = hash_data(test_data)
    assert isinstance(dir_hash1, str)

    (test_data / "file1.txt").write_text("changed")
    dir_hash2 = hash_data(test_data)
    assert dir_hash1 != dir_hash2


# --- Caching Logic Tests ---


def test_hash_caching_file(test_data):
    """Verify that a file hash is cached and reused."""
    file_path = test_data / "file1.txt"
    hash1 = hash_data(file_path)

    # Check that the hash is stored in the SQLite database
    with _get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT hash FROM cache WHERE path=? AND is_dir=0", (str(file_path.resolve()),))
        row = cursor.fetchone()
        assert row is not None  # Entry should exist in database
        assert row[0] == hash1  # Hash should match

    hash2 = hash_data(file_path)
    assert hash1 == hash2


def test_hash_cache_rebuilds_damaged_database(test_data):
    from flexlock.data_hash import CACHE_DB

    broken = b"this is not a sqlite database" * 32
    CACHE_DB.write_bytes(broken)
    source = test_data / "file1.txt"
    assert hash_data(source) == hash_data(source, use_cache=False)
    (quarantine,) = CACHE_DB.parent.glob(f"{CACHE_DB.name}.corrupt-*")
    assert (quarantine / CACHE_DB.name).read_bytes() == broken
    with _get_db() as conn:
        assert conn.execute("SELECT path FROM cache").fetchone() == (str(source),)


def test_hash_cache_migrates_wal_database(test_data):
    from flexlock.data_hash import CACHE_DB

    with _get_db() as conn:
        conn.execute("INSERT INTO cache VALUES ('existing', 0, NULL, NULL, 'hash', 0)")
    conn = sqlite3.connect(CACHE_DB)
    try:
        assert conn.execute("PRAGMA journal_mode=WAL").fetchone() == ("wal",)
    finally:
        conn.close()
    hash_data(test_data / "file1.txt")
    conn = sqlite3.connect(CACHE_DB)
    try:
        assert conn.execute("PRAGMA journal_mode").fetchone() == ("delete",)
        assert conn.execute("SELECT hash FROM cache WHERE path='existing'").fetchone() == ("hash",)
    finally:
        conn.close()


def test_hash_caching_file_invalidation(test_data):
    """Verify that modifying a file invalidates the cache."""
    file_path = test_data / "file1.txt"
    hash1 = hash_data(file_path)
    time.sleep(0.01)  # Ensure mtime is different
    file_path.write_text("new content")
    hash2 = hash_data(file_path)
    assert hash1 != hash2


def test_small_dir_cache_invalidation_by_content(test_data):
    """Test that changing a file's content in a small dir invalidates the cache."""
    hash1 = hash_data(test_data)
    time.sleep(0.01)
    # Modify a nested file. This should change the 'latest_mtime'.
    (test_data / "sub" / "file2.log").write_text("new world")
    hash2 = hash_data(test_data)
    assert hash1 != hash2


def test_small_dir_cache_invalidation_by_add_file(test_data):
    """Test that adding a file to a small dir invalidates the cache."""
    hash1 = hash_data(test_data)
    (test_data / "new_file.txt").write_text("a new file")
    hash2 = hash_data(test_data)
    assert hash1 != hash2


def test_large_dir_detects_nested_edit_with_unchanged_root_mtime(tmp_path, monkeypatch):
    monkeypatch.setenv("FLEXLOCK_CACHE_DIR_FILE_LIMIT", "5")
    root = tmp_path / "large"
    root.mkdir()
    for i in range(10):
        (root / f"file{i}").write_text(str(i))
    before = hash_data(root)
    original = root.stat().st_mtime_ns
    (root / "file3").write_text("changed")
    assert root.stat().st_mtime_ns == original
    assert hash_data(root) != before


def test_directory_ignores_aggregate_cache_and_preserved_timestamps(test_data):
    before = hash_data(test_data)
    file = test_data / "sub" / "file2.log"
    stat = file.stat()
    file.write_text("WORLD")
    os.utime(file, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    assert hash_data(test_data) != before
    with _get_db() as conn:
        assert conn.execute("SELECT * FROM cache WHERE is_dir=1").fetchone() is None


def test_directory_filters_are_independent_and_overlap_is_deduplicated(test_data):
    complete = hash_data(test_data, jobs=1)
    selected = hash_data(test_data, match="**/*.txt", jobs=1)
    assert selected != complete
    assert hash_data(test_data, ignore="*.log", jobs=1) == selected
    assert hash_data(test_data, match=["**/*", "**/*.txt"], jobs=1) == complete


def test_directory_rename_detected_below_newer_file(test_data):
    newest = test_data / "file1.txt"
    os.utime(newest, (2000000000, 2000000000))
    before = hash_data(test_data)
    (test_data / "sub" / "file2.log").rename(test_data / "sub" / "renamed.log")
    assert hash_data(test_data) != before


def test_flexlock_no_cache_env_variable(test_data, monkeypatch):
    """Test that FLEXLOCK_NO_CACHE=1 disables the cache."""
    monkeypatch.setenv("FLEXLOCK_NO_CACHE", "1")
    hash_data(test_data)
    with _get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT mtime, file_count FROM cache WHERE path=?", (str(test_data.resolve()),))
        row = cursor.fetchone()
    assert row is None


# --- use_cache argument (issue 4) ---


def test_use_cache_false_does_not_write_cache(test_data):
    """use_cache=False must recompute and never persist to the cache DB."""
    hash_data(test_data, use_cache=False)
    with _get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM cache WHERE path=?", (str(test_data.resolve()),))
        assert cursor.fetchone() is None


def test_use_cache_false_never_opens_db():
    """use_cache=False must not touch the cache DB at all."""
    with patch("flexlock.data_hash._get_db") as mock_db:
        mock_db.side_effect = AssertionError("cache DB opened despite use_cache=False")
        # Hash a temp file created inline so we don't depend on _get_db.
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as fh:
            fh.write("payload")
            fpath = fh.name
        try:
            hash_data(fpath, use_cache=False)
        finally:
            os.remove(fpath)


def test_no_cache_env_forces_off_even_when_use_cache_true(test_data, monkeypatch):
    """FLEXLOCK_NO_CACHE overrides use_cache=True (force-off only)."""
    monkeypatch.setenv("FLEXLOCK_NO_CACHE", "yes")
    hash_data(test_data, use_cache=True)
    with _get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM cache WHERE path=?", (str(test_data.resolve()),))
        assert cursor.fetchone() is None


# --- dirhash includes file paths (issue 5) ---


def test_dirhash_distinguishes_file_names(tmp_path):
    """Identical contents under different names must hash differently."""
    d1 = tmp_path / "d1"
    d1.mkdir()
    (d1 / "a.txt").write_text("same")
    (d1 / "b.txt").write_text("content")

    d2 = tmp_path / "d2"
    d2.mkdir()
    (d2 / "x.txt").write_text("same")
    (d2 / "y.txt").write_text("content")

    assert hash_data(d1, use_cache=False) != hash_data(d2, use_cache=False)


def test_dirhash_detects_content_swap(tmp_path):
    """Swapping contents between two files changes the directory hash."""
    d = tmp_path / "d"
    d.mkdir()
    (d / "a.txt").write_text("AAA")
    (d / "b.txt").write_text("BBB")
    before = hash_data(d, use_cache=False)

    (d / "a.txt").write_text("BBB")
    (d / "b.txt").write_text("AAA")
    after = hash_data(d, use_cache=False)

    assert before != after


def test_snapshot_records_directory_identity_method(test_data, tmp_path):
    from flexlock.snapshot import RunTracker

    tracker = RunTracker(tmp_path / 'run')
    tracker.record_data({'dataset': str(test_data)})
    identity = tracker.data['data_identity']['dataset']
    assert identity == {
        'path': str(test_data.resolve()),
        'method': 'directory_selected_paths_and_content',
        'algorithm': 'xxh64',
    }
    assert tracker.data['data']['dataset'] == hash_data(test_data)
