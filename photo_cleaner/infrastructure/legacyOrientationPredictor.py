from pathlib import Path
from typing import Any

from photo_cleaner.infrastructure.faceOrientationDetector import (
    FaceOrientationDetector,
)


class LegacyOrientationPredictor:
    def __init__(
        self,
        in_detector: FaceOrientationDetector,
    ) -> None:
        self._detector = in_detector

    def predictOrientation(
        self,
        in_imagePath: Path,
    ) -> dict[str, Any]:
        ret: dict[str, Any] = {}

        detection = self._detector.detectBestRotation(in_imagePath)
        decisionReason = str(detection.get("decisionReason", "unknown"))
        suggestedRotation = detection.get("suggestedRotation")
        confidenceValue = float(detection.get("confidence", 0.0))
        scoresMap = detection.get("scores")
        if scoresMap is None:
            scoresMap = {}

        ratioValue = float(detection.get("confidenceRatio", 0.0))

        suggestedAction: str
        if suggestedRotation == 90:
            suggestedAction = "rotate90"
        elif suggestedRotation == 270:
            suggestedAction = "rotate270"
        elif decisionReason == "model_says_no_rotation":
            suggestedAction = "keep"
        elif suggestedRotation is None:
            suggestedAction = "manual_review"
        else:
            suggestedAction = "manual_review"

        probabilitiesMap: dict[int, float] | None = None

        rawRotationValue = detection.get("rawRotation")
        predictionLabelValue: int | None
        if rawRotationValue is not None:
            predictionLabelValue = int(rawRotationValue)
        else:
            predictionLabelValue = None

        ret["suggestedRotation"] = suggestedRotation
        ret["suggestedAction"] = suggestedAction
        ret["confidence"] = confidenceValue
        ret["margin"] = ratioValue
        ret["decisionReason"] = decisionReason
        ret["probabilities"] = probabilitiesMap
        ret["scores"] = scoresMap
        ret["rawDetection"] = detection
        ret["predictionLabel"] = predictionLabelValue

        return ret
