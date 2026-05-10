import tempfile
import unittest
from pathlib import Path

from PIL import Image

from photo_cleaner.ml.orientationDatasetBuilder import (
    buildOrientationDatasetFromArchive,
    splitSourceIdsByPartition,
)


class OrientationDatasetBuilderTests(unittest.TestCase):
    def test_splitSourceIdsByPartition_sameIdSinglePartition(
        self,
    ) -> None:
        idToPartition = splitSourceIdsByPartition(
            ["a", "b", "c", "d"],
            0,
            0.5,
            0.25,
        )

        self.assertEqual(idToPartition["c"], "train")
        self.assertEqual(idToPartition["a"], "train")
        self.assertEqual(idToPartition["b"], "val")
        self.assertEqual(idToPartition["d"], "test")

    def test_buildOrientationDatasetFromArchive_placesAllVariantsInSameSplit(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tempDir:
            archiveRoot = Path(tempDir) / "archive"
            archiveRoot.mkdir()

            imagePath = archiveRoot / "sample.jpg"
            rgbImage = Image.new("RGB", (64, 48), color=(10, 20, 30))
            rgbImage.save(imagePath, "JPEG")

            outputRoot = Path(tempDir) / "out"
            items = [
                {
                    "id": "img-1",
                    "relativePath": "sample.jpg",
                },
            ]

            buildResult = buildOrientationDatasetFromArchive(
                items,
                archiveRoot,
                outputRoot,
                1,
                1.0,
                0.0,
                32,
                90,
            )

            self.assertEqual(len(buildResult["errors"]), 0)

            train0 = outputRoot / "train" / "0" / "img-1.jpg"
            train90 = outputRoot / "train" / "90" / "img-1.jpg"
            train270 = outputRoot / "train" / "270" / "img-1.jpg"

            self.assertTrue(train0.is_file())
            self.assertTrue(train90.is_file())
            self.assertTrue(train270.is_file())

            self.assertEqual(
                buildResult["idToPartition"]["img-1"],
                "train",
            )
