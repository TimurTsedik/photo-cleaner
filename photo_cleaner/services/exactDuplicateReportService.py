from photo_cleaner.infrastructure.sqlitePhotoRepository import (
    SqlitePhotoRepository,
)


class ExactDuplicateReportService:
    def __init__(
        self,
        in_repository: SqlitePhotoRepository,
    ) -> None:
        self._repository = in_repository

    def printReport(self) -> None:
        duplicateGroups = self._repository.getSha256DuplicateGroups()

        if not duplicateGroups:
            print("No exact duplicates found")
            return

        for groupIndex, group in enumerate(duplicateGroups, start=1):
            print()
            print("=" * 80)
            print(f"Duplicate group #{groupIndex}")
            print(f"sha256: {group[0]['sha256']}")
            print(f"size: {group[0]['size']}")
            print("-" * 80)

            for item in group:
                print(item["relativePath"])