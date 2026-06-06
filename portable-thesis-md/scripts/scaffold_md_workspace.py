#!/usr/bin/env python3
"""Create a conservative Markdown thesis workspace."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path


DEFAULT_CHAPTERS = [
    "1 Introduction",
    "2 Related Work",
    "3 Requirements and Analysis",
    "4 Design",
    "5 Implementation",
    "6 Testing and Evaluation",
    "7 Conclusion",
]


def slugify(text: str) -> str:
    text = re.sub(r"^\d+\s*", "", text).strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_") or "chapter"


def read_profile(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {
        "schemaVersion": 1,
        "projectName": path.parent.name,
        "workspace": {
            "markdownDir": "thesis_md",
            "figuresDir": "figures",
            "docxDir": "docx",
            "venvDir": ".venv",
        },
        "workflow": {"baselineTagPrefix": "to-docx-", "currentPhase": "drafting"},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--profile", default="thesis-project.json")
    parser.add_argument("--chapters", help="Semicolon-separated chapter headings")
    parser.add_argument("--no-git-init", action="store_true")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    profile_path = root / args.profile
    profile = read_profile(profile_path)
    workspace = profile.setdefault("workspace", {})
    md_dir = root / workspace.setdefault("markdownDir", "thesis_md")
    figures_dir = root / workspace.setdefault("figuresDir", "figures")
    docx_dir = root / workspace.setdefault("docxDir", "docx")
    workflow_dir = root / "workflow"

    for directory in (md_dir, figures_dir, docx_dir, workflow_dir):
        directory.mkdir(parents=True, exist_ok=True)

    chapters = [c.strip() for c in (args.chapters.split(";") if args.chapters else DEFAULT_CHAPTERS) if c.strip()]
    created: list[str] = []
    skipped: list[str] = []
    for index, heading in enumerate(chapters, start=1):
        file_path = md_dir / f"{index:02d}_{slugify(heading)}.md"
        if file_path.exists():
            skipped.append(str(file_path))
            continue
        file_path.write_text(
            f"# {heading}\n\n"
            "<!-- template-notes: fill with school template requirements before final DOCX sync. -->\n\n"
            "## Drafting Notes\n\n"
            "- Draft this chapter from project evidence.\n"
            "- Add figure/table/citation notes required by the template.\n",
            encoding="utf-8",
        )
        created.append(str(file_path))

    for name in ("00_front_matter.md", "references.md", "appendices.md"):
        file_path = md_dir / name
        if not file_path.exists():
            file_path.write_text(f"# {name.removesuffix('.md').replace('_', ' ').title()}\n\n", encoding="utf-8")
            created.append(str(file_path))
        else:
            skipped.append(str(file_path))

    profile.setdefault("workflow", {})["currentPhase"] = "drafting"
    profile_path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")

    if not args.no_git_init and not (root / ".git").exists():
        subprocess.run(["git", "init"], cwd=root, check=False)

    print(json.dumps({"created": created, "skipped": skipped, "profile": str(profile_path)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
