from pathlib import Path
from typing import Any

from photo_cleaner.infrastructure.sqlitePhotoRepository import (
    SqlitePhotoRepository,
)
from photo_cleaner.infrastructure.thumbnailGenerator import (
    ThumbnailGenerator,
)
from photo_cleaner.services.duplicateKeepSelector import (
    DuplicateKeepSelector,
)


class DuplicateReportService:
    def __init__(
        self,
        in_repository: SqlitePhotoRepository,
        in_thumbnailGenerator: ThumbnailGenerator,
    ) -> None:
        self._repository = in_repository
        self._thumbnailGenerator = in_thumbnailGenerator
        self._keepSelector = DuplicateKeepSelector()

    def buildReport(
        self,
        in_archiveRoot: str,
        in_workspacePath: str,
        in_maxSide: int,
        in_quality: int,
    ) -> None:
        print("duplicates preparation started")
        print(f"archive root: {in_archiveRoot}")
        print(f"workspace path: {in_workspacePath}")

        exactDuplicateGroups = self._repository.getSha256DuplicateGroups()
        exactDuplicateIds: set[str] = set()
        for group in exactDuplicateGroups:
            for item in group:
                exactDuplicateIds.add(str(item["id"]))
        similarDuplicateGroups = self._repository.getSimilarDuplicateGroups(
            exactDuplicateIds,
        )
        print(
            "duplicate groups loaded: "
            f"exact={len(exactDuplicateGroups)}, "
            f"similar={len(similarDuplicateGroups)}"
        )

        workspacePath = Path(in_workspacePath)
        thumbsPath = workspacePath / "thumbs"
        duplicateActions = self._repository.getDuplicateActions()
        archiveRoot = Path(in_archiveRoot)

        groupedEntries: list[dict[str, Any]] = []
        for group in exactDuplicateGroups:
            groupedEntries.append(
                {
                    "groupType": "exact",
                    "group": group,
                }
            )
        for group in similarDuplicateGroups:
            groupedEntries.append(
                {
                    "groupType": "similar",
                    "group": group,
                }
            )

        logProgressEvery = 25
        preparedGroupsCount = 0
        generatedThumbsCount = 0

        for groupIndex, entry in enumerate(groupedEntries, start=1):
            group = entry["group"]
            groupType = str(entry["groupType"])
            keepItem = self._keepSelector.selectKeepItem(group)
            groupKey = self._buildGroupKey(groupType, group)
            groupSha256 = str(group[0].get("sha256") or "")
            photoIds = [str(item["id"]) for item in group]
            existingGroupAction = duplicateActions.get(groupKey, {})
            selectedKeepPhotoId = str(
                existingGroupAction.get(
                    "selectedKeepPhotoId",
                    keepItem["id"],
                )
            )
            if selectedKeepPhotoId not in photoIds:
                selectedKeepPhotoId = str(keepItem["id"])
            statusValue = str(
                existingGroupAction.get("status", "pending")
            )

            groupAction = {
                "groupKey": groupKey,
                "groupType": groupType,
                "sha256": groupSha256,
                "size": int(group[0]["size"]),
                "photoIds": photoIds,
                "selectedKeepPhotoId": selectedKeepPhotoId,
                "recommendedKeepPhotoId": str(keepItem["id"]),
                "status": statusValue,
            }
            duplicateActions[groupKey] = groupAction
            self._repository.upsertDuplicateAction(groupKey, groupAction)
            preparedGroupsCount += 1

            for item in group:
                relativePath = str(item["relativePath"])
                sourcePath = archiveRoot / relativePath
                thumbFileName = f"{item['id']}.jpg"
                thumbPath = thumbsPath / thumbFileName

                if Path(relativePath).suffix.lower() in {".jpg", ".jpeg"}:
                    if not thumbPath.exists():
                        hasThumb = self._thumbnailGenerator.generateThumbnail(
                            sourcePath,
                            thumbPath,
                            in_maxSide,
                            in_quality,
                        )
                        if hasThumb:
                            generatedThumbsCount += 1

            if groupIndex % logProgressEvery == 0:
                print(
                    "duplicates preparation progress: "
                    f"{groupIndex}/{len(groupedEntries)} groups"
                )

        print(
            "duplicates preparation finished: "
            f"groups={preparedGroupsCount}, "
            f"newThumbnails={generatedThumbsCount}"
        )

    def _buildGroupKey(
        self,
        in_groupType: str,
        in_group: list[dict[str, Any]],
    ) -> str:
        ret = ""
        if in_groupType == "exact":
            groupSha256 = str(in_group[0].get("sha256") or "")
            ret = f"exact:{groupSha256}"
        else:
            similarBase = str(Path(str(in_group[0]["relativePath"])).stem).lower()
            ret = f"similar:{similarBase}:{in_group[0]['mtime']}"
        return ret
