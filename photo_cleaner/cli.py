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
        ],
    )

    parser.add_argument(
        "--config",
        default="config.yaml",
    )

    args = parser.parse_args()
    if args.command == "train-orientation-model":
        PhotoCleanerOperations(args.config).runTrainOrientationModel()
    else:
        runControlPanelServer(args.config)
