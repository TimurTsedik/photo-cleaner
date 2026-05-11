import contextlib
from datetime import datetime
import html
import io
import json
import mimetypes
import traceback
import webbrowser
from pathlib import Path
from threading import Lock, Thread

import falcon
from photo_cleaner.infrastructure.configLoader import (
    ConfigLoader,
)
from photo_cleaner.infrastructure.actionsFileStore import (
    ActionsFileStore,
)
from photo_cleaner.infrastructure.sqlitePhotoRepository import (
    SqlitePhotoRepository,
)
from photo_cleaner.services.duplicateKeepSelector import (
    DuplicateKeepSelector,
)
from photo_cleaner.operations import (
    PhotoCleanerOperations,
)
from waitress import serve
import yaml

WEB_PATH = Path(__file__).resolve().parent / "web"


def _readWebFile(
    in_fileName: str,
) -> str:
    ret = (WEB_PATH / in_fileName).read_text(encoding="utf-8")
    return ret


class ControlPanelState:
    def __init__(
        self,
        in_configPath: str,
    ) -> None:
        self._configPath = Path(in_configPath).resolve()
        self._operations = PhotoCleanerOperations(in_configPath)
        self._config = ConfigLoader().load(str(self._configPath))
        self._workspacePath = Path(self._config["workspace"]["path"]).resolve()
        self._workspacePath.mkdir(
            parents=True,
            exist_ok=True,
        )
        self._actionsFileStore = ActionsFileStore()
        self._lock = Lock()
        self._running = False
        self._logBuffer = io.StringIO()
        self._success = False
        self._finished = True
        self._reportUrl = None
        self._commandName = ""

    def _reloadConfig(
        self,
    ) -> None:
        self._config = ConfigLoader().load(str(self._configPath))
        self._workspacePath = Path(self._config["workspace"]["path"]).resolve()
        self._workspacePath.mkdir(
            parents=True,
            exist_ok=True,
        )

    def _appendLogs(
        self,
        in_text: str,
    ) -> None:
        with self._lock:
            self._logBuffer.write(in_text)

    def _executeCommand(
        self,
        in_command: str,
    ) -> None:
        reportUrl = None
        success = False

        captureBuffer = _LiveLogWriter(self._appendLogs)

        try:
            with contextlib.redirect_stdout(captureBuffer), contextlib.redirect_stderr(captureBuffer):
                if in_command == "scan":
                    self._operations.runScan()
                elif in_command == "duplicates":
                    reportPath = self._operations.runBuildDuplicatesReport()
                    reportUrl = f"/{reportPath}"
                elif in_command == "orientation":
                    reportPath = self._operations.runBuildOrientationCandidatesReport()
                    reportUrl = f"/{reportPath}"
                else:
                    raise ValueError(f"unknown command: {in_command}")
            success = True
        except Exception as exception:
            self._appendLogs(f"command failed: {exception}\n")
            self._appendLogs(traceback.format_exc())
            success = False
            reportUrl = None
        finally:
            with self._lock:
                self._success = success
                self._reportUrl = reportUrl
                self._finished = True
                self._running = False

    def runCommand(
        self,
        in_command: str,
    ) -> dict:
        ret: dict
        workerThread = None

        with self._lock:
            if self._running:
                ret = {
                    "success": False,
                    "started": False,
                    "logs": "another command is already running",
                }
                return ret

            self._running = True
            self._finished = False
            self._success = False
            self._reportUrl = None
            self._commandName = in_command
            self._logBuffer = io.StringIO()
            workerThread = Thread(
                target=self._executeCommand,
                args=(in_command,),
                daemon=True,
            )

        if workerThread is not None:
            workerThread.start()

        ret = {
            "success": True,
            "started": True,
            "logs": "",
        }
        return ret

    def getStatus(
        self,
        in_offset: int,
    ) -> dict:
        with self._lock:
            allLogs = self._logBuffer.getvalue()
            safeOffset = in_offset
            if safeOffset < 0:
                safeOffset = 0
            if safeOffset > len(allLogs):
                safeOffset = len(allLogs)

            logsChunk = allLogs[safeOffset:]
            nextOffset = len(allLogs)
            ret = {
                "running": self._running,
                "finished": self._finished,
                "success": self._success,
                "reportUrl": self._reportUrl,
                "command": self._commandName,
                "logs": logsChunk,
                "nextOffset": nextOffset,
            }
            return ret

    def getWorkspacePath(
        self,
    ) -> Path:
        ret = self._workspacePath
        return ret

    def getRepository(
        self,
    ) -> SqlitePhotoRepository:
        ret = self._buildRepositoryForActions()
        return ret

    def getSummary(
        self,
    ) -> dict:
        repository = SqlitePhotoRepository(str(self._workspacePath / "cleanup.db"))
        repository.initialize()

        orientationBlock = self._config.get("orientation", {})
        excludedPathPrefixes = list(orientationBlock.get("excludedPathPrefixes", []))
        trustedCameraModels = list(orientationBlock.get("trustedCameraModels", []))
        trustedCameraModelsNormalized = {
            str(cameraModel).replace("\x00", "").strip().lower()
            for cameraModel in trustedCameraModels
            if str(cameraModel).strip()
        }

        usedCameraModelCounts = repository.getCameraModelCounts()
        trustedFilesCount = 0
        untrustedFilesCount = 0
        for item in usedCameraModelCounts:
            cameraModel = str(item.get("cameraModel") or "")
            countValue = int(item.get("count") or 0)
            cameraModelNormalized = cameraModel.replace("\x00", "").strip().lower()
            if cameraModelNormalized in trustedCameraModelsNormalized:
                trustedFilesCount += countValue
            else:
                untrustedFilesCount += countValue

        duplicateCandidateIds = repository.getDuplicateCandidatePhotoIds()
        exactDuplicateGroups = repository.getSha256DuplicateGroups()
        similarDuplicateGroups = repository.getSimilarDuplicateGroups(duplicateCandidateIds)

        exactDuplicateFilesCount = 0
        for group in exactDuplicateGroups:
            exactDuplicateFilesCount += len(group)

        similarDuplicateFilesCount = 0
        for group in similarDuplicateGroups:
            similarDuplicateFilesCount += len(group)

        orientationCandidates = repository.getOrientationCandidatesForFaceDetection(
            orientationBlock.get("candidateExtensions", []),
            orientationBlock.get("neverRotateExtensions", []),
            trustedCameraModels,
            repository.getAllDuplicateCandidatePhotoIds(),
        )

        actionsPayload = repository.buildActionsPayloadFromDb()
        orientationActions = actionsPayload.get("orientation", {}).get("items", {})
        duplicateActions = actionsPayload.get("duplicates", {}).get("groups", {})

        orientationAutoCount = 0
        orientationManualCount = 0
        for item in orientationActions.values():
            suggestedAction = str(item.get("suggestedAction", "manual_review"))
            if suggestedAction == "manual_review":
                orientationManualCount += 1
            else:
                orientationAutoCount += 1

        orientationResolvedCount = 0
        orientationPendingCount = 0
        for item in orientationActions.values():
            statusValue = str(item.get("status", "pending"))
            if statusValue == "pending":
                orientationPendingCount += 1
            else:
                orientationResolvedCount += 1

        duplicateConfirmedCount = 0
        duplicatePendingCount = 0
        for item in duplicateActions.values():
            statusValue = str(item.get("status", "pending"))
            if statusValue == "confirmed":
                duplicateConfirmedCount += 1
            else:
                duplicatePendingCount += 1

        dbPath = self._workspacePath / "cleanup.db"
        dbSizeBytes = 0
        dbUpdatedAt = "-"
        if dbPath.exists():
            dbSizeBytes = int(dbPath.stat().st_size)
            dbUpdatedAt = datetime.fromtimestamp(dbPath.stat().st_mtime).isoformat(sep=" ", timespec="seconds")

        ret = {
            "archiveRoot": str(self._config.get("archive", {}).get("root", "")),
            "workspacePath": str(self._workspacePath),
            "excludedPathPrefixes": excludedPathPrefixes,
            "trustedCameraModels": trustedCameraModels,
            "totalFiles": repository.getTotalPhotosCount(),
            "extensionCounts": repository.getExtensionCounts(),
            "usedCameraModelCounts": usedCameraModelCounts,
            "dbSizeBytes": dbSizeBytes,
            "dbUpdatedAt": dbUpdatedAt,
            "exactDuplicateGroupsCount": len(exactDuplicateGroups),
            "exactDuplicateFilesCount": exactDuplicateFilesCount,
            "similarDuplicateGroupsCount": len(similarDuplicateGroups),
            "similarDuplicateFilesCount": similarDuplicateFilesCount,
            "orientationCandidatesCount": len(orientationCandidates),
            "orientationSuggestedAutoCount": orientationAutoCount,
            "orientationSuggestedManualCount": orientationManualCount,
            "duplicateConfirmedCount": duplicateConfirmedCount,
            "duplicatePendingCount": duplicatePendingCount,
            "orientationResolvedCount": orientationResolvedCount,
            "orientationPendingCount": orientationPendingCount,
            "trustedFilesCount": trustedFilesCount,
            "untrustedFilesCount": untrustedFilesCount,
        }
        return ret

    def getEditableConfig(
        self,
    ) -> dict:
        orientationBlock = self._config.get("orientation", {})
        ret = {
            "archiveRoot": str(self._config.get("archive", {}).get("root", "")),
            "trustedCameraModels": list(orientationBlock.get("trustedCameraModels", [])),
            "excludedPathPrefixes": list(orientationBlock.get("excludedPathPrefixes", [])),
        }
        return ret

    def loadActions(
        self,
        in_scope: str,
    ) -> dict:
        repository = self._buildRepositoryForActions()
        scope = in_scope.strip().lower()

        if scope == "orientation":
            ret = {
                "items": repository.getOrientationActions(),
            }
            return ret
        if scope == "duplicates":
            ret = {
                "groups": repository.getDuplicateActions(),
            }
            return ret

        ret = repository.buildActionsPayloadFromDb()
        return ret

    def saveActions(
        self,
        in_scope: str,
        in_payload: dict,
    ) -> dict:
        with self._lock:
            if self._running:
                ret = {
                    "success": False,
                    "message": "command is running, wait for completion",
                }
                return ret

            payloadToSave = in_payload
            if not isinstance(payloadToSave, dict):
                payloadToSave = {}
            repository = self._buildRepositoryForActions()
            scope = in_scope.strip().lower()

            if scope == "orientation":
                photoId = str(payloadToSave.get("photoId", "")).strip()
                if not photoId:
                    ret = {
                        "success": False,
                        "message": "photoId is required for orientation scope",
                    }
                    return ret
                repository.upsertOrientationAction(
                    photoId,
                    payloadToSave,
                )
            elif scope == "duplicates":
                groupKey = str(payloadToSave.get("groupKey", "")).strip()
                if not groupKey:
                    ret = {
                        "success": False,
                        "message": "groupKey is required for duplicates scope",
                    }
                    return ret
                repository.upsertDuplicateAction(
                    groupKey,
                    payloadToSave,
                )
            else:
                orientationItems = payloadToSave.get("orientation", {}).get("items", {})
                duplicateGroups = payloadToSave.get("duplicates", {}).get("groups", {})
                if isinstance(orientationItems, dict):
                    for photoId, item in orientationItems.items():
                        if isinstance(item, dict):
                            repository.upsertOrientationAction(
                                str(photoId),
                                item,
                            )
                if isinstance(duplicateGroups, dict):
                    for groupKey, item in duplicateGroups.items():
                        if isinstance(item, dict):
                            repository.upsertDuplicateAction(
                                str(groupKey),
                                item,
                            )

            self._syncActionsFileFromDb(repository)

            ret = {
                "success": True,
                "message": "actions saved in database",
            }
            return ret

    def _buildRepositoryForActions(
        self,
    ) -> SqlitePhotoRepository:
        dbPath = self._workspacePath / "cleanup.db"
        repository = SqlitePhotoRepository(str(dbPath))
        repository.initialize()
        ret = repository
        return ret

    def _syncActionsFileFromDb(
        self,
        in_repository: SqlitePhotoRepository,
    ) -> None:
        payload = in_repository.buildActionsPayloadFromDb()
        self._actionsFileStore.saveActions(
            self._workspacePath,
            payload,
        )

    def updateConfig(
        self,
        in_payload: dict,
    ) -> dict:
        with self._lock:
            if self._running:
                ret = {
                    "success": False,
                    "message": "command is running, wait for completion",
                }
                return ret

            configToSave = ConfigLoader().load(str(self._configPath))
            archiveBlock = configToSave.setdefault("archive", {})
            orientationBlock = configToSave.setdefault("orientation", {})

            archiveRoot = str(in_payload.get("archiveRoot", "")).strip()
            trustedCameraModelsRaw = in_payload.get("trustedCameraModels", [])
            excludedPathPrefixesRaw = in_payload.get("excludedPathPrefixes", [])

            trustedCameraModels: list[str] = []
            for item in trustedCameraModelsRaw:
                text = str(item).strip()
                if text:
                    trustedCameraModels.append(text)

            excludedPathPrefixes: list[str] = []
            for item in excludedPathPrefixesRaw:
                text = str(item).strip()
                if text:
                    excludedPathPrefixes.append(text)

            if archiveRoot:
                archiveBlock["root"] = archiveRoot
            orientationBlock["trustedCameraModels"] = trustedCameraModels
            orientationBlock["excludedPathPrefixes"] = excludedPathPrefixes

            yamlText = yaml.safe_dump(
                configToSave,
                allow_unicode=True,
                sort_keys=False,
            )
            self._configPath.write_text(yamlText, encoding="utf-8")
            self._reloadConfig()

            ret = {
                "success": True,
                "message": "config.yaml updated",
                "config": self.getEditableConfig(),
            }
            return ret


