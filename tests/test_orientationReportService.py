import sqlite3
import tempfile
import unittest
import json
from pathlib import Path

from PIL import Image

from photo_cleaner.infrastructure.sqlitePhotoRepository import (
    SqlitePhotoRepository,
)
from photo_cleaner.services.orientationReportService import OrientationReportService


class FakePredictor:
    def predictOrientation(
        self,
        in_imagePath: Path,
    ) -> dict:
        ret = {
            "suggestedRotation": 90,
            "suggestedAction": "rotate90",
            "confidence": 0.99,
            "margin": 0.9,
            "decisionReason": "ml_high_confidence",
            "probabilities": {0: 0.01, 90: 0.98, 270: 0.01},
            "scores": {0: 0.01, 90: 0.98, 270: 0.01},
            "predictionLabel": 90,
            "rawDetection": None,
        }
        return ret


class OrientationReportServiceTests(unittest.TestCase):
    def test_buildReport_writesMlHtml(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tempDir:
            workspacePath = Path(tempDir) / "ws"
            workspacePath.mkdir()

            archiveRoot = Path(tempDir) / "arch"
            archiveRoot.mkdir()

            imagePath = archiveRoot / "sample.jpg"
            rgbImage = Image.new("RGB", (64, 48), color=(10, 20, 30))
            rgbImage.save(imagePath, "JPEG")

            dbPath = workspacePath / "cleanup.db"
            repository = SqlitePhotoRepository(str(dbPath))
            repository.initialize()

            sqliteConn = sqlite3.connect(str(dbPath))
            try:
                cursor = sqliteConn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO photos (
                        id, relativePath, extension, size, mtime,
                        sha256, partialSha256, width, height,
                        cameraModel, exifOrientation, isRaw, isJpeg,
                        thumbnailPath, createdAt
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "id-test",
                        "sample.jpg",
                        ".jpg",
                        100,
                        1.0,
                        None,
                        None,
                        1,
                        1,
                        "Canon EOS 5D Mark II",
                        None,
                        0,
                        1,
                        None,
                        1.0,
                    ),
                )
                sqliteConn.commit()
            finally:
                sqliteConn.close()

            service = OrientationReportService(
                repository,
                FakePredictor(),
            )

            service.buildReport(
                str(archiveRoot),
                str(workspacePath),
                [".jpg"],
                [],
                [],
                True,
                "orientation_ml.html",
                "ML orientation report",
                "orientation_ml",
            )

            reportPath = workspacePath / "reports" / "orientation_ml.html"
            self.assertTrue(reportPath.is_file())
            reportText = reportPath.read_text(encoding="utf-8")
            self.assertIn("rotate90", reportText)
            self.assertIn("Candidate #1", reportText)

            actionsPath = workspacePath / "actions.json"
            self.assertTrue(actionsPath.is_file())
            actionsPayload = json.loads(
                actionsPath.read_text(encoding="utf-8"),
            )
            self.assertIn("id-test", actionsPayload["orientation"]["items"])
