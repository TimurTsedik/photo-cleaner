from pathlib import Path
from typing import Any

import torch
import torch.nn as nn
from PIL import Image, ImageOps
from torchvision import transforms
from torchvision.models import efficientnet_b0

from photo_cleaner.ml.orientationTrainer import resolveTorchDevice
from photo_cleaner.services.mlDecisionPolicy import applyMlDecisionPolicy


class MlOrientationDetector:
    def __init__(
        self,
        in_checkpointPath: str,
        in_devicePreference: str,
        in_confidenceThreshold: float,
        in_marginThreshold: float,
    ) -> None:
        self._checkpointPath = in_checkpointPath
        self._devicePreference = in_devicePreference
        self._confidenceThreshold = float(in_confidenceThreshold)
        self._marginThreshold = float(in_marginThreshold)

        deviceName = resolveTorchDevice(in_devicePreference)
        self._deviceName = deviceName

        try:
            checkpointPayload = torch.load(
                in_checkpointPath,
                map_location=deviceName,
                weights_only=False,
            )
        except TypeError:
            checkpointPayload = torch.load(
                in_checkpointPath,
                map_location=deviceName,
            )

        metaPayload = checkpointPayload.get("meta", {})
        classLabelsRaw = metaPayload.get("classLabels", [0, 90, 270])
        self._classLabels = [int(value) for value in classLabelsRaw]
        self._imageSize = int(metaPayload.get("imageSize", 224))

        modelState = checkpointPayload["model_state_dict"]
        self._model = self._buildModel(modelState, deviceName)

        self._evalTransform = transforms.Compose(
            [
                transforms.ToTensor(),
                transforms.Normalize(
                    mean=[0.485, 0.456, 0.406],
                    std=[0.229, 0.224, 0.225],
                ),
            ],
        )

    def _buildModel(
        self,
        in_stateDict: dict[str, Any],
        in_deviceName: str,
    ) -> nn.Module:
        model = efficientnet_b0(weights=None)
        inFeatures = model.classifier[1].in_features
        model.classifier[1] = nn.Linear(inFeatures, 3)
        model.load_state_dict(in_stateDict)
        model.to(in_deviceName)
        model.eval()
        ret = model
        return ret

    def predictOrientation(
        self,
        in_imagePath: Path,
    ) -> dict[str, Any]:
        ret: dict[str, Any] = {}

        try:
            with Image.open(in_imagePath) as imageRaw:
                rgbImage = ImageOps.exif_transpose(imageRaw)
                rgbImage = rgbImage.convert("RGB")
                rgbImage = rgbImage.resize(
                    (self._imageSize, self._imageSize),
                    Image.Resampling.LANCZOS,
                )

            tensorImage = self._evalTransform(rgbImage)
            batchTensor = tensorImage.unsqueeze(0).to(self._deviceName)

            with torch.no_grad():
                logits = self._model(batchTensor)
                probabilitiesTensor = torch.softmax(logits, dim=1)[0]

            probabilitiesByClass: dict[int, float] = {}
            index = 0
            while index < len(self._classLabels):
                labelKey = int(self._classLabels[index])
                probabilityValue = float(probabilitiesTensor[index].item())
                probabilitiesByClass[labelKey] = probabilityValue
                index += 1

            policyResult = applyMlDecisionPolicy(
                probabilitiesByClass,
                self._confidenceThreshold,
                self._marginThreshold,
            )

            ret["suggestedRotation"] = policyResult["suggestedRotation"]
            ret["suggestedAction"] = policyResult["suggestedAction"]
            ret["confidence"] = float(policyResult["confidence"])
            ret["margin"] = float(policyResult["margin"])
            ret["decisionReason"] = str(policyResult["decisionReason"])
            ret["probabilities"] = probabilitiesByClass
            ret["scores"] = probabilitiesByClass
            ret["predictionLabel"] = int(policyResult["predictionLabel"])
            ret["rawDetection"] = None

        except Exception as exception:
            ret["suggestedRotation"] = None
            ret["suggestedAction"] = "manual_review"
            ret["confidence"] = 0.0
            ret["margin"] = 0.0
            ret["decisionReason"] = "image_load_failed"
            ret["probabilities"] = None
            ret["scores"] = {}
            ret["predictionLabel"] = 0
            ret["rawDetection"] = {"error": str(exception)}

        return ret