class _IndexResource:
    def __init__(
        self,
    ) -> None:
        self._htmlText = _readWebFile("controlPanel.html")

    def on_get(
        self,
        in_req: falcon.Request,
        out_resp: falcon.Response,
    ) -> None:
        out_resp.content_type = "text/html; charset=utf-8"
        out_resp.text = self._htmlText


class _RunCommandResource:
    def __init__(
        self,
        in_state: ControlPanelState,
    ) -> None:
        self._state = in_state

    def on_post(
        self,
        in_req: falcon.Request,
        out_resp: falcon.Response,
    ) -> None:
        payload = in_req.media
        if not isinstance(payload, dict):
            payload = {}
        commandName = str(payload.get("command", "")).strip()
        out_resp.media = self._state.runCommand(commandName)


class _StatusResource:
    def __init__(
        self,
        in_state: ControlPanelState,
    ) -> None:
        self._state = in_state

    def on_get(
        self,
        in_req: falcon.Request,
        out_resp: falcon.Response,
    ) -> None:
        offsetValue = in_req.get_param_as_int("offset")
        if offsetValue is None:
            offsetValue = 0
        out_resp.media = self._state.getStatus(offsetValue)


class _SummaryResource:
    def __init__(
        self,
        in_state: ControlPanelState,
    ) -> None:
        self._state = in_state

    def on_get(
        self,
        in_req: falcon.Request,
        out_resp: falcon.Response,
    ) -> None:
        out_resp.set_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        out_resp.set_header("Pragma", "no-cache")
        out_resp.set_header("Expires", "0")
        out_resp.media = self._state.getSummary()


