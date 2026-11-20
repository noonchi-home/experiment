"""Offline checks against the actual supplied PDF, not a model execution."""

import hashlib
import importlib.util
import json
from pathlib import Path
import re
import unittest

import fitz


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "extract_paper_prompts", ROOT / "tools/extract_paper_prompts.py"
)
EXTRACTOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EXTRACTOR)
REVIEWED_PDF_SHA256 = "1fe0e4954d4fefaffb1e9d1619a2e52e1918b2872ca789485ec437e95f82a364"
EXPECTED_SECTIONS = {
    "predictor_no_memory": ("E.1", [31]),
    "predictor_list": ("E.2", [32]),
    "predictor_fsm": ("E.3", [33, 34]),
    "reflector_list_build": ("F.1", [34, 35]),
    "reflector_list_update": ("F.2", [35, 36, 37]),
    "reflector_fsm_build": ("F.3", [37, 38]),
    "reflector_fsm_update": ("F.4", [38, 39, 40]),
}


def compact(text):
    return re.sub(r"\s+", "", text)


class PromptSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source_map = json.loads((ROOT / "prompts/source_map.json").read_text(encoding="utf-8"))
        cls.prompts = {
            name: (ROOT / record["file"]).read_text(encoding="utf-8")
            for name, record in cls.source_map["prompts"].items()
        }

    def test_reviewed_pdf_and_exact_section_coverage(self):
        source = self.source_map["source_pdf"]
        self.assertEqual(source["sha256"], REVIEWED_PDF_SHA256)
        self.assertEqual(hashlib.sha256((ROOT / source["path"]).read_bytes()).hexdigest(), REVIEWED_PDF_SHA256)
        self.assertEqual(set(self.source_map["prompts"]), set(EXPECTED_SECTIONS))
        for name, (section, pages) in EXPECTED_SECTIONS.items():
            with self.subTest(prompt=name):
                record = self.source_map["prompts"][name]
                self.assertEqual((record["section"], record["pages"]), (section, pages))
                self.assertEqual([region["page"] for region in record["regions"]], pages)

    def test_reproducible_extraction_and_metadata(self):
        self.assertEqual(EXTRACTOR.check(ROOT), [])

    def test_independent_pdf_text_matches_every_non_whitespace_character(self):
        # This route does not use the extractor's font filtering or row joining.
        # The independently recorded section/page coverage is checked above.
        with fitz.open(ROOT / self.source_map["source_pdf"]["path"]) as pdf:
            for name, record in self.source_map["prompts"].items():
                with self.subTest(prompt=name):
                    reference = "".join(
                        pdf[region["page"] - 1].get_text(
                            "text", clip=fitz.Rect(region["bbox"]) + (-0.25, -0.25, 0.25, 0.25), sort=False
                        )
                        for region in record["regions"]
                    )
                    body = self.prompts[name]
                    self.assertEqual(compact(body), compact(reference))
                    self.assertEqual(hashlib.sha256(compact(body).encode("utf-8")).hexdigest(), record["non_whitespace_sha256"])
                    data = (ROOT / record["file"]).read_bytes()
                    self.assertEqual(hashlib.sha256(data).hexdigest(), record["sha256"])
                    self.assertNotIn(b"\r", data)
                    self.assertTrue(data.endswith(b"\n"))
                    self.assertTrue(body.startswith("You are "))
                    self.assertTrue(body.rstrip().endswith("}"))

    def test_original_template_placeholders(self):
        common = {"n_tasks_minus_one", "tasks_block", "window"}
        expected = {
            "predictor_no_memory": common,
            "predictor_list": common | {"rules_block"},
            "predictor_fsm": common | {"fsm_block"},
        }
        for name, record in self.source_map["prompts"].items():
            with self.subTest(prompt=name):
                self.assertEqual(set(record["placeholders"]), expected.get(name, set()))

    def test_paper_instructions_not_silently_corrected_or_replaced(self):
        for name in ("predictor_no_memory", "predictor_list", "predictor_fsm"):
            with self.subTest(prompt=name):
                text = compact(self.prompts[name])
                self.assertIn("sampledat1fps", text)
                self.assertIn("task_index=-1", text)
                self.assertIn("holdingortouchinganobject", text)
        for name in ("predictor_list", "predictor_fsm"):
            self.assertIn("REFERENCE,notasastrictmatcher", compact(self.prompts[name]))
        for name in ("reflector_list_build", "reflector_list_update", "reflector_fsm_build", "reflector_fsm_update"):
            with self.subTest(prompt=name):
                self.assertIn("(*@\\textbar@*)", self.prompts[name])
                self.assertIn("–-", self.prompts[name])
                self.assertIn("DoNOTinventhypotheticalactions", compact(self.prompts[name]))

    def test_build_and_update_input_contracts_and_fsm_schema(self):
        for kind in ("list", "fsm"):
            build = compact(self.prompts[f"reflector_{kind}_build"])
            update = compact(self.prompts[f"reflector_{kind}_update"])
            self.assertIn("nopriormemory,nosummary,andnohumanfeedbackyet", build)
            for label in ("Currentmemory:", "Today'svideo:", "Summary:", "Humanfeedback:"):
                self.assertIn(label, update)
            self.assertIn("treatit asauthoritative".replace(" ", ""), update)
        for name in ("reflector_fsm_build", "reflector_fsm_update"):
            text = self.prompts[name]
            for field in ("initial_state", "states", "id", "description", "rules", "trigger", "action", "next", "to", "on"):
                self.assertIn(f'"{field}"', text)
            self.assertIn("Transitionsarenotrobotactions", compact(text))

    def test_paper_configuration_values_and_provenance(self):
        config = json.loads((ROOT / "config/paper.json").read_text(encoding="utf-8"))
        self.assertEqual(config["model"], "Qwen3.5-27B")
        self.assertEqual(config["predictor"], {
            "temperature": 0.3, "enable_thinking": False, "frame_count": 5,
            "frame_stride_seconds": 2, "interval_seconds": 1,
        })
        for key, value in {"temperature": 0.3, "enable_thinking": True, "frame_count": 200,
                           "schedule": "end_of_day", "sampling": "uniform_over_day"}.items():
            self.assertEqual(config["reflector"][key], value)
        self.assertEqual(config["frame_composition"], {
            "layout": "horizontal", "views": ["left_back", "right_back"], "include_wrist_camera": False,
        })
        self.assertEqual(config["memory_lifecycle"], {
            "fixed_during_day": True, "updated_memory_applies": "following_day",
        })
        self.assertEqual(config["provenance"]["source_pdf_sha256"], REVIEWED_PDF_SHA256)


if __name__ == "__main__":
    unittest.main()
