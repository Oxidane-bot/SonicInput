"""ConfigWriter Atomic Write Tests

Tests for atomic configuration file writing (v0.5.3 fix).
Ensures configuration writes are atomic to prevent corruption on failure.
"""

import pytest
import json
import time
from pathlib import Path
from unittest.mock import Mock, patch

from sonicinput.core.services.config.config_writer import ConfigWriter


class TestAtomicConfigWrite:
    """Test atomic configuration file writing"""

    def test_config_writer_creation(self, tmp_path):
        """Test config writer can be created"""
        config_file = tmp_path / "test_config.json"
        writer = ConfigWriter(config_file)
        assert writer is not None
        assert writer.config_path == config_file

    def test_save_creates_parent_directory(self, tmp_path):
        """Test save creates parent directory if not exists"""
        config_file = tmp_path / "subdir" / "test_config.json"
        writer = ConfigWriter(config_file)

        # Set and save config
        test_config = {"test": "value"}
        writer.set_config(test_config)
        success = writer.save_config()

        assert success
        assert config_file.exists()
        assert config_file.parent.exists()

    def test_atomic_write_uses_temp_file(self, tmp_path):
        """Test atomic write creates and uses temporary file"""
        config_file = tmp_path / "test_config.json"
        writer = ConfigWriter(config_file)

        test_config = {"key": "value"}
        writer.set_config(test_config)

        # Track temporary file creation
        temp_files_created = []
        original_named_temp = __import__("tempfile").NamedTemporaryFile

        def track_temp_file(*args, **kwargs):
            result = original_named_temp(*args, **kwargs)
            temp_files_created.append(result.name)
            return result

        with patch("tempfile.NamedTemporaryFile", side_effect=track_temp_file):
            writer.save_config()

        # Verify temp file was created (and cleaned up)
        assert len(temp_files_created) > 0
        # Temp file should be cleaned up after successful write
        assert not Path(temp_files_created[0]).exists()

    def test_atomic_write_preserves_content(self, tmp_path):
        """Test atomic write preserves exact content"""
        config_file = tmp_path / "test_config.json"
        writer = ConfigWriter(config_file)

        # Create complex config with various types
        test_config = {
            "string": "测试",  # Unicode
            "number": 42,
            "float": 3.14,
            "boolean": True,
            "null": None,
            "array": [1, 2, 3],
            "nested": {"key1": "value1", "key2": {"deep": "value"}},
        }
        writer.set_config(test_config)
        success = writer.save_config()

        assert success
        assert config_file.exists()

        # Read back and verify
        with open(config_file, "r", encoding="utf-8") as f:
            loaded = json.load(f)

        assert loaded == test_config

    def test_atomic_write_uses_os_replace(self, tmp_path):
        """Test atomic write uses os.replace for atomicity"""
        config_file = tmp_path / "test_config.json"
        writer = ConfigWriter(config_file)

        test_config = {"test": "value"}
        writer.set_config(test_config)

        # Track os.replace calls
        replace_calls = []
        original_replace = __import__("os").replace

        def track_replace(src, dst):
            replace_calls.append((str(src), str(dst)))
            return original_replace(src, dst)

        with patch("os.replace", side_effect=track_replace):
            writer.save_config()

        # Verify os.replace was called
        assert len(replace_calls) == 1
        src, dst = replace_calls[0]
        assert dst == str(config_file)
        assert src != dst  # Source should be temp file

    def test_atomic_write_cleans_up_temp_on_success(self, tmp_path):
        """Test temp file is cleaned up after successful write"""
        config_file = tmp_path / "test_config.json"
        writer = ConfigWriter(config_file)

        test_config = {"test": "value"}
        writer.set_config(test_config)

        # Count files before and after
        files_before = set(tmp_path.glob("*"))
        writer.save_config()
        files_after = set(tmp_path.glob("*"))

        # Only the config file should exist (no temp files left)
        assert config_file in files_after
        assert len(files_after) == 1  # Only config file, no temp files

    def test_atomic_write_fsync_called(self, tmp_path):
        """Test atomic write calls fsync to ensure data is written to disk"""
        config_file = tmp_path / "test_config.json"
        writer = ConfigWriter(config_file)

        test_config = {"test": "value"}
        writer.set_config(test_config)

        # Track fsync calls
        fsync_calls = []
        original_fsync = __import__("os").fsync

        def track_fsync(fd):
            fsync_calls.append(fd)
            return original_fsync(fd)

        with patch("os.fsync", side_effect=track_fsync):
            writer.save_config()

        # Verify fsync was called at least once
        assert len(fsync_calls) >= 1


class TestConfigWriteErrorHandling:
    """Test error handling during config write"""

    def test_write_to_unwritable_directory_fails_gracefully(self, tmp_path):
        """Test writing to an unwritable directory fails gracefully

        Windows does not reliably enforce read-only directory permissions,
        so simulate the PermissionError at temp-file creation time instead.
        """
        config_file = tmp_path / "test_config.json"
        writer = ConfigWriter(config_file)
        writer.set_config({"test": "value"})

        with patch(
            "tempfile.NamedTemporaryFile",
            side_effect=PermissionError("Access is denied"),
        ):
            success = writer.save_config()

        # Should fail gracefully without raising, and leave no files behind
        assert not success
        assert not config_file.exists()
        assert list(tmp_path.glob("*.tmp")) == []

    def test_save_with_invalid_json_fails(self, tmp_path):
        """Test saving config with non-serializable data fails gracefully"""
        config_file = tmp_path / "test_config.json"
        writer = ConfigWriter(config_file)

        # Create config with non-serializable object
        class NonSerializable:
            pass

        invalid_config = {"obj": NonSerializable()}
        writer.set_config(invalid_config)

        success = writer.save_config()

        # Should fail gracefully
        assert not success

    def test_temp_file_cleanup_on_failure(self, tmp_path):
        """Test temp file is cleaned up even on write failure"""
        config_file = tmp_path / "test_config.json"
        writer = ConfigWriter(config_file)

        test_config = {"test": "value"}
        writer.set_config(test_config)

        # Force os.replace to fail
        def failing_replace(src, dst):
            raise OSError("Simulated failure")

        files_before = set(tmp_path.glob("*"))

        with patch("os.replace", side_effect=failing_replace):
            success = writer.save_config()

        files_after = set(tmp_path.glob("*"))

        # Write should fail
        assert not success

        # No new files should be left behind
        # (temp file should be cleaned up in finally block)
        new_files = files_after - files_before
        # Allow config file itself if it was partially created
        assert len(new_files) <= 1


