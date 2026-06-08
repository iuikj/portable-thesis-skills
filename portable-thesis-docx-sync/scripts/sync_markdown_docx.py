#!/usr/bin/env python3
"""Conservative Markdown-to-DOCX sync helper for template-based thesis drafts.

Default mode writes a plan only. Use --apply to write a DOCX copy. The initial
DOCX path uses a template-body replacement strategy: preserve front matter,
replace abstract/body/reference regions, and fail the quality gate if stale
template/sample content or visible Markdown syntax remains.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import stat
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from lxml import etree

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{W_NS}}}"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"

INLINE_TOKEN_RE = re.compile(
    r"(!\[[^\]]*\]\([^)]+\)|`[^`]+`|\*\*[^*\n]+\*\*|__[^_\n]+__|"
    r"(?<![\w*])\*[^*\s][^*\n]*?\*(?![\w*])|(?<![\w_])_[^_\s][^_\n]*?_(?![\w_])|"
    r"~~[^~\n]+~~|\[[^\]]+\]\([^)]+\))"
)
MARKDOWN_RESIDUE_RE = re.compile(
    r"(\*\*[^*\n]+\*\*|__[^_\n]+__|(?<![\w*])\*[^*\s][^*\n]*?\*(?![\w*])|"
    r"(?<![\w_])_[^_\s][^_\n]*?_(?![\w_])|`[^`]+`|!\[[^\]]*\]\([^)]+\)|"
    r"\[[^\]]+\]\([^)]+\)|~~[^~\n]+~~|^\s*\$\$\s*$|^```)"
)
VISIBLE_MARKDOWN_RESIDUE_RE = re.compile(
    r"(\*\*[^*\n]+\*\*|__[^_\n]+__|`[^`]+`|!\[[^\]]*\]\([^)]+\)|"
    r"\[[^\]]+\]\([^)]+\)|~~[^~\n]+~~|^\s*\$\$\s*$|^```|"
    r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$)"
)
TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$")
BODY_LABEL_RE = re.compile(r"(?:如图|如表|见图|见表|图|表)\s*\d+\s*[-.]\s*\d+")
CAPTION_RE = re.compile(r"^\s*(?:图|表|算法|Figure|Table|Algorithm)\s*\d+\s*[-.]\s*\d+")

STALE_TEMPLATE_TERMS = [
    "正文要求",
    "Corpus表",
    "SSCE模块",
    "XL-MHA-BiLSTM",
    "XHU Video",
    "首页模块",
    "课程模块",
    "购物商城模块",
    "以下的表1-1和图1-1为表和图的示例",
    "文献类型和标志代码对照表",
]


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


def text_of(node: etree._Element) -> str:
    return "".join(t.text or "" for t in node.iter(f"{W}t"))


def text_run(
    text: str,
    *,
    bold: bool = False,
    italic: bool = False,
    code: bool = False,
    strike: bool = False,
    superscript: bool = False,
) -> etree._Element:
    run = etree.Element(f"{W}r")
    if bold or italic or code or strike or superscript:
        props = etree.SubElement(run, f"{W}rPr")
        if bold:
            etree.SubElement(props, f"{W}b")
        if italic:
            etree.SubElement(props, f"{W}i")
        if code:
            font = etree.SubElement(props, f"{W}rFonts")
            font.set(f"{W}ascii", "Consolas")
            font.set(f"{W}hAnsi", "Consolas")
        if strike:
            etree.SubElement(props, f"{W}strike")
        if superscript:
            vert = etree.SubElement(props, f"{W}vertAlign")
            vert.set(f"{W}val", "superscript")
    t = etree.SubElement(run, f"{W}t")
    t.set(XML_SPACE, "preserve")
    t.text = text
    return run


def add_paragraph_props(
    para: etree._Element,
    style: str | None,
    *,
    first_line_chars: int | None = None,
    line_twips: int | None = None,
    align: str | None = None,
) -> None:
    if not any([style, first_line_chars, line_twips, align]):
        return
    props = etree.SubElement(para, f"{W}pPr")
    if style:
        pstyle = etree.SubElement(props, f"{W}pStyle")
        pstyle.set(f"{W}val", style)
    if align:
        jc = etree.SubElement(props, f"{W}jc")
        jc.set(f"{W}val", align)
    if line_twips:
        spacing = etree.SubElement(props, f"{W}spacing")
        spacing.set(f"{W}line", str(line_twips))
        spacing.set(f"{W}lineRule", "exact")
    if first_line_chars:
        indent = etree.SubElement(props, f"{W}ind")
        indent.set(f"{W}firstLineChars", str(first_line_chars))
        indent.set(f"{W}firstLine", "480")


def inline_runs(markdown_text: str) -> list[etree._Element]:
    runs: list[etree._Element] = []
    pos = 0
    for match in INLINE_TOKEN_RE.finditer(markdown_text):
        if match.start() > pos:
            runs.append(text_run(markdown_text[pos : match.start()]))
        token = match.group(0)
        if token.startswith("**") and token.endswith("**"):
            runs.append(text_run(token[2:-2], bold=True))
        elif token.startswith("__") and token.endswith("__"):
            runs.append(text_run(token[2:-2], bold=True))
        elif token.startswith("*") and token.endswith("*"):
            runs.append(text_run(token[1:-1], italic=True))
        elif token.startswith("_") and token.endswith("_"):
            runs.append(text_run(token[1:-1], italic=True))
        elif token.startswith("`") and token.endswith("`"):
            runs.append(text_run(token[1:-1], code=True))
        elif token.startswith("~~") and token.endswith("~~"):
            runs.append(text_run(token[2:-2], strike=True))
        elif token.startswith("!["):
            image = re.match(r"!\[([^\]]*)\]\(([^)]+)\)", token)
            alt = image.group(1).strip() if image else ""
            target = image.group(2).strip() if image else ""
            label = alt or Path(target).name or "image"
            runs.append(text_run(f"[Image: {label}]"))
        else:
            link = re.match(r"\[([^\]]+)\]\(([^)]+)\)", token)
            runs.append(text_run(link.group(1) if link else token))
        pos = match.end()
    if pos < len(markdown_text):
        runs.append(text_run(markdown_text[pos:]))
    return runs or [text_run("")]


def paragraph(
    text: str,
    style: str | None = None,
    *,
    first_line_chars: int | None = None,
    line_twips: int | None = None,
    align: str | None = None,
    code: bool = False,
) -> etree._Element:
    para = etree.Element(f"{W}p")
    add_paragraph_props(para, style, first_line_chars=first_line_chars, line_twips=line_twips, align=align)
    if code:
        para.append(text_run(text, code=True))
    else:
        for run in inline_runs(text):
            para.append(run)
    return para


def table_block(rows: list[list[str]], styles: dict[str, str]) -> etree._Element:
    cols = max((len(r) for r in rows), default=1)
    tbl = etree.Element(f"{W}tbl")
    tbl_pr = etree.SubElement(tbl, f"{W}tblPr")
    tbl_w = etree.SubElement(tbl_pr, f"{W}tblW")
    tbl_w.set(f"{W}w", "0")
    tbl_w.set(f"{W}type", "auto")
    borders = etree.SubElement(tbl_pr, f"{W}tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        border = etree.SubElement(borders, f"{W}{edge}")
        border.set(f"{W}val", "single")
        border.set(f"{W}sz", "4")
        border.set(f"{W}space", "0")
        border.set(f"{W}color", "auto")
    grid = etree.SubElement(tbl, f"{W}tblGrid")
    for _ in range(cols):
        col = etree.SubElement(grid, f"{W}gridCol")
        col.set(f"{W}w", str(max(1200, 9000 // cols)))
    for row_idx, row_cells in enumerate(rows):
        tr = etree.SubElement(tbl, f"{W}tr")
        for col_idx in range(cols):
            tc = etree.SubElement(tr, f"{W}tc")
            tc_pr = etree.SubElement(tc, f"{W}tcPr")
            tc_w = etree.SubElement(tc_pr, f"{W}tcW")
            tc_w.set(f"{W}w", str(max(1200, 9000 // cols)))
            tc_w.set(f"{W}type", "dxa")
            value = row_cells[col_idx] if col_idx < len(row_cells) else ""
            p = paragraph(value, styles.get("normal"), line_twips=400, align="center" if row_idx == 0 else None)
            tc.append(p)
    return tbl


def parse_md_table(lines: list[str], start: int) -> tuple[dict[str, object] | None, int]:
    if start + 1 >= len(lines):
        return None, start
    first = lines[start].strip()
    second = lines[start + 1].strip()
    if not first.startswith("|") or not TABLE_SEPARATOR_RE.match(second):
        return None, start
    rows: list[list[str]] = []
    idx = start
    while idx < len(lines) and lines[idx].strip().startswith("|"):
        if not TABLE_SEPARATOR_RE.match(lines[idx]):
            rows.append([cell.strip() for cell in lines[idx].strip().strip("|").split("|")])
        idx += 1
    return {"type": "table", "rows": rows}, idx


def markdown_blocks(md_dir: Path) -> list[dict[str, object]]:
    blocks: list[dict[str, object]] = []
    for path in sorted(md_dir.glob("*.md")):
        if path.name.lower() in {"readme.md"}:
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        idx = 0
        in_code = False
        code_lang = ""
        code_lines: list[str] = []
        in_math = False
        math_lines: list[str] = []
        while idx < len(lines):
            raw = lines[idx]
            line = raw.rstrip()
            stripped = line.strip()

            if in_code:
                if stripped.startswith("```"):
                    blocks.append(
                        {"source": str(path), "type": "code", "language": code_lang, "text": "\n".join(code_lines)}
                    )
                    in_code = False
                    code_lang = ""
                    code_lines = []
                else:
                    code_lines.append(raw.rstrip("\n"))
                idx += 1
                continue

            if in_math:
                if stripped == "$$":
                    blocks.append({"source": str(path), "type": "math", "text": " ".join(x.strip() for x in math_lines)})
                    in_math = False
                    math_lines = []
                else:
                    math_lines.append(line)
                idx += 1
                continue

            if stripped.startswith("```"):
                in_code = True
                code_lang = stripped.strip("`").strip()
                idx += 1
                continue
            if stripped == "$$":
                in_math = True
                idx += 1
                continue
            if not stripped or stripped == "---" or stripped.startswith("<!--") or stripped.startswith(">"):
                idx += 1
                continue

            table, next_idx = parse_md_table(lines, idx)
            if table is not None:
                table["source"] = str(path)
                blocks.append(table)
                idx = next_idx
                continue

            heading = re.match(r"^(#{1,6})\s+(.+)$", line)
            unordered = re.match(r"^\s*[-*+]\s+(.+)$", line)
            ordered = re.match(r"^\s*\d+[.)]\s+(.+)$", line)
            if heading:
                blocks.append(
                    {
                        "source": str(path),
                        "type": "heading",
                        "level": len(heading.group(1)),
                        "text": heading.group(2).strip(),
                    }
                )
            elif unordered:
                blocks.append({"source": str(path), "type": "list-item", "text": unordered.group(1).strip()})
            elif ordered:
                blocks.append({"source": str(path), "type": "ordered-list-item", "text": ordered.group(1).strip()})
            else:
                blocks.append({"source": str(path), "type": "paragraph", "text": line.strip()})
            idx += 1

        if in_code and code_lines:
            blocks.append({"source": str(path), "type": "code", "language": code_lang, "text": "\n".join(code_lines)})
        if in_math and math_lines:
            blocks.append({"source": str(path), "type": "math", "text": " ".join(x.strip() for x in math_lines)})
    return blocks


def split_front_matter(blocks: list[dict[str, object]]) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    zh: list[dict[str, object]] = []
    en: list[dict[str, object]] = []
    body: list[dict[str, object]] = []
    refs: list[dict[str, object]] = []
    ack: list[dict[str, object]] = []
    section = "body"
    for block in blocks:
        text = str(block.get("text", "")).strip()
        if block.get("type") == "heading":
            normalized = re.sub(r"\s+", "", text).lower()
            if normalized in {"摘要", "摘  要".replace(" ", "")}:
                section = "zh"
                continue
            if normalized == "abstract":
                section = "en"
                continue
            if normalized in {"参考文献", "references"}:
                section = "refs"
                refs.append({**block, "level": 1, "text": "参考文献"})
                continue
            if normalized in {"致谢", "致  谢".replace(" ", ""), "acknowledgements", "acknowledgments"}:
                section = "ack"
                ack.append({**block, "level": 1, "text": "致  谢"})
                continue
            if section in {"zh", "en"}:
                section = "body"
        if section == "zh":
            zh.append(block)
        elif section == "en":
            en.append(block)
        elif section == "refs":
            refs.append(block)
        elif section == "ack":
            ack.append(block)
        else:
            body.append(block)
    return zh, en, body, refs, ack


def markdown_residue(blocks: list[dict[str, object]]) -> list[dict[str, object]]:
    residue: list[dict[str, object]] = []
    for block in blocks:
        text = str(block.get("text", ""))
        if not text:
            continue
        matches = [m.group(0) for m in MARKDOWN_RESIDUE_RE.finditer(text)]
        if matches:
            residue.append({"source": block.get("source"), "type": block.get("type"), "matches": matches[:10], "text": text[:200]})
    return residue


def parse_styles(analysis: dict[str, object]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    scan = analysis.get("templateScan")
    if isinstance(scan, dict):
        all_styles = scan.get("styles")
        if isinstance(all_styles, list):
            for item in all_styles:
                value = str(item)
                if ":" not in value:
                    continue
                style_id, name = value.split(":", 1)
                parsed[name.strip().lower()] = style_id
    return parsed


def style_by_names(parsed: dict[str, str], names: Iterable[str], fallback: str) -> str:
    for name in names:
        key = name.strip().lower()
        if key in parsed:
            return parsed[key]
    return fallback


def default_style_map(analysis: dict[str, object]) -> dict[str, str]:
    parsed = parse_styles(analysis)
    return {
        "normal": style_by_names(parsed, ["Normal"], "Normal"),
        "abstractTitle": style_by_names(parsed, ["heading 1", "标题 1"], style_by_names(parsed, ["Title"], "Heading1")),
        "heading1": style_by_names(parsed, ["Title", "MyStyle_1级", "heading 1", "标题 1"], "Heading1"),
        "heading2": style_by_names(parsed, ["节(论文)", "heading 2", "标题 2"], "Heading2"),
        "heading3": style_by_names(parsed, ["小节(论文)", "heading 3", "标题 3"], "Heading3"),
        "heading4": style_by_names(parsed, ["小小节(论文)", "heading 4", "标题 4"], "Heading4"),
        "conclusion": style_by_names(parsed, ["结语等(论文)", "Title"], "Heading1"),
    }


def block_to_elements(block: dict[str, object], styles: dict[str, str]) -> list[etree._Element]:
    block_type = str(block["type"])
    text = str(block.get("text", ""))
    if block_type == "heading":
        level = int(block.get("level", 1))
        text = normalize_heading_text(text)
        style = styles.get(f"heading{min(level, 4)}") or styles.get("heading3") or "Heading1"
        if text in {"参考文献", "致  谢"}:
            style = styles.get("conclusion") or style
        return [paragraph(text, style, line_twips=400)]
    if block_type == "table":
        rows = block.get("rows", [])
        return [table_block(rows if isinstance(rows, list) else [], styles)]
    if block_type == "code":
        elements = []
        for line in text.splitlines() or [""]:
            elements.append(paragraph(line, styles.get("normal"), line_twips=360, code=True))
        return elements
    if block_type == "math":
        return [paragraph(text, styles.get("normal"), line_twips=400, align="center")]
    if block_type in {"list-item", "ordered-list-item"}:
        return [paragraph(text, styles.get("normal"), line_twips=400)]
    if CAPTION_RE.search(text):
        return [paragraph(text, styles.get("normal"), line_twips=400, align="center")]
    return [paragraph(text, styles.get("normal"), first_line_chars=200, line_twips=400, align="both")]


def normalize_heading_text(text: str) -> str:
    stripped = text.strip()
    match = re.match(r"^第\s*(\d+)\s*章\s+(.+)$", stripped)
    if match:
        return f"{match.group(1)}  {match.group(2).strip()}"
    return stripped


def abstract_elements(title: str, blocks: list[dict[str, object]], styles: dict[str, str]) -> list[etree._Element]:
    elements = [paragraph(title, styles.get("abstractTitle") or styles.get("heading1"), line_twips=400, align="center")]
    for block in blocks:
        block_type = str(block.get("type"))
        text = str(block.get("text", "")).strip()
        if not text:
            continue
        is_keyword = text.lower().startswith("keywords") or text.startswith("关键词")
        if block_type == "table":
            elements.extend(block_to_elements(block, styles))
        else:
            elements.append(
                paragraph(
                    text,
                    styles.get("normal"),
                    first_line_chars=None if is_keyword else 200,
                    line_twips=400,
                    align=None if is_keyword else "both",
                )
            )
    return elements


def toc_placeholder_elements(styles: dict[str, str]) -> list[etree._Element]:
    title = paragraph("目 录", styles.get("abstractTitle") or styles.get("heading1"), line_twips=400, align="center")
    field_para = etree.Element(f"{W}p")
    add_paragraph_props(field_para, styles.get("normal"), line_twips=400)
    for child in [
        _fld_char("begin"),
        _instr_text(' TOC \\o "1-3" \\h \\z \\u '),
        _fld_char("separate"),
        text_run("（在 Word 中更新域以生成目录）"),
        _fld_char("end"),
    ]:
        field_para.append(child)
    return [title, field_para]


def _fld_char(kind: str) -> etree._Element:
    run = etree.Element(f"{W}r")
    fld = etree.SubElement(run, f"{W}fldChar")
    fld.set(f"{W}fldCharType", kind)
    return run


def _instr_text(text: str) -> etree._Element:
    run = etree.Element(f"{W}r")
    instr = etree.SubElement(run, f"{W}instrText")
    instr.set(XML_SPACE, "preserve")
    instr.text = text
    return run


def first_block_index_with(body: etree._Element, markers: list[str], start: int = 0) -> int | None:
    children = list(body)
    for idx in range(start, len(children)):
        text = text_of(children[idx]).strip()
        if any(marker.lower() in text.lower() for marker in markers):
            return idx
    return None


def replace_start_index(body: etree._Element) -> int:
    auth_idx = first_block_index_with(body, ["版权使用授权书"])
    search_from = auth_idx + 1 if auth_idx is not None else 0
    abstract_idx = first_block_index_with(body, ["摘  要", "摘要", "Abstract"], search_from)
    if abstract_idx is not None:
        return abstract_idx
    toc_idx = first_block_index_with(body, ["目 录", "目录"], search_from)
    if toc_idx is not None:
        return toc_idx
    raise ValueError("Could not locate abstract/TOC start. Use --insert-mode after-anchor or inspect template analysis.")


def replace_end_index(body: etree._Element) -> int:
    children = list(body)
    for idx, child in enumerate(children):
        if child.tag == f"{W}sectPr":
            return idx
    return len(children)


def cleanup_unpaired_bookmarks(root: etree._Element) -> list[dict[str, object]]:
    """Remove bookmark endpoints left unpaired after replacing a template range."""
    starts: dict[str, list[etree._Element]] = {}
    ends: dict[str, list[etree._Element]] = {}
    for node in root.iter(f"{W}bookmarkStart"):
        bid = node.get(f"{W}id")
        if bid is not None:
            starts.setdefault(bid, []).append(node)
    for node in root.iter(f"{W}bookmarkEnd"):
        bid = node.get(f"{W}id")
        if bid is not None:
            ends.setdefault(bid, []).append(node)

    removed: list[dict[str, object]] = []
    for bid in sorted(set(starts) ^ set(ends), key=lambda x: int(x) if x.isdigit() else 999999):
        nodes = starts.get(bid) or ends.get(bid) or []
        endpoint = "start" if bid in starts else "end"
        name = starts.get(bid, [{}])[0].get(f"{W}name") if starts.get(bid) else None
        for node in nodes:
            parent = node.getparent()
            if parent is not None:
                parent.remove(node)
        removed.append({"bookmarkId": bid, "name": name, "removedEndpoint": endpoint})
    return removed


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
            if anchor_text in text_of(child):
                return idx + 1
        raise ValueError(f"Anchor text not found: {anchor_text}")
    raise ValueError(f"Unsupported insert mode: {mode}")


def build_replacement_elements(blocks: list[dict[str, object]], styles: dict[str, str]) -> tuple[list[etree._Element], list[dict[str, object]]]:
    zh, en, body, refs, ack = split_front_matter(blocks)
    manual: list[dict[str, object]] = []
    elements: list[etree._Element] = []
    if zh:
        elements.extend(abstract_elements("摘  要", zh, styles))
    else:
        manual.append({"type": "missing-chinese-abstract", "severity": "error"})
    if en:
        elements.extend(abstract_elements("Abstract", en, styles))
    else:
        manual.append({"type": "missing-english-abstract", "severity": "warning"})
    elements.extend(toc_placeholder_elements(styles))
    for block in body:
        elements.extend(block_to_elements(block, styles))
    if refs:
        for block in refs:
            elements.extend(block_to_elements(block, styles))
    else:
        manual.append({"type": "missing-references-section", "severity": "warning"})
    if ack:
        for block in ack:
            elements.extend(block_to_elements(block, styles))
    return elements, manual


def apply_sync(
    template: Path,
    output: Path,
    blocks: list[dict[str, object]],
    styles: dict[str, str],
    mode: str,
    anchor_text: str | None,
) -> dict[str, object]:
    shutil.copy2(template, output)
    output.chmod(output.stat().st_mode | stat.S_IREAD | stat.S_IWRITE)
    with zipfile.ZipFile(template, "r") as zin:
        root = etree.fromstring(zin.read("word/document.xml"))
        body = root.find(f"{W}body")
        if body is None:
            raise ValueError("word/document.xml has no w:body")
        replacement_elements, manual = build_replacement_elements(blocks, styles)
        if mode == "replace-template-body":
            start = replace_start_index(body)
            end = replace_end_index(body)
            children_snapshot = list(body)
            for child in children_snapshot[start:end]:
                body.remove(child)
            for offset, element in enumerate(replacement_elements):
                body.insert(start + offset, element)
            removed_bookmarks = cleanup_unpaired_bookmarks(root)
            applied = {
                "replaceStartBlock": start,
                "replaceEndBlockExclusive": end,
                "insertedBlocks": len(replacement_elements),
                "removedUnpairedBookmarks": removed_bookmarks,
            }
        else:
            idx = insertion_index(body, mode, anchor_text)
            for offset, block in enumerate(blocks):
                for element in block_to_elements(block, styles):
                    body.insert(idx + offset, element)
            applied = {"insertBlock": idx, "insertedBlocks": len(blocks)}
        new_xml = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                if item.filename == "word/document.xml":
                    zout.writestr(item, new_xml)
                else:
                    zout.writestr(item, zin.read(item.filename))
    return {"applied": applied, "manualConfirm": manual}


def visible_markdown_residue(docx: Path) -> list[dict[str, object]]:
    with zipfile.ZipFile(docx, "r") as zf:
        root = etree.fromstring(zf.read("word/document.xml"))
    residue: list[dict[str, object]] = []
    for idx, para in enumerate(root.iter(f"{W}p")):
        if paragraph_uses_code_font(para):
            continue
        text = text_of(para)
        matches = [m.group(0) for m in VISIBLE_MARKDOWN_RESIDUE_RE.finditer(text)]
        if matches:
            residue.append({"paragraphIndex": idx, "matches": matches[:10], "text": text[:200]})
    return residue


def paragraph_uses_code_font(para: etree._Element) -> bool:
    for font in para.iter(f"{W}rFonts"):
        values = {font.get(f"{W}{key}") for key in ("ascii", "hAnsi", "eastAsia", "cs")}
        if any(value and value.lower() in {"consolas", "courier new", "monospace"} for value in values):
            return True
    return False


def docx_text(docx: Path) -> str:
    with zipfile.ZipFile(docx, "r") as zf:
        root = etree.fromstring(zf.read("word/document.xml"))
    return "\n".join(text_of(p).strip() for p in root.iter(f"{W}p") if text_of(p).strip())


def docx_counts(docx: Path) -> dict[str, int]:
    with zipfile.ZipFile(docx, "r") as zf:
        names = zf.namelist()
        root = etree.fromstring(zf.read("word/document.xml"))
    body = root.find(f"{W}body")
    return {
        "zipPartCount": len(names),
        "paragraphCount": len(list(body.iter(f"{W}p"))) if body is not None else 0,
        "tableCount": len(list(body.iter(f"{W}tbl"))) if body is not None else 0,
        "imageBlipCount": sum(1 for _ in root.iter("{http://schemas.openxmlformats.org/drawingml/2006/main}blip")),
        "fieldInstrCount": len(list(root.iter(f"{W}instrText"))),
        "bookmarkStartCount": len(list(root.iter(f"{W}bookmarkStart"))),
        "bookmarkEndCount": len(list(root.iter(f"{W}bookmarkEnd"))),
    }


def acceptance_checks(docx: Path, blocks: list[dict[str, object]], residue: list[dict[str, object]]) -> dict[str, object]:
    text = docx_text(docx)
    stale = [term for term in STALE_TEMPLATE_TERMS if term in text]
    source_labels = sorted({m.group(0) for block in blocks for m in BODY_LABEL_RE.finditer(str(block.get("text", "")))})
    output_captions = sorted({m.group(0) for m in re.finditer(r"(?m)^\s*(?:图|表)\s*\d+\s*[-.]\s*\d+", text)})
    unresolved_labels = [label for label in source_labels if not any(label.replace(" ", "") in cap.replace(" ", "") for cap in output_captions)]
    errors: list[dict[str, object]] = []
    warnings: list[dict[str, object]] = []
    if "本科毕业设计（论文）版权使用授权书" not in text:
        errors.append({"type": "missing-authorization-page"})
    if "摘  要" not in text and "摘要" not in text:
        errors.append({"type": "missing-chinese-abstract-title"})
    if "关键词" not in text:
        errors.append({"type": "missing-chinese-keywords"})
    if "Abstract" not in text:
        errors.append({"type": "missing-english-abstract"})
    if stale:
        errors.append({"type": "stale-template-content", "terms": stale})
    if residue:
        errors.append({"type": "visible-markdown-residue", "count": len(residue), "examples": residue[:5]})
    if unresolved_labels:
        warnings.append(
            {
                "type": "body-figure-table-references-without-captions",
                "labels": unresolved_labels[:20],
                "nextSkill": "portable-thesis-xref-qa",
            }
        )
    status = "blocked" if errors else ("needs-manual-confirmation" if warnings else "pass")
    return {"status": status, "errors": errors, "warnings": warnings, "counts": docx_counts(docx)}


def artifact_list(source: Path, output: Path, sidecar: Path) -> list[dict[str, object]]:
    return [
        {
            "path": str(source),
            "role": "protected_source",
            "kind": "template_or_source_docx",
            "cleanup": False,
        },
        {
            "path": str(output),
            "role": "deliverable",
            "kind": "docx",
            "cleanup": False,
        },
        {
            "path": str(sidecar),
            "role": "sidecar",
            "kind": "sync_report",
            "cleanup": True,
        },
    ]


def xref_audit_command(output: Path, source: Path, sidecar: Path) -> dict[str, object]:
    audit_json = output.with_suffix(".xref_audit.json")
    audit_md = output.with_suffix(".xref_audit.md")
    return {
        "docx": str(output),
        "sourceDocx": str(source),
        "syncSidecar": str(sidecar),
        "outJson": str(audit_json),
        "outMarkdown": str(audit_md),
        "completionGateRequired": "completionGate.qaComplete must be true before qa-complete.",
        "commandArgs": [
            "python",
            "<portable-thesis-xref-qa>/scripts/xref_audit.py",
            "--docx",
            str(output),
            "--source-docx",
            str(source),
            "--sidecar",
            str(sidecar),
            "--out-json",
            str(audit_json),
            "--out-md",
            str(audit_md),
        ],
    }


def workflow_state(
    *,
    output: Path,
    source: Path,
    sidecar: Path,
    apply: bool,
    quality_status: str,
) -> dict[str, object]:
    if not apply:
        return {
            "currentPhase": "docx-sync-plan-review",
            "nextSkill": "portable-thesis-docx-sync",
            "nextAction": "review-plan-then-apply",
            "qaComplete": False,
        }
    if quality_status == "blocked":
        return {
            "currentPhase": "docx-sync",
            "nextSkill": "portable-thesis-docx-sync",
            "nextAction": "fix-docx-sync-quality-gate",
            "qaComplete": False,
            "xrefAuditDeferred": xref_audit_command(output, source, sidecar),
        }
    return {
        "currentPhase": "xref-qa",
        "nextSkill": "portable-thesis-xref-qa",
        "nextAction": "run-xref-audit",
        "qaComplete": False,
        "xrefAudit": xref_audit_command(output, source, sidecar),
    }


def set_workflow(plan: dict[str, object], workflow: dict[str, object]) -> None:
    plan["workflow"] = workflow
    plan["currentPhase"] = workflow.get("currentPhase")
    plan["nextSkill"] = workflow.get("nextSkill")
    plan["nextAction"] = workflow.get("nextAction")


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
    parser.add_argument(
        "--insert-mode",
        choices=["replace-template-body", "append-before-sectpr", "after-anchor"],
        default="replace-template-body",
    )
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
    residue = markdown_residue(blocks)
    styles = default_style_map(analysis)
    manual: list[object] = [] if args.apply else ["Review insertion mode, replacement range, and style mapping before --apply."]
    if args.insert_mode == "append-before-sectpr":
        manual.append(
            {
                "type": "append-before-sectpr-not-acceptable-for-initial-docx",
                "severity": "error",
                "message": "This mode leaves template sample content in place. Use replace-template-body for initial drafts unless the user explicitly approves append-only output.",
            }
        )

    plan: dict[str, object] = {
        "schemaVersion": 2,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "mode": "apply" if args.apply else "plan",
        "sourceDocx": {
            "path": str(template),
            "sha256": sha256(template),
            "size": template.stat().st_size,
            "mtime": datetime.fromtimestamp(template.stat().st_mtime, timezone.utc).isoformat(),
        },
        "markdownDir": str(md_dir),
        "analysisJson": str(analysis_path) if analysis_path else None,
        "outputDocx": str(output),
        "insertMode": args.insert_mode,
        "anchorText": args.anchor_text,
        "blockCount": len(blocks),
        "markdownInlineFormatting": {
            "supported": ["bold", "italic", "inline-code", "strikethrough", "markdown-links-as-text"],
            "blockSupported": ["tables", "code-fences", "display-math-as-centered-text"],
            "firstLineIndentCharsForBody": 200,
            "residueBeforeConversion": residue[:50],
        },
        "styles": styles,
        "manualConfirm": manual,
        "artifacts": artifact_list(template, output, plan_out),
        "qualityGate": {"status": "plan-review"},
    }
    set_workflow(
        plan,
        workflow_state(output=output, source=template, sidecar=plan_out, apply=False, quality_status="plan-review"),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    plan_out.parent.mkdir(parents=True, exist_ok=True)
    if args.apply:
        result = apply_sync(template, output, blocks, styles, args.insert_mode, args.anchor_text)
        plan["applyResult"] = result["applied"]
        plan["manualConfirm"] = list(plan["manualConfirm"]) + list(result["manualConfirm"])  # type: ignore[arg-type]
        plan["outputSha256"] = sha256(output)
        plan["outputSize"] = output.stat().st_size
        plan["sourceProtection"] = {
            "unchanged": sha256(template) == plan["sourceDocx"]["sha256"] and template.stat().st_size == plan["sourceDocx"]["size"],  # type: ignore[index]
            "sha256After": sha256(template),
            "sizeAfter": template.stat().st_size,
            "mtimeAfter": datetime.fromtimestamp(template.stat().st_mtime, timezone.utc).isoformat(),
        }
        after_residue = visible_markdown_residue(output)[:50]
        plan["markdownInlineFormatting"]["residueAfterConversion"] = after_residue  # type: ignore[index]
        gate = acceptance_checks(output, blocks, after_residue)
        plan["qualityGate"] = gate
        if gate["warnings"]:  # type: ignore[index]
            plan["manualConfirm"] = list(plan["manualConfirm"]) + list(gate["warnings"])  # type: ignore[arg-type]
        set_workflow(
            plan,
            workflow_state(
                output=output,
                source=template,
                sidecar=plan_out,
                apply=True,
                quality_status=str(gate.get("status", "unknown")),
            ),
        )
    plan_out.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    print(plan_out)
    if args.apply:
        print(output)
        gate = plan.get("qualityGate", {})
        if isinstance(gate, dict):
            print(f"DOCX_SYNC_QUALITY_GATE={gate.get('status')}")
            if gate.get("status") != "pass":
                print("NEXT_ACTION=review sync sidecar manualConfirm; run portable-thesis-xref-qa before claiming completion")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
