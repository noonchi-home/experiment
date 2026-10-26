"""Processing tests use colored tiles, never claimed as evaluated scenes."""

from __future__ import annotations

import json
import contextlib
import io
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PIL import Image

from pam.contracts import ContractError
from pam.observations import (
    InsufficientObservations,
    Observation,
    ObservationNotReady,
    compose_observations,
    load_observations,
    select_predictor_window,
    select_reflector_frames,
)


class ObservationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.start = datetime(2026, 10, 24, 7, 0, tzinfo=timezone(timedelta(hours=9)))
        self.left = self.root / "left.png"
        self.right = self.root / "right.png"
        Image.new("RGB", (3, 2), (255, 0, 0)).save(self.left)
        Image.new("RGB", (4, 2), (0, 0, 255)).save(self.right)

    def sequence(self, count):
        return [
            Observation(self.start + timedelta(seconds=index), self.left, self.right)
            for index in range(count)
        ]

    def write_manifest(self, records):
        path = self.root / "observations.json"
        path.write_text(json.dumps({"observations": records}), encoding="utf-8")
        return path

    def test_one_second_advance_changes_all_five_timestamps(self):
        observations = self.sequence(10)
        first = select_predictor_window(observations, self.start + timedelta(seconds=8))
        second = select_predictor_window(observations, self.start + timedelta(seconds=9))
        self.assertEqual([item.timestamp for item in first], [observations[i].timestamp for i in (0, 2, 4, 6, 8)])
        self.assertEqual([item.timestamp for item in second], [observations[i].timestamp for i in (1, 3, 5, 7, 9)])

    def test_initial_warmup_is_not_an_action_result(self):
        with self.assertRaises(ObservationNotReady):
            select_predictor_window(self.sequence(8), self.start + timedelta(seconds=7))
        with self.assertRaises(ObservationNotReady):
            select_predictor_window([], self.start)

    def test_missing_required_frame_is_not_nearest_neighbor_or_no_act(self):
        observations = self.sequence(9)
        observations.pop(4)
        with self.assertRaisesRegex(ContractError, "Missing required"):
            select_predictor_window(observations, self.start + timedelta(seconds=8))

    def test_selector_rejects_naive_duplicate_and_unsorted_times(self):
        with self.assertRaises(ContractError):
            select_predictor_window(self.sequence(9), self.start.replace(tzinfo=None))
        naive = Observation(self.start.replace(tzinfo=None), self.left, self.right)
        with self.assertRaises(ContractError):
            select_reflector_frames([naive, naive], count=2)
        observations = self.sequence(9)
        for bad in (list(reversed(observations)), observations + [observations[-1]]):
            with self.assertRaises(ContractError):
                select_predictor_window(bad, self.start + timedelta(seconds=8))

    def test_equivalent_utc_prediction_time_selects_same_instants(self):
        observations = self.sequence(9)
        at = observations[-1].timestamp.astimezone(timezone.utc)
        selected = select_predictor_window(observations, at)
        self.assertEqual(selected, observations[::2])

    def test_uniform_day_selection_has_200_unique_frames_and_both_endpoints(self):
        observations = self.sequence(1000)
        selected = select_reflector_frames(observations)
        self.assertEqual(len(selected), 200)
        self.assertEqual(len({item.timestamp for item in selected}), 200)
        self.assertEqual(selected[0], observations[0])
        self.assertEqual(selected[-1], observations[-1])
        differences = [(b.timestamp - a.timestamp).total_seconds() for a, b in zip(selected, selected[1:])]
        self.assertEqual(set(differences), {5, 6})

    def test_uniform_halfway_rounds_up_and_full_count_does_not_repeat(self):
        observations = self.sequence(4)
        self.assertEqual(select_reflector_frames(observations, count=3), [observations[0], observations[2], observations[3]])
        self.assertEqual(select_reflector_frames(self.sequence(200)), self.sequence(200))

    def test_user_selected_150_of_200_preserves_endpoints_and_uniform_coverage(self):
        observations = self.sequence(200)
        selected = select_reflector_frames(observations, count=150)
        self.assertEqual(len(selected), 150)
        self.assertEqual(len({frame.timestamp for frame in selected}), 150)
        self.assertEqual(selected[0], observations[0])
        self.assertEqual(selected[-1], observations[-1])
        gaps = {(right.timestamp - left.timestamp).total_seconds()
                for left, right in zip(selected, selected[1:])}
        self.assertEqual(gaps, {1, 2})

    def test_insufficient_day_frames_are_not_padded(self):
        with self.assertRaisesRegex(InsufficientObservations, "only 199"):
            select_reflector_frames(self.sequence(199))
        for bad_count in (1, 0, True, 2.5):
            with self.assertRaises(ContractError):
                select_reflector_frames(self.sequence(9), count=bad_count)

    def test_compose_preserves_left_right_orientation_dimensions_and_metadata(self):
        result = compose_observations(self.sequence(1), self.root / "composed")
        self.assertEqual(len(result), 1)
        record = result[0]
        self.assertEqual((record["width"], record["height"]), (7, 2))
        self.assertEqual(record["vertical_padding_px"], 0)
        self.assertEqual(record["content_box"], [0, 0, 7, 2])
        self.assertEqual(record["timestamp"], self.start.isoformat())
        self.assertEqual(record["left_image"], str(self.left.resolve()))
        self.assertEqual(record["right_image"], str(self.right.resolve()))
        with Image.open(record["image_path"]) as image:
            self.assertEqual(image.getpixel((0, 0)), (255, 0, 0))
            self.assertEqual(image.getpixel((2, 1)), (255, 0, 0))
            self.assertEqual(image.getpixel((3, 0)), (0, 0, 255))
            self.assertEqual(image.getpixel((6, 1)), (0, 0, 255))

    def test_vertical_padding_48_preserves_all_rgb_pixels_and_adds_black_margins(self):
        Image.new("RGB", (384, 288), (113, 41, 219)).save(self.left)
        Image.new("RGB", (384, 288), (23, 192, 74)).save(self.right)
        before = (self.left.read_bytes(), self.right.read_bytes())
        record = compose_observations(
            self.sequence(1), self.root / "padded", vertical_padding_px=48)[0]
        self.assertEqual((record["width"], record["height"]), (768, 384))
        self.assertEqual(record["vertical_padding_px"], 48)
        self.assertEqual(record["content_box"], [0, 48, 768, 336])
        self.assertEqual(record["timestamp"], self.start.isoformat())
        with Image.open(record["image_path"]) as combined, Image.open(self.left) as left, Image.open(self.right) as right:
            self.assertEqual(combined.crop((0, 48, 384, 336)).tobytes(), left.tobytes())
            self.assertEqual(combined.crop((384, 48, 768, 336)).tobytes(), right.tobytes())
            self.assertEqual(combined.crop((0, 0, 768, 48)).getextrema(), ((0, 0),) * 3)
            self.assertEqual(combined.crop((0, 336, 768, 384)).getextrema(), ((0, 0),) * 3)
        self.assertEqual((self.left.read_bytes(), self.right.read_bytes()), before)

    def test_zero_padding_matches_default_and_invalid_values_create_no_output(self):
        default = compose_observations(self.sequence(1), self.root / "default")[0]
        zero = compose_observations(self.sequence(1), self.root / "zero", vertical_padding_px=0)[0]
        self.assertEqual(Path(default["image_path"]).read_bytes(), Path(zero["image_path"]).read_bytes())
        for index, invalid in enumerate((-1, True, False, 1.5, "48", None)):
            destination = self.root / f"invalid_padding_{index}"
            with self.subTest(value=invalid), self.assertRaises(ContractError):
                compose_observations(self.sequence(1), destination, vertical_padding_px=invalid)
            self.assertFalse(destination.exists())

    def test_padding_cli_is_reflector_only_and_rejects_negative_or_fractional_values(self):
        from pam.__main__ import parser
        base = ["prepare-reflector", "--observations", "observations.json", "--memory-kind", "fsm",
                "--operation", "build", "--output", "new-output"]
        self.assertEqual(parser().parse_args(base).vertical_padding_px, 0)
        self.assertEqual(parser().parse_args(base + ["--vertical-padding-px", "48"]).vertical_padding_px, 48)
        for bad in ("-1", "1.5", "true"):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                parser().parse_args(base + ["--vertical-padding-px", bad])
        predictor = ["prepare-predictor", "--observations", "observations.json", "--at", self.start.isoformat(),
                     "--output", "new-output", "--vertical-padding-px", "48"]
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parser().parse_args(predictor)

    def test_reflector_cli_records_padding_adaptation_without_model_call(self):
        from pam.__main__ import main
        manifest = self.write_manifest([
            {"timestamp": (self.start + timedelta(seconds=second)).isoformat(),
             "left_image": "left.png", "right_image": "right.png"}
            for second in range(200)
        ])
        output = self.root / "reflector_cli_padding"
        with contextlib.redirect_stdout(io.StringIO()):
            result = main(["prepare-reflector", "--observations", str(manifest),
                           "--memory-kind", "fsm", "--operation", "build",
                           "--vertical-padding-px", "48", "--output", str(output)])
        self.assertEqual(result, 0)
        bundle = json.loads((output / "input_bundle.json").read_text(encoding="utf-8"))
        self.assertFalse(bundle["api_called"])
        self.assertEqual(len(bundle["frames"]), 200)
        self.assertEqual(bundle["image_adaptation"]["kind"], "vertical_black_letterbox")
        self.assertFalse(bundle["image_adaptation"]["paper_parameter"])
        self.assertFalse(bundle["image_adaptation"]["resized"])
        self.assertFalse(bundle["image_adaptation"]["cropped"])
        self.assertTrue(bundle["image_adaptation"]["source_rgb_pixels_preserved"])
        self.assertIn("requires actual verification", bundle["image_adaptation"]["note"])
        self.assertTrue(all(frame["vertical_padding_px"] == 48 for frame in bundle["frames"]))
        with Image.open(bundle["frames"][0]["image_path"]) as combined:
            self.assertEqual(combined.size, (7, 98))
            self.assertEqual(combined.getpixel((0, 48)), (255, 0, 0))
            self.assertEqual(combined.getpixel((6, 49)), (0, 0, 255))

    def test_compose_rejects_missing_camera_unequal_heights_and_same_file(self):
        missing = Observation(self.start, self.left, self.root / "missing.png")
        with self.assertRaisesRegex(ContractError, "Missing right"):
            compose_observations([missing], self.root / "missing-output")
        same = Observation(self.start, self.left, self.left)
        with self.assertRaisesRegex(ContractError, "distinct"):
            compose_observations([same], self.root / "same-output")
        Image.new("RGB", (4, 3), (0, 0, 255)).save(self.right)
        with self.assertRaisesRegex(ContractError, "heights differ"):
            compose_observations(self.sequence(1), self.root / "height-output")

    def test_unreadable_camera_file_is_explicit_error(self):
        self.right.write_text("This is not an image.", encoding="utf-8")
        with self.assertRaisesRegex(ContractError, "Cannot decode"):
            compose_observations(self.sequence(1), self.root / "unreadable-output")

    def test_composition_never_overwrites_previous_or_source_images(self):
        compose_observations(self.sequence(1), self.root / "output")
        with self.assertRaisesRegex(ContractError, "already exist"):
            compose_observations(self.sequence(1), self.root / "output")
        source = self.root / "frame_000.png"
        Image.new("RGB", (3, 2)).save(source)
        with self.assertRaisesRegex(ContractError, "overwrite source"):
            compose_observations([Observation(self.start, source, self.right)], self.root)

    def test_load_resolves_relative_paths_and_keeps_camera_times(self):
        manifest = self.write_manifest([
            {"timestamp": self.start.isoformat(), "left_image": "left.png", "right_image": "right.png"}
        ])
        self.assertEqual(load_observations(manifest), self.sequence(1))

    def test_load_rejects_missing_camera_and_evaluation_label(self):
        valid = {"timestamp": self.start.isoformat(), "left_image": "left.png", "right_image": "right.png"}
        for record in (
            {**valid, "right_image": "absent.png"},
            {**valid, "expected_action": "bring milk"},
            {"timestamp": self.start.isoformat(), "left_image": "left.png"},
        ):
            with self.assertRaises(ContractError):
                load_observations(self.write_manifest([record]))

    def test_load_rejects_duplicate_json_field(self):
        manifest = self.root / "duplicate.json"
        manifest.write_text('{"observations":[],"observations":[]}', encoding="utf-8")
        with self.assertRaisesRegex(ContractError, "Duplicate JSON"):
            load_observations(manifest)


if __name__ == "__main__":
    unittest.main()
