import os
import time
import uuid
from pathlib import Path
from typing import Any
from photo_cleaner.infrastructure.metadataReader import MetadataReader


class FileSystemScanner:
    def __init__(
        self,
        in_metadataReader: MetadataReader,
    ) -> None:
        self._metadataReader = in_metadataReader
    
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

        scannedFilesCount = 0
        matchedFilesCount = 0
        errorCount = 0

        print(f"scan started: {rootPath}")
        print(f"supported extensions: {sorted(supportedExtensions)}")

        for currentRoot, _, files in os.walk(rootPath):
            print(f"scan directory: {currentRoot}, files={len(files)}")

            for fileName in files:
                scannedFilesCount += 1

                if scannedFilesCount % 500 == 0:
                    print(
                        f"scan progress: scanned={scannedFilesCount}, "
                        f"matched={matchedFilesCount}, errors={errorCount}"
                    )

                extension = Path(fileName).suffix.lower()

                if extension not in supportedExtensions:
                    continue

                fullPath = Path(currentRoot) / fileName

                try:
                    stat = fullPath.stat()

                    relativePath = str(
                        fullPath.relative_to(rootPath)
                    )

                    isRaw = extension in in_rawExtensions
                    isJpeg = extension in in_jpegExtensions

                    metadata = {
                        "width": None,
                        "height": None,
                        "cameraModel": None,
                        "exifOrientation": None,
                    }

                    if isJpeg:
                        metadata = self._metadataReader.readMetadata(fullPath)

                    ret.append({
                        "id": str(uuid.uuid4()),
                        "relativePath": relativePath,
                        "extension": extension,
                        "size": stat.st_size,
                        "mtime": stat.st_mtime,
                        "sha256": None,
                        "partialSha256": None,
                        "width": metadata["width"],
                        "height": metadata["height"],
                        "cameraModel": metadata["cameraModel"],
                        "exifOrientation": metadata["exifOrientation"],
                        "isRaw": int(isRaw),
                        "isJpeg": int(isJpeg),
                        "thumbnailPath": None,
                        "createdAt": time.time(),
                    })

                    matchedFilesCount += 1

                    if matchedFilesCount % 100 == 0:
                        print(
                            f"photos found: {matchedFilesCount}, "
                            f"last={relativePath}"
                        )

                except Exception as exception:
                    errorCount += 1
                    print(f"scan file failed: {fullPath} -> {exception}")

        print(
            f"scan finished: scanned={scannedFilesCount}, "
            f"matched={matchedFilesCount}, errors={errorCount}"
        )

        return ret