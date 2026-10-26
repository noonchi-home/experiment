"""Reproduce the seven printed PAM prompts without rewriting their wording.

Only --write changes files. --check compares the committed prompt artifacts to
the supplied PDF and checks the source map. This does not call a model.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

import fitz


SOURCE_PATH = "papers/2610.21211v1.pdf"
SOURCE_SHA256 = "1fe0e4954d4fefaffb1e9d1619a2e52e1918b2872ca789485ec437e95f82a364"
SPECS = (
    ("predictor_no_memory", "E.1", (31,)),
    ("predictor_list", "E.2", (32,)),
    ("predictor_fsm", "E.3", (33, 34)),
    ("reflector_list_build", "F.1", (34, 35)),
    ("reflector_list_update", "F.2", (35, 36, 37)),
    ("reflector_fsm_build", "F.3", (37, 38)),
    ("reflector_fsm_update", "F.4", (38, 39, 40)),
)
PROMPT_FONT = "SFTT0900"
PROMPT_MATH_FONT = "CMSY9"
PRINTED_CHARACTER_WIDTH = 4.706
PRINTED_LEFT_EDGE = 108.0
EXTRACTOR_VERSION = 1


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def non_whitespace(text: str) -> str:
    """Used only for independent verification, never to rewrite a prompt."""
    return re.sub(r"\s+", "", text)


def page_lines(page: fitz.Page) -> list[dict]:
    lines = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            spans = line["spans"]
            lines.append(
                {
                    "text": "".join(span["text"] for span in spans),
                    "bbox": line["bbox"],
                    "fonts": {span["font"] for span in spans},
                    "baseline": spans[0]["origin"][1],
                }
            )
    # MuPDF can split one physical row into separate line objects when a
    # monospace JSON value is aligned beyond its key. Rejoin those fragments
    # using the printed x positions instead of inventing a newline between them.
    rows = []
    for line in sorted(lines, key=lambda item: (round(item["baseline"], 2), item["bbox"][0])):
        if not rows or abs(rows[-1]["baseline"] - line["baseline"]) > 0.25:
            rows.append(dict(line))
            continue
        row = rows[-1]
        gap = max(0, round((line["bbox"][0] - row["bbox"][2]) / PRINTED_CHARACTER_WIDTH))
        row["text"] += " " * gap + line["text"]
        row["bbox"] = (
            min(row["bbox"][0], line["bbox"][0]),
            min(row["bbox"][1], line["bbox"][1]),
            max(row["bbox"][2], line["bbox"][2]),
            max(row["bbox"][3], line["bbox"][3]),
        )
        row["fonts"] = row["fonts"] | line["fonts"]
    return rows


def extract(root: Path) -> tuple[dict[str, str], dict]:
    """Return the printed prompt text and source metadata; no filesystem writes."""
    pdf_path = root / SOURCE_PATH
    pdf_bytes = pdf_path.read_bytes()
    if sha256(pdf_bytes) != SOURCE_SHA256:
        raise ValueError("The source PDF differs from the reviewed version; review before extracting.")

    outputs = {}
    source_map = {
        "schema_version": 1,
        "source_pdf": {"path": SOURCE_PATH, "sha256": SOURCE_SHA256, "page_count": 40},
        "extractor": {
            "path": "tools/extract_paper_prompts.py",
            "version": EXTRACTOR_VERSION,
            "engine": "PyMuPDF",
            "validated_version": fitz.VersionBind,
            "text_encoding": "UTF-8",
            "newline": "LF",
        },
        "prompts": {},
        "preserved_printed_quirks": [
            "E.1/E.2/E.3 retain the printed 'sampled at 1 fps' wording; actual input stride is 2 seconds (p.31 introduction and A.2).",
            "Reflector prompts retain the printed (*@\\textbar@*) marker and printed punctuation, including the en-dash/hyphen sequence.",
            "Printed line wrapping and placeholder text are retained; the example output blocks are templates, not standalone valid JSON documents.",
        ],
    }

    with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
        if len(document) != 40:
            raise ValueError("Expected the reviewed 40-page source PDF.")
        for prompt_id, section, pages in SPECS:
            printed_lines = []
            regions = []
            independent_text = []
            for page_number in pages:
                page = document[page_number - 1]
                lines = page_lines(page)
                lower = 0.0
                upper = page.rect.height
                if page_number == pages[0]:
                    headings = [line for line in lines if line["text"].startswith(section)]
                    if len(headings) != 1:
                        raise ValueError(f"Cannot identify heading {section} on page {page_number}.")
                    lower = headings[0]["bbox"][3]
                later_headings = [
                    line for line in lines
                    if re.match(r"[EF]\.\d(?:\s|[A-Z]|$)", line["text"])
                    and line["bbox"][1] > lower
                ]
                if later_headings:
                    upper = min(line["bbox"][1] for line in later_headings)
                selected = [
                    line for line in lines
                    if line["bbox"][1] >= lower
                    and line["bbox"][3] <= upper
                    and line["fonts"] & {PROMPT_FONT, PROMPT_MATH_FONT}
                ]
                if not selected:
                    raise ValueError(f"Empty prompt region for {prompt_id}, page {page_number}.")

                # All prompt letters and inline mathematical arrows must survive.
                # Vertical blank lines and indentation are recovered from the PDF
                # geometry. Page breaks do not create artificial blank paragraphs.
                previous_baseline = None
                for line in selected:
                    if previous_baseline is not None and line["baseline"] - previous_baseline > 15:
                        printed_lines.append("")
                    indent = max(0, round((line["bbox"][0] - PRINTED_LEFT_EDGE) / PRINTED_CHARACTER_WIDTH))
                    printed_lines.append(" " * indent + line["text"].rstrip())
                    previous_baseline = line["baseline"]

                bounds = [
                    min(line["bbox"][0] for line in selected),
                    min(line["bbox"][1] for line in selected),
                    max(line["bbox"][2] for line in selected),
                    max(line["bbox"][3] for line in selected),
                ]
                # Independent plain-text extraction checks that filtering fonts
                # and recovering layout has not omitted or rearranged any token.
                clip = fitz.Rect(bounds) + (-0.25, -0.25, 0.25, 0.25)
                independent = page.get_text("text", clip=clip, sort=False)
                selected_text = "\n".join(line["text"] for line in selected)
                if non_whitespace(independent) != non_whitespace(selected_text):
                    raise ValueError(f"Independent PDF token comparison failed for {prompt_id}, page {page_number}.")
                independent_text.append(independent)
                regions.append({"page": page_number, "bbox": [round(value, 4) for value in bounds]})

            body = "\n".join(printed_lines).strip() + "\n"
            if not body.startswith("You are ") or not body.rstrip().endswith("}"):
                raise ValueError(f"Incomplete start or output schema in {prompt_id}.")
            if non_whitespace(body) != non_whitespace("\n".join(independent_text)):
                raise ValueError(f"Cross-page token comparison failed for {prompt_id}.")
            outputs[prompt_id] = body
            source_map["prompts"][prompt_id] = {
                "file": f"prompts/paper/{prompt_id}.txt",
                "pages": list(pages),
                "section": section,
                "sha256": sha256(body.encode("utf-8")),
                "non_whitespace_sha256": sha256(non_whitespace(body).encode("utf-8")),
                "placeholders": sorted(set(re.findall(r"\{([a-z][a-z0-9_]*)\}", body))),
                "regions": regions,
                "cleanup": [
                    "Selected the printed monospace prompt listing within its appendix section; excluded section headings, explanatory prose, and page footers.",
                    "Rejoined PDF fragments on the same printed baseline and recovered indentation/blank-line spacing from coordinates; retained printed line wrapping and joined page continuations with one LF.",
                    "Removed trailing whitespace and wrote UTF-8/LF with a final newline; no wording, symbol, model instruction, or scenario was changed.",
                ],
            }
    return outputs, source_map


def check(root: Path) -> list[str]:
    outputs, generated_map = extract(root)
    errors = []
    map_path = root / "prompts/source_map.json"
    if not map_path.is_file():
        return ["Missing prompts/source_map.json"]
    stored_map = json.loads(map_path.read_text(encoding="utf-8"))
    # A runtime version difference alone is not a content change. Provenance keeps
    # the version that wrote the artifacts, while all resulting text is rechecked.
    generated_map["extractor"]["validated_version"] = stored_map["extractor"]["validated_version"]
    if stored_map != generated_map:
        errors.append("Source map differs from the reviewed PDF extraction.")
    for prompt_id, body in outputs.items():
        path = root / generated_map["prompts"][prompt_id]["file"]
        if not path.is_file() or path.read_bytes() != body.encode("utf-8"):
            errors.append(f"Source prompt mismatch: {prompt_id}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="Write source prompts and source_map.json.")
    mode.add_argument("--check", action="store_true", help="Verify source prompts without writing.")
    args = parser.parse_args()
    root = args.root.resolve()
    if args.write:
        outputs, source_map = extract(root)
        for prompt_id, body in outputs.items():
            path = root / source_map["prompts"][prompt_id]["file"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body.encode("utf-8"))
        (root / "prompts/source_map.json").write_bytes(
            (json.dumps(source_map, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        )
        print(f"Wrote {len(outputs)} source prompts; no model inference was run.")
        return 0
    errors = check(root)
    for error in errors:
        print(error)
    print("PASS: seven prompts match the source PDF." if not errors else "FAIL: source verification failed.")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
