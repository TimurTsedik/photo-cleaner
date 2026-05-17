"""Minimal smoke test: verify that log() writes to file without double-printing
and that operations calling log() do not crash."""

import contextlib
import io
import logging
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from photo_cleaner.logging_config import log, logger


class LogTests(unittest.TestCase):
    def test_log_to_file_only(self):
        """log() with user=False writes to file but NOT to stdout."""
        with tempfile.TemporaryDirectory() as tmp:
            log_path = os.path.join(tmp, "test.log")

            # Reconfigure logger to use a temporary file
            for handler in logger.handlers[:]:
                logger.removeHandler(handler)

            fh = logging.FileHandler(log_path)
            logger.addHandler(fh)

            log("debug message", level="debug")

            with open(log_path) as f:
                content = f.read()

            self.assertIn("debug message", content)

    def test_user_true_prints_to_stdout(self):
        """log(..., user=True) calls print() — captured by redirect_stdout."""
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            log("hello admin", level="info", user=True)
        self.assertEqual(buf.getvalue(), "hello admin\n")

    def test_log_no_user_no_print(self):
        """log(..., user=False) does NOT call print()."""
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            log("internal only", level="debug")
        self.assertEqual(buf.getvalue(), "")


class OperationsDoesNotCrashTests(unittest.TestCase):
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
