"""CLI integration for explicit frozen-day memory selection; no model calls."""

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from pam.__main__ import main
from pam.memory_store import initialize_store
from pam.messages import PROJECT_ROOT, read_json
from tools.make_processing_fixture import create_fixture


class MemoryCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        create_fixture(self.root / "fixtures", count=9)
        self.store = self.root / "memory_store"
        initialize_store(self.store, PROJECT_ROOT / "scenarios/morning/initial_fsm.json", "2026-10-24")

    def run_cli(self, day="2026-10-24", extra=()):
        output = self.root / "output"
        args = ["prepare-predictor", "--observations", str(self.root / "fixtures/observations.json"),
                "--scenario", str(PROJECT_ROOT / "scenarios/morning/scenario.json"),
                "--memory-kind", "fsm", "--memory-store", str(self.store), "--day", day,
                "--at", "2026-10-24T07:00:08+09:00", "--output", str(output), *extra]
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            code = main(args)
        return code, output, json.loads(stream.getvalue())

    def test_explicit_day_uses_stored_snapshot_not_scenario_default(self):
        code, output, printed = self.run_cli()
        self.assertEqual(code, 0, printed)
        bundle = read_json(output / "input_bundle.json")
        self.assertEqual(bundle["memory_assignment"]["version_id"], "000_seed")
        self.assertEqual(bundle["inputs"]["memory"]["path"], str((self.store / "versions/000_seed.json").resolve()))

    def test_unknown_day_fails_without_falling_back_to_seed(self):
        code, output, printed = self.run_cli("2026-10-25")
        self.assertEqual(code, 2)
        self.assertEqual(printed["status"], "input_error")
        self.assertFalse((output / "input_bundle.json").exists())

    def test_memory_file_and_store_cannot_be_mixed(self):
        code, _, printed = self.run_cli(extra=("--memory", str(self.store / "versions/000_seed.json")))
        self.assertEqual(code, 2)
        self.assertIn("without --memory", printed["error"])


if __name__ == "__main__":
    unittest.main()
