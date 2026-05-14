from photo_cleaner.infrastructure.fileSystemScanner import (
    FileSystemScanner,
)
from photo_cleaner.infrastructure.sqlitePhotoRepository import (
    SqlitePhotoRepository,
)


class ScanService:
    def __init__(
        self,
        in_scanner: FileSystemScanner,
        in_repository: SqlitePhotoRepository,
    ) -> None:
        self._scanner = in_scanner
        self._repository = in_repository

    def scan(
        self,
        in_archiveRoot: str,
        in_jpegExtensions: set[str],
        in_rawExtensions: set[str],
        in_excludedPathPrefixes: list[str],
    ) -> None:
        photos = self._scanner.scan(
            in_archiveRoot,
            in_jpegExtensions,
            in_rawExtensions,
            in_excludedPathPrefixes,
        )

        for photo in photos:
            self._repository.insertPhoto(photo)

        scannedRelativePaths = [
            str(photo["relativePath"])
            for photo in photos
        ]
        self._repository.syncPhotosToRelativePaths(scannedRelativePaths)