import json
import time
from pathlib import Path
from typing import Any

import torch
import torch.nn as nn
from PIL import Image
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms
from torchvision.models import (
    EfficientNet_B0_Weights,
    efficientnet_b0,
)


def resolveTorchDevice(
    in_devicePreference: str,
) -> str:
    ret = "cpu"
    candidate = in_devicePreference.lower().strip()

    if candidate == "mps":
        mpsBackend = getattr(torch.backends, "mps", None)
        if mpsBackend is not None and mpsBackend.is_available():
            ret = "mps"
        else:
            ret = "cpu"
    elif candidate == "cuda":
        if torch.cuda.is_available():
            ret = "cuda"
        else:
            ret = "cpu"
    else:
        ret = "cpu"

    return ret


class OrientationImageFolderDataset(Dataset):
    def __init__(
        self,
        in_rootDir: Path,
        in_transform: Any,
    ) -> None:
        self._rootDir = in_rootDir
        self._transform = in_transform
        self._samples: list[tuple[Path, int]] = []
        labelDirs: list[tuple[str, int]] = [
            ("0", 0),
            ("90", 1),
            ("270", 2),
        ]

        for labelDirName, labelIndex in labelDirs:
            classDir = in_rootDir / labelDirName
            if not classDir.is_dir():
                continue
            for imagePath in sorted(classDir.glob("*.jpg")):
                self._samples.append((imagePath, labelIndex))

    def __len__(
        self,
    ) -> int:
        ret = len(self._samples)
        return ret

    def __getitem__(
        self,
        in_index: int,
    ) -> tuple[Any, int]:
        imagePath, labelIndex = self._samples[in_index]
        with Image.open(imagePath) as image:
            rgbImage = image.convert("RGB")
            tensorImage = self._transform(rgbImage)

        ret = (tensorImage, labelIndex)
        return ret


def buildConfusionMatrix(
    in_numClasses: int,
) -> list[list[int]]:
    ret: list[list[int]] = []
    rowIndex = 0

    while rowIndex < in_numClasses:
        row: list[int] = []
        colIndex = 0
        while colIndex < in_numClasses:
            row.append(0)
            colIndex += 1
        ret.append(row)
        rowIndex += 1

    return ret


def evaluateOrientationModel(
    in_model: nn.Module,
    in_dataLoader: DataLoader,
    in_deviceName: str,
    in_numClasses: int,
) -> tuple[float, list[list[int]]]:
    in_model.eval()
    correctCount = 0
    totalCount = 0
    confusion = buildConfusionMatrix(in_numClasses)

    with torch.no_grad():
        for batchImages, batchLabels in in_dataLoader:
            batchImages = batchImages.to(in_deviceName)
            batchLabels = batchLabels.to(in_deviceName)
            outputs = in_model(batchImages)
            predictions = torch.argmax(outputs, dim=1)

            sampleIndex = 0
            while sampleIndex < len(batchLabels):
                labelValue = int(batchLabels[sampleIndex].item())
                predValue = int(predictions[sampleIndex].item())
                confusion[labelValue][predValue] += 1
                if predValue == labelValue:
                    correctCount += 1
                totalCount += 1
                sampleIndex += 1

    accuracy = correctCount / totalCount if totalCount > 0 else 0.0
    ret = (accuracy, confusion)
    return ret


def formatDurationSeconds(
    in_seconds: float,
) -> str:
    ret: str

    totalSeconds = int(max(0.0, in_seconds))
    hours = totalSeconds // 3600
    minutes = (totalSeconds % 3600) // 60
    seconds = totalSeconds % 60

    if hours > 0:
        ret = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    else:
        ret = f"{minutes:02d}:{seconds:02d}"

    return ret


def printProgressLine(
    in_message: str,
) -> None:
    print(in_message, flush=True)


