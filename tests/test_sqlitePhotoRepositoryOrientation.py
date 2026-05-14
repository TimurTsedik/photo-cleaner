import sqlite3
import tempfile
import unittest
import time
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
    def test_insertPhoto_sameRelativePath_updatesRowWithoutDuplicate(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tempDir:
            dbPath = str(Path(tempDir) / "t.db")
            repository = SqlitePhotoRepository(dbPath)
            repository.initialize()

            firstPhoto = {
                "id": "photo-first-id",
                "relativePath": "folder/a.jpg",
                "extension": ".jpg",
                "size": 10,
                "mtime": 1.0,
                "sha256": "sha-first",
                "partialSha256": None,
                "width": 100,
                "height": 80,
                "cameraModel": "Canon EOS 450D",
                "exifOrientation": None,
                "isRaw": 0,
                "isJpeg": 1,
                "thumbnailPath": None,
                "createdAt": 1.0,
            }
            secondPhoto = dict(firstPhoto)
            secondPhoto["id"] = "photo-second-id"
            secondPhoto["size"] = 999
            secondPhoto["mtime"] = 2.0
            secondPhoto["sha256"] = "sha-second"
            secondPhoto["width"] = 200
            secondPhoto["height"] = 160
            secondPhoto["createdAt"] = 2.0

            repository.insertPhoto(firstPhoto)
            repository.insertPhoto(secondPhoto)

            connection = sqlite3.connect(dbPath)
            connection.row_factory = sqlite3.Row
            try:
                cursor = connection.cursor()
                cursor.execute("SELECT COUNT(*) AS countValue FROM photos")
                countRow = cursor.fetchone()
                self.assertEqual(int(countRow["countValue"]), 1)

                cursor.execute(
                    "SELECT id, relativePath, size, mtime, sha256, width, height "
                    "FROM photos WHERE relativePath = ?",
                    ("folder/a.jpg",),
                )
                photoRow = cursor.fetchone()
                self.assertIsNotNone(photoRow)
                self.assertEqual(str(photoRow["id"]), "photo-first-id")
                self.assertEqual(int(photoRow["size"]), 999)
                self.assertEqual(float(photoRow["mtime"]), 2.0)
                self.assertEqual(str(photoRow["sha256"]), "sha-second")
                self.assertEqual(int(photoRow["width"]), 200)
                self.assertEqual(int(photoRow["height"]), 160)
            finally:
                connection.close()

    def test_getExtensionCounts_groupsAndNormalizes(
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
                    "size": 10,
                    "mtime": nowValue,
                    "sha256": None,
                    "partialSha256": None,
                    "width": 1,
                    "height": 1,
                    "cameraModel": "X",
                    "exifOrientation": None,
                    "isRaw": 0,
                    "isJpeg": 1,
                    "thumbnailPath": None,
                    "createdAt": nowValue,
                }

                row1 = dict(baseRow)
                row1["id"] = "p1"
                row1["relativePath"] = "a.JPG"
                row1["extension"] = ".JPG"
                insertPhoto(connection, row1)

                row2 = dict(baseRow)
                row2["id"] = "p2"
                row2["relativePath"] = "b.jpg"
                row2["extension"] = ".jpg"
                insertPhoto(connection, row2)

                row3 = dict(baseRow)
                row3["id"] = "p3"
                row3["relativePath"] = "c.CR2"
                row3["extension"] = ".CR2"
                insertPhoto(connection, row3)
            finally:
                connection.close()

            extensionCounts = repository.getExtensionCounts()
            self.assertEqual(
                extensionCounts,
                [
                    {"extension": ".jpg", "count": 2},
                    {"extension": ".cr2", "count": 1},
                ],
            )

    def test_getCameraModelCounts_groupsAndNormalizes(
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
                    "exifOrientation": None,
                    "isRaw": 0,
                    "isJpeg": 1,
                    "thumbnailPath": None,
                    "createdAt": nowValue,
                }

                row1 = dict(baseRow)
                row1["id"] = "p1"
                row1["relativePath"] = "a.jpg"
                row1["cameraModel"] = "Canon EOS 450D"
                insertPhoto(connection, row1)

                row2 = dict(baseRow)
                row2["id"] = "p2"
                row2["relativePath"] = "b.jpg"
                row2["cameraModel"] = " Canon EOS 450D\x00 "
                insertPhoto(connection, row2)

                row3 = dict(baseRow)
                row3["id"] = "p3"
                row3["relativePath"] = "c.jpg"
                row3["cameraModel"] = None
                insertPhoto(connection, row3)
            finally:
                connection.close()

            cameraCounts = repository.getCameraModelCounts()
            self.assertEqual(
                cameraCounts,
                [
                    {"cameraModel": "Canon EOS 450D", "count": 2},
                    {"cameraModel": "(unknown)", "count": 1},
                ],
            )

    def test_getTotalPhotosCount_returnsNumberOfRows(
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
                    "cameraModel": "X",
                    "exifOrientation": None,
                    "isRaw": 0,
                    "isJpeg": 1,
                    "thumbnailPath": None,
                    "createdAt": nowValue,
                }

                row1 = dict(baseRow)
                row1["id"] = "p1"
                row1["relativePath"] = "a.jpg"
                insertPhoto(connection, row1)

                row2 = dict(baseRow)
                row2["id"] = "p2"
                row2["relativePath"] = "b.jpg"
                insertPhoto(connection, row2)
            finally:
                connection.close()

            totalCount = repository.getTotalPhotosCount()
            self.assertEqual(totalCount, 2)

    def test_getOrientationCandidatesForFaceDetection_anyExifValue(
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

                rowExif6 = dict(baseRow)
                rowExif6["id"] = "p-6"
                rowExif6["relativePath"] = "exif6.jpg"
                rowExif6["exifOrientation"] = 6
                insertPhoto(connection, rowExif6)
            finally:
                connection.close()

            candidates = repository.getOrientationCandidatesForFaceDetection(
                [".jpg"],
                [],
            )

            ids = {item["id"] for item in candidates}
            self.assertIn("p-null", ids)
            self.assertIn("p-1", ids)
            self.assertIn("p-6", ids)

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

    def test_getConfirmedOrientationPhotosForOrientationDataset_returnsConfirmedRotations(
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
                    "cameraModel": "NIKON D800",
                    "exifOrientation": None,
                }

                rowConfirmed = dict(baseRow)
                rowConfirmed["id"] = "confirmed-90"
                rowConfirmed["relativePath"] = "confirmed.jpg"
                insertPhoto(connection, rowConfirmed)

                rowPending = dict(baseRow)
                rowPending["id"] = "pending-270"
                rowPending["relativePath"] = "pending.jpg"
                insertPhoto(connection, rowPending)

                rowNoRotation = dict(baseRow)
                rowNoRotation["id"] = "confirmed-none"
                rowNoRotation["relativePath"] = "none.jpg"
                insertPhoto(connection, rowNoRotation)
            finally:
                connection.close()

            repository.upsertOrientationAction(
                "confirmed-90",
                {
                    "photoId": "confirmed-90",
                    "selectedRotation": 90,
                    "status": "confirmed",
                    "updatedAt": time.time(),
                },
            )
            repository.upsertOrientationAction(
                "pending-270",
                {
                    "photoId": "pending-270",
                    "selectedRotation": 270,
                    "status": "pending",
                    "updatedAt": time.time(),
                },
            )
            repository.upsertOrientationAction(
                "confirmed-none",
                {
                    "photoId": "confirmed-none",
                    "selectedRotation": None,
                    "status": "confirmed",
                    "updatedAt": time.time(),
                },
            )

            photosList = repository.getConfirmedOrientationPhotosForOrientationDataset(
                [".jpg"],
                [],
            )

            self.assertEqual(len(photosList), 1)
            self.assertEqual(photosList[0]["id"], "confirmed-90")
            self.assertEqual(photosList[0]["baseRotation"], 90)

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

    def test_getOrientationCandidatesForFaceDetection_excludesDuplicateIds(
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
                    "cameraModel": "NIKON D800",
                }

                excludedRow = dict(baseRow)
                excludedRow["id"] = "excluded-dup"
                excludedRow["relativePath"] = "excluded.jpg"
                insertPhoto(connection, excludedRow)

                includedRow = dict(baseRow)
                includedRow["id"] = "included-ori"
                includedRow["relativePath"] = "included.jpg"
                insertPhoto(connection, includedRow)
            finally:
                connection.close()

            candidates = repository.getOrientationCandidatesForFaceDetection(
                [".jpg"],
                [],
                [],
                {"excluded-dup"},
            )

            ids = {item["id"] for item in candidates}
            self.assertEqual(ids, {"included-ori"})

    def test_getDuplicateCandidatePhotoIds_returnsOnlyExactDuplicates(
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
                    "partialSha256": None,
                    "width": 1,
                    "height": 1,
                    "isRaw": 0,
                    "isJpeg": 1,
                    "thumbnailPath": None,
                    "createdAt": nowValue,
                    "exifOrientation": None,
                    "cameraModel": "NIKON D800",
                }

                row1 = dict(baseRow)
                row1["id"] = "dup-1"
                row1["relativePath"] = "dup-1.jpg"
                row1["sha256"] = "hash-a"
                insertPhoto(connection, row1)

                row2 = dict(baseRow)
                row2["id"] = "dup-2"
                row2["relativePath"] = "dup-2.jpg"
                row2["sha256"] = "hash-a"
                insertPhoto(connection, row2)

                row3 = dict(baseRow)
                row3["id"] = "solo"
                row3["relativePath"] = "solo.jpg"
                row3["sha256"] = "hash-b"
                insertPhoto(connection, row3)
            finally:
                connection.close()

            duplicateIds = repository.getDuplicateCandidatePhotoIds()
            self.assertEqual(duplicateIds, {"dup-1", "dup-2"})

    def test_getSimilarDuplicateGroups_detectsCopyWithDifferentSize(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tempDir:
            dbPath = str(Path(tempDir) / "t.db")
            repository = SqlitePhotoRepository(dbPath)
            repository.initialize()

            connection = sqlite3.connect(dbPath)
            try:
                nowValue = 1000.0
                baseRow = {
                    "extension": ".jpg",
                    "mtime": nowValue,
                    "sha256": None,
                    "partialSha256": None,
                    "width": 2304,
                    "height": 1728,
                    "isRaw": 0,
                    "isJpeg": 1,
                    "thumbnailPath": None,
                    "createdAt": nowValue,
                    "exifOrientation": None,
                    "cameraModel": "PENTAX Optio S4i ",
                }

                row1 = dict(baseRow)
                row1["id"] = "sim-1"
                row1["relativePath"] = "a/IMGP0427.JPG"
                row1["size"] = 2868321
                insertPhoto(connection, row1)

                row2 = dict(baseRow)
                row2["id"] = "sim-2"
                row2["relativePath"] = "b/IMGP0427 (1).JPG"
                row2["size"] = 2570240
                insertPhoto(connection, row2)
            finally:
                connection.close()

            similarGroups = repository.getSimilarDuplicateGroups(set())
            self.assertEqual(len(similarGroups), 1)
            ids = {item["id"] for item in similarGroups[0]}
            self.assertEqual(ids, {"sim-1", "sim-2"})

    def test_getAllDuplicateCandidatePhotoIds_returnsOnlyExactDuplicates(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tempDir:
            dbPath = str(Path(tempDir) / "t.db")
            repository = SqlitePhotoRepository(dbPath)
            repository.initialize()

            connection = sqlite3.connect(dbPath)
            try:
                nowValue = 2000.0
                baseRow = {
                    "extension": ".jpg",
                    "mtime": nowValue,
                    "partialSha256": None,
                    "width": 2304,
                    "height": 1728,
                    "isRaw": 0,
                    "isJpeg": 1,
                    "thumbnailPath": None,
                    "createdAt": nowValue,
                    "exifOrientation": None,
                    "cameraModel": "PENTAX Optio S4i ",
                }

                exact1 = dict(baseRow)
                exact1["id"] = "exact-1"
                exact1["relativePath"] = "x/exact1.jpg"
                exact1["size"] = 100
                exact1["sha256"] = "same"
                insertPhoto(connection, exact1)

                exact2 = dict(baseRow)
                exact2["id"] = "exact-2"
                exact2["relativePath"] = "x/exact2.jpg"
                exact2["size"] = 100
                exact2["sha256"] = "same"
                insertPhoto(connection, exact2)

                sim1 = dict(baseRow)
                sim1["id"] = "sim-1"
                sim1["relativePath"] = "x/IMG_1000.JPG"
                sim1["size"] = 300
                sim1["sha256"] = None
                insertPhoto(connection, sim1)

                sim2 = dict(baseRow)
                sim2["id"] = "sim-2"
                sim2["relativePath"] = "x/IMG_1000 (1).JPG"
                sim2["size"] = 280
                sim2["sha256"] = None
                insertPhoto(connection, sim2)
            finally:
                connection.close()

            duplicateIds = repository.getAllDuplicateCandidatePhotoIds()
            self.assertEqual(
                duplicateIds,
                {"exact-1", "exact-2"},
            )

    def test_getSimilarDuplicateGroups_doesNotMergeSequentialFrameNames(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tempDir:
            dbPath = str(Path(tempDir) / "t.db")
            repository = SqlitePhotoRepository(dbPath)
            repository.initialize()

            connection = sqlite3.connect(dbPath)
            try:
                nowValue = 3000.0
                baseRow = {
                    "extension": ".jpg",
                    "mtime": nowValue,
                    "sha256": None,
                    "partialSha256": None,
                    "width": 2304,
                    "height": 1728,
                    "isRaw": 0,
                    "isJpeg": 1,
                    "thumbnailPath": None,
                    "createdAt": nowValue,
                    "exifOrientation": None,
                    "cameraModel": "Canon EOS 450D",
                }

                frame1 = dict(baseRow)
                frame1["id"] = "f1"
                frame1["relativePath"] = "x/IMG_1441.JPG"
                frame1["size"] = 3767447
                insertPhoto(connection, frame1)

                frame2 = dict(baseRow)
                frame2["id"] = "f2"
                frame2["relativePath"] = "x/IMG_1442.JPG"
                frame2["size"] = 3949680
                insertPhoto(connection, frame2)
            finally:
                connection.close()

            similarGroups = repository.getSimilarDuplicateGroups(set())
            self.assertEqual(similarGroups, [])

    def test_getArchivePhotosPage_returnsOrderedPageAndTotal(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tempDir:
            dbPath = str(Path(tempDir) / "t.db")
            repository = SqlitePhotoRepository(dbPath)
            repository.initialize()

            connection = sqlite3.connect(dbPath)
            try:
                nowValue = 5000.0
                baseRow = {
                    "extension": ".jpg",
                    "size": 10,
                    "mtime": nowValue,
                    "sha256": None,
                    "partialSha256": None,
                    "width": 100,
                    "height": 80,
                    "cameraModel": "Canon EOS 450D",
                    "exifOrientation": 1,
                    "isRaw": 0,
                    "isJpeg": 1,
                    "thumbnailPath": None,
                    "createdAt": nowValue,
                }

                for index in range(45):
                    row = dict(baseRow)
                    row["id"] = f"photo-{index:03d}"
                    row["relativePath"] = f"archive/img_{index:03d}.jpg"
                    row["size"] = 1000 + index
                    insertPhoto(connection, row)
            finally:
                connection.close()

            pageOne = repository.getArchivePhotosPage(1, 20)
            pageThree = repository.getArchivePhotosPage(3, 20)

            self.assertEqual(pageOne["total"], 45)
            self.assertEqual(pageOne["page"], 1)
            self.assertEqual(pageOne["pageSize"], 20)
            self.assertEqual(len(pageOne["items"]), 20)
            self.assertEqual(pageOne["items"][0]["relativePath"], "archive/img_000.jpg")
            self.assertEqual(pageOne["items"][-1]["relativePath"], "archive/img_019.jpg")

            self.assertEqual(pageThree["total"], 45)
            self.assertEqual(pageThree["page"], 3)
            self.assertEqual(pageThree["pageSize"], 20)
            self.assertEqual(len(pageThree["items"]), 5)
            self.assertEqual(pageThree["items"][0]["relativePath"], "archive/img_040.jpg")
            self.assertEqual(pageThree["items"][-1]["relativePath"], "archive/img_044.jpg")