class _ConfigResource:
    def __init__(
        self,
        in_state: ControlPanelState,
    ) -> None:
        self._state = in_state

    def on_get(
        self,
        in_req: falcon.Request,
        out_resp: falcon.Response,
    ) -> None:
        out_resp.media = self._state.getEditableConfig()

    def on_post(
        self,
        in_req: falcon.Request,
        out_resp: falcon.Response,
    ) -> None:
        payload = in_req.media
        if not isinstance(payload, dict):
            payload = {}
        out_resp.media = self._state.updateConfig(payload)


class _ActionsResource:
    def __init__(
        self,
        in_state: ControlPanelState,
    ) -> None:
        self._state = in_state

    def on_get(
        self,
        in_req: falcon.Request,
        out_resp: falcon.Response,
    ) -> None:
        scope = in_req.get_param("scope") or "all"
        out_resp.media = self._state.loadActions(scope)

    def on_post(
        self,
        in_req: falcon.Request,
        out_resp: falcon.Response,
    ) -> None:
        scope = in_req.get_param("scope") or "all"
        payload = in_req.media
        if not isinstance(payload, dict):
            payload = {}
        out_resp.media = self._state.saveActions(scope, payload)


class _DynamicDuplicatesReportResource:
    def __init__(
        self,
        in_state: ControlPanelState,
    ) -> None:
        self._state = in_state
        self._keepSelector = DuplicateKeepSelector()

    def on_get(
        self,
        in_req: falcon.Request,
        out_resp: falcon.Response,
    ) -> None:
        repository = self._state.getRepository()
        exactDuplicateGroups = repository.getSha256DuplicateGroups()
        exactDuplicateIds: set[str] = set()
        for group in exactDuplicateGroups:
            for item in group:
                exactDuplicateIds.add(str(item["id"]))
        similarDuplicateGroups = repository.getSimilarDuplicateGroups(
            exactDuplicateIds,
        )
        duplicateActions = repository.getDuplicateActions()
        actionsPayload = repository.buildActionsPayloadFromDb()

        groupedEntries: list[dict] = []
        for group in exactDuplicateGroups:
            groupedEntries.append({
                "groupType": "exact",
                "group": group,
            })
        for group in similarDuplicateGroups:
            groupedEntries.append({
                "groupType": "similar",
                "group": group,
            })

        cardsParts: list[str] = []
        for groupIndex, entry in enumerate(groupedEntries, start=1):
            groupType = str(entry["groupType"])
            group = entry["group"]
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
            statusValue = str(existingGroupAction.get("status", "pending"))
            if groupType == "exact":
                groupLabel = "Exact duplicate"
                ruleLabel = "sha256"
            else:
                groupLabel = "Similar duplicate"
                ruleLabel = "name + dimensions + camera + mtime"

            cardsParts.append(
                f'<div class="card group" data-group-key="{html.escape(groupKey)}">'
            )
            cardsParts.append(f"<h2>{groupLabel} group #{groupIndex}</h2>")
            cardsParts.append(
                '<div class="meta">'
                f"match rule: {html.escape(ruleLabel)}<br>"
                f"sha256: {html.escape(groupSha256) if groupSha256 else 'n/a'}<br>"
                f"size: {int(group[0]['size'])}"
                "</div>"
            )
            cardsParts.append(
                '<div class="status">status: '
                f'<span id="dup-status-{html.escape(groupKey)}">'
                f'{html.escape(statusValue)}</span>, '
                'selected KEEP id: '
                f'<span id="dup-selected-{html.escape(groupKey)}">'
                f'{html.escape(selectedKeepPhotoId)}</span>'
                "</div>"
            )
            cardsParts.append(
                '<div class="controls">'
                f'<button onclick="pcDupAcceptRecommended('
                f'\'{html.escape(groupKey)}\', '
                f'\'{html.escape(str(keepItem["id"]))}\')">'
                "Agree with recommended KEEP"
                "</button>"
                "</div>"
            )
            cardsParts.append('<div class="items">')

            for item in group:
                photoId = str(item["id"])
                isKeep = photoId == selectedKeepPhotoId
                role = "KEEP" if isKeep else "MOVE"
                cssClass = "keep" if isKeep else "move"
                badgeClass = "badgeKeep" if isKeep else "badgeMove"
                relativePath = str(item["relativePath"])
                isChecked = (
                    'checked="checked"'
                    if photoId == selectedKeepPhotoId
                    else ""
                )

                cardsParts.append(f'<div class="item {cssClass}">')
                cardsParts.append(f'<div class="badge {badgeClass}">{role}</div>')
                cardsParts.append(
                    "<label>"
                    f'<input type="radio" name="dup-{html.escape(groupKey)}" '
                    f'value="{html.escape(photoId)}" '
                    f'onchange="pcDupSetSelection(\'{html.escape(groupKey)}\', '
                    f'\'{html.escape(photoId)}\', false)" '
                    f'{isChecked}> '
                    "KEEP this file"
                    "</label>"
                )

                thumbPath = self._state.getWorkspacePath() / "thumbs" / f"{photoId}.jpg"
                if thumbPath.exists():
                    cardsParts.append(
                        f'<img src="/workspace/thumbs/{html.escape(photoId)}.jpg">'
                    )
                else:
                    cardsParts.append('<div class="rawBox">RAW / no preview</div>')

                cardsParts.append(
                    f'<div class="path">{html.escape(relativePath)}</div>'
                )
                cardsParts.append("</div>")

            cardsParts.append("</div>")
            cardsParts.append("</div>")

        summaryHtml = (
            f"<p>Total duplicate groups: {len(groupedEntries)}</p>"
            f"<p>Exact groups: {len(exactDuplicateGroups)}, "
            f"Similar groups: {len(similarDuplicateGroups)}</p>"
        )
        reportHtml = (
            "<!doctype html>"
            "<html><head><meta charset=\"utf-8\">"
            "<title>Exact duplicate report</title>"
            "<link rel=\"stylesheet\" href=\"/assets/reports/reportCommon.css\">"
            "</head><body>"
            "<h1>Exact duplicate report</h1>"
            "<div class=\"subtitle\">Exact + similar duplicate groups</div>"
            "<div class=\"toolbar\">"
            "<button onclick=\"pcDupApplyAllRecommended()\">"
            "Согласиться со всеми рекомендациями"
            "</button>"
            "<span id=\"pcActionsInfo\" class=\"meta\">Автосохранение включено</span>"
            "</div>"
            f"{summaryHtml}"
            f"{''.join(cardsParts)}"
            f"<script id=\"pc-actions-state\" type=\"application/json\">{self._escapeJsonForHtml(actionsPayload)}</script>"
            "<div id=\"pc-report-config\" data-actions-path=\"/api/actions?scope=duplicates\"></div>"
            "<script src=\"/assets/reports/duplicatesReport.js\"></script>"
            "</body></html>"
        )

        out_resp.content_type = "text/html; charset=utf-8"
        out_resp.text = reportHtml

    def _buildGroupKey(
        self,
        in_groupType: str,
        in_group: list[dict],
    ) -> str:
        ret = ""
        if in_groupType == "exact":
            groupSha256 = str(in_group[0].get("sha256") or "")
            ret = f"exact:{groupSha256}"
        else:
            similarBase = str(Path(str(in_group[0]["relativePath"])).stem).lower()
            ret = f"similar:{similarBase}:{in_group[0]['mtime']}"
        return ret

    def _escapeJsonForHtml(
        self,
        in_payload: dict,
    ) -> str:
        payloadText = json.dumps(in_payload, ensure_ascii=False)
        ret = payloadText.replace("</", "<\\/")
        return ret


