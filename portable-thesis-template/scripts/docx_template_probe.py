#!/usr/bin/env python3
"""Read-only DOCX template probe for portable thesis template analysis."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def text_of(node: ET.Element) -> str:
    return "".join(t.text or "" for t in node.findall(".//w:t", NS))


def parse_xml(zf: zipfile.ZipFile, name: str) -> ET.Element | None:
    try:
        return ET.fromstring(zf.read(name))
    except KeyError:
        return None


def style_ids(styles_root: ET.Element | None) -> list[str]:
    if styles_root is None:
        return []
    ids: list[str] = []
    for style in styles_root.findall(".//w:style", NS):
        style_id = style.attrib.get(f"{{{NS['w']}}}styleId")
        name = style.find("w:name", NS)
        label = name.attrib.get(f"{{{NS['w']}}}val") if name is not None else None
        ids.append(f"{style_id}:{label}" if label else str(style_id))
    return sorted(x for x in ids if x)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--docx", required=True, help="Path to the official template DOCX")
    parser.add_argument("--out", required=True, help="JSON output path")
    args = parser.parse_args()

    docx = Path(args.docx).resolve()
    out = Path(args.out).resolve()
    stat = docx.stat()

    with zipfile.ZipFile(docx) as zf:
        names = zf.namelist()
        document = parse_xml(zf, "word/document.xml")
        styles = parse_xml(zf, "word/styles.xml")
        header_names = [n for n in names if re.match(r"word/header\d+\.xml$", n)]
        footer_names = [n for n in names if re.match(r"word/footer\d+\.xml$", n)]

        paragraphs = document.findall(".//w:p", NS) if document is not None else []
        tables = document.findall(".//w:tbl", NS) if document is not None else []
        sample = [text_of(p).strip() for p in paragraphs if text_of(p).strip()]

        report = {
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "sourceFiles": {
                "template": {
                    "path": str(docx),
                    "sha256": sha256(docx),
                    "size": stat.st_size,
                    "mtime": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                },
                "writtenRequirements": [],
            },
            "methodology": [
                "Read-only OOXML probe.",
                "Use explicit template text as authoritative.",
                "Use this probe as evidence, not as the full analysis.",
            ],
            "templateRequirements": {
                "sourcePriority": [
                    "explicit-template-text",
                    "official-handbook",
                    "style-inference",
                ],
                "documentStructure": [],
                "protectedRegions": [],
                "editableRegions": [],
                "pageSetup": {},
                "typography": {},
                "headingRules": {},
                "numberingAndElements": {},
                "referenceRequirements": {},
                "submissionRequirements": {},
            },
            "templateScan": {
                "paragraphCount": len(paragraphs),
                "tableCount": len(tables),
                "imageCount": len([n for n in names if n.startswith("word/media/")]),
                "sectionCount": len(document.findall(".//w:sectPr", NS)) if document is not None else 0,
                "styles": style_ids(styles),
                "headers": header_names,
                "footers": footer_names,
                "fieldCounts": {
                    "fldChar": len(document.findall(".//w:fldChar", NS)) if document is not None else 0,
                    "instrText": len(document.findall(".//w:instrText", NS)) if document is not None else 0,
                    "bookmarkStart": len(document.findall(".//w:bookmarkStart", NS)) if document is not None else 0,
                },
                "sampleParagraphs": sample[:80],
            },
            "conflicts": [],
            "workflowRecommendations": {
                "markdownChapters": [],
                "docxSync": {
                    "copyTemplateFirst": True,
                    "preserveRegions": [],
                    "editableRegions": [],
                },
                "qaChecklist": [],
            },
        }

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
