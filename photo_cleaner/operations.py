from pathlib import Path

from photo_cleaner.infrastructure.configLoader import (
    ConfigLoader,
)
from photo_cleaner.infrastructure.exifToolMetadataReader import (
    ExifToolMetadataReader,
)
from photo_cleaner.infrastructure.fileSystemScanner import (
    FileSystemScanner,
)
from photo_cleaner.infrastructure.metadataReader import MetadataReader
from photo_cleaner.infrastructure.sha256FileHasher import (
    Sha256FileHasher,
)
from photo_cleaner.infrastructure.sqlitePhotoRepository import (
    SqlitePhotoRepository,
)
from photo_cleaner.infrastructure.thumbnailGenerator import (
    ThumbnailGenerator,
)
from photo_cleaner.services.hashDuplicateCandidatesService import (
    HashDuplicateCandidatesService,
)
from photo_cleaner.services.duplicateReportService import (
    DuplicateReportService,
)
from photo_cleaner.services.orientationReportService import OrientationReportService
from photo_cleaner.services.applyActionsService import ApplyActionsService
from photo_cleaner.services.scanService import (
    ScanService,
)


class PhotoCleanerOperations:
    def __init__(
        self,
        in_configPath: str,
    ) -> None:
        self._configPath = in_configPath

    def _loadConfig(
        self,
    ) -> dict:
        ret = ConfigLoader().load(self._configPath)
        return ret

    def _buildRepository(
        self,
        in_config: dict,
    ) -> SqlitePhotoRepository:
        workspacePath = Path(in_config["workspace"]["path"])
        workspacePath.mkdir(
            parents=True,
            exist_ok=True,
        )
        dbPath = workspacePath / "cleanup.db"
        repository = SqlitePhotoRepository(
            str(dbPath),
        )
        repository.initialize()
        ret = repository
        return ret

    def runScan(
        self,
    ) -> None:
        config = self._loadConfig()
        repository = self._buildRepository(config)
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
        log("scan completed", level="info", user=True)

    def runBuildDuplicatesReport(
        self,
    ) -> str:
        config = self._loadConfig()
        repository = self._buildRepository(config)

        hasherService = HashDuplicateCandidatesService(
            repository,
            Sha256FileHasher(),
        )
        hasherService.hashDuplicateCandidates(
            config["archive"]["root"],
        )
        log("hash duplicates completed", level="debug")

        reportService = DuplicateReportService(
            repository,
            ThumbnailGenerator(),
        )
        reportService.buildReport(
            config["archive"]["root"],
            config["workspace"]["path"],
            config["thumbnails"]["maxSide"],
            config["thumbnails"]["quality"],
        )
        ret = "reports/duplicates"
        return ret

    def runBuildOrientationCandidatesReport(
        self,
    ) -> str:
        from photo_cleaner.infrastructure.mlOrientationDetector import (
            MlOrientationDetector,
        )

        config = self._loadConfig()
        repository = self._buildRepository(config)

        orientationBlock = config.get("orientation", {})
        mlBlock = orientationBlock.get("ml", {})

        checkpointPath = str(
            mlBlock.get(
                "checkpointPath",
                "./workspace/models/orientation_efficientnet_b0.pt",
            )
        )
        devicePreference = str(mlBlock.get("device", "mps"))
        confidenceThreshold = float(mlBlock.get("confidenceThreshold", 0.95))
        marginThreshold = float(mlBlock.get("marginThreshold", 0.25))

        detector = MlOrientationDetector(
            checkpointPath,
            devicePreference,
            confidenceThreshold,
            marginThreshold,
        )
        reportService = OrientationReportService(
            repository,
            detector,
        )
        reportService.buildReport(
            config["archive"]["root"],
            config["workspace"]["path"],
            orientationBlock["candidateExtensions"],
            orientationBlock["neverRotateExtensions"],
            orientationBlock.get("trustedCameraModels", []),
            True,
            "orientation_ml",
        )
        ret = "reports/orientation"
        return ret

    def runBuildOrientationDataset(
        self,
    ) -> None:
        from photo_cleaner.ml.orientationDatasetBuilder import (
            buildOrientationDatasetFromArchive,
        )

        config = self._loadConfig()
        repository = self._buildRepository(config)

        orientationBlock = config.get("orientation", {})
        mlBlock = orientationBlock.get("ml", {})

        datasetCameraModel = str(
            mlBlock.get("datasetCameraModel", "Canon EOS 5D Mark II"),
        )
        datasetRoot = Path(
            str(mlBlock.get("datasetRoot", "./workspace/orientation_dataset"))
        )
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
        confirmedOrientationPhotos = (
            repository.getConfirmedOrientationPhotosForOrientationDataset(
                orientationBlock["candidateExtensions"],
                orientationBlock["neverRotateExtensions"],
            )
        )
        trustedUprightCount = len(photosForDataset)
        confirmedOrientationCount = len(confirmedOrientationPhotos)
        mergedPhotosById: dict[str, dict] = {}
        for photo in photosForDataset:
            photoCopy = dict(photo)
            photoCopy["baseRotation"] = 0
            mergedPhotosById[str(photoCopy["id"])] = photoCopy
        for photo in confirmedOrientationPhotos:
            photoCopy = dict(photo)
            mergedPhotosById[str(photoCopy["id"])] = photoCopy
        photosForDataset = list(mergedPhotosById.values())
        print(
            "build-orientation-dataset sources: "
            f"trustedUpright={trustedUprightCount} "
            f"confirmedOrientation={confirmedOrientationCount} "
            f"total={len(photosForDataset)}"
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

    def runTrainOrientationModel(
        self,
    ) -> None:
        from photo_cleaner.ml.orientationTrainer import trainOrientationModel

        config = self._loadConfig()
        self._buildRepository(config)

        log("train-orientation-model bootstrap...", level="info", user=True)
        print("train-orientation-model importing modules...", flush=True)
        print("train-orientation-model modules imported", flush=True)

        orientationBlock = config.get("orientation", {})
        mlBlock = orientationBlock.get("ml", {})

        datasetRoot = Path(
            str(mlBlock.get("datasetRoot", "./workspace/orientation_dataset"))
        )
        checkpointPath = Path(
            str(
                mlBlock.get(
                    "checkpointPath",
                    "./workspace/models/orientation_efficientnet_b0.pt",
                )
            )
        )
        metricsPath = Path(
            str(
                mlBlock.get(
                    "metricsPath",
                    "./workspace/models/orientation_metrics.json",
                )
            )
        )
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

    def runApply(
        self,
        in_dryRun: bool,
        in_applyPendingDuplicates: bool = False,
        in_applyPendingOrientation: bool = False,
    ) -> dict:
        config = self._loadConfig()
        repository = self._buildRepository(config)
        applyService = ApplyActionsService(repository)

        duplicateBlock = config.get("duplicates", {})
        trashDir = str(
            duplicateBlock.get("trashDir", ".photo-cleaner-trash/duplicates")
        )

        ret = applyService.apply(
            config["archive"]["root"],
            config["workspace"]["path"],
            trashDir,
            in_dryRun,
            in_applyPendingDuplicates,
            in_applyPendingOrientation,
        )
        print(
            "apply finished: "
            f"dryRun={ret['dryRun']} "
            f"duplicatePlanned={ret['duplicatePlanned']} "
            f"duplicateApplied={ret['duplicateApplied']} "
            f"duplicateSkipped={ret['duplicateSkipped']} "
            f"orientationPlanned={ret['orientationPlanned']} "
            f"orientationApplied={ret['orientationApplied']} "
            f"orientationSkipped={ret['orientationSkipped']} "
            f"errors={len(ret['errors'])}"
        )
        return ret

    def runUndoLastApply(
        self,
        in_dryRun: bool,
    ) -> dict:
        config = self._loadConfig()
        repository = self._buildRepository(config)
        applyService = ApplyActionsService(repository)

        ret = applyService.undoLastApply(
            config["archive"]["root"],
            config["workspace"]["path"],
            in_dryRun,
        )
        print(
            "undo-last-apply finished: "
            f"dryRun={ret['dryRun']} "
            f"targetRunId={ret['targetRunId']} "
            f"planned={ret['planned']} "
            f"applied={ret['applied']} "
            f"skipped={ret['skipped']} "
            f"errors={len(ret['errors'])}"
        )
        return ret