def trainOrientationModel(
    in_datasetRoot: Path,
    in_checkpointPath: Path,
    in_metricsPath: Path,
    in_epochs: int,
    in_batchSize: int,
    in_learningRate: float,
    in_devicePreference: str,
    in_imageSize: int,
    in_randomSeed: int,
    in_numWorkers: int,
    in_verbose: bool = False,
    in_logEveryBatches: int = 10,
) -> dict[str, Any]:
    ret: dict[str, Any] = {}
    trainingStartedAt = time.time()

    deviceName = resolveTorchDevice(in_devicePreference)

    torch.manual_seed(in_randomSeed)

    if in_verbose:
        printProgressLine(
            "train-orientation-model started: "
            f"datasetRoot={in_datasetRoot}, "
            f"device={deviceName}, epochs={in_epochs}, "
            f"batchSize={in_batchSize}, numWorkers={in_numWorkers}"
        )
        printProgressLine("preparing datasets and dataloaders...")

    trainTransform = transforms.Compose(
        [
            transforms.RandomApply(
                [
                    transforms.ColorJitter(
                        brightness=0.2,
                        contrast=0.2,
                        saturation=0.2,
                        hue=0.05,
                    ),
                ],
                p=0.5,
            ),
            transforms.ToTensor(),
            transforms.Normalize(
                mean=[0.485, 0.456, 0.406],
                std=[0.229, 0.224, 0.225],
            ),
        ],
    )

    evalTransform = transforms.Compose(
        [
            transforms.ToTensor(),
            transforms.Normalize(
                mean=[0.485, 0.456, 0.406],
                std=[0.229, 0.224, 0.225],
            ),
        ],
    )

    trainDataset = OrientationImageFolderDataset(
        in_datasetRoot / "train",
        trainTransform,
    )
    valDataset = OrientationImageFolderDataset(
        in_datasetRoot / "val",
        evalTransform,
    )

    trainLoader = DataLoader(
        trainDataset,
        batch_size=in_batchSize,
        shuffle=True,
        num_workers=in_numWorkers,
    )
    valLoader = DataLoader(
        valDataset,
        batch_size=in_batchSize,
        shuffle=False,
        num_workers=in_numWorkers,
    )

    weightsEnum = EfficientNet_B0_Weights.IMAGENET1K_V1
    if in_verbose:
        printProgressLine(
            "loading EfficientNet-B0 backbone weights..."
        )
    model = efficientnet_b0(weights=weightsEnum)
    inFeatures = model.classifier[1].in_features
    model.classifier[1] = nn.Linear(inFeatures, 3)
    model = model.to(deviceName)

    lossFunction = nn.CrossEntropyLoss()
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=in_learningRate,
    )

    bestValAccuracy = -1.0
    bestEpochIndex = 0
    epochLog: list[dict[str, Any]] = []

    if in_verbose:
        printProgressLine(
            "model initialized. dataset samples: "
            f"train={len(trainDataset)}, val={len(valDataset)}"
        )

    epochIndex = 1
    while epochIndex <= in_epochs:
        model.train()
        trainLossSum = 0.0
        trainBatchCount = 0
        epochStartedAt = time.time()
        totalTrainBatches = len(trainLoader)

        if in_verbose:
            printProgressLine(f"epoch {epochIndex}/{in_epochs} started")

        for batchIndex, (batchImages, batchLabels) in enumerate(
            trainLoader,
            start=1,
        ):
            batchImages = batchImages.to(deviceName)
            batchLabels = batchLabels.to(deviceName)

            optimizer.zero_grad()
            outputs = model(batchImages)
            lossValue = lossFunction(outputs, batchLabels)
            lossValue.backward()
            optimizer.step()

            trainLossSum += float(lossValue.item())
            trainBatchCount += 1

            if in_verbose:
                shouldLogBatch = (
                    batchIndex % max(1, in_logEveryBatches) == 0
                    or batchIndex == totalTrainBatches
                )
                if shouldLogBatch:
                    elapsedEpochSeconds = time.time() - epochStartedAt
                    avgBatchSeconds = (
                        elapsedEpochSeconds / batchIndex
                        if batchIndex > 0
                        else 0.0
                    )
                    remainingBatches = totalTrainBatches - batchIndex
                    etaEpochSeconds = avgBatchSeconds * remainingBatches
                    progressPercent = (
                        (batchIndex / totalTrainBatches) * 100.0
                        if totalTrainBatches > 0
                        else 100.0
                    )

                    printProgressLine(
                        f"epoch {epochIndex}/{in_epochs} batch "
                        f"{batchIndex}/{totalTrainBatches} "
                        f"({progressPercent:.1f}%) "
                        f"loss={float(lossValue.item()):.4f} "
                        f"eta={formatDurationSeconds(etaEpochSeconds)}"
                    )

        trainLossAvg = (
            trainLossSum / trainBatchCount if trainBatchCount > 0 else 0.0
        )

        valAccuracy, valConfusion = evaluateOrientationModel(
            model,
            valLoader,
            deviceName,
            3,
        )

        epochRecord: dict[str, Any] = {
            "epoch": epochIndex,
            "trainLoss": trainLossAvg,
            "valAccuracy": valAccuracy,
            "valConfusion": valConfusion,
        }
        epochLog.append(epochRecord)

        if valAccuracy > bestValAccuracy:
            bestValAccuracy = valAccuracy
            bestEpochIndex = epochIndex

            checkpointPayload: dict[str, Any] = {
                "model_state_dict": model.state_dict(),
                "meta": {
                    "classLabels": [0, 90, 270],
                    "imageSize": in_imageSize,
                    "weightsBackbone": "efficientnet_b0_imagenet1k_v1",
                    "bestEpoch": bestEpochIndex,
                    "valAccuracy": bestValAccuracy,
                },
            }

            in_checkpointPath.parent.mkdir(parents=True, exist_ok=True)
            torch.save(checkpointPayload, in_checkpointPath)

        if in_verbose:
            isBest = valAccuracy >= bestValAccuracy and bestEpochIndex == epochIndex
            epochElapsed = formatDurationSeconds(time.time() - epochStartedAt)
            printProgressLine(
                f"epoch {epochIndex}/{in_epochs} finished: "
                f"trainLoss={trainLossAvg:.4f}, "
                f"valAccuracy={valAccuracy:.4f}, "
                f"bestValAccuracy={bestValAccuracy:.4f}, "
                f"bestEpoch={bestEpochIndex}, "
                f"checkpointUpdated={str(isBest).lower()}, "
                f"elapsed={epochElapsed}"
            )

        epochIndex += 1

    metricsPayload: dict[str, Any] = {
        "device": deviceName,
        "epochs": in_epochs,
        "bestEpoch": bestEpochIndex,
        "bestValAccuracy": bestValAccuracy,
        "epochsHistory": epochLog,
        "checkpointPath": str(in_checkpointPath),
    }

    in_metricsPath.parent.mkdir(parents=True, exist_ok=True)
    in_metricsPath.write_text(
        json.dumps(metricsPayload, indent=2),
        encoding="utf-8",
    )

    ret["metricsPath"] = str(in_metricsPath)
    ret["checkpointPath"] = str(in_checkpointPath)
    ret["bestValAccuracy"] = bestValAccuracy
    ret["device"] = deviceName

    if in_verbose:
        printProgressLine(
            "train-orientation-model completed: "
            f"bestEpoch={bestEpochIndex}, "
            f"bestValAccuracy={bestValAccuracy:.4f}, "
            f"elapsed={formatDurationSeconds(time.time() - trainingStartedAt)}, "
            f"checkpoint={in_checkpointPath}, metrics={in_metricsPath}"
        )

    return ret
