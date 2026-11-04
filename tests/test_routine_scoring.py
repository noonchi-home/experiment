"""Scoring tests on handwritten labels and predictions (not model results)."""

from __future__ import annotations

import unittest

from pam.routine_scoring import ScoringError, score_round

# 10 seconds: 0-1 nothing, 2-5 deliver cup (index 0, late from 4), 6-7 clear cup or bowl (1 or 6),
# 8-9 can delivery (index 2, given/missed only).
LABELS = {
    "per_second": [[-1], [-1], [0], [0], [0], [0], [1, 6], [1, 6], [2], [2]],
    "segments": [
        {"frame_start": 0, "frame_end": 1, "labels": [-1], "kind": "none", "scoring": None, "late_from_frame": None},
        {"frame_start": 2, "frame_end": 5, "labels": [0], "kind": "deliver",
         "scoring": "on_time_late_missed", "late_from_frame": 4},
        {"frame_start": 6, "frame_end": 7, "labels": [1, 6], "kind": "clear", "scoring": None, "late_from_frame": None},
        {"frame_start": 8, "frame_end": 9, "labels": [2], "kind": "deliver",
         "scoring": "given_or_missed", "late_from_frame": None},
    ],
}


class RoutineScoringTests(unittest.TestCase):
    def test_perfect_predictions(self):
        result = score_round(LABELS, [-1, -1, 0, 0, 0, 0, 6, 1, 2, 2], 10)
        self.assertEqual(result["accuracy"], 1.0)
        self.assertEqual(result["task_macro"], {"precision": 1.0, "recall": 1.0, "f1": 1.0})
        self.assertEqual(result["delivery_outcomes"], {"on_time": 1, "given": 1})
        self.assertEqual(result["mean_first_fire_delay_seconds"], 0)

    def test_late_missed_and_either_of_two_labels(self):
        predictions = [-1, 9, -1, -1, 0, -1, -1, 6, -1, -1]
        result = score_round(LABELS, predictions, 10)
        deliver, clear, can = result["segments"]
        self.assertEqual((deliver["outcome"], deliver["first_fire_delay_seconds"]), ("late", 2))
        self.assertEqual((clear["fired"], clear["first_fire_delay_seconds"]), (True, 1))
        self.assertEqual((can["outcome"], can["first_fire_delay_seconds"]), ("missed", 2))
        self.assertEqual(result["per_class"]["6"]["tp"], 1)
        self.assertEqual(result["distractor_predictions"], {"9": 1})
        self.assertAlmostEqual(result["no_act"]["recall"], 1 / 2)

    def test_invalid_output_is_never_no_action(self):
        result = score_round(LABELS, [None, -1, 0, 0, 0, 0, 1, 1, 2, 2], 10)
        self.assertEqual(result["invalid_outputs"], 1)
        self.assertEqual(result["no_act"]["fn"], 1)
        self.assertEqual(result["no_act"]["fp"], 0)

    def test_length_mismatch_is_rejected(self):
        with self.assertRaises(ScoringError):
            score_round(LABELS, [-1] * 9, 10)


if __name__ == "__main__":
    unittest.main()
