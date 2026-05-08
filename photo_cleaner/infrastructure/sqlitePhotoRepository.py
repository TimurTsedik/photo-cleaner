import sqlite3
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