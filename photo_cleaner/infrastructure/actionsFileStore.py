import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ActionsFileStore:
    def getActionsPath(
        self,
        in_workspacePath: Path,
    ) -> Path:
        ret = in_workspacePath / "actions.json"
        return ret

    def loadActions(
        self,
        in_workspacePath: Path,
    ) -> dict[str, Any]:
        ret: dict[str, Any]

        actionsPath = self.getActionsPath(in_workspacePath)
        ret = {
            "version": 1,
            "updatedAt": None,
            "duplicates": {
                "groups": {},
            },
            "orientation": {
                "items": {},
            },
        }

        if actionsPath.exists():
            try:
                payloadRaw = json.loads(
                    actionsPath.read_text(encoding="utf-8"),
                )
                if isinstance(payloadRaw, dict):
                    ret.update(payloadRaw)
                    if "duplicates" not in ret or not isinstance(ret["duplicates"], dict):
                        ret["duplicates"] = {"groups": {}}
                    if "groups" not in ret["duplicates"] or not isinstance(ret["duplicates"]["groups"], dict):
                        ret["duplicates"]["groups"] = {}
                    if "orientation" not in ret or not isinstance(ret["orientation"], dict):
                        ret["orientation"] = {"items": {}}
                    if "items" not in ret["orientation"] or not isinstance(ret["orientation"]["items"], dict):
                        ret["orientation"]["items"] = {}
            except Exception:
                pass

        return ret

    def saveActions(
        self,
        in_workspacePath: Path,
        in_actionsPayload: dict[str, Any],
    ) -> None:
        payloadToSave = dict(in_actionsPayload)
        payloadToSave["version"] = 1
        payloadToSave["updatedAt"] = (
            datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
        )

        actionsPath = self.getActionsPath(in_workspacePath)
        actionsPath.write_text(
            json.dumps(payloadToSave, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
