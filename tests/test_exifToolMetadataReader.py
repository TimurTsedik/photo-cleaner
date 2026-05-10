from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from photo_cleaner.infrastructure.exifToolMetadataReader import ExifToolMetadataReader


class ExifToolMetadataReaderTests(TestCase):
    def test_readMetadata_returnsParsedValues_whenExiftoolResponds(self) -> None:
        reader = ExifToolMetadataReader()

        availabilityProcess = SimpleNamespace(
            returncode=0,
            stdout="12.80\n",
            stderr="",
        )
        metadataProcess = SimpleNamespace(
            returncode=0,
            stdout='[{"Model":"Canon EOS 5D Mark II","ImageWidth":5616,"ImageHeight":3744,"Orientation":1}]',
            stderr="",
        )

        with patch(
            "photo_cleaner.infrastructure.exifToolMetadataReader.subprocess.run",
            side_effect=[availabilityProcess, metadataProcess],
        ):
            ret = reader.readMetadata(Path("fake.cr2"))

        self.assertEqual(ret["cameraModel"], "Canon EOS 5D Mark II")
        self.assertEqual(ret["width"], 5616)
        self.assertEqual(ret["height"], 3744)
        self.assertEqual(ret["exifOrientation"], 1)

    def test_readMetadata_returnsDefaults_whenExiftoolUnavailable(self) -> None:
        reader = ExifToolMetadataReader()

        unavailableProcess = SimpleNamespace(
            returncode=1,
            stdout="",
            stderr="not found",
        )

        with patch(
            "photo_cleaner.infrastructure.exifToolMetadataReader.subprocess.run",
            return_value=unavailableProcess,
        ) as mockedRun:
            ret = reader.readMetadata(Path("fake.cr2"))

        self.assertIsNone(ret["cameraModel"])
        self.assertIsNone(ret["width"])
        self.assertIsNone(ret["height"])
        self.assertIsNone(ret["exifOrientation"])
        self.assertEqual(mockedRun.call_count, 1)
