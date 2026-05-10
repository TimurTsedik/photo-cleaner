from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from photo_cleaner.infrastructure.fileSystemScanner import (
    FileSystemScanner,
    pathMatchesExcludedPrefix,
)
from photo_cleaner.infrastructure.metadataReader import MetadataReader


_VALID_MINIMAL_JPEG_BYTES = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01"
    b"\x00\x01\x00\x00\xff\xdb\x00C\x00\xff\xd9"
)


class FileSystemScannerExclusionTests(TestCase):
    def test_pathMatchesExcludedPrefix_absoluteSubtree(
        self,
    ) -> None:
        with TemporaryDirectory() as tmpDir:
            rootPath = Path(tmpDir)
            astroDir = rootPath / "astro"
            astroDir.mkdir()
            innerPath = astroDir / "x.jpg"
            innerPath.write_bytes(_VALID_MINIMAL_JPEG_BYTES)

            excludedPrefix = str(astroDir.resolve()) + "/"

            self.assertTrue(
                pathMatchesExcludedPrefix(
                    innerPath,
                    rootPath,
                    [excludedPrefix],
                ),
            )

            topPath = rootPath / "keep.jpg"
            topPath.write_bytes(_VALID_MINIMAL_JPEG_BYTES)

            self.assertFalse(
                pathMatchesExcludedPrefix(
                    topPath,
                    rootPath,
                    [excludedPrefix],
                ),
            )

    def test_pathMatchesExcludedPrefix_relativeToArchive(
        self,
    ) -> None:
        with TemporaryDirectory() as tmpDir:
            rootPath = Path(tmpDir)
            skipDir = rootPath / "skip" / "nested"
            skipDir.mkdir(parents=True)
            innerPath = skipDir / "a.jpg"
            innerPath.write_bytes(_VALID_MINIMAL_JPEG_BYTES)

            self.assertTrue(
                pathMatchesExcludedPrefix(
                    innerPath,
                    rootPath,
                    ["skip"],
                ),
            )

    def test_scan_skipsExcludedDirectories(
        self,
    ) -> None:
        scanner = FileSystemScanner(
            in_metadataReader=MetadataReader(),
            in_rawMetadataReader=None,
        )

        with TemporaryDirectory() as tmpDir:
            rootPath = Path(tmpDir)
            (rootPath / "visible.jpg").write_bytes(_VALID_MINIMAL_JPEG_BYTES)
            blockedDir = rootPath / "blocked"
            blockedDir.mkdir()
            (blockedDir / "hidden.jpg").write_bytes(_VALID_MINIMAL_JPEG_BYTES)

            photos = scanner.scan(
                in_rootPath=str(rootPath),
                in_jpegExtensions={".jpg"},
                in_rawExtensions=set(),
                in_excludedPathPrefixes=["blocked"],
            )

            relativePaths = {item["relativePath"].replace("\\", "/") for item in photos}

            self.assertIn("visible.jpg", relativePaths)
            self.assertNotIn("blocked/hidden.jpg", relativePaths)
