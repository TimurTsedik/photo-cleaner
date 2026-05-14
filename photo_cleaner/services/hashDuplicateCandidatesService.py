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
        photosForHashing = self._repository.getPhotosForHashing()
        rootPath = Path(in_archiveRoot)
        hashedCount = 0
        skippedCount = 0

        for photoIndex, photo in enumerate(photosForHashing, start=1):
            print(
                f"hash photo {photoIndex}/{len(photosForHashing)} "
                f"path={photo['relativePath']}"
            )

            if photo["sha256"]:
                skippedCount += 1
                continue

            fullPath = rootPath / photo["relativePath"]

            sha256 = self._hasher.calculate(fullPath)

            self._repository.updatePhotoSha256(
                photo["id"],
                sha256,
            )
            hashedCount += 1

        print(
            "hash duplicates finished: "
            f"total={len(photosForHashing)}, hashed={hashedCount}, skipped={skippedCount}"
        )