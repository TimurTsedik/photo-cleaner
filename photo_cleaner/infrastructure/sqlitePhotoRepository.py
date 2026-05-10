import sqlite3
import re
from pathlib import Path
from typing import Any


class SqlitePhotoRepository:
    def __init__(
        self,
        in_dbPath: str,
    ) -> None:
        self._dbPath = in_dbPath

    def initialize(self) -> None:
        connection = sqlite3.connect(self._dbPath)

        try:
            cursor = connection.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS photos (
                    id TEXT PRIMARY KEY,

                    relativePath TEXT NOT NULL UNIQUE,
                    extension TEXT NOT NULL,

                    size INTEGER NOT NULL,
                    mtime REAL NOT NULL,

                    sha256 TEXT,
                    partialSha256 TEXT,

                    width INTEGER,
                    height INTEGER,

                    cameraModel TEXT,
                    exifOrientation INTEGER,

                    isRaw INTEGER NOT NULL,
                    isJpeg INTEGER NOT NULL,

                    thumbnailPath TEXT,

                    createdAt REAL NOT NULL
                )
            """)

            connection.commit()

        finally:
            connection.close()

    def insertPhoto(
        self,
        in_photo: dict[str, Any],
    ) -> None:
        connection = sqlite3.connect(self._dbPath)

        try:
            cursor = connection.cursor()

            cursor.execute("""
                INSERT OR REPLACE INTO photos (
                    id,
                    relativePath,
                    extension,
                    size,
                    mtime,
                    sha256,
                    partialSha256,
                    width,
                    height,
                    cameraModel,
                    exifOrientation,
                    isRaw,
                    isJpeg,
                    thumbnailPath,
                    createdAt
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                in_photo["id"],
                in_photo["relativePath"],
                in_photo["extension"],
                in_photo["size"],
                in_photo["mtime"],
                in_photo["sha256"],
                in_photo["partialSha256"],
                in_photo["width"],
                in_photo["height"],
                in_photo["cameraModel"],
                in_photo["exifOrientation"],
                in_photo["isRaw"],
                in_photo["isJpeg"],
                in_photo["thumbnailPath"],
                in_photo["createdAt"],
            ))

            connection.commit()

        finally:
            connection.close()

    def getDuplicateSizeGroups(self) -> list[list[dict[str, Any]]]:
        ret: list[list[dict[str, Any]]] = []

        connection = sqlite3.connect(self._dbPath)
        connection.row_factory = sqlite3.Row

        try:
            cursor = connection.cursor()

            cursor.execute("""
                SELECT size
                FROM photos
                GROUP BY size
                HAVING COUNT(*) > 1
                ORDER BY size DESC
            """)

            sizes = [
                row["size"]
                for row in cursor.fetchall()
            ]

            for size in sizes:
                cursor.execute("""
                    SELECT id, relativePath, size, sha256
                    FROM photos
                    WHERE size = ?
                    ORDER BY relativePath
                """, (size,))

                ret.append([
                    dict(row)
                    for row in cursor.fetchall()
                ])

        finally:
            connection.close()

        return ret

    def updatePhotoSha256(
        self,
        in_photoId: str,
        in_sha256: str,
    ) -> None:
        connection = sqlite3.connect(self._dbPath)

        try:
            cursor = connection.cursor()

            cursor.execute("""
                UPDATE photos
                SET sha256 = ?
                WHERE id = ?
            """, (
                in_sha256,
                in_photoId,
            ))

            connection.commit()

        finally:
            connection.close()

    def getSha256DuplicateGroups(self) -> list[list[dict[str, Any]]]:
        ret: list[list[dict[str, Any]]] = []

        connection = sqlite3.connect(self._dbPath)
        connection.row_factory = sqlite3.Row

        try:
            cursor = connection.cursor()

            cursor.execute("""
                SELECT sha256
                FROM photos
                WHERE sha256 IS NOT NULL
                GROUP BY sha256
                HAVING COUNT(*) > 1
                ORDER BY COUNT(*) DESC
            """)

            hashes = [
                row["sha256"]
                for row in cursor.fetchall()
            ]

            for sha256 in hashes:
                cursor.execute("""
                    SELECT id, relativePath, size, sha256, mtime
                    FROM photos
                    WHERE sha256 = ?
                    ORDER BY relativePath
                """, (sha256,))

                ret.append([
                    dict(row)
                    for row in cursor.fetchall()
                ])

        finally:
            connection.close()

        return ret
    def getOrientationCandidates(
        self,
        in_candidateExtensions: list[str],
        in_neverRotateExtensions: list[str],
    ) -> list[dict[str, Any]]:
        ret: list[dict[str, Any]] = []

        candidateExtensions = {
            extension.lower().strip()
            for extension in in_candidateExtensions
        }

        neverRotateExtensions = {
            extension.lower().strip()
            for extension in in_neverRotateExtensions
        }

        connection = sqlite3.connect(self._dbPath)
        connection.row_factory = sqlite3.Row

        try:
            cursor = connection.cursor()

            cursor.execute("""
                SELECT
                    id,
                    relativePath,
                    extension,
                    size,
                    sha256,
                    width,
                    height,
                    cameraModel,
                    exifOrientation
                FROM photos
                WHERE isJpeg = 1
                AND exifOrientation IN (6, 8)
                ORDER BY relativePath
            """)

            for row in cursor.fetchall():
                item = dict(row)
                extension = str(item["extension"]).lower().strip()

                if extension in neverRotateExtensions:
                    continue

                if extension not in candidateExtensions:
                    continue

                item["suggestedRotation"] = 90 if item["exifOrientation"] == 6 else 270

                ret.append(item)

        finally:
            connection.close()

        return ret

    def getTrustedUprightPhotosForOrientationDataset(
        self,
        in_candidateExtensions: list[str],
        in_neverRotateExtensions: list[str],
        in_cameraModel: str,
    ) -> list[dict[str, Any]]:
        ret: list[dict[str, Any]] = []

        candidateExtensions = {
            extension.lower().strip()
            for extension in in_candidateExtensions
        }

        neverRotateExtensions = {
            extension.lower().strip()
            for extension in in_neverRotateExtensions
        }

        connection = sqlite3.connect(self._dbPath)
        connection.row_factory = sqlite3.Row

        try:
            cursor = connection.cursor()

            cursor.execute("""
                SELECT
                    id,
                    relativePath,
                    extension,
                    cameraModel,
                    exifOrientation
                FROM photos
                WHERE isJpeg = 1
                AND cameraModel = ?
                AND exifOrientation = 1
                ORDER BY relativePath
            """, (in_cameraModel,))

            for row in cursor.fetchall():
                item = dict(row)
                extension = str(item["extension"]).lower().strip()

                if extension in neverRotateExtensions:
                    continue

                if extension not in candidateExtensions:
                    continue

                ret.append(item)

        finally:
            connection.close()

        return ret

    def getOrientationCandidatesForFaceDetection(
        self,
        in_candidateExtensions: list[str],
        in_neverRotateExtensions: list[str],
        in_trustedCameraModels: list[str] | None = None,
        in_excludedPhotoIds: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        ret: list[dict[str, Any]] = []

        candidateExtensions = {
            extension.lower().strip()
            for extension in in_candidateExtensions
        }

        neverRotateExtensions = {
            extension.lower().strip()
            for extension in in_neverRotateExtensions
        }

        trustedCameraModelsNormalized: set[str] = set()
        if in_trustedCameraModels is not None:
            trustedCameraModelsNormalized = {
                str(cameraModel).replace("\x00", "").strip().lower()
                for cameraModel in in_trustedCameraModels
                if str(cameraModel).strip()
            }
        excludedPhotoIds = in_excludedPhotoIds or set()

        connection = sqlite3.connect(self._dbPath)
        connection.row_factory = sqlite3.Row

        try:
            cursor = connection.cursor()

            cursor.execute("""
                SELECT
                    id,
                    relativePath,
                    extension,
                    size,
                    cameraModel,
                    exifOrientation
                FROM photos
                WHERE isJpeg = 1
                AND exifOrientation IS NULL
                ORDER BY relativePath
            """)

            for row in cursor.fetchall():
                item = dict(row)
                photoId = str(item.get("id") or "")
                if photoId in excludedPhotoIds:
                    continue
                extension = str(item["extension"]).lower().strip()

                if extension in neverRotateExtensions:
                    continue

                if extension not in candidateExtensions:
                    continue

                cameraModelNormalized = str(
                    item.get("cameraModel") or ""
                ).replace("\x00", "").strip().lower()
                if cameraModelNormalized in trustedCameraModelsNormalized:
                    continue

                ret.append(item)

        finally:
            connection.close()

        return ret

    def getDuplicateCandidatePhotoIds(
        self,
    ) -> set[str]:
        ret: set[str] = set()

        connection = sqlite3.connect(self._dbPath)
        connection.row_factory = sqlite3.Row

        try:
            cursor = connection.cursor()
            cursor.execute("""
                SELECT id
                FROM photos
                WHERE sha256 IS NOT NULL
                AND sha256 IN (
                    SELECT sha256
                    FROM photos
                    WHERE sha256 IS NOT NULL
                    GROUP BY sha256
                    HAVING COUNT(*) > 1
                )
            """)

            for row in cursor.fetchall():
                ret.add(str(row["id"]))
        finally:
            connection.close()

        return ret

    def getSimilarDuplicateGroups(
        self,
        in_excludedPhotoIds: set[str] | None = None,
    ) -> list[list[dict[str, Any]]]:
        ret: list[list[dict[str, Any]]] = []

        excludedPhotoIds = in_excludedPhotoIds or set()
        groupedItems: dict[str, list[dict[str, Any]]] = {}

        connection = sqlite3.connect(self._dbPath)
        connection.row_factory = sqlite3.Row

        try:
            cursor = connection.cursor()
            cursor.execute("""
                SELECT
                    id,
                    relativePath,
                    extension,
                    size,
                    sha256,
                    mtime,
                    width,
                    height,
                    cameraModel
                FROM photos
                WHERE isJpeg = 1
                ORDER BY relativePath
            """)

            for row in cursor.fetchall():
                item = dict(row)
                photoId = str(item["id"])
                if photoId in excludedPhotoIds:
                    continue

                extension = str(item["extension"] or "").lower().strip()
                if extension not in {".jpg", ".jpeg"}:
                    continue

                width = item.get("width")
                height = item.get("height")
                if width is None or height is None:
                    continue

                relativePath = str(item["relativePath"])
                stem = Path(relativePath).stem
                normalizedStem = self._normalizeDuplicateStem(stem)
                if not normalizedStem:
                    continue

                cameraModel = str(item.get("cameraModel") or "").replace("\x00", "").strip().lower()
                mtimeSecond = int(float(item["mtime"]))
                key = (
                    f"{normalizedStem}|{cameraModel}|"
                    f"{int(width)}x{int(height)}|{mtimeSecond}"
                )

                existingList = groupedItems.get(key)
                if existingList is None:
                    groupedItems[key] = [item]
                else:
                    existingList.append(item)
        finally:
            connection.close()

        for groupItems in groupedItems.values():
            if len(groupItems) < 2:
                continue

            uniqueSizes = {int(item["size"]) for item in groupItems}
            if len(uniqueSizes) < 2:
                continue

            sortedGroup = sorted(
                groupItems,
                key=lambda in_item: str(in_item["relativePath"]).lower(),
            )
            ret.append(sortedGroup)

        ret.sort(
            key=lambda in_group: int(in_group[0]["size"]),
            reverse=True,
        )

        return ret

    def getAllDuplicateCandidatePhotoIds(
        self,
    ) -> set[str]:
        ret = self.getDuplicateCandidatePhotoIds()
        similarGroups = self.getSimilarDuplicateGroups(ret)
        for group in similarGroups:
            for item in group:
                ret.add(str(item["id"]))
        return ret

    def _normalizeDuplicateStem(
        self,
        in_stem: str,
    ) -> str:
        ret = in_stem.lower().strip()
        ret = re.sub(r"\s*\(\d+\)$", "", ret)
        ret = re.sub(r"\s+copy$", "", ret)
        ret = re.sub(r"_copy$", "", ret)
        ret = re.sub(r"-copy$", "", ret)
        # Remove trailing copy index only when filename already
        # has its own numeric sequence before the final separator.
        # Example: IMG_0347_1 -> IMG_0347, but IMG_1531 stays IMG_1531.
        ret = re.sub(r"(?<=\d)[_-](\d{1,3})$", "", ret)
        return ret