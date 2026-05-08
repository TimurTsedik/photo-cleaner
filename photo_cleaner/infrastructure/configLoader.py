from pathlib import Path
from typing import Any

import yaml


class ConfigLoader:
    def load(self, in_path: str) -> dict[str, Any]:
        ret: dict[str, Any]

        path = Path(in_path)

        with path.open("r", encoding="utf-8") as file:
            ret = yaml.safe_load(file)

        return ret