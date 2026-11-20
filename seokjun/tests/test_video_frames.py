"""Offline ffmpeg extraction tests on a generated test pattern, not a recorded scene."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from pam.contracts import ContractError
from pam.video_frames import extract_frames, extract_reflector_frames, probe_duration, uniform_indices


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg is not installed")
class VideoFrameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.video = cls.root / "pattern.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=duration=6:size=320x180:rate=24",
                        "-pix_fmt", "yuv420p", str(cls.video)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_one_frame_per_second_with_requested_size(self):
        frames = extract_frames(self.video, self.root / "seconds", fps=1, width=160, height=90)
        self.assertEqual([frame["seconds"] for frame in frames], [0, 1, 2, 3, 4, 5])
        with Image.open(frames[0]["image_path"]) as image:
            self.assertEqual(image.size, (160, 90))

    def test_reflector_frames_are_exactly_the_requested_count_in_order(self):
        self.assertAlmostEqual(probe_duration(self.video), 6.0, places=1)
        frames = extract_reflector_frames(self.video, self.root / "reflector", count=20, width=160, height=90)
        self.assertEqual(len(frames), 20)
        self.assertEqual(frames[0]["seconds"], 0)
        seconds = [frame["seconds"] for frame in frames]
        self.assertEqual(seconds, sorted(set(seconds)))
        self.assertLess(seconds[-1], 6.0)

    def test_existing_output_directory_is_never_reused(self):
        target = self.root / "reused"
        target.mkdir()
        with self.assertRaises(ContractError):
            extract_frames(self.video, target, fps=1, width=160, height=90)

    def test_uniform_indices_match_the_reflector_rule(self):
        self.assertEqual(uniform_indices(5, 5), [0, 1, 2, 3, 4])
        self.assertEqual(uniform_indices(201, 3), [0, 100, 200])
        with self.assertRaises(ContractError):
            uniform_indices(3, 5)


if __name__ == "__main__":
    unittest.main()