class _DynamicOrientationReportResource:
    def __init__(
        self,
        in_state: ControlPanelState,
    ) -> None:
        self._state = in_state

    def on_get(
        self,
        in_req: falcon.Request,
        out_resp: falcon.Response,
    ) -> None:
        repository = self._state.getRepository()
        actionsPayload = repository.buildActionsPayloadFromDb()
        orientationItemsMap = repository.getOrientationActions()
        orientationItems = list(orientationItemsMap.values())
        orientationItems.sort(
            key=lambda in_item: str(in_item.get("relativePath", "")).lower()
        )

        cardsParts: list[str] = []
        for index, item in enumerate(orientationItems, start=1):
            photoId = str(item.get("photoId", ""))
            if not photoId:
                continue
            relativePath = str(item.get("relativePath", ""))
            cameraModel = str(item.get("cameraModel") or "unknown")
            suggestedAction = str(item.get("suggestedAction", "manual_review"))
            selectedAction = str(item.get("selectedAction", suggestedAction))
            selectedStatus = str(item.get("status", "pending"))
            decisionReason = str(item.get("decisionReason", "unknown"))
            confidenceValue = float(item.get("confidence", 0.0))
            marginValue = float(item.get("margin", 0.0))
            suggestedRotation = item.get("suggestedRotation")
            selectedRotation = item.get("selectedRotation")
            thumbsSubdir = str(item.get("thumbsSubdir", "orientation_ml"))

            if selectedRotation is not None:
                try:
                    selectedRotation = int(selectedRotation)
                except (TypeError, ValueError):
                    selectedRotation = None
            if suggestedRotation is not None:
                try:
                    suggestedRotation = int(suggestedRotation)
                except (TypeError, ValueError):
                    suggestedRotation = None

            selectedRotationDisplay = (
                str(selectedRotation)
                if selectedRotation is not None
                else "none"
            )
            suggestedRotationDisplay = (
                str(suggestedRotation)
                if suggestedRotation is not None
                else "none"
            )
            suggestedRotationJs = (
                "null"
                if suggestedRotation is None
                else str(int(suggestedRotation))
            )
            suggestedActionJs = (
                suggestedAction
                .replace("\\", "\\\\")
                .replace("'", "\\'")
            )

            previewTitle = "SELECTED ORIGINAL"
            previewPath = f"/workspace/thumbs/{html.escape(thumbsSubdir)}/{html.escape(photoId)}_original.jpg"
            if selectedRotation == 90:
                previewTitle = "SELECTED ROTATE 90"
                previewPath = f"/workspace/thumbs/{html.escape(thumbsSubdir)}/{html.escape(photoId)}_rotate90.jpg"
            elif selectedRotation == 270:
                previewTitle = "SELECTED ROTATE 270"
                previewPath = f"/workspace/thumbs/{html.escape(thumbsSubdir)}/{html.escape(photoId)}_rotate270.jpg"

            cardsParts.append(
                f'<div class="card orientation-card" data-photo-id="{html.escape(photoId)}">'
            )
            cardsParts.append(f"<h2>Candidate #{index}</h2>")
            cardsParts.append(f'<div class="path">{html.escape(relativePath)}</div>')
            cardsParts.append(f'<p>camera: {html.escape(cameraModel)}</p>')
            cardsParts.append(
                f'<p class="suggest">ACTION: {html.escape(suggestedAction)}</p>'
            )
            cardsParts.append(
                f'<p class="meta">suggested rotation (apply): {html.escape(suggestedRotationDisplay)}</p>'
            )
            cardsParts.append(
                f'<p class="meta">selected rotation: '
                f'<span id="orientation-selected-{html.escape(photoId)}">'
                f'{html.escape(selectedRotationDisplay)}</span></p>'
            )
            cardsParts.append(
                f'<p class="meta">selected action: '
                f'<span id="orientation-action-{html.escape(photoId)}">'
                f'{html.escape(selectedAction)}</span></p>'
            )
            cardsParts.append(
                f'<p class="status">status: '
                f'<span id="orientation-status-{html.escape(photoId)}">'
                f'{html.escape(selectedStatus)}</span></p>'
            )
            cardsParts.append(
                "<p>"
                f"confidence: {confidenceValue:.3f}<br>"
                f"margin: {marginValue:.3f}<br>"
                f"decision: {html.escape(decisionReason)}"
                "</p>"
            )
            cardsParts.append(f'<div class="meta">id: {html.escape(photoId)}</div>')
            cardsParts.append('<div class="controls">')
            cardsParts.append(
                "<button "
                f'onclick="pcOrientationApplySuggested(\'{html.escape(photoId)}\', '
                f"{suggestedRotationJs}, "
                f"'{suggestedActionJs}')"
                '">Accept suggested</button>'
            )
            cardsParts.append(
                "<button "
                f'onclick="pcOrientationSet(\'{html.escape(photoId)}\', 90, '
                "'rotate90')"
                '">Set 90</button>'
            )
            cardsParts.append(
                "<button "
                f'onclick="pcOrientationSet(\'{html.escape(photoId)}\', 270, '
                "'rotate270')"
                '">Set 270</button>'
            )
            cardsParts.append(
                "<button "
                f'onclick="pcOrientationSet(\'{html.escape(photoId)}\', null, '
                "'manual_review')"
                '">Manual review</button>'
            )
            cardsParts.append("</div>")
            cardsParts.append('<div class="variants">')
            cardsParts.append(
                '<div class="variant">'
                '<div class="badge">ORIGINAL</div>'
                f'<img src="/workspace/thumbs/{html.escape(thumbsSubdir)}/{html.escape(photoId)}_original.jpg">'
                "</div>"
            )
            cardsParts.append(
                '<div class="variant">'
                f'<div class="badge" id="orientation-preview-title-{html.escape(photoId)}">{html.escape(previewTitle)}</div>'
                f'<img id="orientation-preview-img-{html.escape(photoId)}" src="{previewPath}">'
                "</div>"
            )
            cardsParts.append("</div>")
            cardsParts.append("</div>")

        summaryHtml = f"<p>Total candidates in DB: {len(orientationItems)}</p>"
        reportHtml = (
            "<!doctype html>"
            "<html><head><meta charset=\"utf-8\">"
            "<title>ML orientation report</title>"
            "<link rel=\"stylesheet\" href=\"/assets/reports/reportCommon.css\">"
            "</head><body>"
            "<h1>ML orientation report</h1>"
            "<div class=\"subtitle\">ML suggestions for rotation candidates</div>"
            "<div class=\"toolbar\">"
            "<span id=\"pcActionsInfo\" class=\"meta\">Автосохранение включено</span>"
            "</div>"
            f"{summaryHtml}"
            f"{''.join(cardsParts)}"
            f"<script id=\"pc-actions-state\" type=\"application/json\">{self._escapeJsonForHtml(actionsPayload)}</script>"
            "<div id=\"pc-report-config\" "
            "data-actions-path=\"/api/actions?scope=orientation\" "
            "data-thumbs-subdir=\"orientation_ml\" "
            "data-thumbs-base-path=\"/workspace/thumbs\"></div>"
            "<script src=\"/assets/reports/orientationReport.js\"></script>"
            "</body></html>"
        )

        out_resp.content_type = "text/html; charset=utf-8"
        out_resp.text = reportHtml

    def _escapeJsonForHtml(
        self,
        in_payload: dict,
    ) -> str:
        payloadText = json.dumps(in_payload, ensure_ascii=False)
        ret = payloadText.replace("</", "<\\/")
        return ret


