import os
import time
import uuid
from pathlib import Path
from typing import Any


class FileSystemScanner:
    def scan(
        self,
        in_rootPath: str,
        in_jpegExtensions: set[str],
        in_rawExtensions: set[str],
    ) -> list[dict[str, Any]]:
        ret: list[dict[str, Any]] = []

        rootPath = Path(in_rootPath)

        supportedExtensions = (
            in_jpegExtensions |
            in_rawExtensions
        )

        for currentRoot, _, files in os.walk(rootPath):
            for fileName in files:
                extension = Path(fileName).suffix.lower()

                if extension not in supportedExtensions:
                    continue

                fullPath = Path(currentRoot) / fileName

                stat = fullPath.stat()

                relativePath = str(
                    fullPath.relative_to(rootPath)
                )

                isRaw = extension in in_rawExtensions
                isJpeg = extension in in_jpegExtensions

                ret.append({
                    "id": str(uuid.uuid4()),
                    "relativePath": relativePath,
                    "extension": extension,
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                    "sha256": None,
                    "partialSha256": None,
                    "width": None,
                    "height": None,
                    "cameraModel": None,
                    "exifOrientation": None,
                    "isRaw": int(isRaw),
                    "isJpeg": int(isJpeg),
                    "thumbnailPath": None,
                    "createdAt": time.time(),
                })

        return ret