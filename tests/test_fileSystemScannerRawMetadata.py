from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from photo_cleaner.infrastructure.fileSystemScanner import FileSystemScanner


class _FakeJpegMetadataReader:
    def __init__(self) -> None:
        self.calls = 0

    def readMetadata(
        self,
        in_path: Path,
    ) -> dict[str, object]:
        self.calls += 1
        ret = {
            "width": 100,
            "height": 100,
            "cameraModel": "jpeg",
            "exifOrientation": 1,
        }
        return ret


class _FakeRawMetadataReader:
    def __init__(self) -> None:
        self.calls = 0

    def readMetadata(
        self,
        in_path: Path,
    ) -> dict[str, object]:
        self.calls += 1
        ret = {
            "width": 200,
            "height": 150,
            "cameraModel": "Canon EOS 5D Mark II",
            "exifOrientation": 1,
        }
        return ret


class FileSystemScannerRawMetadataTests(TestCase):
    def test_scan_usesRawMetadataReader_forRawFiles(self) -> None:
        jpegReader = _FakeJpegMetadataReader()
        rawReader = _FakeRawMetadataReader()
        scanner = FileSystemScanner(
            in_metadataReader=jpegReader,
            in_rawMetadataReader=rawReader,
        )

        with TemporaryDirectory() as tmpDir:
            rootPath = Path(tmpDir)
            jpegPath = rootPath / "a.jpg"
            rawPath = rootPath / "b.cr2"
            jpegPath.write_bytes(b"jpeg")
            rawPath.write_bytes(b"raw")

            photos = scanner.scan(
                in_rootPath=str(rootPath),
                in_jpegExtensions={".jpg"},
                in_rawExtensions={".cr2"},
                in_excludedPathPrefixes=[],
            )

        photosByExtension = {
            item["extension"]: item
            for item in photos
        }

        self.assertEqual(jpegReader.calls, 1)
        self.assertEqual(rawReader.calls, 1)
        self.assertEqual(
            photosByExtension[".cr2"]["cameraModel"],
            "Canon EOS 5D Mark II",
        )
