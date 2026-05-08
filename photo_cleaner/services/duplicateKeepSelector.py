import re
from pathlib import Path
from typing import Any


class DuplicateKeepSelector:
    _garbageNamePatterns = [
        r"\(\d+\)",        # IMG_001 (1).JPG
        r" copy\b",        # copy
        r" копия\b",       # копия
        r"_copy\b",
        r"-copy\b",
        r"_\d+$",          # IMG_001_1
        r"-\d+$",          # IMG_001-3
        r"æ|¡|¿|¼|«|¬",    # битая кодировка
    ]

    _badPathParts = [
        "backup",
        "copy",
        "копия",
        "duplicate",
        "duplicates",
        "temp",
        "tmp",
    ]

    def selectKeepItem(
        self,
        in_group: list[dict[str, Any]],
    ) -> dict[str, Any]:
        ret = sorted(
            in_group,
            key=self._calculatePenalty,
        )[0]

        return ret

    def selectMoveItems(
        self,
        in_group: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        keepItem = self.selectKeepItem(in_group)

        ret = [
            item
            for item in in_group
            if item["id"] != keepItem["id"]
        ]

        return ret

    def _calculatePenalty(
        self,
        in_item: dict[str, Any],
    ) -> tuple[int, int, str]:
        relativePath = in_item["relativePath"]
        filePath = Path(relativePath)
        stem = filePath.stem.lower()
        pathLower = relativePath.lower()

        penalty = 0

        for pattern in self._garbageNamePatterns:
            if re.search(pattern, stem, re.IGNORECASE):
                penalty += 100

        for badPart in self._badPathParts:
            if badPart in pathLower:
                penalty += 50

        if not self._hasReadableName(filePath.name):
            penalty += 200

        # Чем короче путь, тем лучше.
        pathLength = len(relativePath)

        ret = (
            penalty,
            pathLength,
            relativePath.lower(),
        )

        return ret

    def _hasReadableName(
        self,
        in_name: str,
    ) -> bool:
        ret = bool(
            re.search(r"[a-zA-Zа-яА-Я0-9]", in_name)
        )

        return ret