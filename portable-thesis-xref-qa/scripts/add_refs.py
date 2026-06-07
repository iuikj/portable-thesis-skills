#!/usr/bin/env python3
"""Add low-risk thesis caption/citation cross-reference fields to a DOCX copy."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import shutil
import zipfile
from collections import defaultdict
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


def text_of_para(para: etree._Element) -> str:
    return "".join(t.text or "" for t in para.iter(f"{W}t"))


def has_field(para: etree._Element) -> bool:
    return para.find(f".//{W}fldChar") is not None or para.find(f".//{W}fldSimple") is not None


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


def make_seq_field(name: str, display: str) -> list[etree._Element]:
    return [
        make_fld_char("begin"),
        make_instr(f" SEQ {name} \\* ARABIC "),
        make_fld_char("separate"),
        make_run_text(display),
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


def add_bookmark(para: etree._Element, name: str, bookmark_id: int) -> None:
    start = etree.Element(f"{W}bookmarkStart")
    start.set(f"{W}id", str(bookmark_id))
    start.set(f"{W}name", name)
    end = etree.Element(f"{W}bookmarkEnd")
    end.set(f"{W}id", str(bookmark_id))
    para.insert(0, start)
    para.append(end)


def clear_para_keep_props(para: etree._Element) -> etree._Element | None:
    props = para.find(f"{W}pPr")
    props_copy = copy.deepcopy(props) if props is not None else None
    for child in list(para):
        para.remove(child)
    if props_copy is not None:
        para.append(props_copy)
    return props_copy


def label_parts(raw_label: str) -> tuple[str, str, str] | None:
    match = re.search(r"(图|表|算法|Figure|Table|Algorithm|Fig\.|Tbl\.)\s*(\d+)[-.](\d+)", raw_label, re.I)
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
    return f"_Ref_{kind}{clean}"


def make_caption_map(paragraphs: list[etree._Element]) -> list[dict[str, object]]:
    captions: list[dict[str, object]] = []
    caption_pat = re.compile(r"^\s*((?:图|表|算法|Figure|Table|Algorithm|Fig\.|Tbl\.)\s*\d+[-.]\d+)\b", re.I)
    for idx, para in enumerate(paragraphs):
        text = text_of_para(para).strip()
        if not text:
            continue
        match = caption_pat.search(text)
        if not match:
            continue
        parts = label_parts(match.group(1))
        if parts is None:
            continue
        kind, display_prefix, label = parts
        captions.append(
            {
                "idx": idx,
                "kind": kind,
                "displayPrefix": display_prefix,
                "label": label,
                "matchText": match.group(1),
                "bookmark": bookmark_name(kind, label),
                "text": text,
                "alreadyFielded": has_field(para),
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
    pattern = re.compile(r"^\[(\d+)\]")
    for idx, para in enumerate(paragraphs):
        text = text_of_para(para).strip()
        in_refs, just_started = section_state(text, in_refs)
        if not in_refs or just_started:
            continue
        match = pattern.search(text)
        if match:
            num = match.group(1)
            entries.append({"idx": idx, "num": num, "bookmark": f"_RefBib{num}", "text": text})
    return entries


def find_refs(paragraphs: list[etree._Element], captions: list[dict[str, object]], bib_entries: list[dict[str, object]]) -> tuple[dict[int, list[dict[str, object]]], dict[int, list[dict[str, object]]]]:
    caption_by_key = {(cap["kind"], cap["label"]): cap for cap in captions}
    bib_by_num = {entry["num"]: entry for entry in bib_entries}
    body_refs: dict[int, list[dict[str, object]]] = defaultdict(list)
    citation_refs: dict[int, list[dict[str, object]]] = defaultdict(list)
    body_pat = re.compile(r"((?:如图|如表|见图|见表|图|表|Figure|Table|Fig\.|Tbl\.)\s*(\d+)[-.](\d+))", re.I)
    citation_pat = re.compile(r"\[(\d+(?:\s*[,;，、]\s*\d+)*)\]")
    caption_indices = {cap["idx"] for cap in captions}
    bib_indices = {entry["idx"] for entry in bib_entries}

    for idx, para in enumerate(paragraphs):
        if idx in caption_indices or idx in bib_indices or has_field(para):
            continue
        text = text_of_para(para)
        for match in body_pat.finditer(text):
            raw = match.group(1)
            parts = label_parts(raw)
            if parts is None:
                continue
            kind, _prefix, label = parts
            cap = caption_by_key.get((kind, label))
            if cap is not None:
                body_refs[idx].append(
                    {
                        "start": match.start(1),
                        "end": match.end(1),
                        "matchText": raw,
                        "bookmark": cap["bookmark"],
                        "label": label,
                    }
                )
        for match in citation_pat.finditer(text):
            nums = [x for x in re.split(r"\s*[,;，、]\s*", match.group(1)) if x]
            if all(num in bib_by_num for num in nums):
                citation_refs[idx].append(
                    {
                        "start": match.start(0),
                        "end": match.end(0),
                        "matchText": match.group(0),
                        "bookmark": bib_by_num[nums[0]]["bookmark"],
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


def add_caption_fields(paragraphs: list[etree._Element], captions: list[dict[str, object]], start_id: int) -> tuple[int, int]:
    added = 0
    next_id = start_id
    for cap in captions:
        if cap["alreadyFielded"]:
            continue
        para = paragraphs[int(cap["idx"])]
        text = str(cap["text"]).strip()
        suffix = text.split(str(cap["matchText"]), 1)[1].strip() if str(cap["matchText"]) in text else ""
        clear_para_keep_props(para)
        para.append(make_run_text(str(cap["displayPrefix"]) + " "))
        seq_name = f"SEQ_{cap['kind']}_{str(cap['label']).split('-')[0]}"
        for run in make_seq_field(seq_name, str(cap["label"])):
            para.append(run)
        if suffix:
            para.append(make_run_text(" " + suffix))
        next_id += 1
        add_bookmark(para, str(cap["bookmark"]), next_id)
        added += 1
    return added, next_id


def add_bibliography_bookmarks(paragraphs: list[etree._Element], entries: list[dict[str, object]], start_id: int) -> tuple[int, int]:
    added = 0
    next_id = start_id
    for entry in entries:
        para = paragraphs[int(entry["idx"])]
        next_id += 1
        add_bookmark(para, str(entry["bookmark"]), next_id)
        added += 1
    return added, next_id


def run_repair(input_docx: Path, output_docx: Path) -> dict[str, object]:
    shutil.copy2(input_docx, output_docx)
    with zipfile.ZipFile(input_docx, "r") as zin:
        root = etree.fromstring(zin.read("word/document.xml"))
        body = root.find(f"{W}body")
        paragraphs = list(body.iter(f"{W}p")) if body is not None else []
        captions = make_caption_map(paragraphs)
        bib_entries = make_bibliography_map(paragraphs)
        next_bookmark_id = max_bookmark_id(root)

        caption_added, next_bookmark_id = add_caption_fields(paragraphs, captions, next_bookmark_id)
        bib_added, next_bookmark_id = add_bibliography_bookmarks(paragraphs, bib_entries, next_bookmark_id)
        body_refs, citation_refs = find_refs(paragraphs, captions, bib_entries)

        body_added = 0
        for idx, refs in body_refs.items():
            for ref in sorted(refs, key=lambda x: int(x["start"]), reverse=True):
                if replace_text_range_with_field(paragraphs[idx], ref):
                    body_added += 1

        citation_added = 0
        for idx, refs in citation_refs.items():
            for ref in sorted(refs, key=lambda x: int(x["start"]), reverse=True):
                if replace_text_range_with_field(paragraphs[idx], ref, superscript=True):
                    citation_added += 1

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
            "captionSeqFields": caption_added,
            "bodyRefFields": body_added,
            "bibliographyBookmarks": bib_added,
            "bibliographyCitationRefs": citation_added,
        },
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
