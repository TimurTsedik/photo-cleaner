import html
from pathlib import Path
from typing import Any

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
        in_reportFileName: str,
        in_reportTitle: str,
        in_thumbsSubdir: str,
    ) -> None:
        print("orientation report started")
        print(f"archive root: {in_archiveRoot}")
        print(f"workspace path: {in_workspacePath}")
        print(f"include all candidates: {in_includeAllCandidates}")

        candidates = self._repository.getOrientationCandidatesForFaceDetection(
            in_candidateExtensions,
            in_neverRotateExtensions,
            in_trustedCameraModels,
        )
        print(f"candidates loaded: {len(candidates)}")

        archiveRoot = Path(in_archiveRoot)
        workspacePath = Path(in_workspacePath)
        reportsPath = workspacePath / "reports"
        thumbsPath = workspacePath / "thumbs" / in_thumbsSubdir
        reportsPath.mkdir(parents=True, exist_ok=True)
        thumbsPath.mkdir(parents=True, exist_ok=True)
        print(f"reports path: {reportsPath}")
        print(f"thumbs path: {thumbsPath}")

        htmlParts: list[str] = []

        htmlParts.append(f"""
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>{html.escape(in_reportTitle)}</title>
<style>
body {{ font-family: Arial, sans-serif; background: #111; color: #eee; margin: 24px; }}
.item {{ border: 1px solid #444; border-radius: 12px; margin-bottom: 20px; padding: 16px; background: #1b1b1b; }}
.path {{ word-break: break-all; color: #ccc; }}
.suggest {{ color: #ffd43b; font-weight: bold; }}
.meta {{ color: #aaa; margin-top: 8px; }}
.variants {{ display: flex; flex-wrap: wrap; gap: 16px; margin-top: 12px; }}
.variant {{ width: 300px; border: 1px solid #333; border-radius: 10px; padding: 12px; background: #222; }}
.badge {{ display: inline-block; padding: 4px 8px; border-radius: 6px; font-weight: bold; margin-bottom: 8px; background: #444; }}
img {{ max-width: 256px; max-height: 256px; display: block; margin-bottom: 8px; background: #333; }}
</style>
</head>
<body>
<h1>{html.escape(in_reportTitle)}</h1>
""")

        foundCount = 0
        missingCount = 0
        skippedCount = 0
        checkedCount = 0
        reasonCounts: dict[str, int] = {}
        rotationCounts: dict[int, int] = {}
        actionCounts: dict[str, int] = {}
        logProgressEvery = 10

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
            probabilitiesMap = detection.get("probabilities")

            print(
                "orientation row: "
                f"{item['relativePath']} "
                f"action={suggestedAction} "
                f"reason={decisionReason} "
                f"confidence={confidenceValue:.3f}"
            )

            originalThumbFileName = f"{item['id']}_original.jpg"
            originalThumbPath = thumbsPath / originalThumbFileName

            self._buildVariantThumbnail(
                sourcePath,
                originalThumbPath,
                0,
            )

            suggestedThumbPath: Path | None = None
            suggestedThumbFileName = ""

            if suggestedRotation == 90:
                suggestedThumbFileName = f"{item['id']}_rotate90.jpg"
                suggestedThumbPath = thumbsPath / suggestedThumbFileName
                self._buildVariantThumbnail(
                    sourcePath,
                    suggestedThumbPath,
                    90,
                )
            elif suggestedRotation == 270:
                suggestedThumbFileName = f"{item['id']}_rotate270.jpg"
                suggestedThumbPath = thumbsPath / suggestedThumbFileName
                self._buildVariantThumbnail(
                    sourcePath,
                    suggestedThumbPath,
                    270,
                )

            htmlParts.append('<div class="item">')
            htmlParts.append(f"<h2>Candidate #{foundCount}</h2>")
            htmlParts.append(
                f'<div class="path">{html.escape(item["relativePath"])}</div>'
            )
            htmlParts.append(
                f'<p>camera: {html.escape(str(item["cameraModel"]))}</p>'
            )
            htmlParts.append(
                f'<p class="suggest">ACTION: {html.escape(suggestedAction)}</p>'
            )

            rotationDisplay = (
                str(suggestedRotation)
                if suggestedRotation is not None
                else "none"
            )
            htmlParts.append(
                f'<p class="meta">suggested rotation (apply): {rotationDisplay}</p>'
            )

            probabilitiesHtml = ""
            if isinstance(probabilitiesMap, dict):
                sortedItems = sorted(probabilitiesMap.items())
                partsList: list[str] = []
                for labelKey, probabilityValue in sortedItems:
                    partsList.append(
                        f"{labelKey}: {float(probabilityValue):.3f}"
                    )
                probabilitiesHtml = "<br>".join(partsList)

            predictionLabelValue = detection.get("predictionLabel")
            predictionHtml = ""
            if predictionLabelValue is not None:
                predictionHtml = (
                    f"top class label: "
                    f"{html.escape(str(predictionLabelValue))}<br>"
                )

            htmlParts.append(
                "<p>"
                f"confidence: {confidenceValue:.3f}<br>"
                f"margin: {marginValue:.3f}<br>"
                f"{predictionHtml}"
                f"decision: {html.escape(decisionReason)}<br>"
                f"{probabilitiesHtml}"
                "</p>"
            )

            htmlParts.append(
                f'<div class="meta">id: {html.escape(str(item["id"]))}</div>'
            )
            htmlParts.append('<div class="variants">')
            htmlParts.append(
                self._renderVariantHtml(
                    "ORIGINAL",
                    f"../thumbs/{in_thumbsSubdir}/{originalThumbFileName}",
                )
            )

            if suggestedThumbPath is not None and suggestedThumbFileName:
                titleSuffix = (
                    "SUGGESTED ROTATE "
                    f"{suggestedRotation}"
                )
                htmlParts.append(
                    self._renderVariantHtml(
                        titleSuffix,
                        f"../thumbs/{in_thumbsSubdir}/{suggestedThumbFileName}",
                    )
                )

            htmlParts.append("</div>")
            htmlParts.append("</div>")

            if index % logProgressEvery == 0:
                print(
                    "orientation progress: "
                    f"{index}/{len(candidates)} "
                    f"checked={checkedCount} "
                    f"rendered={foundCount} "
                    f"skipped={skippedCount} "
                    f"missing={missingCount}"
                )

        summaryHtml = (
            f"<p>Total candidates in query: {len(candidates)}, "
            f"rendered rows: {foundCount}"
            f", missing files: {missingCount}"
            f", skipped by filter: {skippedCount}"
            f", rotate90: {rotationCounts.get(90, 0)}"
            f", rotate270: {rotationCounts.get(270, 0)}</p>"
        )

        reasonsParts: list[str] = []
        for reasonKey, reasonCount in sorted(reasonCounts.items()):
            reasonsParts.append(
                f"{html.escape(reasonKey)}={reasonCount}"
            )
        reasonsHtml = ", ".join(reasonsParts)

        actionsParts: list[str] = []
        for actionKey, actionCount in sorted(actionCounts.items()):
            actionsParts.append(
                f"{html.escape(actionKey)}={actionCount}"
            )
        actionsHtml = ", ".join(actionsParts)

        htmlParts.insert(1, summaryHtml)
        htmlParts.insert(
            2,
            f"<p>Decision reasons: {reasonsHtml}</p>",
        )
        htmlParts.insert(
            3,
            f"<p>Actions: {actionsHtml}</p>",
        )

        htmlParts.append("</body></html>")

        reportPath = reportsPath / in_reportFileName

        reportPath.write_text(
            "\n".join(htmlParts),
            encoding="utf-8",
        )

        print(
            "orientation report finished: "
            f"total={len(candidates)} "
            f"checked={checkedCount} "
            f"rendered={foundCount} "
            f"skipped={skippedCount} "
            f"missing={missingCount}"
        )
        print(f"orientation report created: {reportPath}")

    def _buildVariantThumbnail(
        self,
        in_sourcePath: Path,
        in_outputPath: Path,
        in_angle: int,
    ) -> None:
        if in_outputPath.exists():
            return

        try:
            from PIL import Image

            with Image.open(in_sourcePath) as image:
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

        except Exception as exception:
            print(f"orientation thumbnail failed: {in_sourcePath} -> {exception}")

    def _renderVariantHtml(
        self,
        in_title: str,
        in_thumbRelativePath: str,
    ) -> str:
        ret = (
            '<div class="variant">'
            f'<div class="badge">{html.escape(in_title)}</div>'
            f'<img src="{html.escape(in_thumbRelativePath)}">'
            '</div>'
        )

        return ret
