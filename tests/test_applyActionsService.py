import sqlite3
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from photo_cleaner.infrastructure.sqlitePhotoRepository import (
    SqlitePhotoRepository,
)
from photo_cleaner.services.applyActionsService import ApplyActionsService


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


class ApplyActionsServiceTests(unittest.TestCase):
    def test_apply_movesConfirmedDuplicateToTrash(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tempDir:
            archiveRoot = Path(tempDir) / "archive"
            archiveRoot.mkdir(parents=True, exist_ok=True)
            keepPath = archiveRoot / "keep.jpg"
            movePath = archiveRoot / "move.jpg"
            keepPath.write_bytes(b"keep")
            movePath.write_bytes(b"move")

            dbPath = Path(tempDir) / "cleanup.db"
            repository = SqlitePhotoRepository(str(dbPath))
            repository.initialize()
            connection = sqlite3.connect(str(dbPath))
            try:
                rowBase = {
                    "extension": ".jpg",
                    "size": 10,
                    "mtime": 1.0,
                    "sha256": None,
                    "partialSha256": None,
                    "width": 1,
                    "height": 1,
                    "cameraModel": "Canon EOS 5D Mark II",
                    "exifOrientation": None,
                    "isRaw": 0,
                    "isJpeg": 1,
                    "thumbnailPath": None,
                    "createdAt": 1.0,
                }
                keepRow = dict(rowBase)
                keepRow["id"] = "keep-id"
                keepRow["relativePath"] = "keep.jpg"
                insertPhoto(connection, keepRow)

                moveRow = dict(rowBase)
                moveRow["id"] = "move-id"
                moveRow["relativePath"] = "move.jpg"
                insertPhoto(connection, moveRow)
            finally:
                connection.close()

            repository.upsertDuplicateAction(
                "exact:test",
                {
                    "groupKey": "exact:test",
                    "status": "confirmed",
                    "selectedKeepPhotoId": "keep-id",
                    "photoIds": ["keep-id", "move-id"],
                },
            )

            service = ApplyActionsService(repository)
            applyResult = service.apply(
                str(archiveRoot),
                tempDir,
                ".trash/duplicates",
                False,
            )

            self.assertTrue(keepPath.exists())
            self.assertFalse(movePath.exists())
            self.assertTrue(
                (archiveRoot / ".trash" / "duplicates" / "move.jpg").exists()
            )
            self.assertEqual(applyResult["duplicateApplied"], 1)
            self.assertEqual(len(applyResult["errors"]), 0)
            self.assertEqual(repository.getTotalPhotosCount(), 1)
            duplicateActions = repository.getDuplicateActions()
            self.assertEqual(
                duplicateActions["exact:test"]["status"],
                "applied",
            )

    def test_apply_rotatesConfirmedOrientationPhoto(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tempDir:
            archiveRoot = Path(tempDir) / "archive"
            archiveRoot.mkdir(parents=True, exist_ok=True)
            imagePath = archiveRoot / "rot.jpg"
            image = Image.new("RGB", (2, 3), color=(255, 0, 0))
            image.save(imagePath, "JPEG")
            initialBytes = imagePath.read_bytes()

            dbPath = Path(tempDir) / "cleanup.db"
            repository = SqlitePhotoRepository(str(dbPath))
            repository.initialize()
            connection = sqlite3.connect(str(dbPath))
            try:
                insertPhoto(
                    connection,
                    {
                        "id": "rot-id",
                        "relativePath": "rot.jpg",
                        "extension": ".jpg",
                        "size": 10,
                        "mtime": 1.0,
                        "sha256": None,
                        "partialSha256": None,
                        "width": 2,
                        "height": 3,
                        "cameraModel": "Canon EOS 5D Mark II",
                        "exifOrientation": None,
                        "isRaw": 0,
                        "isJpeg": 1,
                        "thumbnailPath": None,
                        "createdAt": 1.0,
                    },
                )
            finally:
                connection.close()

            repository.upsertOrientationAction(
                "rot-id",
                {
                    "photoId": "rot-id",
                    "relativePath": "rot.jpg",
                    "status": "confirmed",
                    "selectedRotation": 90,
                },
            )

            thumbsPath = Path(tempDir) / "thumbs"
            thumbsPath.mkdir(parents=True, exist_ok=True)
            staleThumbPath = thumbsPath / "rot-id.jpg"
            staleThumbPath.write_bytes(b"stale")

            service = ApplyActionsService(repository)
            applyResult = service.apply(
                str(archiveRoot),
                tempDir,
                ".trash/duplicates",
                False,
            )

            with Image.open(imagePath) as rotatedImage:
                self.assertEqual(rotatedImage.size, (3, 2))
            self.assertFalse(staleThumbPath.exists())
            reorientedOriginalPath = (
                archiveRoot / ".photo-cleaner-trash" / "reoriented" / "rot.jpg"
            )
            self.assertTrue(reorientedOriginalPath.exists())
            self.assertEqual(reorientedOriginalPath.read_bytes(), initialBytes)
            self.assertEqual(applyResult["orientationApplied"], 1)
            self.assertEqual(len(applyResult["errors"]), 0)
            orientationActions = repository.getOrientationActions()
            self.assertEqual(
                orientationActions["rot-id"]["status"],
                "applied",
            )

    def test_apply_dryRun_doesNotModifyFiles(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tempDir:
            archiveRoot = Path(tempDir) / "archive"
            archiveRoot.mkdir(parents=True, exist_ok=True)
            imagePath = archiveRoot / "dry.jpg"
            image = Image.new("RGB", (2, 3), color=(255, 0, 0))
            image.save(imagePath, "JPEG")
            initialBytes = imagePath.read_bytes()

            dbPath = Path(tempDir) / "cleanup.db"
            repository = SqlitePhotoRepository(str(dbPath))
            repository.initialize()
            connection = sqlite3.connect(str(dbPath))
            try:
                insertPhoto(
                    connection,
                    {
                        "id": "dry-id",
                        "relativePath": "dry.jpg",
                        "extension": ".jpg",
                        "size": 10,
                        "mtime": 1.0,
                        "sha256": None,
                        "partialSha256": None,
                        "width": 2,
                        "height": 3,
                        "cameraModel": "Canon EOS 5D Mark II",
                        "exifOrientation": None,
                        "isRaw": 0,
                        "isJpeg": 1,
                        "thumbnailPath": None,
                        "createdAt": 1.0,
                    },
                )
            finally:
                connection.close()

            repository.upsertOrientationAction(
                "dry-id",
                {
                    "photoId": "dry-id",
                    "relativePath": "dry.jpg",
                    "status": "confirmed",
                    "selectedRotation": 270,
                },
            )

            service = ApplyActionsService(repository)
            applyResult = service.apply(
                str(archiveRoot),
                tempDir,
                ".trash/duplicates",
                True,
            )

            self.assertEqual(initialBytes, imagePath.read_bytes())
            self.assertFalse(
                (archiveRoot / ".photo-cleaner-trash" / "reoriented" / "dry.jpg").exists()
            )
            self.assertEqual(applyResult["orientationApplied"], 1)
            orientationActions = repository.getOrientationActions()
            self.assertEqual(
                orientationActions["dry-id"]["status"],
                "confirmed",
            )

    def test_undoLastApply_restoresMovedAndRotatedFiles(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tempDir:
            archiveRoot = Path(tempDir) / "archive"
            archiveRoot.mkdir(parents=True, exist_ok=True)

            keepPath = archiveRoot / "keep.jpg"
            movePath = archiveRoot / "move.jpg"
            rotPath = archiveRoot / "rot.jpg"
            keepPath.write_bytes(b"keep")
            movePath.write_bytes(b"move")
            image = Image.new("RGB", (2, 3), color=(255, 0, 0))
            image.save(rotPath, "JPEG")
            initialRotBytes = rotPath.read_bytes()

            dbPath = Path(tempDir) / "cleanup.db"
            repository = SqlitePhotoRepository(str(dbPath))
            repository.initialize()
            connection = sqlite3.connect(str(dbPath))
            try:
                rowBase = {
                    "extension": ".jpg",
                    "size": 10,
                    "mtime": 1.0,
                    "sha256": None,
                    "partialSha256": None,
                    "width": 2,
                    "height": 3,
                    "cameraModel": "Canon EOS 5D Mark II",
                    "exifOrientation": None,
                    "isRaw": 0,
                    "isJpeg": 1,
                    "thumbnailPath": None,
                    "createdAt": 1.0,
                }
                keepRow = dict(rowBase)
                keepRow["id"] = "keep-id"
                keepRow["relativePath"] = "keep.jpg"
                insertPhoto(connection, keepRow)

                moveRow = dict(rowBase)
                moveRow["id"] = "move-id"
                moveRow["relativePath"] = "move.jpg"
                insertPhoto(connection, moveRow)

                rotRow = dict(rowBase)
                rotRow["id"] = "rot-id"
                rotRow["relativePath"] = "rot.jpg"
                insertPhoto(connection, rotRow)
            finally:
                connection.close()

            repository.upsertDuplicateAction(
                "exact:test",
                {
                    "groupKey": "exact:test",
                    "status": "confirmed",
                    "selectedKeepPhotoId": "keep-id",
                    "photoIds": ["keep-id", "move-id"],
                },
            )
            repository.upsertOrientationAction(
                "rot-id",
                {
                    "photoId": "rot-id",
                    "relativePath": "rot.jpg",
                    "status": "confirmed",
                    "selectedRotation": 90,
                },
            )

            service = ApplyActionsService(repository)
            _ = service.apply(
                str(archiveRoot),
                tempDir,
                ".trash/duplicates",
                False,
            )

            self.assertFalse(movePath.exists())
            self.assertTrue(
                (archiveRoot / ".trash" / "duplicates" / "move.jpg").exists()
            )
            with Image.open(rotPath) as rotatedImage:
                self.assertEqual(rotatedImage.size, (3, 2))
            thumbsPath = Path(tempDir) / "thumbs"
            thumbsPath.mkdir(parents=True, exist_ok=True)
            staleThumbPath = thumbsPath / "rot-id.jpg"
            staleThumbPath.write_bytes(b"stale-after-apply")

            undoResult = service.undoLastApply(
                str(archiveRoot),
                tempDir,
                False,
            )

            self.assertTrue(movePath.exists())
            self.assertFalse(
                (archiveRoot / ".trash" / "duplicates" / "move.jpg").exists()
            )
            self.assertEqual(initialRotBytes, rotPath.read_bytes())
            self.assertFalse(staleThumbPath.exists())
            self.assertEqual(undoResult["applied"], 2)
            self.assertEqual(len(undoResult["errors"]), 0)
            duplicateActions = repository.getDuplicateActions()
            orientationActions = repository.getOrientationActions()
            self.assertEqual(
                duplicateActions["exact:test"]["status"],
                "confirmed",
            )
            self.assertEqual(
                orientationActions["rot-id"]["status"],
                "confirmed",
            )

    def test_apply_pendingDuplicatesWithConsent_usesRecommendedKeep(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tempDir:
            archiveRoot = Path(tempDir) / "archive"
            archiveRoot.mkdir(parents=True, exist_ok=True)
            keepPath = archiveRoot / "keep.jpg"
            movePath = archiveRoot / "move.jpg"
            keepPath.write_bytes(b"keep")
            movePath.write_bytes(b"move")

            dbPath = Path(tempDir) / "cleanup.db"
            repository = SqlitePhotoRepository(str(dbPath))
            repository.initialize()
            connection = sqlite3.connect(str(dbPath))
            try:
                rowBase = {
                    "extension": ".jpg",
                    "size": 10,
                    "mtime": 1.0,
                    "sha256": None,
                    "partialSha256": None,
                    "width": 1,
                    "height": 1,
                    "cameraModel": "Canon EOS 5D Mark II",
                    "exifOrientation": None,
                    "isRaw": 0,
                    "isJpeg": 1,
                    "thumbnailPath": None,
                    "createdAt": 1.0,
                }
                keepRow = dict(rowBase)
                keepRow["id"] = "keep-id"
                keepRow["relativePath"] = "keep.jpg"
                insertPhoto(connection, keepRow)

                moveRow = dict(rowBase)
                moveRow["id"] = "move-id"
                moveRow["relativePath"] = "move.jpg"
                insertPhoto(connection, moveRow)
            finally:
                connection.close()

            repository.upsertDuplicateAction(
                "exact:test",
                {
                    "groupKey": "exact:test",
                    "status": "pending",
                    "selectedKeepPhotoId": "",
                    "recommendedKeepPhotoId": "keep-id",
                    "photoIds": ["keep-id", "move-id"],
                },
            )

            service = ApplyActionsService(repository)
            applyResult = service.apply(
                str(archiveRoot),
                tempDir,
                ".trash/duplicates",
                False,
                True,
                False,
            )

            self.assertTrue(keepPath.exists())
            self.assertFalse(movePath.exists())
            self.assertEqual(applyResult["duplicateApplied"], 1)
            self.assertEqual(len(applyResult["errors"]), 0)

    def test_apply_pendingOrientationWithConsent_usesSuggestedRotation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tempDir:
            archiveRoot = Path(tempDir) / "archive"
            archiveRoot.mkdir(parents=True, exist_ok=True)
            imagePath = archiveRoot / "rot.jpg"
            image = Image.new("RGB", (2, 3), color=(255, 0, 0))
            image.save(imagePath, "JPEG")

            dbPath = Path(tempDir) / "cleanup.db"
            repository = SqlitePhotoRepository(str(dbPath))
            repository.initialize()
            connection = sqlite3.connect(str(dbPath))
            try:
                insertPhoto(
                    connection,
                    {
                        "id": "rot-id",
                        "relativePath": "rot.jpg",
                        "extension": ".jpg",
                        "size": 10,
                        "mtime": 1.0,
                        "sha256": None,
                        "partialSha256": None,
                        "width": 2,
                        "height": 3,
                        "cameraModel": "Canon EOS 5D Mark II",
                        "exifOrientation": None,
                        "isRaw": 0,
                        "isJpeg": 1,
                        "thumbnailPath": None,
                        "createdAt": 1.0,
                    },
                )
            finally:
                connection.close()

            repository.upsertOrientationAction(
                "rot-id",
                {
                    "photoId": "rot-id",
                    "relativePath": "rot.jpg",
                    "status": "pending",
                    "selectedRotation": None,
                    "suggestedRotation": 90,
                },
            )

            service = ApplyActionsService(repository)
            applyResult = service.apply(
                str(archiveRoot),
                tempDir,
                ".trash/duplicates",
                False,
                False,
                True,
            )

            with Image.open(imagePath) as rotatedImage:
                self.assertEqual(rotatedImage.size, (3, 2))
            self.assertEqual(applyResult["orientationApplied"], 1)
            self.assertEqual(len(applyResult["errors"]), 0)
