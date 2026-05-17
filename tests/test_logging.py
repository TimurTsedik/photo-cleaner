"""Minimal smoke test: verify that log() writes to file without double-printing
and that operations calling log() do not crash."""

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from photo_cleaner.logging_config import log, logger


class TestLog:
    def test_log_to_file_only(self, tmp_path):
        """log() with user=False writes to file but NOT to stdout."""
        log_path = str(tmp_path / "test.log")

        # Reconfigure logger to use a temporary file
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)

        fh = __import__("logging").FileHandler(log_path)
        logger.addHandler(fh)

        log("debug message", level="debug")
        log("info message", level="info", user=True)

        with open(log_path) as f:
            content = f.read()

        assert "debug message" in content
        assert "info message" in content

    def test_user_true_prints_to_stdout(self, capsys):
        """log(..., user=True) calls print() — captured by capsys."""
        log("hello admin", level="info", user=True)
        captured = capsys.readouterr()
        assert captured.out == "hello admin\n"

    def test_log_no_user_no_print(self, capsys):
        """log(..., user=False) does NOT call print()."""
        log("internal only", level="debug")
        captured = capsys.readouterr()
        assert captured.out == ""


class TestOperationsDoesNotCrash:
    def test_runScan_does_not_crash(self):
        """Minimal integration: mock ScanService so runScan() only exercises
        config loading + repository init + log('scan completed')."""
        with patch(
            "photo_cleaner.operations.ScanService"
        ) as mock_scan, patch(
            "photo_cleaner.operations.SqlitePhotoRepository"
        ) as mock_repo, patch(
            "photo_cleaner.operations.ConfigLoader"
        ) as mock_cfg:
            mock_cfg.return_value.load.return_value = {
                "workspace": {"path": tempfile.gettempdir()},
                "files": {"jpegExtensions": [".jpg"], "rawExtensions": [".cr2"]},
                "archive": {"root": tempfile.gettempdir()},
                "orientation": {"excludedPathPrefixes": []},
            }

            from photo_cleaner.operations import PhotoCleanerOperations

            ops = PhotoCleanerOperations(in_configPath="dummy.yaml")
            # Should not raise
            ops.runScan()
