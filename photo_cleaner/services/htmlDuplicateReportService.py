import html
import json
from pathlib import Path
from typing import Any

from photo_cleaner.infrastructure.fileSystemScanner import (
    pathMatchesExcludedPrefix,
)
from photo_cleaner.infrastructure.sqlitePhotoRepository import (
    SqlitePhotoRepository,
)
from photo_cleaner.infrastructure.thumbnailGenerator import (
    ThumbnailGenerator,
)
from photo_cleaner.infrastructure.actionsFileStore import (
    ActionsFileStore,
)
from photo_cleaner.services.duplicateKeepSelector import (
    DuplicateKeepSelector,
)


class HtmlDuplicateReportService:
    def __init__(
        self,
        in_repository: SqlitePhotoRepository,
        in_thumbnailGenerator: ThumbnailGenerator,
    ) -> None:
        self._repository = in_repository
        self._thumbnailGenerator = in_thumbnailGenerator
        self._keepSelector = DuplicateKeepSelector()
        self._actionsFileStore = ActionsFileStore()

    def buildReport(
        self,
        in_archiveRoot: str,
        in_workspacePath: str,
        in_maxSide: int,
        in_quality: int,
    ) -> None:
        print("duplicates report started")
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
            f"duplicate groups loaded: exact={len(exactDuplicateGroups)}, "
            f"similar={len(similarDuplicateGroups)}"
        )

        workspacePath = Path(in_workspacePath)
        thumbsPath = workspacePath / "thumbs"
        reportsPath = workspacePath / "reports"

        reportsPath.mkdir(
            parents=True,
            exist_ok=True,
        )
        actionsPayload = self._actionsFileStore.loadActions(workspacePath)
        duplicateActions = actionsPayload["duplicates"]["groups"]

        htmlParts: list[str] = []

        htmlParts.append("""
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Photo Cleaner — Exact Duplicates</title>
<style>
body {
    font-family: Arial, sans-serif;
    background: #111;
    color: #eee;
    margin: 24px;
}
.group {
    border: 1px solid #444;
    border-radius: 12px;
    margin-bottom: 24px;
    padding: 16px;
    background: #1b1b1b;
}
.meta {
    color: #aaa;
    font-size: 13px;
    margin-bottom: 12px;
}
.items {
    display: flex;
    flex-wrap: wrap;
    gap: 16px;
}
.item {
    width: 300px;
    border: 1px solid #333;
    border-radius: 10px;
    padding: 12px;
    background: #222;
}
.keep {
    border-color: #2f9e44;
}
.move {
    border-color: #e03131;
}
.badge {
    display: inline-block;
    padding: 4px 8px;
    border-radius: 6px;
    font-weight: bold;
    margin-bottom: 8px;
}
.badgeKeep {
    background: #2f9e44;
}
.badgeMove {
    background: #e03131;
}
img {
    max-width: 256px;
    max-height: 256px;
    display: block;
    margin-bottom: 8px;
    background: #333;
}
.path {
    font-size: 12px;
    word-break: break-all;
    color: #ddd;
}
.rawBox {
    width: 256px;
    height: 160px;
    background: #333;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #aaa;
    margin-bottom: 8px;
}
button {
    background: #2b2b2b;
    color: #eee;
    border: 1px solid #555;
    border-radius: 8px;
    padding: 8px 10px;
    cursor: pointer;
}
button:hover {
    background: #353535;
}
.toolbar {
    margin: 12px 0 18px 0;
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
}
.controls {
    margin-top: 8px;
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
}
.status {
    color: #9ad1ff;
    font-size: 13px;
    margin-top: 8px;
}
</style>
</head>
<body>
<h1>Exact duplicate report</h1>
<div class="toolbar">
  <button onclick="pcConnectActionsFile()">Connect actions.json</button>
  <button onclick="pcSaveActions()">Save actions.json</button>
  <span id="pcActionsInfo" class="meta">actions.json not connected (download fallback)</span>
</div>
""")

        totalGroupsCount = len(exactDuplicateGroups) + len(similarDuplicateGroups)
        htmlParts.append(f"<p>Total duplicate groups: {totalGroupsCount}</p>")
        htmlParts.append(
            f"<p>Exact groups: {len(exactDuplicateGroups)}, "
            f"Similar groups: {len(similarDuplicateGroups)}</p>"
        )

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

        for groupIndex, entry in enumerate(groupedEntries, start=1):
            group = entry["group"]
            groupType = str(entry["groupType"])
            keepItem = self._keepSelector.selectKeepItem(group)
            groupSha256 = str(group[0].get("sha256") or "")
            if groupType == "exact":
                groupKey = f"exact:{groupSha256}"
                groupLabel = "Exact duplicate"
                ruleLabel = "sha256"
            else:
                similarBase = str(Path(str(group[0]["relativePath"])).stem).lower()
                groupKey = f"similar:{similarBase}:{group[0]['mtime']}"
                groupLabel = "Similar duplicate"
                ruleLabel = "name + dimensions + camera + mtime"
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

            duplicateActions[groupKey] = {
                "groupKey": groupKey,
                "groupType": groupType,
                "sha256": groupSha256,
                "size": group[0]["size"],
                "photoIds": photoIds,
                "selectedKeepPhotoId": selectedKeepPhotoId,
                "recommendedKeepPhotoId": str(keepItem["id"]),
                "status": statusValue,
            }

            htmlParts.append(
                f'<div class="group" data-group-key="{html.escape(groupKey)}">'
            )
            htmlParts.append(f"<h2>{groupLabel} group #{groupIndex}</h2>")
            htmlParts.append(
                '<div class="meta">'
                f"match rule: {html.escape(ruleLabel)}<br>"
                f"sha256: {html.escape(groupSha256) if groupSha256 else 'n/a'}<br>"
                f"size: {group[0]['size']}"
                "</div>"
            )
            htmlParts.append(
                '<div class="status">status: '
                f'<span id="dup-status-{html.escape(groupKey)}">'
                f'{html.escape(statusValue)}</span>, '
                'selected KEEP id: '
                f'<span id="dup-selected-{html.escape(groupKey)}">'
                f'{html.escape(selectedKeepPhotoId)}</span>'
                "</div>"
            )
            htmlParts.append(
                '<div class="controls">'
                f'<button onclick="pcDupAcceptRecommended('
                f'\'{html.escape(groupKey)}\', '
                f'\'{html.escape(str(keepItem["id"]))}\')">'
                "Agree with recommended KEEP"
                "</button>"
                f'<button onclick="pcDupApplySelected(\'{html.escape(groupKey)}\')">'
                "Choose selected KEEP"
                "</button>"
                "</div>"
            )
            htmlParts.append('<div class="items">')

            for item in group:
                isKeep = str(item["id"]) == selectedKeepPhotoId
                role = "KEEP" if isKeep else "MOVE"
                cssClass = "keep" if isKeep else "move"
                badgeClass = "badgeKeep" if isKeep else "badgeMove"

                relativePath = item["relativePath"]
                sourcePath = archiveRoot / relativePath

                thumbFileName = f"{item['id']}.jpg"
                thumbPath = thumbsPath / thumbFileName
                thumbRelativePath = f"../thumbs/{thumbFileName}"

                hasThumb = False

                if Path(relativePath).suffix.lower() in {".jpg", ".jpeg"}:
                    if not thumbPath.exists():
                        hasThumb = self._thumbnailGenerator.generateThumbnail(
                            sourcePath,
                            thumbPath,
                            in_maxSide,
                            in_quality,
                        )
                    else:
                        hasThumb = True

                htmlParts.append(f'<div class="item {cssClass}">')
                htmlParts.append(
                    f'<div class="badge {badgeClass}">{role}</div>'
                )
                isChecked = (
                    'checked="checked"'
                    if str(item["id"]) == selectedKeepPhotoId
                    else ""
                )
                htmlParts.append(
                    "<label>"
                    f'<input type="radio" name="dup-{html.escape(groupKey)}" '
                    f'value="{html.escape(str(item["id"]))}" {isChecked}> '
                    "KEEP this file"
                    "</label>"
                )

                if hasThumb:
                    htmlParts.append(
                        f'<img src="{html.escape(thumbRelativePath)}">'
                    )
                else:
                    htmlParts.append('<div class="rawBox">RAW / no preview</div>')

                htmlParts.append(
                    f'<div class="path">{html.escape(relativePath)}</div>'
                )
                htmlParts.append("</div>")

            htmlParts.append("</div>")
            htmlParts.append("</div>")

            if groupIndex % logProgressEvery == 0:
                print(
                    f"duplicates report progress: "
                    f"{groupIndex}/{len(groupedEntries)} groups"
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
            )
        )
        htmlParts.append("""
</body>
</html>
""")

        reportPath = reportsPath / "duplicates.html"

        reportPath.write_text(
            "\n".join(htmlParts),
            encoding="utf-8",
        )

        print(
            f"duplicates report finished: groups={len(groupedEntries)} "
            f"report={reportPath}"
        )
        print(f"report created: {reportPath}")

    def _buildActionsScript(
        self,
        in_actionsPayload: dict[str, Any],
        in_actionsRelativePath: str,
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
const pcActionsState = JSON.parse(`{escapedPayload}`);
let pcActionsFileHandle = null;
let pcHasUnsavedChanges = false;

function pcUpdateInfo(in_text) {{
  const out_node = document.getElementById("pcActionsInfo");
  if (out_node) {{
    out_node.textContent = in_text;
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

function pcDupSetSelection(in_groupKey, in_photoId) {{
  if (!pcActionsState.duplicates || !pcActionsState.duplicates.groups) {{
    return;
  }}
  const out_group = pcActionsState.duplicates.groups[in_groupKey];
  if (!out_group) {{
    return;
  }}
  out_group.selectedKeepPhotoId = in_photoId;
  out_group.status = "confirmed";
  const out_selectedNode = document.getElementById(`dup-selected-${{in_groupKey}}`);
  if (out_selectedNode) {{
    out_selectedNode.textContent = in_photoId;
  }}
  const out_statusNode = document.getElementById(`dup-status-${{in_groupKey}}`);
  if (out_statusNode) {{
    out_statusNode.textContent = "confirmed";
  }}
}}

function pcDupAcceptRecommended(in_groupKey, in_recommendedPhotoId) {{
  pcDupSetSelection(in_groupKey, in_recommendedPhotoId);
  const out_radio = document.querySelector(
    `input[name="dup-${{in_groupKey}}"][value="${{in_recommendedPhotoId}}"]`
  );
  if (out_radio) {{
    out_radio.checked = true;
  }}
  pcHasUnsavedChanges = true;
  pcAutoSaveActions();
}}

function pcDupApplySelected(in_groupKey) {{
  const out_selectedRadio = document.querySelector(
    `input[name="dup-${{in_groupKey}}"]:checked`
  );
  if (!out_selectedRadio) {{
    return;
  }}
  pcDupSetSelection(in_groupKey, out_selectedRadio.value);
  pcHasUnsavedChanges = true;
  pcAutoSaveActions();
}}

pcUpdateInfo(`actions source: ${{pcActionsPath}}`);
</script>
"""
        return ret

class HtmlOrientationReportService:
    def __init__(
        self,
        in_repository: SqlitePhotoRepository,
        in_thumbnailGenerator: ThumbnailGenerator,
    ) -> None:
        self._repository = in_repository
        self._thumbnailGenerator = in_thumbnailGenerator

    def buildReport(
        self,
        in_archiveRoot: str,
        in_workspacePath: str,
        in_maxSide: int,
        in_quality: int,
        in_candidateExtensions: list[str],
        in_neverRotateExtensions: list[str],
        in_excludedPathPrefixes: list[str],
    ) -> None:
        candidates = self._repository.getOrientationCandidates(
            in_candidateExtensions,
            in_neverRotateExtensions,
        )

        archiveRootPath = Path(in_archiveRoot)

        filteredCandidates: list[dict[str, Any]] = []
        for item in candidates:
            absoluteItemPath = archiveRootPath / str(item["relativePath"])
            if pathMatchesExcludedPrefix(
                absoluteItemPath,
                archiveRootPath,
                in_excludedPathPrefixes,
            ):
                continue
            filteredCandidates.append(item)

        candidates = filteredCandidates

        workspacePath = Path(in_workspacePath)
        thumbsPath = workspacePath / "thumbs" / "orientation"
        reportsPath = workspacePath / "reports"

        reportsPath.mkdir(
            parents=True,
            exist_ok=True,
        )

        htmlParts: list[str] = []

        htmlParts.append("""
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Orientation candidates</title>
<style>
body { font-family: Arial, sans-serif; background: #111; color: #eee; margin: 24px; }
.item { border: 1px solid #444; border-radius: 12px; margin-bottom: 24px; padding: 16px; background: #1b1b1b; }
.meta { color: #aaa; font-size: 13px; margin-bottom: 12px; word-break: break-all; }
.variants { display: flex; flex-wrap: wrap; gap: 16px; }
.variant { width: 300px; border: 1px solid #333; border-radius: 10px; padding: 12px; background: #222; }
.badge { display: inline-block; padding: 4px 8px; border-radius: 6px; font-weight: bold; margin-bottom: 8px; background: #444; }
img { max-width: 256px; max-height: 256px; display: block; margin-bottom: 8px; background: #333; }
</style>
</head>
<body>
<h1>Orientation candidates</h1>
""")

        htmlParts.append(f"<p>Total candidates: {len(candidates)}</p>")

        archiveRoot = Path(in_archiveRoot)

        for index, item in enumerate(candidates, start=1):
            relativePath = item["relativePath"]
            sourcePath = archiveRoot / relativePath
            cameraModel = item["cameraModel"] or "unknown"
            exifOrientation = item["exifOrientation"] or "unknown"

            suggestedRotation = int(item["suggestedRotation"])

            variants = [
                ("ORIGINAL", 0),
                (f"SUGGESTED ROTATE {suggestedRotation}", suggestedRotation),
            ]

            htmlParts.append('<div class="item">')
            htmlParts.append(f"<h2>Candidate #{index}</h2>")
            htmlParts.append(
                '<div class="meta">'
                f"path: {html.escape(relativePath)}<br>"
                f"camera: {html.escape(str(cameraModel))}<br>"
                f"exif orientation: {html.escape(str(exifOrientation))}"
                "</div>"
            )
            htmlParts.append('<div class="variants">')

            for title, angle in variants:
                thumbFileName = f"{item['id']}_{angle}.jpg"
                thumbPath = thumbsPath / thumbFileName

                self._buildVariantThumbnail(
                    sourcePath,
                    thumbPath,
                    in_maxSide,
                    in_quality,
                    angle,
                )

                htmlParts.append(
                    '<div class="variant">'
                    f'<div class="badge">{html.escape(title)}</div>'
                    f'<img src="../thumbs/orientation/{html.escape(thumbFileName)}">'
                    "</div>"
                )

            htmlParts.append("</div>")
            htmlParts.append("</div>")

        htmlParts.append("</body></html>")

        reportPath = reportsPath / "orientation.html"

        reportPath.write_text(
            "\n".join(htmlParts),
            encoding="utf-8",
        )

        print(f"orientation report created: {reportPath}")

    def _buildVariantThumbnail(
        self,
        in_sourcePath: Path,
        in_outputPath: Path,
        in_maxSide: int,
        in_quality: int,
        in_angle: int,
    ) -> None:
        if in_outputPath.exists():
            return

        in_outputPath.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        try:
            from PIL import Image, ImageOps

            with Image.open(in_sourcePath) as image:
                image = ImageOps.exif_transpose(image)

                if in_angle != 0:
                    image = image.rotate(
                        -in_angle,
                        expand=True,
                    )

                image.thumbnail((in_maxSide, in_maxSide))
                image.convert("RGB").save(
                    in_outputPath,
                    "JPEG",
                    quality=in_quality,
                    optimize=True,
                )

        except Exception as exception:
            print(f"orientation thumbnail failed: {in_sourcePath} -> {exception}")