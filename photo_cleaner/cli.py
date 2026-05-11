import argparse
from photo_cleaner.controlPanelServer import (
    runControlPanelServer,
)
from photo_cleaner.operations import (
    PhotoCleanerOperations,
)


def main() -> None:
    parser = argparse.ArgumentParser(prog="photo-cleaner")

    parser.add_argument(
        "command",
        nargs="?",
        choices=[
            "train-orientation-model",
            "apply",
            "undo-last-apply",
        ],
    )

    parser.add_argument(
        "--config",
        default="config.yaml",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
    )

    args = parser.parse_args()
    if args.command == "train-orientation-model":
        PhotoCleanerOperations(args.config).runTrainOrientationModel()
    elif args.command == "apply":
        PhotoCleanerOperations(args.config).runApply(args.dry_run)
    elif args.command == "undo-last-apply":
        PhotoCleanerOperations(args.config).runUndoLastApply(args.dry_run)
    else:
        runControlPanelServer(args.config)
