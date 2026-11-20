"""Create a local reviewed source copy. Does not create a repo or upload anything."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil

ROOT = Path(__file__).resolve().parents[1]
TOP_FILES = ("README.md", "THIRD_PARTY.md", ".gitignore", ".gitattributes", "pyproject.toml")
DIRECTORIES = ("pam", "tests", "config", "scenarios", "prompts", "tools", "experiments")
DOCS = (
    "docs/논문충실도_검증보고서.md",
    "docs/GitHub_공개안내.md",
    "docs/검증결과_2026-10-25.json",
    "docs/diagrams/pam-fsm-rdt.html",
    "docs/diagrams/pam-fsm-rdt.svg",
    "docs/diagrams/pam-fsm-rdt.png",
)


def build(destination: Path):
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=False)
    files = [ROOT / p for p in (*TOP_FILES, *DOCS)]
    for directory in DIRECTORIES:
        files.extend(p for p in (ROOT / directory).rglob("*")
                     if p.is_file() and "__pycache__" not in p.parts
                     and not p.name.startswith(".env") and p.suffix not in {".pyc", ".key", ".pem"})
    manifest = []
    for source in sorted(files):
        relative = source.relative_to(ROOT)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        manifest.append({"path": relative.as_posix(), "bytes": target.stat().st_size,
                         "sha256": hashlib.sha256(target.read_bytes()).hexdigest()})
    (destination / "snapshot_manifest.json").write_text(json.dumps({
        "purpose": "Reviewed local source snapshot, not uploaded to GitHub",
        "excluded": ["papers", "reference", "data", "artifacts", "records", "presentation", ".venv", "tmp"],
        "files": manifest}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"destination": str(destination), "files": len(manifest),
            "bytes": sum(f["bytes"] for f in manifest), "uploaded": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.output), ensure_ascii=False))
