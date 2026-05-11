import json
import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

from photo_cleaner.infrastructure.sqlitePhotoRepository import (
    SqlitePhotoRepository,
)


class ApplyActionsService:
    def __init__(
        self,
        in_repository: SqlitePhotoRepository,
    ) -> None:
        self._repository = in_repository

    def apply(
        self,
        in_archiveRoot: str,
        in_workspacePath: str,
        in_duplicateTrashDir: str,
        in_dryRun: bool,
    ) -> dict[str, Any]:
        ret: dict[str, Any] = {
            "dryRun": bool(in_dryRun),
            "runId": None,
            "duplicatePlanned": 0,
            "duplicateApplied": 0,
            "duplicateSkipped": 0,
            "orientationPlanned": 0,
            "orientationApplied": 0,
            "orientationSkipped": 0,
            "errors": [],
        }

        archiveRoot = Path(in_archiveRoot)
        workspacePath = Path(in_workspacePath)
        journalPath = self._resolveJournalPath(workspacePath)
        backupRoot = self._resolveBackupRoot(workspacePath)
        duplicateTrashRoot = self._resolveDuplicateTrashRoot(
            archiveRoot,
            in_duplicateTrashDir,
        )
        runId = self._buildRunId("apply")
        ret["runId"] = runId

        if not in_dryRun:
            self._appendJournalRecord(
                journalPath,
                {
                    "recordType": "runStart",
                    "runId": runId,
                    "dryRun": False,
                    "startedAt": self._utcNowIso(),
                },
            )

        duplicateResult = self._applyDuplicateActions(
            archiveRoot,
            duplicateTrashRoot,
            in_dryRun,
            journalPath,
            runId,
        )
        orientationResult = self._applyOrientationActions(
            archiveRoot,
            backupRoot,
            in_dryRun,
            journalPath,
            runId,
        )

        ret["duplicatePlanned"] = int(duplicateResult["planned"])
        ret["duplicateApplied"] = int(duplicateResult["applied"])
        ret["duplicateSkipped"] = int(duplicateResult["skipped"])
        ret["orientationPlanned"] = int(orientationResult["planned"])
        ret["orientationApplied"] = int(orientationResult["applied"])
        ret["orientationSkipped"] = int(orientationResult["skipped"])
        ret["errors"] = list(duplicateResult["errors"]) + list(orientationResult["errors"])

        if not in_dryRun:
            self._appendJournalRecord(
                journalPath,
                {
                    "recordType": "runEnd",
                    "runId": runId,
                    "dryRun": False,
                    "finishedAt": self._utcNowIso(),
                    "result": {
                        "duplicateApplied": ret["duplicateApplied"],
                        "orientationApplied": ret["orientationApplied"],
                        "errors": len(ret["errors"]),
                    },
                },
            )

        return ret

    def undoLastApply(
        self,
        in_archiveRoot: str,
        in_workspacePath: str,
        in_dryRun: bool,
    ) -> dict[str, Any]:
        ret: dict[str, Any] = {
            "dryRun": bool(in_dryRun),
            "targetRunId": None,
            "planned": 0,
            "applied": 0,
            "skipped": 0,
            "errors": [],
        }

        archiveRoot = Path(in_archiveRoot)
        workspacePath = Path(in_workspacePath)
        journalPath = self._resolveJournalPath(workspacePath)
        records = self._loadJournalRecords(journalPath)
        targetRunId = self._findLastReversibleRunId(records)
        ret["targetRunId"] = targetRunId

        if targetRunId is None:
            ret["errors"].append("no applied runs found for undo")
            return ret

        undoRunId = self._buildRunId("undo")
        if not in_dryRun:
            self._appendJournalRecord(
                journalPath,
                {
                    "recordType": "undoStart",
                    "undoRunId": undoRunId,
                    "targetRunId": targetRunId,
                    "dryRun": False,
                    "startedAt": self._utcNowIso(),
                },
            )

        runOperations = [
            record
            for record in records
            if str(record.get("recordType")) == "operation"
            and str(record.get("runId")) == targetRunId
        ]
        runOperations.reverse()

        for operationRecord in runOperations:
            ret["planned"] = int(ret["planned"]) + 1
            operationType = str(operationRecord.get("operationType", ""))

            if operationType == "moveDuplicate":
                sourcePath = Path(str(operationRecord.get("sourcePath", "")))
                destinationPath = Path(str(operationRecord.get("destinationPath", "")))
                if in_dryRun:
                    print(f"dry-run undo move duplicate: {destinationPath} -> {sourcePath}")
                    ret["applied"] = int(ret["applied"]) + 1
                    continue
                try:
                    if not destinationPath.exists():
                        raise FileNotFoundError(f"missing moved file: {destinationPath}")
                    sourcePath.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(destinationPath), str(sourcePath))
                    print(f"undo moved duplicate: {destinationPath} -> {sourcePath}")
                    ret["applied"] = int(ret["applied"]) + 1
                except Exception as exception:
                    ret["skipped"] = int(ret["skipped"]) + 1
                    ret["errors"].append(f"failed to undo duplicate move: {exception}")
            elif operationType == "rotatePhoto":
                sourcePath = Path(str(operationRecord.get("sourcePath", "")))
                backupPath = Path(str(operationRecord.get("backupPath", "")))
                if in_dryRun:
                    print(f"dry-run undo rotate photo: {sourcePath} <- {backupPath}")
                    ret["applied"] = int(ret["applied"]) + 1
                    continue
                try:
                    if not backupPath.exists():
                        raise FileNotFoundError(f"missing rotation backup: {backupPath}")
                    sourcePath.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(backupPath, sourcePath)
                    print(f"undo rotated photo: {sourcePath} <- {backupPath}")
                    ret["applied"] = int(ret["applied"]) + 1
                except Exception as exception:
                    ret["skipped"] = int(ret["skipped"]) + 1
                    ret["errors"].append(f"failed to undo photo rotation: {exception}")
            else:
                ret["skipped"] = int(ret["skipped"]) + 1
                ret["errors"].append(f"unknown operation type in journal: {operationType}")

        if not in_dryRun:
            self._appendJournalRecord(
                journalPath,
                {
                    "recordType": "undoEnd",
                    "undoRunId": undoRunId,
                    "targetRunId": targetRunId,
                    "dryRun": False,
                    "finishedAt": self._utcNowIso(),
                    "result": {
                        "applied": ret["applied"],
                        "skipped": ret["skipped"],
                        "errors": len(ret["errors"]),
                    },
                },
            )

        _ = archiveRoot
        return ret

    def _applyDuplicateActions(
        self,
        in_archiveRoot: Path,
        in_duplicateTrashRoot: Path,
        in_dryRun: bool,
        in_journalPath: Path,
        in_runId: str,
    ) -> dict[str, Any]:
        ret: dict[str, Any] = {
            "planned": 0,
            "applied": 0,
            "skipped": 0,
            "errors": [],
        }

        duplicateActions = self._repository.getDuplicateActions()
        movePhotoIds: list[str] = []
        for groupPayload in duplicateActions.values():
            statusValue = str(groupPayload.get("status", "")).strip().lower()
            if statusValue != "confirmed":
                continue

            selectedKeepPhotoId = str(groupPayload.get("selectedKeepPhotoId", "")).strip()
            photoIds = groupPayload.get("photoIds", [])
            if not isinstance(photoIds, list):
                continue

            for photoId in photoIds:
                photoIdStr = str(photoId).strip()
                if not photoIdStr:
                    continue
                if photoIdStr == selectedKeepPhotoId:
                    continue
                movePhotoIds.append(photoIdStr)

        uniqueMovePhotoIds = sorted(set(movePhotoIds))
        idToRelativePath = self._repository.getPhotoPathsByIds(uniqueMovePhotoIds)

        for photoId in uniqueMovePhotoIds:
            relativePath = idToRelativePath.get(photoId)
            if relativePath is None:
                ret["skipped"] = int(ret["skipped"]) + 1
                ret["errors"].append(f"duplicate photo id is missing in photos table: {photoId}")
                continue

            sourcePath = in_archiveRoot / relativePath
            destinationPath = in_duplicateTrashRoot / relativePath
            destinationPath = self._buildUniqueDestinationPath(destinationPath)
            ret["planned"] = int(ret["planned"]) + 1

            if not sourcePath.exists():
                ret["skipped"] = int(ret["skipped"]) + 1
                ret["errors"].append(f"duplicate source is missing: {relativePath}")
                continue

            if in_dryRun:
                print(f"dry-run move duplicate: {sourcePath} -> {destinationPath}")
                ret["applied"] = int(ret["applied"]) + 1
                continue

            try:
                destinationPath.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(sourcePath), str(destinationPath))
                self._appendJournalRecord(
                    in_journalPath,
                    {
                        "recordType": "operation",
                        "runId": in_runId,
                        "operationType": "moveDuplicate",
                        "photoId": photoId,
                        "sourcePath": str(sourcePath),
                        "destinationPath": str(destinationPath),
                        "at": self._utcNowIso(),
                    },
                )
                print(f"moved duplicate: {sourcePath} -> {destinationPath}")
                ret["applied"] = int(ret["applied"]) + 1
            except Exception as exception:
                ret["skipped"] = int(ret["skipped"]) + 1
                ret["errors"].append(
                    f"failed to move duplicate {relativePath}: {exception}"
                )

        return ret

    def _applyOrientationActions(
        self,
        in_archiveRoot: Path,
        in_backupRoot: Path,
        in_dryRun: bool,
        in_journalPath: Path,
        in_runId: str,
    ) -> dict[str, Any]:
        ret: dict[str, Any] = {
            "planned": 0,
            "applied": 0,
            "skipped": 0,
            "errors": [],
        }

        orientationActions = self._repository.getOrientationActions()
        for actionPayload in orientationActions.values():
            statusValue = str(actionPayload.get("status", "")).strip().lower()
            if statusValue != "confirmed":
                continue

            selectedRotationRaw = actionPayload.get("selectedRotation")
            try:
                selectedRotation = int(selectedRotationRaw)
            except (TypeError, ValueError):
                selectedRotation = None

            if selectedRotation not in {90, 270}:
                continue

            relativePath = str(actionPayload.get("relativePath", "")).strip()
            if not relativePath:
                ret["skipped"] = int(ret["skipped"]) + 1
                ret["errors"].append("orientation action does not have relativePath")
                continue

            sourcePath = in_archiveRoot / relativePath
            ret["planned"] = int(ret["planned"]) + 1

            if not sourcePath.exists():
                ret["skipped"] = int(ret["skipped"]) + 1
                ret["errors"].append(f"orientation source is missing: {relativePath}")
                continue

            if sourcePath.suffix.lower() not in {".jpg", ".jpeg"}:
                ret["skipped"] = int(ret["skipped"]) + 1
                ret["errors"].append(f"orientation apply supports only jpeg: {relativePath}")
                continue

            backupPath = in_backupRoot / in_runId / relativePath

            if in_dryRun:
                print(
                    "dry-run rotate photo: "
                    f"path={sourcePath}, rotation={selectedRotation}, backup={backupPath}"
                )
                ret["applied"] = int(ret["applied"]) + 1
                continue

            try:
                backupPath.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(sourcePath, backupPath)
                self._rotateJpeg(sourcePath, selectedRotation)
                self._appendJournalRecord(
                    in_journalPath,
                    {
                        "recordType": "operation",
                        "runId": in_runId,
                        "operationType": "rotatePhoto",
                        "sourcePath": str(sourcePath),
                        "backupPath": str(backupPath),
                        "rotation": selectedRotation,
                        "at": self._utcNowIso(),
                    },
                )
                print(
                    "rotated photo: "
                    f"path={sourcePath}, rotation={selectedRotation}"
                )
                ret["applied"] = int(ret["applied"]) + 1
            except Exception as exception:
                ret["skipped"] = int(ret["skipped"]) + 1
                ret["errors"].append(
                    f"failed to rotate photo {relativePath}: {exception}"
                )

        return ret

    def _rotateJpeg(
        self,
        in_sourcePath: Path,
        in_rotation: int,
    ) -> None:
        with Image.open(in_sourcePath) as imageRaw:
            imageOut = ImageOps.exif_transpose(imageRaw)
            imageOut = imageOut.convert("RGB")
            if in_rotation == 90:
                imageOut = imageOut.transpose(Image.Transpose.ROTATE_270)
            elif in_rotation == 270:
                imageOut = imageOut.transpose(Image.Transpose.ROTATE_90)
            imageOut.save(
                in_sourcePath,
                "JPEG",
                quality=95,
                optimize=True,
            )

    def _resolveDuplicateTrashRoot(
        self,
        in_archiveRoot: Path,
        in_duplicateTrashDir: str,
    ) -> Path:
        duplicateTrashDir = str(in_duplicateTrashDir).strip()
        if not duplicateTrashDir:
            duplicateTrashDir = ".photo-cleaner-trash/duplicates"

        duplicateTrashPath = Path(duplicateTrashDir)
        ret = duplicateTrashPath
        if not duplicateTrashPath.is_absolute():
            ret = in_archiveRoot / duplicateTrashPath
        return ret

    def _resolveJournalPath(
        self,
        in_workspacePath: Path,
    ) -> Path:
        ret = in_workspacePath / "apply_journal.jsonl"
        return ret

    def _resolveBackupRoot(
        self,
        in_workspacePath: Path,
    ) -> Path:
        ret = in_workspacePath / "apply_backups"
        return ret

    def _appendJournalRecord(
        self,
        in_journalPath: Path,
        in_record: dict[str, Any],
    ) -> None:
        in_journalPath.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(in_record, ensure_ascii=False)
        with in_journalPath.open("a", encoding="utf-8") as fileObject:
            fileObject.write(line + "\n")

    def _loadJournalRecords(
        self,
        in_journalPath: Path,
    ) -> list[dict[str, Any]]:
        ret: list[dict[str, Any]] = []
        if not in_journalPath.exists():
            return ret

        for line in in_journalPath.read_text(encoding="utf-8").splitlines():
            lineValue = line.strip()
            if not lineValue:
                continue
            try:
                payload = json.loads(lineValue)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                ret.append(payload)

        return ret

    def _findLastReversibleRunId(
        self,
        in_records: list[dict[str, Any]],
    ) -> str | None:
        ret: str | None = None

        completedRunIds: list[str] = []
        undoneTargetRunIds: set[str] = set()
        for record in in_records:
            recordType = str(record.get("recordType", ""))
            if recordType == "runEnd":
                runId = str(record.get("runId", "")).strip()
                dryRunValue = bool(record.get("dryRun", False))
                if runId and not dryRunValue:
                    completedRunIds.append(runId)
            if recordType == "undoEnd":
                targetRunId = str(record.get("targetRunId", "")).strip()
                if targetRunId:
                    undoneTargetRunIds.add(targetRunId)

        for runId in reversed(completedRunIds):
            if runId not in undoneTargetRunIds:
                ret = runId
                break

        return ret

    def _buildRunId(
        self,
        in_prefix: str,
    ) -> str:
        ret = f"{in_prefix}-{int(time.time())}-{uuid.uuid4().hex[:8]}"
        return ret

    def _utcNowIso(
        self,
    ) -> str:
        ret = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        return ret

    def _buildUniqueDestinationPath(
        self,
        in_destinationPath: Path,
    ) -> Path:
        ret = in_destinationPath
        if ret.exists():
            index = 1
            while ret.exists():
                stem = in_destinationPath.stem
                suffix = in_destinationPath.suffix
                candidateName = f"{stem}_{index}{suffix}"
                ret = in_destinationPath.with_name(candidateName)
                index += 1
        return ret
