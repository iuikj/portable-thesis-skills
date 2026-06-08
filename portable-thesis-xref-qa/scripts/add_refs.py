#!/usr/bin/env python3
"""Add low-risk thesis caption/citation cross-reference fields to a DOCX copy."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import shutil
import stat
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from lxml import etree

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{W_NS}}}"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"

LABEL_RE = re.compile(r"(图|表|算法|Figure|Table|Algorithm|Fig\.|Tbl\.)\s*(\d+)[-.](\d+)", re.I)
CAPTION_RE = re.compile(r"^\s*((?:图|表|算法|Figure|Table|Algorithm|Fig\.|Tbl\.)\s*\d+[-.]\d+)", re.I)
BODY_REF_RE = re.compile(r"((?:如图|如表|见图|见表|图|表|Figure|Table|Fig\.|Tbl\.)\s*\d+[-.]\d+)", re.I)
BIB_ENTRY_RE = re.compile(r"^\s*(\[(\d+)\])")
SINGLE_CITATION_RE = re.compile(r"\[(\d+)\]")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def text_of_para(para: etree._Element) -> str:
    return "".join(t.text or "" for t in para.iter(f"{W}t"))


def has_field(para: etree._Element) -> bool:
    return para.find(f".//{W}fldChar") is not None or para.find(f".//{W}fldSimple") is not None


def field_type(instr: str) -> str:
    parts = instr.strip().split()
    return parts[0].upper() if parts else "UNKNOWN"


def field_result_spans(para: etree._Element) -> list[dict[str, object]]:
    """Return visible-text spans occupied by complex field results.

    Spans use the same coordinate system as text_of_para(). This lets repair
    skip labels that are already inside REF/SEQ results while still repairing
    ordinary text elsewhere in the same paragraph.
    """
    spans: list[dict[str, object]] = []
    cursor = 0
    current: dict[str, object] | None = None
    instr_parts: list[str] = []
    in_result = False
    result_start: int | None = None

    for run in para.iter(f"{W}r"):
        fld_char = run.find(f"{W}fldChar")
        instr_text = run.find(f"{W}instrText")

        if fld_char is not None:
            fld_type = fld_char.get(f"{W}fldCharType")
            if fld_type == "begin":
                current = {"instr": ""}
                instr_parts = []
                in_result = False
                result_start = None
            elif fld_type == "separate" and current is not None:
                current["instr"] = "".join(instr_parts).strip()
                in_result = True
                result_start = cursor

        if current is not None and instr_text is not None and not in_result:
            instr_parts.append(instr_text.text or "")

        text_len = sum(len(t.text or "") for t in run.findall(f"{W}t"))
        cursor += text_len

        if fld_char is not None and fld_char.get(f"{W}fldCharType") == "end" and current is not None:
            if result_start is not None:
                spans.append(
                    {
                        "start": result_start,
                        "end": cursor,
                        "instr": str(current.get("instr", "")),
                        "type": field_type(str(current.get("instr", ""))),
                    }
                )
            current = None
            in_result = False
            result_start = None
            instr_parts = []

    cursor = 0
    for child in para:
        child_text_len = sum(len(t.text or "") for t in child.iter(f"{W}t"))
        if child.tag == f"{W}fldSimple":
            instr = child.get(f"{W}instr", "").strip()
            spans.append({"start": cursor, "end": cursor + child_text_len, "instr": instr, "type": field_type(instr)})
        cursor += child_text_len

    return spans


def range_covered_by_field(
    para: etree._Element,
    start: int,
    end: int,
    allowed_types: set[str] | None = None,
) -> bool:
    for span in field_result_spans(para):
        if allowed_types is not None and str(span["type"]) not in allowed_types:
            continue
        if int(span["start"]) <= start and end <= int(span["end"]):
            return True
    return False


def make_run_text(text: str, superscript: bool = False, rpr: etree._Element | None = None) -> etree._Element:
    run = etree.Element(f"{W}r")
    if rpr is not None:
        run.append(copy.deepcopy(rpr))
    elif superscript:
        props = etree.SubElement(run, f"{W}rPr")
        vert = etree.SubElement(props, f"{W}vertAlign")
        vert.set(f"{W}val", "superscript")
    if superscript and rpr is not None:
        props = run.find(f"{W}rPr")
        if props is None:
            props = etree.Element(f"{W}rPr")
            run.insert(0, props)
        vert = props.find(f"{W}vertAlign")
        if vert is None:
            vert = etree.SubElement(props, f"{W}vertAlign")
        vert.set(f"{W}val", "superscript")
    t = etree.SubElement(run, f"{W}t")
    t.set(XML_SPACE, "preserve")
    t.text = text
    return run


def make_fld_char(kind: str) -> etree._Element:
    run = etree.Element(f"{W}r")
    fld = etree.SubElement(run, f"{W}fldChar")
    fld.set(f"{W}fldCharType", kind)
    return run


def make_instr(text: str) -> etree._Element:
    run = etree.Element(f"{W}r")
    instr = etree.SubElement(run, f"{W}instrText")
    instr.set(XML_SPACE, "preserve")
    instr.text = text
    return run


def make_ref_field(bookmark: str, display: str, superscript: bool = False) -> list[etree._Element]:
    return [
        make_fld_char("begin"),
        make_instr(f" REF {bookmark} \\h "),
        make_fld_char("separate"),
        make_run_text(display, superscript=superscript),
        make_fld_char("end"),
    ]


def max_bookmark_id(root: etree._Element) -> int:
    values = []
    for node in root.iter(f"{W}bookmarkStart"):
        try:
            values.append(int(node.get(f"{W}id", "0")))
        except ValueError:
            pass
    return max(values, default=0)


def existing_bookmark_names(root: etree._Element) -> set[str]:
    return {name for node in root.iter(f"{W}bookmarkStart") if (name := node.get(f"{W}name"))}


def bookmark_elements(name: str, bookmark_id: int) -> tuple[etree._Element, etree._Element]:
    start = etree.Element(f"{W}bookmarkStart")
    start.set(f"{W}id", str(bookmark_id))
    start.set(f"{W}name", name)
    end = etree.Element(f"{W}bookmarkEnd")
    end.set(f"{W}id", str(bookmark_id))
    return start, end


def insert_bookmark_around_text_range(para: etree._Element, start: int, end: int, name: str, bookmark_id: int) -> bool:
    """Wrap a simple single-run text range in a bookmark without changing text."""
    cursor = 0
    for run in list(para.findall(f"{W}r")):
        text_nodes = run.findall(f"{W}t")
        for t_node in text_nodes:
            text = t_node.text or ""
            node_start = cursor
            node_end = cursor + len(text)
            if node_start <= start and end <= node_end:
                local_start = start - node_start
                local_end = end - node_start
                prefix = text[:local_start]
                target = text[local_start:local_end]
                suffix = text[local_end:]
                if not target:
                    return False
                parent = run.getparent()
                if parent is None:
                    return False
                run_index = list(parent).index(run)
                rpr = run.find(f"{W}rPr")
                bm_start, bm_end = bookmark_elements(name, bookmark_id)
                replacements: list[etree._Element] = []
                if prefix:
                    replacements.append(make_run_text(prefix, rpr=rpr))
                replacements.append(bm_start)
                replacements.append(make_run_text(target, rpr=rpr))
                replacements.append(bm_end)
                if suffix:
                    replacements.append(make_run_text(suffix, rpr=rpr))
                parent.remove(run)
                for offset, replacement in enumerate(replacements):
                    parent.insert(run_index + offset, replacement)
                return True
            cursor = node_end
    return False


def label_parts(raw_label: str) -> tuple[str, str, str] | None:
    match = LABEL_RE.search(raw_label)
    if not match:
        return None
    prefix = match.group(1)
    chapter = match.group(2)
    number = match.group(3)
    if prefix.lower().startswith(("fig", "figure")) or prefix == "图":
        kind = "fig"
        display_prefix = "图" if prefix == "图" else prefix
    elif prefix.lower().startswith(("tbl", "table")) or prefix == "表":
        kind = "tbl"
        display_prefix = "表" if prefix == "表" else prefix
    else:
        kind = "alg"
        display_prefix = prefix
    return kind, display_prefix, f"{chapter}-{number}"


def bookmark_name(kind: str, label: str) -> str:
    clean = label.replace("-", "_").replace(".", "_")
    return f"_Ref_{kind}{clean}_label"


def make_caption_map(paragraphs: list[etree._Element]) -> list[dict[str, object]]:
    captions: list[dict[str, object]] = []
    for idx, para in enumerate(paragraphs):
        full_text = text_of_para(para)
        if not full_text.strip():
            continue
        match = CAPTION_RE.search(full_text)
        if not match:
            continue
        label_match = LABEL_RE.search(match.group(1))
        if not label_match:
            continue
        parts = label_parts(label_match.group(0))
        if parts is None:
            continue
        kind, display_prefix, label = parts
        start = match.start(1) + label_match.start(0)
        end = match.start(1) + label_match.end(0)
        captions.append(
            {
                "idx": idx,
                "kind": kind,
                "displayPrefix": display_prefix,
                "label": label,
                "matchText": label_match.group(0),
                "start": start,
                "end": end,
                "bookmark": bookmark_name(kind, label),
                "text": full_text.strip(),
                "alreadyFielded": range_covered_by_field(para, start, end, {"SEQ", "REF"}),
                "bookmarkAvailable": False,
            }
        )
    return captions


def section_state(text: str, in_refs: bool) -> tuple[bool, bool]:
    stripped = text.strip()
    if stripped in {"参考文献", "References", "REFERENCES"}:
        return True, True
    if in_refs and stripped in {"致谢", "致  谢", "附录", "Appendix", "Appendices"}:
        return False, False
    return in_refs, False


def make_bibliography_map(paragraphs: list[etree._Element]) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    in_refs = False
    for idx, para in enumerate(paragraphs):
        full_text = text_of_para(para)
        in_refs, just_started = section_state(full_text, in_refs)
        if not in_refs or just_started:
            continue
        match = BIB_ENTRY_RE.search(full_text)
        if match:
            marker = match.group(1)
            num = match.group(2)
            entries.append(
                {
                    "idx": idx,
                    "num": num,
                    "marker": marker,
                    "start": match.start(1),
                    "end": match.end(1),
                    "bookmark": f"_RefBib{num}_label",
                    "text": full_text.strip(),
                    "alreadyFielded": range_covered_by_field(para, match.start(1), match.end(1), {"REF"}),
                    "bookmarkAvailable": False,
                }
            )
    return entries


def add_caption_bookmarks(
    paragraphs: list[etree._Element],
    captions: list[dict[str, object]],
    start_id: int,
    existing_names: set[str],
    manual_confirm: list[dict[str, object]],
) -> tuple[int, int]:
    added = 0
    next_id = start_id
    for cap in captions:
        name = str(cap["bookmark"])
        if name in existing_names:
            cap["bookmarkAvailable"] = True
            continue
        para = paragraphs[int(cap["idx"])]
        if cap["alreadyFielded"] or has_field(para):
            manual_confirm.append(
                {
                    "type": "caption-bookmark-not-added",
                    "reason": "caption label is in or near existing fields",
                    "label": cap["matchText"],
                    "paragraphIndex": cap["idx"],
                }
            )
            continue
        next_id += 1
        if insert_bookmark_around_text_range(para, int(cap["start"]), int(cap["end"]), name, next_id):
            existing_names.add(name)
            cap["bookmarkAvailable"] = True
            added += 1
        else:
            manual_confirm.append(
                {
                    "type": "caption-bookmark-not-added",
                    "reason": "caption label spans multiple runs or could not be located safely",
                    "label": cap["matchText"],
                    "paragraphIndex": cap["idx"],
                }
            )
    return added, next_id


def add_bibliography_bookmarks(
    paragraphs: list[etree._Element],
    entries: list[dict[str, object]],
    start_id: int,
    existing_names: set[str],
    manual_confirm: list[dict[str, object]],
) -> tuple[int, int]:
    added = 0
    next_id = start_id
    for entry in entries:
        name = str(entry["bookmark"])
        if name in existing_names:
            entry["bookmarkAvailable"] = True
            continue
        para = paragraphs[int(entry["idx"])]
        if entry["alreadyFielded"] or has_field(para):
            manual_confirm.append(
                {
                    "type": "bibliography-bookmark-not-added",
                    "reason": "bibliography marker is in or near existing fields",
                    "label": entry["marker"],
                    "paragraphIndex": entry["idx"],
                }
            )
            continue
        next_id += 1
        if insert_bookmark_around_text_range(para, int(entry["start"]), int(entry["end"]), name, next_id):
            existing_names.add(name)
            entry["bookmarkAvailable"] = True
            added += 1
        else:
            manual_confirm.append(
                {
                    "type": "bibliography-bookmark-not-added",
                    "reason": "bibliography marker spans multiple runs or could not be located safely",
                    "label": entry["marker"],
                    "paragraphIndex": entry["idx"],
                }
            )
    return added, next_id


def find_refs(
    paragraphs: list[etree._Element],
    captions: list[dict[str, object]],
    bib_entries: list[dict[str, object]],
) -> tuple[dict[int, list[dict[str, object]]], dict[int, list[dict[str, object]]]]:
    caption_by_key = {
        (cap["kind"], cap["label"]): cap for cap in captions if bool(cap.get("bookmarkAvailable"))
    }
    bib_by_num = {entry["num"]: entry for entry in bib_entries if bool(entry.get("bookmarkAvailable"))}
    body_refs: dict[int, list[dict[str, object]]] = defaultdict(list)
    citation_refs: dict[int, list[dict[str, object]]] = defaultdict(list)
    caption_indices = {cap["idx"] for cap in captions}
    bib_indices = {entry["idx"] for entry in bib_entries}

    for idx, para in enumerate(paragraphs):
        if idx in caption_indices or idx in bib_indices:
            continue
        text = text_of_para(para)
        for match in BODY_REF_RE.finditer(text):
            raw = match.group(1)
            label_match = LABEL_RE.search(raw)
            if not label_match:
                continue
            parts = label_parts(label_match.group(0))
            if parts is None:
                continue
            kind, _prefix, label = parts
            cap = caption_by_key.get((kind, label))
            if cap is None:
                continue
            label_start = match.start(1) + label_match.start(0)
            label_end = match.start(1) + label_match.end(0)
            if range_covered_by_field(para, label_start, label_end, {"REF", "PAGEREF"}):
                continue
            body_refs[idx].append(
                {
                    "start": label_start,
                    "end": label_end,
                    "matchText": label_match.group(0),
                    "bookmark": cap["bookmark"],
                    "label": label,
                }
            )
        for match in SINGLE_CITATION_RE.finditer(text):
            num = match.group(1)
            entry = bib_by_num.get(num)
            if entry is None:
                continue
            if range_covered_by_field(para, match.start(0), match.end(0), {"REF"}):
                continue
            citation_refs[idx].append(
                {
                    "start": match.start(0),
                    "end": match.end(0),
                    "matchText": match.group(0),
                    "bookmark": entry["bookmark"],
                    "label": match.group(0),
                }
            )
    return body_refs, citation_refs


def replace_text_range_with_field(para: etree._Element, ref: dict[str, object], superscript: bool = False) -> bool:
    runs = list(para.findall(f"{W}r"))
    cursor = 0
    for run in runs:
        text_nodes = run.findall(f"{W}t")
        for t_node in text_nodes:
            text = t_node.text or ""
            start = cursor
            end = cursor + len(text)
            target_start = int(ref["start"])
            target_end = int(ref["end"])
            if start <= target_start and target_end <= end:
                local_start = target_start - start
                local_end = target_end - start
                prefix = text[:local_start]
                suffix = text[local_end:]
                parent = run.getparent()
                if parent is None:
                    return False
                run_index = list(parent).index(run)
                rpr = run.find(f"{W}rPr")
                replacements: list[etree._Element] = []
                if prefix:
                    replacements.append(make_run_text(prefix, rpr=rpr))
                replacements.extend(make_ref_field(str(ref["bookmark"]), str(ref["matchText"]), superscript=superscript))
                if suffix:
                    replacements.append(make_run_text(suffix, rpr=rpr))
                parent.remove(run)
                for offset, replacement in enumerate(replacements):
                    parent.insert(run_index + offset, replacement)
                return True
            cursor = end
    return False


def run_repair(input_docx: Path, output_docx: Path) -> dict[str, object]:
    shutil.copy2(input_docx, output_docx)
    output_docx.chmod(output_docx.stat().st_mode | stat.S_IREAD | stat.S_IWRITE)
    manual_confirm: list[dict[str, object]] = []
    with zipfile.ZipFile(input_docx, "r") as zin:
        root = etree.fromstring(zin.read("word/document.xml"))
        body = root.find(f"{W}body")
        paragraphs = list(body.iter(f"{W}p")) if body is not None else []
        captions = make_caption_map(paragraphs)
        bib_entries = make_bibliography_map(paragraphs)
        next_bookmark_id = max_bookmark_id(root)
        names = existing_bookmark_names(root)

        caption_bookmarks, next_bookmark_id = add_caption_bookmarks(
            paragraphs, captions, next_bookmark_id, names, manual_confirm
        )
        bib_bookmarks, next_bookmark_id = add_bibliography_bookmarks(
            paragraphs, bib_entries, next_bookmark_id, names, manual_confirm
        )
        body_refs, citation_refs = find_refs(paragraphs, captions, bib_entries)

        body_added = 0
        for idx, refs in body_refs.items():
            for ref in sorted(refs, key=lambda x: int(x["start"]), reverse=True):
                if replace_text_range_with_field(paragraphs[idx], ref):
                    body_added += 1
                else:
                    manual_confirm.append(
                        {
                            "type": "body-ref-not-replaced",
                            "reason": "reference label spans multiple runs or could not be located safely",
                            "label": ref["matchText"],
                            "paragraphIndex": idx,
                        }
                    )

        citation_added = 0
        for idx, refs in citation_refs.items():
            for ref in sorted(refs, key=lambda x: int(x["start"]), reverse=True):
                if replace_text_range_with_field(paragraphs[idx], ref, superscript=True):
                    citation_added += 1
                else:
                    manual_confirm.append(
                        {
                            "type": "bibliography-citation-not-replaced",
                            "reason": "citation marker spans multiple runs or could not be located safely",
                            "label": ref["matchText"],
                            "paragraphIndex": idx,
                        }
                    )

        new_xml = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
        with zipfile.ZipFile(output_docx, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                if item.filename == "word/document.xml":
                    zout.writestr(item, new_xml)
                else:
                    zout.writestr(item, zin.read(item.filename))

    return {
        "schemaVersion": 1,
        "repairType": "low-risk-xref-fields",
        "inputDocx": str(input_docx),
        "outputDocx": str(output_docx),
        "inputSha256": sha256(input_docx),
        "outputSha256": sha256(output_docx),
        "repairs": {
            "captionBookmarks": caption_bookmarks,
            "captionSeqFields": 0,
            "bodyRefFields": body_added,
            "bibliographyBookmarks": bib_bookmarks,
            "bibliographyCitationRefs": citation_added,
        },
        "manualConfirm": manual_confirm,
        "workflow": {
            "qaComplete": False,
            "currentPhase": "xref-qa",
            "nextSkill": "portable-thesis-xref-qa",
            "nextAction": "run-post-repair-audit",
            "postRepairAudit": {
                "docx": str(output_docx),
                "sourceDocx": str(input_docx),
                "outJson": str(output_docx.with_suffix(".xref_audit.json")),
                "outMarkdown": str(output_docx.with_suffix(".xref_audit.md")),
                "commandArgs": [
                    "python",
                    "<portable-thesis-xref-qa>/scripts/xref_audit.py",
                    "--docx",
                    str(output_docx),
                    "--source-docx",
                    str(input_docx),
                    "--out-json",
                    str(output_docx.with_suffix(".xref_audit.json")),
                    "--out-md",
                    str(output_docx.with_suffix(".xref_audit.md")),
                ],
            },
        },
        "notes": [
            "Caption numbering text is not converted to SEQ automatically; chapter-style numbering requires manual confirmation or a template-specific rule.",
            "Bookmarks are inserted around existing label text only, not whole caption or bibliography paragraphs.",
        ],
        "repairedAt": datetime.now(timezone.utc).isoformat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--docx", required=True, help="Input DOCX copy")
    parser.add_argument("--out", help="Output repaired DOCX path")
    parser.add_argument("--sidecar", help="Repair JSON sidecar path")
    parser.add_argument("--apply", action="store_true", help="Required to write repaired DOCX")
    args = parser.parse_args()

    if not args.apply:
        raise SystemExit("Refusing to repair without --apply. Run xref_audit.py first and review the plan.")

    input_docx = Path(args.docx).resolve()
    out = Path(args.out).resolve() if args.out else input_docx.with_name(input_docx.stem + "_xref.docx")
    sidecar = Path(args.sidecar).resolve() if args.sidecar else out.with_suffix(out.suffix + ".xref_repair.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    result = run_repair(input_docx, out)
    sidecar.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out)
    print(sidecar)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
