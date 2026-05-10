from pathlib import Path
import argparse
import json

from photo_cleaner.infrastructure.configLoader import (
    ConfigLoader,
)
from photo_cleaner.infrastructure.fileSystemScanner import (
    FileSystemScanner,
)
from photo_cleaner.infrastructure.sqlitePhotoRepository import (
    SqlitePhotoRepository,
)
from photo_cleaner.services.scanService import (
    ScanService,
)
from photo_cleaner.infrastructure.sha256FileHasher import (
    Sha256FileHasher,
)
from photo_cleaner.services.hashDuplicateCandidatesService import (
    HashDuplicateCandidatesService,
)
from photo_cleaner.services.exactDuplicateReportService import (
    ExactDuplicateReportService,
)
from photo_cleaner.infrastructure.thumbnailGenerator import (
    ThumbnailGenerator,
)
from photo_cleaner.services.htmlDuplicateReportService import (
    HtmlDuplicateReportService,
    HtmlOrientationReportService,
)
from photo_cleaner.infrastructure.metadataReader import MetadataReader
from photo_cleaner.infrastructure.exifToolMetadataReader import (
    ExifToolMetadataReader,
)
from photo_cleaner.services.orientationReportService import OrientationReportService


def main() -> None:
    parser = argparse.ArgumentParser(prog="photo-cleaner")

    parser.add_argument(
        "command",
        choices=[
            "scan",
            "hash-duplicates",
            "find-duplicates",
            "build-report",
            "build_duplicates_report",
            "build-orientation-report",
            "build-orientation-dataset",
            "train-orientation-model",
            "predict-orientation",
            "build-orientation-ml-report",
        ],
    )

    parser.add_argument(
        "--config",
        default="config.yaml",
    )

    parser.add_argument(
        "--image",
        dest="predictImagePath",
        default=None,
        help="Full path to a JPEG/PNG for predict-orientation",
    )

    args = parser.parse_args()

    config = ConfigLoader().load(args.config)

    workspacePath = Path(
        config["workspace"]["path"]
    )

    workspacePath.mkdir(
        parents=True,
        exist_ok=True,
    )

    dbPath = workspacePath / "cleanup.db"

    repository = SqlitePhotoRepository(
        str(dbPath),
    )

    repository.initialize()

    if args.command == "scan":
        scanService = ScanService(
            FileSystemScanner(
                MetadataReader(),
                ExifToolMetadataReader(),
            ),
            repository,
        )

        orientationBlock = config.get("orientation", {})
        excludedPrefixes = orientationBlock.get("excludedPathPrefixes", [])
        if excludedPrefixes is None:
            excludedPrefixes = []

        scanService.scan(
            config["archive"]["root"],
            set(config["files"]["jpegExtensions"]),
            set(config["files"]["rawExtensions"]),
            excludedPrefixes,
        )

        print("scan completed")

    elif args.command == "hash-duplicates":
        service = HashDuplicateCandidatesService(
            repository,
            Sha256FileHasher(),
        )

        service.hashDuplicateCandidates(
            config["archive"]["root"],
        )

        print("hash duplicates completed")

    elif args.command == "find-duplicates":
        service = ExactDuplicateReportService(
            repository,
        )

        service.printReport()

    elif args.command in {"build-report", "build_duplicates_report"}:
        service = HtmlDuplicateReportService(
            repository,
            ThumbnailGenerator(),
        )

        service.buildReport(
            config["archive"]["root"],
            config["workspace"]["path"],
            config["thumbnails"]["maxSide"],
            config["thumbnails"]["quality"],
        )

    elif args.command == "build-orientation-report":
        service = HtmlOrientationReportService(
            repository,
            ThumbnailGenerator(),
        )

        service.buildReport(
            config["archive"]["root"],
            config["workspace"]["path"],
            config["thumbnails"]["maxSide"],
            config["thumbnails"]["quality"],
            config["orientation"]["candidateExtensions"],
            config["orientation"]["neverRotateExtensions"],
            config["orientation"]["excludedPathPrefixes"],
        )
    elif args.command == "build-orientation-dataset":
        from photo_cleaner.ml.orientationDatasetBuilder import (
            buildOrientationDatasetFromArchive,
        )

        orientationBlock = config.get("orientation", {})
        mlBlock = orientationBlock.get("ml", {})

        datasetCameraModel = str(
            mlBlock.get("datasetCameraModel", "Canon EOS 5D Mark II"),
        )
        datasetRoot = Path(str(mlBlock.get("datasetRoot", "./workspace/orientation_dataset")))
        randomSeed = int(mlBlock.get("randomSeed", 42))
        trainRatio = float(mlBlock.get("trainRatio", 0.7))
        valRatio = float(mlBlock.get("valRatio", 0.15))
        imageSize = int(mlBlock.get("imageSize", 224))
        jpegQuality = int(mlBlock.get("jpegQuality", 92))

        photosForDataset = repository.getTrustedUprightPhotosForOrientationDataset(
            orientationBlock["candidateExtensions"],
            orientationBlock["neverRotateExtensions"],
            datasetCameraModel,
        )

        buildResult = buildOrientationDatasetFromArchive(
            photosForDataset,
            Path(config["archive"]["root"]),
            datasetRoot,
            randomSeed,
            trainRatio,
            valRatio,
            imageSize,
            jpegQuality,
        )

        print(
            "build-orientation-dataset finished: "
            f"manifest={buildResult['manifestPath']} "
            f"errors={len(buildResult['errors'])}"
        )

    elif args.command == "train-orientation-model":
        print("train-orientation-model bootstrap...", flush=True)
        print("train-orientation-model importing modules...", flush=True)
        from photo_cleaner.ml.orientationTrainer import trainOrientationModel
        print("train-orientation-model modules imported", flush=True)

        orientationBlock = config.get("orientation", {})
        mlBlock = orientationBlock.get("ml", {})

        datasetRoot = Path(str(mlBlock.get("datasetRoot", "./workspace/orientation_dataset")))
        checkpointPath = Path(str(mlBlock.get("checkpointPath", "./workspace/models/orientation_efficientnet_b0.pt")))
        metricsPath = Path(str(mlBlock.get("metricsPath", "./workspace/models/orientation_metrics.json")))
        epochs = int(mlBlock.get("epochs", 15))
        batchSize = int(mlBlock.get("batchSize", 16))
        learningRate = float(mlBlock.get("learningRate", 0.0001))
        devicePreference = str(mlBlock.get("device", "mps"))
        imageSize = int(mlBlock.get("imageSize", 224))
        randomSeed = int(mlBlock.get("randomSeed", 42))
        numWorkers = int(mlBlock.get("numWorkers", 0))
        verbose = bool(mlBlock.get("verbose", False))
        logEveryBatches = int(mlBlock.get("logEveryBatches", 10))

        trainResult = trainOrientationModel(
            datasetRoot,
            checkpointPath,
            metricsPath,
            epochs,
            batchSize,
            learningRate,
            devicePreference,
            imageSize,
            randomSeed,
            numWorkers,
            verbose,
            logEveryBatches,
        )

        print(
            "train-orientation-model finished: "
            f"checkpoint={trainResult['checkpointPath']} "
            f"bestValAccuracy={trainResult['bestValAccuracy']:.4f} "
            f"device={trainResult['device']}"
        )

    elif args.command == "predict-orientation":
        from photo_cleaner.infrastructure.mlOrientationDetector import (
            MlOrientationDetector,
        )

        if args.predictImagePath is None:
            raise SystemExit("predict-orientation requires --image /path/to/file.jpg")

        orientationBlock = config.get("orientation", {})
        mlBlock = orientationBlock.get("ml", {})

        checkpointPath = str(mlBlock.get("checkpointPath", "./workspace/models/orientation_efficientnet_b0.pt"))
        devicePreference = str(mlBlock.get("device", "mps"))
        confidenceThreshold = float(mlBlock.get("confidenceThreshold", 0.95))
        marginThreshold = float(mlBlock.get("marginThreshold", 0.25))

        detector = MlOrientationDetector(
            checkpointPath,
            devicePreference,
            confidenceThreshold,
            marginThreshold,
        )

        predictionPayload = detector.predictOrientation(Path(args.predictImagePath))

        jsonText = json.dumps(predictionPayload, indent=2)
        print(jsonText)

    elif args.command == "build-orientation-ml-report":
        from photo_cleaner.infrastructure.mlOrientationDetector import (
            MlOrientationDetector,
        )

        orientationBlock = config.get("orientation", {})
        mlBlock = orientationBlock.get("ml", {})

        checkpointPath = str(mlBlock.get("checkpointPath", "./workspace/models/orientation_efficientnet_b0.pt"))
        devicePreference = str(mlBlock.get("device", "mps"))
        confidenceThreshold = float(mlBlock.get("confidenceThreshold", 0.95))
        marginThreshold = float(mlBlock.get("marginThreshold", 0.25))

        detector = MlOrientationDetector(
            checkpointPath,
            devicePreference,
            confidenceThreshold,
            marginThreshold,
        )

        service = OrientationReportService(
            repository,
            detector,
        )

        service.buildReport(
            config["archive"]["root"],
            config["workspace"]["path"],
            orientationBlock["candidateExtensions"],
            orientationBlock["neverRotateExtensions"],
            orientationBlock.get("trustedCameraModels", []),
            True,
            "orientation_ml.html",
            "ML orientation report",
            "orientation_ml",
        )