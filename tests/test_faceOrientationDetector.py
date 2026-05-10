from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock

from photo_cleaner.infrastructure.faceOrientationDetector import FaceOrientationDetector


class FaceOrientationDetectorTests(TestCase):
    def test_detectBestRotation_returnsSuggestion_whenModelConfident(self) -> None:
        detector = FaceOrientationDetector()
        detector._encodeCompareImageForModel = MagicMock(return_value="base64")  # type: ignore[method-assign]
        detector._requestModel = MagicMock(return_value={"choices": [{"message": {"content": "{\"choice\":\"B\",\"confidence\":0.92,\"reason\":\"upright\"}"}}]})  # type: ignore[method-assign]

        ret = detector.detectBestRotation(Path("fake.jpg"))

        self.assertEqual(ret["suggestedRotation"], 90)
        self.assertEqual(ret["decisionReason"], "openrouter_vision")
        self.assertEqual(ret["rawRotation"], 90)
        self.assertEqual(ret["rawChoice"], "B")

    def test_detectBestRotation_skips_whenModelConfidenceTooLow(self) -> None:
        detector = FaceOrientationDetector()
        detector._encodeCompareImageForModel = MagicMock(return_value="base64")  # type: ignore[method-assign]
        detector._requestModel = MagicMock(return_value={"choices": [{"message": {"content": "{\"choice\":\"C\",\"confidence\":0.41,\"reason\":\"weak\"}"}}]})  # type: ignore[method-assign]

        ret = detector.detectBestRotation(Path("fake.jpg"))

        self.assertIsNone(ret["suggestedRotation"])
        self.assertEqual(ret["decisionReason"], "low_confidence")

    def test_detectBestRotation_skips_whenModelResponseInvalid(self) -> None:
        detector = FaceOrientationDetector()
        detector._encodeCompareImageForModel = MagicMock(return_value="base64")  # type: ignore[method-assign]
        detector._requestModel = MagicMock(return_value={"choices": [{"message": {"content": "{\"rotation\":45,\"confidence\":0.95,\"reason\":\"bad\"}"}}]})  # type: ignore[method-assign]

        ret = detector.detectBestRotation(Path("fake.jpg"))

        self.assertIsNone(ret["suggestedRotation"])
        self.assertEqual(ret["decisionReason"], "model_parse_failed")
