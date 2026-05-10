import json
import random
import time
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps


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


def splitSourceIdsByPartition(
    in_sourceIds: list[str],
    in_randomSeed: int,
    in_trainRatio: float,
    in_valRatio: float,
) -> dict[str, str]:
    ret: dict[str, str] = {}

    testRatio = 1.0 - in_trainRatio - in_valRatio
    if testRatio < -1e-6 or in_trainRatio < 0 or in_valRatio < 0:
        raise ValueError("invalid split ratios")

    workingIds = list(in_sourceIds)
    randomGenerator = random.Random(in_randomSeed)
    randomGenerator.shuffle(workingIds)

    totalCount = len(workingIds)
    trainCut = int(totalCount * in_trainRatio)
    valCut = trainCut + int(totalCount * in_valRatio)

    index = 0
    for sourceId in workingIds:
        if index < trainCut:
            partitionName = "train"
        elif index < valCut:
            partitionName = "val"
        else:
            partitionName = "test"
        ret[sourceId] = partitionName
        index += 1

    return ret


def buildOrientationDatasetFromArchive(
    in_items: list[dict[str, Any]],
    in_archiveRoot: Path,
    in_outputRoot: Path,
    in_randomSeed: int,
    in_trainRatio: float,
    in_valRatio: float,
    in_imageSize: int,
    in_jpegQuality: int,
) -> dict[str, Any]:
    ret: dict[str, Any] = {}

    sourceIds = [str(item["id"]) for item in in_items]

    idToPartition = splitSourceIdsByPartition(
        sourceIds,
        in_randomSeed,
        in_trainRatio,
        in_valRatio,
    )

    summaryCounts: dict[str, dict[str, int]] = {
        "train": {"0": 0, "90": 0, "270": 0},
        "val": {"0": 0, "90": 0, "270": 0},
        "test": {"0": 0, "90": 0, "270": 0},
    }

    errors: list[str] = []
    totalItems = len(in_items)
    processedCount = 0
    progressPrintStep = 25
    startedAt = time.time()

    print(
        "build-orientation-dataset started: "
        f"items={totalItems}, output={in_outputRoot}, imageSize={in_imageSize}"
    )

    for item in in_items:
        sourceId = str(item["id"])
        partitionName = idToPartition[sourceId]
        relativePath = str(item["relativePath"])
        sourcePath = in_archiveRoot / relativePath

        if not sourcePath.exists():
            errors.append(f"missing file: {relativePath}")
            continue

        try:
            with Image.open(sourcePath) as imageRaw:
                baseImage = ImageOps.exif_transpose(imageRaw)
                baseImage = baseImage.convert("RGB")

                variants: list[tuple[str, int]] = [
                    ("0", 0),
                    ("90", 90),
                    ("270", 270),
                ]

                for labelStr, angleInt in variants:
                    if angleInt == 0:
                        imageVariant = baseImage.copy()
                    elif angleInt == 90:
                        imageVariant = baseImage.transpose(
                            Image.Transpose.ROTATE_270,
                        )
                    elif angleInt == 270:
                        imageVariant = baseImage.transpose(
                            Image.Transpose.ROTATE_90,
                        )
                    else:
                        imageVariant = baseImage.copy()

                    imageResized = imageVariant.resize(
                        (in_imageSize, in_imageSize),
                        Image.Resampling.LANCZOS,
                    )

                    classDir = (
                        in_outputRoot
                        / partitionName
                        / labelStr
                    )
                    classDir.mkdir(parents=True, exist_ok=True)

                    outPath = classDir / f"{sourceId}.jpg"
                    imageResized.save(
                        outPath,
                        "JPEG",
                        quality=in_jpegQuality,
                        optimize=True,
                    )
                    summaryCounts[partitionName][labelStr] += 1

        except Exception as exception:
            errors.append(
                f"{relativePath}: {exception}",
            )

        processedCount += 1

        if (
            processedCount % progressPrintStep == 0
            or processedCount == totalItems
        ):
            elapsedSeconds = time.time() - startedAt
            averageSecondsPerItem = (
                elapsedSeconds / processedCount
                if processedCount > 0
                else 0.0
            )
            remainingItems = totalItems - processedCount
            etaSeconds = averageSecondsPerItem * remainingItems
            progressPercent = (
                (processedCount / totalItems) * 100.0
                if totalItems > 0
                else 100.0
            )

            print(
                "build-orientation-dataset progress: "
                f"{processedCount}/{totalItems} ({progressPercent:.1f}%), "
                f"errors={len(errors)}, "
                f"elapsed={formatDurationSeconds(elapsedSeconds)}, "
                f"eta={formatDurationSeconds(etaSeconds)}, "
                f"remaining={remainingItems}"
            )

    manifestPath = in_outputRoot / "dataset_manifest.json"
    manifestPayload: dict[str, Any] = {
        "sourceCount": len(sourceIds),
        "splitRatios": {
            "train": in_trainRatio,
            "val": in_valRatio,
            "test": 1.0 - in_trainRatio - in_valRatio,
        },
        "randomSeed": in_randomSeed,
        "imageSize": in_imageSize,
        "counts": summaryCounts,
        "errors": errors,
    }

    manifestPath.write_text(
        json.dumps(manifestPayload, indent=2),
        encoding="utf-8",
    )

    ret["manifestPath"] = str(manifestPath)
    ret["counts"] = summaryCounts
    ret["errors"] = errors
    ret["idToPartition"] = idToPartition

    print(
        "build-orientation-dataset finished: "
        f"items={totalItems}, errors={len(errors)}, "
        f"elapsed={formatDurationSeconds(time.time() - startedAt)}, "
        f"manifest={manifestPath}"
    )

    return ret
