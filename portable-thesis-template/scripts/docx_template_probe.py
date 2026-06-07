#!/usr/bin/env python3
"""Read-only DOCX template probe for portable thesis template analysis.

This script intentionally parses OOXML directly instead of relying on
python-docx. Some school templates contain stale OLE relationships that make
python-docx fail even though Word can open the document.
"""

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


def attr(node: ET.Element, name: str) -> str | None:
    return node.attrib.get(f"{{{NS['w']}}}{name}")


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


def paragraph_style(para: ET.Element) -> str | None:
    style = para.find("w:pPr/w:pStyle", NS)
    return attr(style, "val") if style is not None else None


def field_instrs(root: ET.Element | None) -> list[str]:
    if root is None:
        return []
    values: list[str] = []
    for instr in root.findall(".//w:instrText", NS):
        if instr.text and instr.text.strip():
            values.append(instr.text.strip())
    for field in root.findall(".//w:fldSimple", NS):
        value = attr(field, "instr")
        if value:
            values.append(value.strip())
    return values


def classify_regions(paragraph_records: list[dict[str, object]]) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    protected: list[dict[str, object]] = []
    editable: list[dict[str, object]] = []
    protected_terms = [
        "原创性声明",
        "版权使用授权书",
        "毕业设计说明书题目",
        "指导教师",
        "密级",
        "目  录",
        "目录",
    ]
    editable_terms = [
        "摘要",
        "abstract",
        "绪论",
        "引言",
        "正文",
        "参考文献",
        "致谢",
        "附录",
    ]

    for record in paragraph_records:
        text = str(record.get("text", "")).strip()
        if not text:
            continue
        lowered = text.lower()
        if any(term in text for term in protected_terms):
            protected.append(
                {
                    "paragraphIndex": record["index"],
                    "evidence": text[:120],
                    "reason": "front-matter-or-generated-section-marker",
                }
            )
        elif any(term in lowered for term in editable_terms):
            editable.append(
                {
                    "paragraphIndex": record["index"],
                    "evidence": text[:120],
                    "reason": "likely-user-content-section-marker",
                }
            )
    return protected[:40], editable[:80]


def table_samples(document: ET.Element | None) -> list[dict[str, object]]:
    if document is None:
        return []
    samples: list[dict[str, object]] = []
    for idx, table in enumerate(document.findall(".//w:tbl", NS)):
        cells: list[str] = []
        for cell in table.findall(".//w:tc", NS)[:12]:
            text = text_of(cell).strip()
            if text:
                cells.append(text[:80])
        samples.append({"index": idx, "sampleCells": cells})
    return samples[:20]


def write_markdown(report: dict[str, object], path: Path) -> None:
    source = report["sourceFiles"]["template"]  # type: ignore[index]
    scan = report["templateScan"]  # type: ignore[assignment]
    req = report["templateRequirements"]  # type: ignore[assignment]
    protected = req.get("protectedRegions", [])  # type: ignore[union-attr]
    editable = req.get("editableRegions", [])  # type: ignore[union-attr]

    lines = [
        "# Template Analysis",
        "",
        f"- Template: `{source['path']}`",
        f"- SHA256: `{source['sha256']}`",
        f"- Size: {source['size']} bytes",
        f"- Modified: {source['mtime']}",
        "",
        "## Structural Scan",
        "",
        f"- Paragraphs: {scan['paragraphCount']}",
        f"- Tables: {scan['tableCount']}",
        f"- Images: {scan['imageCount']}",
        f"- Sections: {scan['sectionCount']}",
        f"- Fields: {scan['fieldCounts']}",
        "",
        "## Protected Region Evidence",
        "",
    ]
    if protected:
        for item in protected[:20]:
            lines.append(f"- p{item['paragraphIndex']}: {item['evidence']}")
    else:
        lines.append("- No protected region markers detected automatically.")

    lines.extend(["", "## Editable Region Evidence", ""])
    if editable:
        for item in editable[:30]:
            lines.append(f"- p{item['paragraphIndex']}: {item['evidence']}")
    else:
        lines.append("- No editable region markers detected automatically.")

    lines.extend(
        [
            "",
            "## Workflow Recommendations",
            "",
            "- Copy the template before editing.",
            "- Treat this probe as evidence; resolve ambiguous regions manually before DOCX sync.",
            "- Preserve front matter, headers, footers, TOC, fields, and bookmarks unless explicitly approved.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--docx", required=True, help="Path to the official template DOCX")
    parser.add_argument("--out", required=True, help="JSON output path")
    parser.add_argument("--markdown-out", help="Optional Markdown summary output path")
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
        paragraph_records = []
        for idx, para in enumerate(paragraphs):
            text = text_of(para).strip()
            if not text:
                continue
            paragraph_records.append(
                {
                    "index": idx,
                    "styleId": paragraph_style(para),
                    "text": text[:500],
                    "fieldInstrs": field_instrs(para),
                }
            )
        protected_regions, editable_regions = classify_regions(paragraph_records)
        instrs = field_instrs(document)

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
                "protectedRegions": protected_regions,
                "editableRegions": editable_regions,
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
                "fieldInstrs": instrs[:80],
                "paragraphs": paragraph_records[:160],
                "tables": table_samples(document),
            },
            "conflicts": [],
            "workflowRecommendations": {
                "markdownChapters": [],
                "docxSync": {
                    "copyTemplateFirst": True,
                    "preserveRegions": protected_regions,
                    "editableRegions": editable_regions,
                },
                "qaChecklist": [],
            },
        }

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.markdown_out:
        write_markdown(report, Path(args.markdown_out).resolve())
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
