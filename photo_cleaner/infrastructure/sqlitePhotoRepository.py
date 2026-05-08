import sqlite3
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