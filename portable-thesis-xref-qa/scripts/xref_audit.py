#!/usr/bin/env python3
"""Audit thesis DOCX cross-references without modifying the document."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from lxml import etree

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{W_NS}}}"

BLOCKING_ISSUE_TYPES = {"unbalanced-fields", "unpaired-bookmarks", "orphan-ref-targets"}
REPAIRABLE_ISSUE_TYPES = {"static-body-reference", "static-bibliography-citation"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, object]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def artifact_entry(
    path: Path,
    *,
    role: str,
    kind: str,
    cleanup: bool,
    created_by: str,
    note: str,
) -> dict[str, object]:
    return {
        "path": str(path),
        "role": role,
        "kind": kind,
        "cleanup": cleanup,
        "created_by": created_by,
        "note": note,
    }


def upsert_artifact(data: dict[str, object], entry: dict[str, object]) -> None:
    artifacts = data.setdefault("artifacts", [])
    if not isinstance(artifacts, list):
        artifacts = []
        data["artifacts"] = artifacts
    entry_path = entry.get("path")
    if not isinstance(entry_path, str):
        artifacts.append(entry)
        return
    key = os.path.normcase(str(Path(entry_path).resolve()))
    for index, existing in enumerate(artifacts):
        if not isinstance(existing, dict):
            continue
        existing_path = existing.get("path")
        if isinstance(existing_path, str) and os.path.normcase(str(Path(existing_path).resolve())) == key:
            artifacts[index] = entry
            break
    else:
        artifacts.append(entry)


def update_sync_sidecar(
    sidecar: Path,
    report: dict[str, object],
    out_json: Path,
    out_md: Path,
) -> None:
    if not sidecar.exists():
        raise SystemExit(f"sidecar not found: {sidecar}")
    data = load_json(sidecar)
    upsert_artifact(
        data,
        artifact_entry(
            out_json,
            role="intermediate",
            kind="xref_audit_json",
            cleanup=True,
            created_by="xref_audit.py",
            note="Cross-reference QA audit JSON; keep until the final DOCX is accepted.",
        ),
    )
    upsert_artifact(
        data,
        artifact_entry(
            out_md,
            role="intermediate",
            kind="xref_audit_markdown",
            cleanup=True,
            created_by="xref_audit.py",
            note="Cross-reference QA audit Markdown summary; keep until the final DOCX is accepted.",
        ),
    )
    gate = report.get("completionGate", {})
    if not isinstance(gate, dict):
        gate = {
            "qaComplete": False,
            "currentPhase": "xref-qa",
            "nextSkill": "portable-thesis-xref-qa",
            "nextAction": "manual-confirm-or-script-enhancement",
        }
    qa_complete = bool(gate.get("qaComplete"))
    data["xrefQa"] = {
        "latestAuditJson": str(out_json),
        "latestAuditMarkdown": str(out_md),
        "completionGate": gate,
        "issueCount": len(report.get("issues", [])) if isinstance(report.get("issues"), list) else None,
    }
    workflow = data.get("workflow")
    if not isinstance(workflow, dict):
        workflow = {}
    workflow.update(
        {
            "qaComplete": qa_complete,
            "currentPhase": gate.get("currentPhase") or ("qa-complete" if qa_complete else "xref-qa"),
            "nextSkill": gate.get("nextSkill"),
            "nextAction": gate.get("nextAction") or ("complete" if qa_complete else "manual-confirm-or-script-enhancement"),
            "latestXrefAudit": str(out_json),
            "latestXrefMarkdown": str(out_md),
        }
    )
    data["workflow"] = workflow
    data["currentPhase"] = workflow["currentPhase"]
    data["nextSkill"] = workflow["nextSkill"]
    data["nextAction"] = workflow["nextAction"]
    write_json(sidecar, data)


def text_of_para(para: etree._Element) -> str:
    return "".join(t.text or "" for t in para.iter(f"{W}t"))


def parse_fields(para: etree._Element) -> list[dict[str, str]]:
    fields: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    instr_parts: list[str] = []
    result_parts: list[str] = []

    for run in para.iter(f"{W}r"):
        fld_char = run.find(f"{W}fldChar")
        instr_text = run.find(f"{W}instrText")
        text = run.find(f"{W}t")

        if fld_char is not None:
            fld_type = fld_char.get(f"{W}fldCharType")
            if fld_type == "begin":
                current = {"instr": "", "result": ""}
                instr_parts = []
                result_parts = []
            elif fld_type == "separate" and current is not None:
                current["instr"] = "".join(instr_parts).strip()
            elif fld_type == "end" and current is not None:
                if current["instr"]:
                    current["result"] = "".join(result_parts)
                    fields.append(current)
                current = None

        if current is not None:
            if instr_text is not None:
                instr_parts.append(instr_text.text or "")
            elif text is not None and current["instr"]:
                result_parts.append(text.text or "")

    for field in para.iter(f"{W}fldSimple"):
        instr = field.get(f"{W}instr", "").strip()
        result = "".join(t.text or "" for t in field.iter(f"{W}t"))
        if instr:
            fields.append({"instr": instr, "result": result})

    return fields


def field_type(instr: str) -> str:
    parts = instr.strip().split()
    return parts[0].upper() if parts else "UNKNOWN"


def field_result_spans(para: etree._Element) -> list[dict[str, object]]:
    """Return visible-text spans occupied by field results in text_of_para coordinates."""
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

        cursor += sum(len(t.text or "") for t in run.findall(f"{W}t"))

        if fld_char is not None and fld_char.get(f"{W}fldCharType") == "end" and current is not None:
            if result_start is not None:
                instr = str(current.get("instr", ""))
                spans.append({"start": result_start, "end": cursor, "instr": instr, "type": field_type(instr)})
            current = None
            instr_parts = []
            in_result = False
            result_start = None

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


def ref_target(instr: str) -> str | None:
    parts = instr.strip().split()
    if len(parts) >= 2 and parts[0].upper() in {"REF", "PAGEREF"}:
        return parts[1]
    return None


def looks_like_code_context(text: str) -> bool:
    code_markers = ["def ", "class ", "return ", "import ", "for ", "while ", "=", "(", ")", "{", "}", ";"]
    return sum(1 for marker in code_markers if marker in text) >= 2


def bookmark_report(root: etree._Element) -> dict[str, object]:
    starts = []
    ends = []
    for node in root.iter(f"{W}bookmarkStart"):
        starts.append({"id": node.get(f"{W}id"), "name": node.get(f"{W}name")})
    for node in root.iter(f"{W}bookmarkEnd"):
        ends.append({"id": node.get(f"{W}id")})
    start_ids = [x["id"] for x in starts]
    end_ids = [x["id"] for x in ends]
    return {
        "starts": starts,
        "startCount": len(starts),
        "endCount": len(ends),
        "duplicateStartIds": [k for k, v in Counter(start_ids).items() if v > 1],
        "missingEndIds": sorted(set(start_ids) - set(end_ids)),
        "orphanEndIds": sorted(set(end_ids) - set(start_ids)),
    }


def source_bookmark_noise(source_docx: Path | None) -> dict[str, set[str]]:
    if source_docx is None:
        return {"missingEndIds": set(), "orphanEndIds": set()}
    try:
        with zipfile.ZipFile(source_docx, "r") as zf:
            root = etree.fromstring(zf.read("word/document.xml"))
        report = bookmark_report(root)
        return {
            "missingEndIds": set(report["missingEndIds"]),  # type: ignore[arg-type]
            "orphanEndIds": set(report["orphanEndIds"]),  # type: ignore[arg-type]
        }
    except Exception:
        return {"missingEndIds": set(), "orphanEndIds": set()}


def in_references_section(text: str, ref_section_active: bool) -> tuple[bool, bool]:
    stripped = text.strip()
    if stripped in {"参考文献", "References", "REFERENCES"}:
        return True, True
    if ref_section_active and stripped in {"致谢", "致  谢", "附录", "Appendix", "Appendices"}:
        return False, False
    return ref_section_active, False


def audit_docx(docx: Path, source_docx: Path | None = None) -> dict[str, object]:
    stat = docx.stat()
    report: dict[str, object] = {
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "file": {
            "path": str(docx),
            "sha256": sha256(docx),
            "size": stat.st_size,
            "mtime": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
        },
        "sourceProtection": None,
        "structure": {},
        "fields": {"total": 0, "byType": {}, "fldCharBalance": {}},
        "bookmarks": {},
        "captions": [],
        "bodyReferences": [],
        "bibliography": {"entries": [], "citations": []},
        "issues": [],
        "manualConfirm": [],
    }
    if source_docx:
        src_stat = source_docx.stat()
        report["sourceProtection"] = {
            "path": str(source_docx),
            "sha256": sha256(source_docx),
            "size": src_stat.st_size,
            "mtime": datetime.fromtimestamp(src_stat.st_mtime, timezone.utc).isoformat(),
        }

    with zipfile.ZipFile(docx, "r") as zf:
        names = zf.namelist()
        root = etree.fromstring(zf.read("word/document.xml"))
        body = root.find(f"{W}body")
        paragraphs = list(body.iter(f"{W}p")) if body is not None else []
        tables = list(body.iter(f"{W}tbl")) if body is not None else []

        fields: list[dict[str, str]] = []
        for para in paragraphs:
            fields.extend(parse_fields(para))

        by_type: dict[str, int] = {}
        for field in fields:
            kind = field_type(field["instr"])
            by_type[kind] = by_type.get(kind, 0) + 1

        begins = sum(1 for x in root.iter(f"{W}fldChar") if x.get(f"{W}fldCharType") == "begin")
        separates = sum(1 for x in root.iter(f"{W}fldChar") if x.get(f"{W}fldCharType") == "separate")
        ends = sum(1 for x in root.iter(f"{W}fldChar") if x.get(f"{W}fldCharType") == "end")

        bookmarks = bookmark_report(root)
        bookmark_names = {x["name"] for x in bookmarks["starts"] if x.get("name")}  # type: ignore[index]

        report["structure"] = {
            "zipPartCount": len(names),
            "paragraphCount": len(paragraphs),
            "tableCount": len(tables),
        }
        report["fields"] = {
            "total": len(fields),
            "byType": by_type,
            "all": fields[:200],
            "fldCharBalance": {
                "begin": begins,
                "separate": separates,
                "end": ends,
                "balanced": begins == separates == ends,
            },
        }
        report["bookmarks"] = bookmarks

        caption_pat = re.compile(
            r"^\s*((?:图|表|算法|Figure|Table|Algorithm|Fig\.|Tbl\.)\s*\d+[-.]\d+)\b",
            re.IGNORECASE,
        )
        body_label_pat = re.compile(
            r"((?:如图|如表|见图|见表|图|表|Figure|Table|Fig\.|Tbl\.)\s*\d+[-.]\d+)",
            re.IGNORECASE,
        )
        cite_pat = re.compile(r"\[(\d+(?:\s*[,;，、]\s*\d+)*)\]")
        bib_entry_pat = re.compile(r"^\[(\d+)\]")

        ref_section = False
        bibliography_entry_numbers: set[str] = set()
        caption_labels: set[str] = set()
        for idx, para in enumerate(paragraphs):
            text = text_of_para(para).strip()
            if not text:
                continue
            ref_section, just_started_refs = in_references_section(text, ref_section)
            para_fields = parse_fields(para)

            cap_match = caption_pat.search(text)
            if cap_match:
                cap_start = cap_match.start(1)
                cap_end = cap_match.end(1)
                report["captions"].append(
                    {
                        "paragraphIndex": idx,
                        "label": cap_match.group(1),
                        "text": text[:200],
                        "hasField": range_covered_by_field(para, cap_start, cap_end, {"SEQ", "REF"}),
                    }
                )
                caption_labels.add(re.sub(r"\s+", "", cap_match.group(1)).replace(".", "-"))
                continue

            if ref_section and not just_started_refs:
                bib_match = bib_entry_pat.search(text)
                if bib_match:
                    bibliography_entry_numbers.add(bib_match.group(1))
                    report["bibliography"]["entries"].append(  # type: ignore[index]
                        {"paragraphIndex": idx, "number": bib_match.group(1), "text": text[:220]}
                    )
                continue

            for match in body_label_pat.finditer(text):
                label_match = re.search(
                    r"(图|表|算法|Figure|Table|Algorithm|Fig\.|Tbl\.)\s*\d+[-.]\d+",
                    match.group(1),
                    re.IGNORECASE,
                )
                field_start = match.start(1) + (label_match.start(0) if label_match else 0)
                field_end = match.start(1) + (label_match.end(0) if label_match else len(match.group(1)))
                report["bodyReferences"].append(
                    {
                        "paragraphIndex": idx,
                        "label": match.group(1),
                        "fieldText": label_match.group(0) if label_match else match.group(1),
                        "context": text[:220],
                        "hasField": range_covered_by_field(para, field_start, field_end, {"REF", "PAGEREF"}),
                    }
                )
            for match in cite_pat.finditer(text):
                nums = [x for x in re.split(r"\s*[,;，、]\s*", match.group(1)) if x]
                if "0" in nums or looks_like_code_context(text):
                    continue
                report["bibliography"]["citations"].append(  # type: ignore[index]
                    {
                        "paragraphIndex": idx,
                        "label": match.group(0),
                        "context": text[:220],
                        "hasField": range_covered_by_field(para, match.start(0), match.end(0), {"REF"}),
                    }
                )

        issues = report["issues"]  # type: ignore[assignment]
        if not report["fields"]["fldCharBalance"]["balanced"]:  # type: ignore[index]
            issues.append({"severity": "error", "type": "unbalanced-fields", "repairable": False})
        inherited_noise = source_bookmark_noise(source_docx)
        missing_end_ids = set(bookmarks["missingEndIds"])  # type: ignore[arg-type]
        orphan_end_ids = set(bookmarks["orphanEndIds"])  # type: ignore[arg-type]
        new_missing_end_ids = sorted(missing_end_ids - inherited_noise["missingEndIds"])
        new_orphan_end_ids = sorted(orphan_end_ids - inherited_noise["orphanEndIds"])
        inherited_missing_end_ids = sorted(missing_end_ids & inherited_noise["missingEndIds"])
        inherited_orphan_end_ids = sorted(orphan_end_ids & inherited_noise["orphanEndIds"])

        if new_missing_end_ids or new_orphan_end_ids:
            issues.append({"severity": "error", "type": "unpaired-bookmarks", "repairable": False})
        if inherited_missing_end_ids or inherited_orphan_end_ids:
            issues.append(
                {
                    "severity": "info",
                    "type": "inherited-template-bookmark-noise",
                    "missingEndIds": inherited_missing_end_ids,
                    "orphanEndIds": inherited_orphan_end_ids,
                    "repairable": False,
                }
            )

        orphan_refs = []
        for field in fields:
            target = ref_target(field["instr"])
            if target and target not in bookmark_names:
                orphan_refs.append(target)
        if orphan_refs:
            issues.append(
                {
                    "severity": "error",
                    "type": "orphan-ref-targets",
                    "targets": sorted(set(orphan_refs)),
                    "repairable": False,
                }
            )

        for item in report["bodyReferences"]:  # type: ignore[assignment]
            if not item["hasField"]:
                normalized_label = re.sub(r"^(如|见)", "", str(item.get("fieldText") or item.get("label") or ""))
                normalized_label = re.sub(r"\s+", "", normalized_label).replace(".", "-")
                if normalized_label not in caption_labels:
                    issues.append(
                        {
                            "severity": "warning",
                            "type": "static-body-reference",
                            "label": item["label"],
                            "paragraphIndex": item["paragraphIndex"],
                            "repairable": "missing-caption-target",
                        }
                    )
                    continue
                issues.append(
                    {
                        "severity": "info",
                        "type": "static-body-reference",
                        "label": item["label"],
                        "paragraphIndex": item["paragraphIndex"],
                        "repairable": "needs-unambiguous-caption-target",
                    }
                )
        for item in report["bibliography"]["citations"]:  # type: ignore[index]
            if not item["hasField"]:
                nums = [x for x in re.findall(r"\d+", str(item["label"]))]
                if bibliography_entry_numbers and not all(num in bibliography_entry_numbers for num in nums):
                    issues.append(
                        {
                            "severity": "info",
                            "type": "static-bracket-not-bibliography",
                            "label": item["label"],
                            "paragraphIndex": item["paragraphIndex"],
                            "repairable": False,
                        }
                    )
                    continue
                issues.append(
                    {
                        "severity": "info",
                        "type": "static-bibliography-citation",
                        "label": item["label"],
                        "paragraphIndex": item["paragraphIndex"],
                        "repairable": "needs-unambiguous-bibliography-entry",
                    }
                )

    add_completion_gate(report)
    return report


def add_completion_gate(report: dict[str, object]) -> None:
    issues = report.get("issues", [])
    if not isinstance(issues, list):
        issues = []
    manual_confirm = report.get("manualConfirm", [])
    if not isinstance(manual_confirm, list):
        manual_confirm = []

    issue_counts = Counter(str(issue.get("type", "unknown")) for issue in issues if isinstance(issue, dict))
    blocking = [
        issue
        for issue in issues
        if isinstance(issue, dict)
        and (issue.get("severity") == "error" or str(issue.get("type")) in BLOCKING_ISSUE_TYPES)
    ]
    repairable = [
        issue
        for issue in issues
        if isinstance(issue, dict)
        and str(issue.get("type")) in REPAIRABLE_ISSUE_TYPES
        and issue.get("repairable") not in {False, None, "missing-caption-target"}
    ]
    manual = [
        issue
        for issue in issues
        if isinstance(issue, dict)
        and str(issue.get("type")) in REPAIRABLE_ISSUE_TYPES
        and issue.get("repairable") in {False, None, "missing-caption-target"}
    ]
    qa_complete = not blocking and not repairable and not manual and not manual_confirm
    if repairable:
        next_action = "run-low-risk-repair"
    elif blocking or manual or manual_confirm:
        next_action = "manual-confirm-or-script-enhancement"
    else:
        next_action = "complete"

    report["completionGate"] = {
        "qaComplete": qa_complete,
        "currentPhase": "qa-complete" if qa_complete else "xref-qa",
        "nextSkill": None if qa_complete else "portable-thesis-xref-qa",
        "nextAction": next_action,
        "issueCounts": dict(issue_counts),
        "blockingIssues": blocking,
        "repairableIssues": repairable,
        "manualIssues": manual,
        "manualConfirmCount": len(manual_confirm),
    }


def write_markdown(report: dict[str, object], path: Path) -> None:
    fields = report["fields"]  # type: ignore[assignment]
    bookmarks = report["bookmarks"]  # type: ignore[assignment]
    lines = [
        "# Xref QA Audit",
        "",
        f"- DOCX: `{report['file']['path']}`",  # type: ignore[index]
        f"- SHA256: `{report['file']['sha256']}`",  # type: ignore[index]
        f"- Fields: {fields['total']} {fields['byType']}",
        f"- fldChar balanced: {fields['fldCharBalance']['balanced']}",
        f"- Bookmarks: start={bookmarks['startCount']} end={bookmarks['endCount']}",
        f"- Captions: {len(report['captions'])}",  # type: ignore[arg-type]
        f"- Body refs: {len(report['bodyReferences'])}",  # type: ignore[arg-type]
        f"- Bibliography citations: {len(report['bibliography']['citations'])}",  # type: ignore[index]
        f"- Issues: {len(report['issues'])}",  # type: ignore[arg-type]
        f"- QA complete: {report.get('completionGate', {}).get('qaComplete') if isinstance(report.get('completionGate'), dict) else False}",
        f"- Next action: {report.get('completionGate', {}).get('nextAction') if isinstance(report.get('completionGate'), dict) else 'unknown'}",
        "",
        "## Issues",
        "",
    ]
    for issue in report["issues"]:  # type: ignore[assignment]
        lines.append(f"- {issue['severity']}: {issue['type']} {issue.get('label', '')}")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--docx", required=True, help="DOCX copy to audit")
    parser.add_argument("--source-docx", help="Optional original source/template DOCX")
    parser.add_argument("--sidecar", help="Optional .sync.json sidecar to update with xref QA workflow state")
    parser.add_argument("--out-json", help="JSON report path")
    parser.add_argument("--out-md", help="Markdown report path")
    parser.add_argument("--fail-on-incomplete", action="store_true", help="Exit 2 when completionGate.qaComplete is false")
    args = parser.parse_args()

    docx = Path(args.docx).resolve()
    source = Path(args.source_docx).resolve() if args.source_docx else None
    report = audit_docx(docx, source)

    out_json = Path(args.out_json).resolve() if args.out_json else docx.with_suffix(".xref_audit.json")
    out_md = Path(args.out_md).resolve() if args.out_md else docx.with_suffix(".xref_audit.md")
    out_json.parent.mkdir(parents=True, exist_ok=True)
    write_json(out_json, report)
    write_markdown(report, out_md)
    if args.sidecar:
        update_sync_sidecar(Path(args.sidecar).resolve(), report, out_json, out_md)
    print(out_json)
    print(out_md)
    gate = report.get("completionGate", {})
    qa_complete = bool(gate.get("qaComplete")) if isinstance(gate, dict) else False
    next_action = gate.get("nextAction") if isinstance(gate, dict) else "unknown"
    print(f"QA_COMPLETE={str(qa_complete).lower()}")
    print(f"NEXT_ACTION={next_action}")
    if args.fail_on_incomplete and not qa_complete:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
