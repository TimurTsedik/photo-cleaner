from pathlib import Path

from photo_cleaner.infrastructure.sha256FileHasher import (
    Sha256FileHasher,
)
from photo_cleaner.infrastructure.sqlitePhotoRepository import (
    SqlitePhotoRepository,
)


class HashDuplicateCandidatesService:
    def __init__(
        self,
        in_repository: SqlitePhotoRepository,
        in_hasher: Sha256FileHasher,
    ) -> None:
        self._repository = in_repository
        self._hasher = in_hasher

    def hashDuplicateCandidates(
        self,
        in_archiveRoot: str,
    ) -> None:
        duplicateSizeGroups = self._repository.getDuplicateSizeGroups()
        rootPath = Path(in_archiveRoot)

        for groupIndex, group in enumerate(duplicateSizeGroups, start=1):
            print(
                f"hash group {groupIndex}/{len(duplicateSizeGroups)} "
                f"size={group[0]['size']} files={len(group)}"
            )

            for photo in group:
                if photo["sha256"]:
                    continue

                fullPath = rootPath / photo["relativePath"]

                sha256 = self._hasher.calculate(fullPath)

                self._repository.updatePhotoSha256(
                    photo["id"],
                    sha256,
                )