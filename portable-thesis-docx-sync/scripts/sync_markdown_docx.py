#!/usr/bin/env python3
"""Conservative Markdown-to-DOCX sync helper for template-based thesis drafts.

Default mode writes a plan only. Use --apply with an explicit insertion mode to
write a DOCX copy. This helper is intentionally conservative; agents should
patch this bundled script when behavior must become reusable instead of writing
one-off scripts in the thesis project root.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from lxml import etree

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{W_NS}}}"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path | None) -> dict[str, object]:
    if path is None or not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_from_profile(root: Path, profile: dict[str, object], dotted: str) -> Path | None:
    cur: object = profile
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    if not isinstance(cur, str) or not cur:
        return None
    path = Path(cur)
    return path if path.is_absolute() else root / path


def text_run(text: str) -> etree._Element:
    run = etree.Element(f"{W}r")
    t = etree.SubElement(run, f"{W}t")
    t.set(XML_SPACE, "preserve")
    t.text = text
    return run


def paragraph(text: str, style: str | None = None) -> etree._Element:
    para = etree.Element(f"{W}p")
    if style:
        props = etree.SubElement(para, f"{W}pPr")
        pstyle = etree.SubElement(props, f"{W}pStyle")
        pstyle.set(f"{W}val", style)
    para.append(text_run(text))
    return para


def markdown_blocks(md_dir: Path) -> list[dict[str, object]]:
    blocks: list[dict[str, object]] = []
    for path in sorted(md_dir.glob("*.md")):
        if path.name.lower() in {"readme.md"}:
            continue
        in_code = False
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.rstrip()
            if line.startswith("```"):
                in_code = not in_code
                continue
            if in_code or not line.strip() or line.lstrip().startswith("<!--"):
                continue
            if line.startswith(">"):
                continue
            heading = re.match(r"^(#{1,6})\s+(.+)$", line)
            if heading:
                blocks.append(
                    {
                        "source": str(path),
                        "type": "heading",
                        "level": len(heading.group(1)),
                        "text": heading.group(2).strip(),
                    }
                )
            elif line.startswith("|"):
                blocks.append({"source": str(path), "type": "table-text", "text": line.strip()})
            else:
                blocks.append({"source": str(path), "type": "paragraph", "text": line.strip()})
    return blocks


def block_to_para(block: dict[str, object], styles: dict[str, str]) -> etree._Element:
    text = str(block["text"])
    if block["type"] == "heading":
        level = int(block["level"])
        style = styles.get(f"heading{level}") or styles.get("heading") or "Heading1"
        return paragraph(text, style)
    if block["type"] == "table-text":
        return paragraph(text, styles.get("tableText") or styles.get("normal") or "Normal")
    return paragraph(text, styles.get("normal") or "Normal")


def default_style_map(analysis: dict[str, object]) -> dict[str, str]:
    styles = {"heading1": "Heading1", "heading2": "Heading2", "heading3": "Heading3", "normal": "Normal"}
    scan = analysis.get("templateScan")
    if isinstance(scan, dict):
        all_styles = scan.get("styles")
        if isinstance(all_styles, list):
            for item in all_styles:
                value = str(item)
                lower = value.lower()
                style_id = value.split(":", 1)[0]
                if "normal" in lower:
                    styles["normal"] = style_id
                elif "heading 1" in lower or "标题 1" in lower:
                    styles["heading1"] = style_id
                elif "heading 2" in lower or "标题 2" in lower:
                    styles["heading2"] = style_id
                elif "heading 3" in lower or "标题 3" in lower:
                    styles["heading3"] = style_id
    return styles


def insertion_index(body: etree._Element, mode: str, anchor_text: str | None) -> int:
    children = list(body)
    if mode == "append-before-sectpr":
        for idx, child in enumerate(children):
            if child.tag == f"{W}sectPr":
                return idx
        return len(children)
    if mode == "after-anchor":
        if not anchor_text:
            raise ValueError("--anchor-text is required for --insert-mode after-anchor")
        for idx, child in enumerate(children):
            if child.tag != f"{W}p":
                continue
            text = "".join(t.text or "" for t in child.iter(f"{W}t"))
            if anchor_text in text:
                return idx + 1
        raise ValueError(f"Anchor text not found: {anchor_text}")
    raise ValueError(f"Unsupported insert mode: {mode}")


def apply_sync(template: Path, output: Path, blocks: list[dict[str, object]], styles: dict[str, str], mode: str, anchor_text: str | None) -> None:
    shutil.copy2(template, output)
    with zipfile.ZipFile(template, "r") as zin:
        root = etree.fromstring(zin.read("word/document.xml"))
        body = root.find(f"{W}body")
        if body is None:
            raise ValueError("word/document.xml has no w:body")
        idx = insertion_index(body, mode, anchor_text)
        for offset, block in enumerate(blocks):
            body.insert(idx + offset, block_to_para(block, styles))
        new_xml = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                if item.filename == "word/document.xml":
                    zout.writestr(item, new_xml)
                else:
                    zout.writestr(item, zin.read(item.filename))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".", help="Thesis project root")
    parser.add_argument("--profile", default="thesis-project.json", help="Project profile path")
    parser.add_argument("--template", help="Template/source DOCX path")
    parser.add_argument("--markdown-dir", help="Markdown source directory")
    parser.add_argument("--analysis", help="Template analysis JSON path")
    parser.add_argument("--out", help="Output DOCX path")
    parser.add_argument("--plan-out", help="Plan/sidecar JSON path")
    parser.add_argument("--apply", action="store_true", help="Write output DOCX")
    parser.add_argument("--insert-mode", choices=["append-before-sectpr", "after-anchor"], default="append-before-sectpr")
    parser.add_argument("--anchor-text", help="Anchor text for --insert-mode after-anchor")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    profile_path = Path(args.profile)
    if not profile_path.is_absolute():
        profile_path = root / profile_path
    profile = load_json(profile_path)

    template = Path(args.template).resolve() if args.template else resolve_from_profile(root, profile, "template.sourceDocx")
    md_dir = Path(args.markdown_dir).resolve() if args.markdown_dir else resolve_from_profile(root, profile, "workspace.markdownDir")
    analysis_path = Path(args.analysis).resolve() if args.analysis else resolve_from_profile(root, profile, "template.analysisJson")
    analysis = load_json(analysis_path)
    if template is None or md_dir is None:
        raise SystemExit("Template and markdown directory must be provided or present in thesis-project.json.")
    if not template.exists():
        raise SystemExit(f"Template not found: {template}")
    if not md_dir.exists():
        raise SystemExit(f"Markdown directory not found: {md_dir}")

    docx_dir = resolve_from_profile(root, profile, "workspace.docxDir") or root / "docx"
    output = Path(args.out).resolve() if args.out else docx_dir / f"{template.stem}_draft_{sha256(template)[:8]}.docx"
    plan_out = Path(args.plan_out).resolve() if args.plan_out else output.with_suffix(output.suffix + ".sync.json")
    blocks = markdown_blocks(md_dir)
    styles = default_style_map(analysis)
    plan = {
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "mode": "apply" if args.apply else "plan",
        "sourceDocx": {"path": str(template), "sha256": sha256(template), "size": template.stat().st_size},
        "markdownDir": str(md_dir),
        "analysisJson": str(analysis_path) if analysis_path else None,
        "outputDocx": str(output),
        "insertMode": args.insert_mode,
        "anchorText": args.anchor_text,
        "blockCount": len(blocks),
        "styles": styles,
        "manualConfirm": [] if args.apply else ["Review insertion mode and style mapping before --apply."],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    plan_out.parent.mkdir(parents=True, exist_ok=True)
    if args.apply:
        apply_sync(template, output, blocks, styles, args.insert_mode, args.anchor_text)
        plan["outputSha256"] = sha256(output)
        plan["outputSize"] = output.stat().st_size
    plan_out.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    print(plan_out)
    if args.apply:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
