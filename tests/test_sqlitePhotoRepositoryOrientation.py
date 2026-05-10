import sqlite3
import tempfile
import unittest
from pathlib import Path

from photo_cleaner.infrastructure.sqlitePhotoRepository import (
    SqlitePhotoRepository,
)


def insertPhoto(
    in_connection: sqlite3.Connection,
    in_row: dict,
) -> None:
    cursor = in_connection.cursor()
    cursor.execute(
        """
        INSERT OR REPLACE INTO photos (
            id, relativePath, extension, size, mtime, sha256, partialSha256,
            width, height, cameraModel, exifOrientation, isRaw, isJpeg,
            thumbnailPath, createdAt
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            in_row["id"],
            in_row["relativePath"],
            in_row["extension"],
            in_row["size"],
            in_row["mtime"],
            in_row["sha256"],
            in_row["partialSha256"],
            in_row["width"],
            in_row["height"],
            in_row["cameraModel"],
            in_row["exifOrientation"],
            in_row["isRaw"],
            in_row["isJpeg"],
            in_row["thumbnailPath"],
            in_row["createdAt"],
        ),
    )
    in_connection.commit()


class SqlitePhotoRepositoryOrientationTests(unittest.TestCase):
    def test_getOrientationCandidatesForFaceDetection_onlyNullExif(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tempDir:
            dbPath = str(Path(tempDir) / "t.db")
            repository = SqlitePhotoRepository(dbPath)
            repository.initialize()

            connection = sqlite3.connect(dbPath)
            try:
                nowValue = 1.0
                baseRow = {
                    "id": "p1",
                    "relativePath": "a.jpg",
                    "extension": ".jpg",
                    "size": 10,
                    "mtime": nowValue,
                    "sha256": None,
                    "partialSha256": None,
                    "width": 1,
                    "height": 1,
                    "cameraModel": "X",
                    "isRaw": 0,
                    "isJpeg": 1,
                    "thumbnailPath": None,
                    "createdAt": nowValue,
                }

                rowNull = dict(baseRow)
                rowNull["id"] = "p-null"
                rowNull["relativePath"] = "null.jpg"
                rowNull["exifOrientation"] = None
                insertPhoto(connection, rowNull)

                rowExif1 = dict(baseRow)
                rowExif1["id"] = "p-1"
                rowExif1["relativePath"] = "exif1.jpg"
                rowExif1["exifOrientation"] = 1
                insertPhoto(connection, rowExif1)
            finally:
                connection.close()

            candidates = repository.getOrientationCandidatesForFaceDetection(
                [".jpg"],
                [],
            )

            ids = {item["id"] for item in candidates}
            self.assertIn("p-null", ids)
            self.assertNotIn("p-1", ids)

    def test_getTrustedUprightPhotosForOrientationDataset_filtersCanon(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tempDir:
            dbPath = str(Path(tempDir) / "t.db")
            repository = SqlitePhotoRepository(dbPath)
            repository.initialize()

            connection = sqlite3.connect(dbPath)
            try:
                nowValue = 1.0
                baseRow = {
                    "extension": ".jpg",
                    "size": 10,
                    "mtime": nowValue,
                    "sha256": None,
                    "partialSha256": None,
                    "width": 1,
                    "height": 1,
                    "isRaw": 0,
                    "isJpeg": 1,
                    "thumbnailPath": None,
                    "createdAt": nowValue,
                }

                canonRow = dict(baseRow)
                canonRow["id"] = "c1"
                canonRow["relativePath"] = "c.jpg"
                canonRow["cameraModel"] = "Canon EOS 5D Mark II"
                canonRow["exifOrientation"] = 1
                insertPhoto(connection, canonRow)

                otherRow = dict(baseRow)
                otherRow["id"] = "o1"
                otherRow["relativePath"] = "o.jpg"
                otherRow["cameraModel"] = "OTHER"
                otherRow["exifOrientation"] = 1
                insertPhoto(connection, otherRow)
            finally:
                connection.close()

            photosList = repository.getTrustedUprightPhotosForOrientationDataset(
                [".jpg"],
                [],
                "Canon EOS 5D Mark II",
            )

            ids = {item["id"] for item in photosList}
            self.assertEqual(ids, {"c1"})

    def test_getOrientationCandidatesForFaceDetection_excludesCameraModels(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tempDir:
            dbPath = str(Path(tempDir) / "t.db")
            repository = SqlitePhotoRepository(dbPath)
            repository.initialize()

            connection = sqlite3.connect(dbPath)
            try:
                nowValue = 1.0
                baseRow = {
                    "extension": ".jpg",
                    "size": 10,
                    "mtime": nowValue,
                    "sha256": None,
                    "partialSha256": None,
                    "width": 1,
                    "height": 1,
                    "isRaw": 0,
                    "isJpeg": 1,
                    "thumbnailPath": None,
                    "createdAt": nowValue,
                    "exifOrientation": None,
                }

                excludedRow = dict(baseRow)
                excludedRow["id"] = "excluded"
                excludedRow["relativePath"] = "excluded.jpg"
                excludedRow["cameraModel"] = "Canon EOS 450D"
                insertPhoto(connection, excludedRow)

                includedRow = dict(baseRow)
                includedRow["id"] = "included"
                includedRow["relativePath"] = "included.jpg"
                includedRow["cameraModel"] = "NIKON D800"
                insertPhoto(connection, includedRow)
            finally:
                connection.close()

            candidates = repository.getOrientationCandidatesForFaceDetection(
                [".jpg"],
                [],
                ["Canon EOS 450D"],
            )

            ids = {item["id"] for item in candidates}
            self.assertEqual(ids, {"included"})
