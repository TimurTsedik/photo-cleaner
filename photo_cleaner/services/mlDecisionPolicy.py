from typing import Any


def applyMlDecisionPolicy(
    in_probabilitiesByClass: dict[int, float],
    in_confidenceThreshold: float,
    in_marginThreshold: float,
) -> dict[str, Any]:
    ret: dict[str, Any] = {}

    itemsSorted = sorted(
        in_probabilitiesByClass.items(),
        key=lambda pair: pair[1],
        reverse=True,
    )

    if len(itemsSorted) < 2:
        topLabel = itemsSorted[0][0] if len(itemsSorted) == 1 else 0
        topProb = itemsSorted[0][1] if len(itemsSorted) == 1 else 0.0
        secondProb = 0.0
    else:
        topLabel = int(itemsSorted[0][0])
        topProb = float(itemsSorted[0][1])
        secondProb = float(itemsSorted[1][1])

    marginValue = topProb - secondProb

    suggestedRotation: int | None
    suggestedAction: str
    decisionReason: str

    if topProb >= in_confidenceThreshold and marginValue >= in_marginThreshold:
        decisionReason = "ml_high_confidence"
        if topLabel == 0:
            suggestedRotation = None
            suggestedAction = "keep"
        elif topLabel == 90:
            suggestedRotation = 90
            suggestedAction = "rotate90"
        elif topLabel == 270:
            suggestedRotation = 270
            suggestedAction = "rotate270"
        else:
            suggestedRotation = None
            suggestedAction = "manual_review"
            decisionReason = "ml_unknown_class"
    else:
        decisionReason = "manual_review"
        suggestedRotation = None
        suggestedAction = "manual_review"

    ret["suggestedRotation"] = suggestedRotation
    ret["suggestedAction"] = suggestedAction
    ret["decisionReason"] = decisionReason
    ret["confidence"] = topProb
    ret["margin"] = marginValue
    ret["predictionLabel"] = topLabel

    return ret
