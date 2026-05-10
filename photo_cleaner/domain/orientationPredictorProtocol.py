from pathlib import Path
from typing import Any, Protocol


class OrientationPredictorProtocol(Protocol):
    def predictOrientation(
        self,
        in_imagePath: Path,
    ) -> dict[str, Any]:
        ...