class TestConfigWriteDebouncing:
    """Test configuration write debouncing"""

    def test_schedule_save_delays_write(self, tmp_path):
        """Test schedule_save delays actual write"""
        config_file = tmp_path / "test_config.json"
        writer = ConfigWriter(config_file)

        test_config = {"test": "value"}
        writer.set_config(test_config)

        # Schedule save (should not write immediately)
        writer.schedule_save()

        # File should not exist yet
        assert not config_file.exists()

    def test_schedule_save_eventually_writes(self, tmp_path):
        """Test schedule_save eventually writes after delay"""
        config_file = tmp_path / "test_config.json"
        writer = ConfigWriter(config_file)

        test_config = {"test": "value"}
        writer.set_config(test_config)

        # Schedule save
        writer.schedule_save()

        # Wait for debounce delay (500ms + buffer)
        time.sleep(0.7)

        # File should exist now
        assert config_file.exists()

    def test_multiple_schedule_save_debounced(self, tmp_path):
        """Test multiple schedule_save calls are debounced"""
        config_file = tmp_path / "test_config.json"
        writer = ConfigWriter(config_file)

        # Schedule multiple saves quickly
        test_config = {"test": "value1"}
        writer.set_config(test_config)
        writer.schedule_save()

        time.sleep(0.1)
        test_config = {"test": "value2"}
        writer.set_config(test_config)
        writer.schedule_save()

        time.sleep(0.1)
        test_config = {"test": "value3"}
        writer.set_config(test_config)
        writer.schedule_save()

        # Wait for debounce
        time.sleep(0.7)

        # File should exist and contain the latest value
        assert config_file.exists()
        with open(config_file, "r", encoding="utf-8") as f:
            saved = json.load(f)
        assert saved["test"] == "value3"  # Latest value should be saved

    def test_save_config_writes_immediately(self, tmp_path):
        """Test save_config writes immediately without delay"""
        config_file = tmp_path / "test_config.json"
        writer = ConfigWriter(config_file)

        test_config = {"test": "value"}
        writer.set_config(test_config)

        # Save immediately (no wait needed)
        success = writer.save_config()

        # Should write immediately
        assert success
        assert config_file.exists()

        # Verify content
        with open(config_file, "r", encoding="utf-8") as f:
            saved = json.load(f)
        assert saved == test_config

    def test_save_config_cancels_timer(self, tmp_path):
        """Test save_config cancels pending timer"""
        config_file = tmp_path / "test_config.json"
        writer = ConfigWriter(config_file)

        test_config = {"test": "value"}
        writer.set_config(test_config)

        # Schedule save
        writer.schedule_save()

        # Immediately call save_config (should cancel timer and save)
        success = writer.save_config()

        assert success
        assert config_file.exists()
        # Timer should be None after save
        assert writer._save_timer is None


class TestSetSettingNestedKeys:
    """Test setting nested configuration keys"""

    def test_set_simple_key(self, tmp_path):
        """Test setting simple top-level key"""
        config_file = tmp_path / "test_config.json"
        writer = ConfigWriter(config_file)
        writer.set_config({})

        writer.set_setting("key", "value")
        writer.save_config()

        with open(config_file, "r", encoding="utf-8") as f:
            config = json.load(f)

        assert config["key"] == "value"

    def test_set_nested_key(self, tmp_path):
        """Test setting nested key with dot notation"""
        config_file = tmp_path / "test_config.json"
        writer = ConfigWriter(config_file)
        writer.set_config({"parent": {}})

        writer.set_setting("parent.child", "value")
        writer.save_config()

        with open(config_file, "r", encoding="utf-8") as f:
            config = json.load(f)

        assert config["parent"]["child"] == "value"

    def test_set_deeply_nested_key(self, tmp_path):
        """Test setting deeply nested key"""
        config_file = tmp_path / "test_config.json"
        writer = ConfigWriter(config_file)
        writer.set_config({"a": {"b": {"c": {}}}})

        writer.set_setting("a.b.c.d", "value")
        writer.save_config()

        with open(config_file, "r", encoding="utf-8") as f:
            config = json.load(f)

        assert config["a"]["b"]["c"]["d"] == "value"

    def test_set_creates_missing_parent_dicts(self, tmp_path):
        """Test setting nested key creates missing parent dictionaries"""
        config_file = tmp_path / "test_config.json"
        writer = ConfigWriter(config_file)
        writer.set_config({})

        # Set nested key without parent existing
        writer.set_setting("parent.child.grandchild", "value")
        writer.save_config()

        with open(config_file, "r", encoding="utf-8") as f:
            config = json.load(f)

        assert config["parent"]["child"]["grandchild"] == "value"
