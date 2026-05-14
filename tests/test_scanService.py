import tempfile
import unittest
from pathlib import Path

from photo_cleaner.infrastructure.sqlitePhotoRepository import (
    SqlitePhotoRepository,
)
from photo_cleaner.services.scanService import ScanService


class _FakeScanner:
    def __init__(
        self,
        in_scanResults: list[list[dict]],
    ) -> None:
        self._scanResults = list(in_scanResults)
        self._scanCallCount = 0

    def scan(
        self,
        in_archiveRoot: str,
        in_jpegExtensions: set[str],
        in_rawExtensions: set[str],
        in_excludedPathPrefixes: list[str],
    ) -> list[dict]:
        _ = in_archiveRoot
        _ = in_jpegExtensions
        _ = in_rawExtensions
        _ = in_excludedPathPrefixes

        if self._scanCallCount >= len(self._scanResults):
            return []
        ret = self._scanResults[self._scanCallCount]
        self._scanCallCount += 1
        return ret


class ScanServiceTests(unittest.TestCase):
    def test_scan_syncsDatabaseToCurrentScannerResults(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tempDir:
            dbPath = str(Path(tempDir) / "cleanup.db")
            repository = SqlitePhotoRepository(dbPath)
            repository.initialize()

            firstScanPhotos = [
                {
                    "id": "photo-1",
                    "relativePath": "keep/a.jpg",
                    "extension": ".jpg",
                    "size": 10,
                    "mtime": 1.0,
                    "sha256": None,
                    "partialSha256": None,
                    "width": 100,
                    "height": 100,
                    "cameraModel": "Canon",
                    "exifOrientation": None,
                    "isRaw": 0,
                    "isJpeg": 1,
                    "thumbnailPath": None,
                    "createdAt": 1.0,
                },
                {
                    "id": "photo-2",
                    "relativePath": "ignored/b.jpg",
                    "extension": ".jpg",
                    "size": 20,
                    "mtime": 1.0,
                    "sha256": None,
                    "partialSha256": None,
                    "width": 100,
                    "height": 100,
                    "cameraModel": "Canon",
                    "exifOrientation": None,
                    "isRaw": 0,
                    "isJpeg": 1,
                    "thumbnailPath": None,
                    "createdAt": 1.0,
                },
            ]
            secondScanPhotos = [
                {
                    "id": "photo-1-new",
                    "relativePath": "keep/a.jpg",
                    "extension": ".jpg",
                    "size": 11,
                    "mtime": 2.0,
                    "sha256": None,
                    "partialSha256": None,
                    "width": 120,
                    "height": 120,
                    "cameraModel": "Canon",
                    "exifOrientation": 1,
                    "isRaw": 0,
                    "isJpeg": 1,
                    "thumbnailPath": None,
                    "createdAt": 2.0,
                },
            ]

            scanner = _FakeScanner([firstScanPhotos, secondScanPhotos])
            service = ScanService(scanner, repository)

            service.scan(
                "/tmp/archive",
                {".jpg"},
                {".cr2"},
                [],
            )
            self.assertEqual(repository.getTotalPhotosCount(), 2)

            service.scan(
                "/tmp/archive",
                {".jpg"},
                {".cr2"},
                ["ignored"],
            )
            self.assertEqual(repository.getTotalPhotosCount(), 1)

            photoPaths = repository.getPhotoPathsByIds(["photo-1", "photo-2", "photo-1-new"])
            self.assertEqual(photoPaths, {"photo-1": "keep/a.jpg"})