class _WorkspaceFileResource:
    def __init__(
        self,
        in_state: ControlPanelState,
    ) -> None:
        self._state = in_state

    def on_get(
        self,
        in_req: falcon.Request,
        out_resp: falcon.Response,
        in_relativePath: str,
    ) -> None:
        targetPath = self._state.getWorkspacePath() / in_relativePath
        resolvedPath = targetPath.resolve()
        workspacePath = self._state.getWorkspacePath()

        try:
            resolvedPath.relative_to(workspacePath)
        except ValueError as exception:
            raise falcon.HTTPForbidden(
                title="Forbidden",
                description="Requested path is outside workspace",
            ) from exception

        if not resolvedPath.is_file():
            raise falcon.HTTPNotFound()

        contentType = mimetypes.guess_type(str(resolvedPath))[0] or "application/octet-stream"
        out_resp.content_type = contentType
        out_resp.data = resolvedPath.read_bytes()


class _StaticAssetResource:
    def on_get(
        self,
        in_req: falcon.Request,
        out_resp: falcon.Response,
        in_assetPath: str,
    ) -> None:
        assetPath = (WEB_PATH / in_assetPath).resolve()
        try:
            assetPath.relative_to(WEB_PATH)
        except ValueError as exception:
            raise falcon.HTTPForbidden(
                title="Forbidden",
                description="Requested asset is outside web root",
            ) from exception

        if not assetPath.is_file():
            raise falcon.HTTPNotFound()

        out_resp.content_type = mimetypes.guess_type(str(assetPath))[0] or "application/octet-stream"
        out_resp.data = assetPath.read_bytes()


