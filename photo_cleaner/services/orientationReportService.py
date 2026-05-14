from pathlib import Path

from photo_cleaner.domain.orientationPredictorProtocol import (
    OrientationPredictorProtocol,
)
from photo_cleaner.infrastructure.sqlitePhotoRepository import (
    SqlitePhotoRepository,
)


class OrientationReportService:
    def __init__(
        self,
        in_repository: SqlitePhotoRepository,
        in_predictor: OrientationPredictorProtocol,
    ) -> None:
        self._repository = in_repository
        self._predictor = in_predictor

    def buildReport(
        self,
        in_archiveRoot: str,
        in_workspacePath: str,
        in_candidateExtensions: list[str],
        in_neverRotateExtensions: list[str],
        in_trustedCameraModels: list[str],
        in_includeAllCandidates: bool,
        in_thumbsSubdir: str,
    ) -> None:
        print("orientation preparation started")
        print(f"archive root: {in_archiveRoot}")
        print(f"workspace path: {in_workspacePath}")
        print(f"include all candidates: {in_includeAllCandidates}")

        workspacePath = Path(in_workspacePath)
        archiveRoot = Path(in_archiveRoot)

        duplicateCandidateIds = self._repository.getAllDuplicateCandidatePhotoIds()
        print(
            "duplicate candidates detected (not excluded): "
            f"{len(duplicateCandidateIds)}"
        )

        candidates = self._repository.getOrientationCandidatesForFaceDetection(
            in_candidateExtensions,
            in_neverRotateExtensions,
            in_trustedCameraModels,
            set(),
        )
        print(f"candidates loaded: {len(candidates)}")

        thumbsPath = workspacePath / "thumbs" / in_thumbsSubdir
        thumbsPath.mkdir(parents=True, exist_ok=True)
        print(f"thumbs path: {thumbsPath}")

        orientationActions = self._repository.getOrientationActions()

        foundCount = 0
        missingCount = 0
        skippedCount = 0
        checkedCount = 0
        reasonCounts: dict[str, int] = {}
        rotationCounts: dict[int, int] = {}
        actionCounts: dict[str, int] = {}
        logProgressEvery = 10
        generatedThumbsCount = 0

        index = 0
        for item in candidates:
            index += 1
            sourcePath = archiveRoot / item["relativePath"]

            if not sourcePath.exists():
                missingCount += 1
                if missingCount <= 5:
                    print(f"missing file: {sourcePath}")
                continue

            checkedCount += 1
            detection = self._predictor.predictOrientation(sourcePath)
            decisionReason = str(detection.get("decisionReason", "unknown"))
            reasonCounts[decisionReason] = reasonCounts.get(decisionReason, 0) + 1

            suggestedRotation = detection.get("suggestedRotation")
            suggestedAction = str(detection.get("suggestedAction", "manual_review"))
            actionCounts[suggestedAction] = actionCounts.get(suggestedAction, 0) + 1

            shouldRenderItem = in_includeAllCandidates
            if not in_includeAllCandidates:
                if suggestedRotation is not None:
                    shouldRenderItem = True
                else:
                    shouldRenderItem = False

            if not shouldRenderItem:
                skippedCount += 1
                if checkedCount <= 5:
                    print(
                        f"skip: {item['relativePath']} "
                        f"reason={decisionReason} "
                        f"confidence={detection.get('confidence', 0):.3f}"
                    )
                if index % logProgressEvery == 0:
                    print(
                        "orientation progress: "
                        f"{index}/{len(candidates)} "
                        f"checked={checkedCount} "
                        f"rendered={foundCount} "
                        f"skipped={skippedCount} "
                        f"missing={missingCount}"
                    )
                continue

            foundCount += 1

            if suggestedRotation is not None:
                rotationCounts[int(suggestedRotation)] = (
                    rotationCounts.get(int(suggestedRotation), 0) + 1
                )

            confidenceValue = float(detection.get("confidence", 0.0))
            marginValue = float(detection.get("margin", 0.0))
            photoId = str(item["id"])
            relativePath = str(item["relativePath"])

            existingOrientationAction = orientationActions.get(photoId, {})
            selectedRotation = existingOrientationAction.get(
                "selectedRotation",
                suggestedRotation,
            )
            if selectedRotation is not None:
                try:
                    selectedRotation = int(selectedRotation)
                except (TypeError, ValueError):
                    selectedRotation = None
            if selectedRotation not in {None, 90, 270}:
                selectedRotation = None
            selectedAction = existingOrientationAction.get(
                "selectedAction",
                suggestedAction,
            )
            selectedStatus = existingOrientationAction.get(
                "status",
                "pending",
            )
            actionPayload = {
                "photoId": photoId,
                "relativePath": relativePath,
                "cameraModel": item.get("cameraModel"),
                "sourceReport": "orientation",
                "thumbsSubdir": in_thumbsSubdir,
                "suggestedRotation": suggestedRotation,
                "suggestedAction": suggestedAction,
                "selectedRotation": selectedRotation,
                "selectedAction": selectedAction,
                "status": selectedStatus,
                "decisionReason": decisionReason,
                "confidence": confidenceValue,
                "margin": marginValue,
            }
            orientationActions[photoId] = actionPayload
            self._repository.upsertOrientationAction(photoId, actionPayload)

            print(
                "orientation row: "
                f"{item['relativePath']} "
                f"action={suggestedAction} "
                f"reason={decisionReason} "
                f"confidence={confidenceValue:.3f}"
            )

            originalThumbFileName = f"{photoId}_original.jpg"
            originalThumbPath = thumbsPath / originalThumbFileName

            generatedThumbsCount += self._buildVariantThumbnail(
                sourcePath,
                originalThumbPath,
                0,
            )

            rotate90ThumbFileName = f"{photoId}_rotate90.jpg"
            rotate90ThumbPath = thumbsPath / rotate90ThumbFileName
            generatedThumbsCount += self._buildVariantThumbnail(
                sourcePath,
                rotate90ThumbPath,
                90,
            )

            rotate270ThumbFileName = f"{photoId}_rotate270.jpg"
            rotate270ThumbPath = thumbsPath / rotate270ThumbFileName
            generatedThumbsCount += self._buildVariantThumbnail(
                sourcePath,
                rotate270ThumbPath,
                270,
            )

            if index % logProgressEvery == 0:
                print(
                    "orientation progress: "
                    f"{index}/{len(candidates)} "
                    f"checked={checkedCount} "
                    f"rendered={foundCount} "
                    f"skipped={skippedCount} "
                    f"missing={missingCount}"
                )

        print(
            "orientation preparation finished: "
            f"total={len(candidates)} "
            f"checked={checkedCount} "
            f"stored={foundCount} "
            f"skipped={skippedCount} "
            f"missing={missingCount} "
            f"rotate90={rotationCounts.get(90, 0)} "
            f"rotate270={rotationCounts.get(270, 0)} "
            f"actions={actionCounts} "
            f"reasons={reasonCounts} "
            f"newThumbnails={generatedThumbsCount}"
        )

    def _buildVariantThumbnail(
        self,
        in_sourcePath: Path,
        in_outputPath: Path,
        in_angle: int,
    ) -> int:
        ret = 0
        if in_outputPath.exists():
            return ret

        try:
            from PIL import Image, ImageOps

            with Image.open(in_sourcePath) as image:
                image = ImageOps.exif_transpose(image)
                image.thumbnail((256, 256))
                image = image.convert("RGB")

                if in_angle == 90:
                    image = image.transpose(Image.Transpose.ROTATE_270)
                elif in_angle == 270:
                    image = image.transpose(Image.Transpose.ROTATE_90)

                image.save(
                    in_outputPath,
                    "JPEG",
                    quality=75,
                    optimize=True,
                )
                ret = 1

        except Exception as exception:
            print(f"orientation thumbnail failed: {in_sourcePath} -> {exception}")
        return ret
