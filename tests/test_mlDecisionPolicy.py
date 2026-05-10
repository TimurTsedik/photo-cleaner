from unittest import TestCase

from photo_cleaner.services.mlDecisionPolicy import applyMlDecisionPolicy


class MlDecisionPolicyTests(TestCase):
    def test_applyMlDecisionPolicy_acceptsWhenConfidenceAndMarginHigh(
        self,
    ) -> None:
        ret = applyMlDecisionPolicy(
            {0: 0.01, 90: 0.97, 270: 0.02},
            0.95,
            0.25,
        )

        self.assertEqual(ret["suggestedAction"], "rotate270")
        self.assertEqual(ret["suggestedRotation"], 270)
        self.assertEqual(ret["decisionReason"], "ml_high_confidence")
        self.assertGreaterEqual(float(ret["confidence"]), 0.95)
        self.assertGreaterEqual(float(ret["margin"]), 0.25)

    def test_applyMlDecisionPolicy_invertsRotate270Class(
        self,
    ) -> None:
        ret = applyMlDecisionPolicy(
            {0: 0.02, 90: 0.01, 270: 0.97},
            0.95,
            0.25,
        )

        self.assertEqual(ret["suggestedAction"], "rotate90")
        self.assertEqual(ret["suggestedRotation"], 90)
        self.assertEqual(ret["decisionReason"], "ml_high_confidence")

    def test_applyMlDecisionPolicy_manualReviewWhenMarginLow(
        self,
    ) -> None:
        ret = applyMlDecisionPolicy(
            {0: 0.4, 90: 0.5, 270: 0.1},
            0.95,
            0.25,
        )

        self.assertEqual(ret["suggestedAction"], "manual_review")
        self.assertIsNone(ret["suggestedRotation"])
        self.assertEqual(ret["decisionReason"], "manual_review")

    def test_applyMlDecisionPolicy_keepUprightClass(
        self,
    ) -> None:
        ret = applyMlDecisionPolicy(
            {0: 0.99, 90: 0.005, 270: 0.005},
            0.95,
            0.25,
        )

        self.assertEqual(ret["suggestedAction"], "keep")
        self.assertIsNone(ret["suggestedRotation"])
        self.assertEqual(ret["decisionReason"], "ml_high_confidence")
