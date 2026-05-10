from photo_cleaner.infrastructure.faceOrientationDetector import (
    FaceOrientationDetector,
)
from photo_cleaner.infrastructure.legacyOrientationPredictor import (
    LegacyOrientationPredictor,
)
from photo_cleaner.services.orientationReportService import OrientationReportService


class FaceOrientationReportService(OrientationReportService):
    def __init__(
        self,
        in_repository,
        in_detector: FaceOrientationDetector,
    ) -> None:
        legacyPredictor = LegacyOrientationPredictor(in_detector)
        super().__init__(
            in_repository,
            legacyPredictor,
        )

    def buildReport(
        self,
        in_archiveRoot: str,
        in_workspacePath: str,
        in_candidateExtensions: list[str],
        in_neverRotateExtensions: list[str],
        in_trustedCameraModels: list[str],
    ) -> None:
        super().buildReport(
            in_archiveRoot,
            in_workspacePath,
            in_candidateExtensions,
            in_neverRotateExtensions,
            in_trustedCameraModels,
            False,
            "face_orientation.html",
            "Face orientation report",
            "face_orientation",
        )
