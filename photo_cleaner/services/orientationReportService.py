import html
import json
from pathlib import Path
from typing import Any

from photo_cleaner.domain.orientationPredictorProtocol import (
    OrientationPredictorProtocol,
)
from photo_cleaner.infrastructure.sqlitePhotoRepository import (
    SqlitePhotoRepository,
)
from photo_cleaner.infrastructure.actionsFileStore import (
    ActionsFileStore,
)


class OrientationReportService:
    def __init__(
        self,
        in_repository: SqlitePhotoRepository,
        in_predictor: OrientationPredictorProtocol,
    ) -> None:
        self._repository = in_repository
        self._predictor = in_predictor
        self._actionsFileStore = ActionsFileStore()

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

        workspacePath = Path(in_workspacePath)
        archiveRoot = Path(in_archiveRoot)

        duplicateCandidateIds = self._repository.getAllDuplicateCandidatePhotoIds()
        print(
            "duplicate candidates excluded from orientation: "
            f"{len(duplicateCandidateIds)}"
        )

        candidates = self._repository.getOrientationCandidatesForFaceDetection(
            in_candidateExtensions,
            in_neverRotateExtensions,
            in_trustedCameraModels,
            duplicateCandidateIds,
        )
        print(f"candidates loaded: {len(candidates)}")

        reportsPath = workspacePath / "reports"
        thumbsPath = workspacePath / "thumbs" / in_thumbsSubdir
        reportsPath.mkdir(parents=True, exist_ok=True)
        thumbsPath.mkdir(parents=True, exist_ok=True)
        print(f"reports path: {reportsPath}")
        print(f"thumbs path: {thumbsPath}")

        actionsPayload = self._actionsFileStore.loadActions(workspacePath)
        orientationActions = actionsPayload["orientation"]["items"]

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
.toolbar {{ margin: 12px 0 18px 0; display: flex; gap: 8px; flex-wrap: wrap; }}
button {{ background: #2b2b2b; color: #eee; border: 1px solid #555; border-radius: 8px; padding: 8px 10px; cursor: pointer; }}
button:hover {{ background: #353535; }}
.status {{ color: #9ad1ff; margin-bottom: 8px; }}
.controls {{ margin-top: 10px; display: flex; gap: 8px; flex-wrap: wrap; }}
</style>
</head>
<body>
<h1>{html.escape(in_reportTitle)}</h1>
<div class="toolbar">
  <button onclick="pcConnectActionsFile()">Connect actions.json</button>
  <button onclick="pcSaveActions()">Save actions.json</button>
  <span id="pcActionsInfo" class="meta">actions.json not connected (download fallback)</span>
</div>
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
            orientationActions[photoId] = {
                "photoId": photoId,
                "relativePath": relativePath,
                "cameraModel": item.get("cameraModel"),
                "sourceReport": in_reportFileName,
                "suggestedRotation": suggestedRotation,
                "suggestedAction": suggestedAction,
                "selectedRotation": selectedRotation,
                "selectedAction": selectedAction,
                "status": selectedStatus,
                "decisionReason": decisionReason,
                "confidence": confidenceValue,
                "margin": marginValue,
            }

            print(
                "orientation row: "
                f"{item['relativePath']} "
                f"action={suggestedAction} "
                f"reason={decisionReason} "
                f"confidence={confidenceValue:.3f}"
            )

            originalThumbFileName = f"{photoId}_original.jpg"
            originalThumbPath = thumbsPath / originalThumbFileName

            self._buildVariantThumbnail(
                sourcePath,
                originalThumbPath,
                0,
            )

            rotate90ThumbFileName = f"{photoId}_rotate90.jpg"
            rotate90ThumbPath = thumbsPath / rotate90ThumbFileName
            self._buildVariantThumbnail(
                sourcePath,
                rotate90ThumbPath,
                90,
            )

            rotate270ThumbFileName = f"{photoId}_rotate270.jpg"
            rotate270ThumbPath = thumbsPath / rotate270ThumbFileName
            self._buildVariantThumbnail(
                sourcePath,
                rotate270ThumbPath,
                270,
            )

            selectedRotationDisplay = (
                str(selectedRotation)
                if selectedRotation is not None
                else "none"
            )
            suggestedRotationJs = (
                "null"
                if suggestedRotation is None
                else str(int(suggestedRotation))
            )
            suggestedActionJs = (
                str(suggestedAction)
                .replace("\\", "\\\\")
                .replace("'", "\\'")
            )

            selectedVariantTitle, selectedVariantPath = (
                self._resolveSelectedVariantPreview(
                    photoId,
                    selectedRotation,
                    in_thumbsSubdir,
                )
            )

            htmlParts.append(
                f'<div class="item" data-photo-id="{html.escape(photoId)}">'
            )
            htmlParts.append(f"<h2>Candidate #{foundCount}</h2>")
            htmlParts.append(
                f'<div class="path">{html.escape(relativePath)}</div>'
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
            htmlParts.append(
                f'<p class="meta">selected rotation: '
                f'<span id="orientation-selected-{html.escape(photoId)}">'
                f'{html.escape(selectedRotationDisplay)}</span></p>'
            )
            htmlParts.append(
                f'<p class="meta">selected action: '
                f'<span id="orientation-action-{html.escape(photoId)}">'
                f'{html.escape(str(selectedAction))}</span></p>'
            )
            htmlParts.append(
                f'<p class="status">status: '
                f'<span id="orientation-status-{html.escape(photoId)}">'
                f'{html.escape(selectedStatus)}</span></p>'
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
            htmlParts.append('<div class="controls">')
            htmlParts.append(
                "<button "
                f'onclick="pcOrientationApplySuggested(\'{html.escape(photoId)}\', '
                f"{suggestedRotationJs}, "
                f"'{suggestedActionJs}')"
                '">Accept suggested</button>'
            )
            htmlParts.append(
                "<button "
                f'onclick="pcOrientationSet(\'{html.escape(photoId)}\', 90, '
                "'rotate90')"
                '">Set 90</button>'
            )
            htmlParts.append(
                "<button "
                f'onclick="pcOrientationSet(\'{html.escape(photoId)}\', 270, '
                "'rotate270')"
                '">Set 270</button>'
            )
            htmlParts.append(
                "<button "
                f'onclick="pcOrientationSet(\'{html.escape(photoId)}\', null, '
                "'manual_review')"
                '">Manual review</button>'
            )
            htmlParts.append('</div>')
            htmlParts.append('<div class="variants">')
            htmlParts.append(
                self._renderVariantHtml(
                    "ORIGINAL",
                    f"../thumbs/{in_thumbsSubdir}/{originalThumbFileName}",
                )
            )
            htmlParts.append(
                self._renderVariantHtml(
                    selectedVariantTitle,
                    selectedVariantPath,
                    f"orientation-preview-title-{photoId}",
                    f"orientation-preview-img-{photoId}",
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

        self._actionsFileStore.saveActions(
            workspacePath,
            actionsPayload,
        )
        actionsRelativePath = "../actions.json"
        htmlParts.append(
            self._buildActionsScript(
                actionsPayload,
                actionsRelativePath,
                in_thumbsSubdir,
            )
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

    def _buildActionsScript(
        self,
        in_actionsPayload: dict[str, Any],
        in_actionsRelativePath: str,
        in_thumbsSubdir: str,
    ) -> str:
        payloadJson = json.dumps(
            in_actionsPayload,
            ensure_ascii=False,
        )
        escapedPayload = (
            payloadJson.replace("\\", "\\\\")
            .replace("`", "\\`")
            .replace("</", "<\\/")
        )

        ret = f"""
<script>
const pcActionsPath = {json.dumps(in_actionsRelativePath)};
const pcThumbsSubdir = {json.dumps(in_thumbsSubdir)};
const pcActionsState = JSON.parse(`{escapedPayload}`);
let pcActionsFileHandle = null;
let pcHasUnsavedChanges = false;

function pcUpdateInfo(in_text) {{
  const node = document.getElementById("pcActionsInfo");
  if (node) {{
    node.textContent = in_text;
  }}
}}

async function pcConnectActionsFile() {{
  if (!window.showOpenFilePicker) {{
    pcUpdateInfo("File System Access API unavailable; use Save actions.json");
    return;
  }}
  try {{
    const out_files = await window.showOpenFilePicker({{
      multiple: false,
      suggestedName: "actions.json",
      types: [{{ description: "JSON", accept: {{ "application/json": [".json"] }} }}],
    }});
    pcActionsFileHandle = out_files[0];
    pcUpdateInfo("actions.json connected");
    if (pcHasUnsavedChanges) {{
      await pcAutoSaveActions();
    }}
  }} catch (in_error) {{
    pcUpdateInfo("actions.json connection canceled");
  }}
}}

function pcDownloadActions() {{
  const out_blob = new Blob(
    [JSON.stringify(pcActionsState, null, 2)],
    {{ type: "application/json" }}
  );
  const out_url = URL.createObjectURL(out_blob);
  const out_link = document.createElement("a");
  out_link.href = out_url;
  out_link.download = "actions.json";
  out_link.click();
  URL.revokeObjectURL(out_url);
}}

async function pcWriteActionsToConnectedFile() {{
  pcActionsState.updatedAt = new Date().toISOString();
  const out_writable = await pcActionsFileHandle.createWritable();
  await out_writable.write(JSON.stringify(pcActionsState, null, 2));
  await out_writable.close();
  pcHasUnsavedChanges = false;
}}

async function pcAutoSaveActions() {{
  if (!pcActionsFileHandle) {{
    pcUpdateInfo("unsaved changes (connect actions.json for background autosave)");
    return;
  }}
  try {{
    await pcWriteActionsToConnectedFile();
    pcUpdateInfo("actions.json autosaved");
  }} catch (in_error) {{
    pcUpdateInfo("autosave failed; use Save actions.json");
  }}
}}

async function pcSaveActions() {{
  if (pcActionsFileHandle) {{
    try {{
      await pcWriteActionsToConnectedFile();
      pcUpdateInfo("actions.json updated");
      return;
    }} catch (in_error) {{
      pcUpdateInfo("write failed; fallback to download");
    }}
  }}
  pcDownloadActions();
  pcHasUnsavedChanges = false;
  pcUpdateInfo("actions.json downloaded");
}}

function pcOrientationApplySuggested(in_photoId, in_rotation, in_action) {{
  pcOrientationSet(in_photoId, in_rotation, in_action);
}}

function pcOrientationSet(in_photoId, in_rotation, in_action) {{
  if (!pcActionsState.orientation || !pcActionsState.orientation.items) {{
    return;
  }}
  const out_item = pcActionsState.orientation.items[in_photoId];
  if (!out_item) {{
    return;
  }}
  out_item.selectedRotation = in_rotation;
  out_item.selectedAction = in_action;
  out_item.status = "confirmed";

  const out_rotationNode = document.getElementById(`orientation-selected-${{in_photoId}}`);
  if (out_rotationNode) {{
    out_rotationNode.textContent = in_rotation === null ? "none" : String(in_rotation);
  }}
  const out_statusNode = document.getElementById(`orientation-status-${{in_photoId}}`);
  if (out_statusNode) {{
    out_statusNode.textContent = "confirmed";
  }}
  const out_actionNode = document.getElementById(`orientation-action-${{in_photoId}}`);
  if (out_actionNode) {{
    out_actionNode.textContent = String(in_action);
  }}

  let out_previewTitle = "SELECTED ORIGINAL";
  let out_previewSrc = `../thumbs/${{pcThumbsSubdir}}/${{in_photoId}}_original.jpg`;
  if (in_rotation === 90) {{
    out_previewTitle = "SELECTED ROTATE 90";
    out_previewSrc = `../thumbs/${{pcThumbsSubdir}}/${{in_photoId}}_rotate90.jpg`;
  }} else if (in_rotation === 270) {{
    out_previewTitle = "SELECTED ROTATE 270";
    out_previewSrc = `../thumbs/${{pcThumbsSubdir}}/${{in_photoId}}_rotate270.jpg`;
  }}

  const out_previewTitleNode = document.getElementById(`orientation-preview-title-${{in_photoId}}`);
  if (out_previewTitleNode) {{
    out_previewTitleNode.textContent = out_previewTitle;
  }}
  const out_previewImageNode = document.getElementById(`orientation-preview-img-${{in_photoId}}`);
  if (out_previewImageNode) {{
    out_previewImageNode.src = out_previewSrc;
  }}
  pcHasUnsavedChanges = true;
  pcAutoSaveActions();
}}

pcUpdateInfo(`actions source: ${{pcActionsPath}}`);
</script>
"""
        return ret

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
        in_titleElementId: str | None = None,
        in_imageElementId: str | None = None,
    ) -> str:
        titleIdAttr = ""
        imageIdAttr = ""
        if in_titleElementId:
            titleIdAttr = f' id="{html.escape(in_titleElementId)}"'
        if in_imageElementId:
            imageIdAttr = f' id="{html.escape(in_imageElementId)}"'

        ret = (
            '<div class="variant">'
            f'<div class="badge"{titleIdAttr}>{html.escape(in_title)}</div>'
            f'<img{imageIdAttr} src="{html.escape(in_thumbRelativePath)}">'
            '</div>'
        )

        return ret

    def _resolveSelectedVariantPreview(
        self,
        in_photoId: str,
        in_selectedRotation: int | None,
        in_thumbsSubdir: str,
    ) -> tuple[str, str]:
        title = "SELECTED ORIGINAL"
        thumbRelativePath = (
            f"../thumbs/{in_thumbsSubdir}/{in_photoId}_original.jpg"
        )

        if in_selectedRotation == 90:
            title = "SELECTED ROTATE 90"
            thumbRelativePath = (
                f"../thumbs/{in_thumbsSubdir}/{in_photoId}_rotate90.jpg"
            )
        elif in_selectedRotation == 270:
            title = "SELECTED ROTATE 270"
            thumbRelativePath = (
                f"../thumbs/{in_thumbsSubdir}/{in_photoId}_rotate270.jpg"
            )

        ret = (title, thumbRelativePath)
        return ret