class _HealthResource:
    def on_get(
        self,
        in_req: falcon.Request,
        out_resp: falcon.Response,
    ) -> None:
        out_resp.media = {
            "service": "photo-cleaner-panel",
            "status": "ok",
        }


def _buildIndexHtml() -> str:
    ret = _readWebFile("controlPanel.html")
    return ret


def runControlPanelServer(
    in_configPath: str,
    in_host: str = "127.0.0.1",
    in_port: int = 8765,
) -> None:
    state = ControlPanelState(in_configPath)
    app = falcon.App()
    app.add_route("/", _IndexResource())
    app.add_route("/api/run", _RunCommandResource(state))
    app.add_route("/api/status", _StatusResource(state))
    app.add_route("/api/summary", _SummaryResource(state))
    app.add_route("/api/config", _ConfigResource(state))
    app.add_route("/api/actions", _ActionsResource(state))
    app.add_route("/api/health", _HealthResource())
    app.add_route("/reports/duplicates", _DynamicDuplicatesReportResource(state))
    app.add_route("/reports/orientation", _DynamicOrientationReportResource(state))
    app.add_route("/assets/{in_assetPath:path}", _StaticAssetResource())
    app.add_route("/workspace/{in_relativePath:path}", _WorkspaceFileResource(state))

    controlPanelUrl = f"http://{in_host}:{in_port}"
    print(f"control panel started: {controlPanelUrl}")
    print("press Ctrl+C to stop")
    webbrowser.open(controlPanelUrl, new=2)
    try:
        serve(
            app,
            host=in_host,
            port=in_port,
            threads=8,
            _quiet=True,
        )
    except OSError as exception:
        raise RuntimeError(
            f"failed to bind control panel port {in_host}:{in_port}. "
            "stop existing process and retry."
        ) from exception


class _LiveLogWriter:
    def __init__(
        self,
        in_appendFn,
    ) -> None:
        self._appendFn = in_appendFn

    def write(
        self,
        in_text: str,
    ) -> int:
        if in_text:
            self._appendFn(in_text)
        ret = len(in_text)
        return ret

    def flush(
        self,
    ) -> None:
        return
