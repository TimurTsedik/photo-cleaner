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
from photo_cleaner.infrastructure.sha256FileHasher import (
    Sha256FileHasher,
)
from photo_cleaner.services.scanService import (
    ScanService,
)
from photo_cleaner.services.hashService import (
    HashService,
)


def main() -> None:
    parser = argparse.ArgumentParser(prog="photo-cleaner")

    parser.add_argument(
        "command",
        choices=[
            "scan",
            "hash-duplicates",
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
            FileSystemScanner(),
            repository,
        )

        scanService.scan(
            config["archive"]["root"],
            set(config["files"]["jpegExtensions"]),
            set(config["files"]["rawExtensions"]),
        )

        print("scan completed")
    elif args.command == "hash-duplicates":
        hashService = HashService(
            repository,
            Sha256FileHasher(),
        )

        hashedCount = hashService.hashDuplicateSizePhotos(
            config["archive"]["root"],
        )

        print(f"hash completed, files hashed: {hashedCount}")