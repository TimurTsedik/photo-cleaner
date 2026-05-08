from pathlib import Path
import argparse

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

def main() -> None:
    parser = argparse.ArgumentParser(prog="photo-cleaner")

    parser.add_argument(
        "command",
        choices=[
            "scan",
            "hash-duplicates",
            "find-duplicates",
            "build-report",
            "build-orientation-report",
        ],
    )

    parser.add_argument(
        "--config",
        default="config.yaml",
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
            ),
            repository,
        )

        scanService.scan(
            config["archive"]["root"],
            set(config["files"]["jpegExtensions"]),
            set(config["files"]["rawExtensions"]),
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

    elif args.command == "build-report":
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
            config["orientation"]["trustedCameraModels"],
            config["orientation"]["candidateExtensions"],
            config["orientation"]["neverRotateExtensions"],
        )