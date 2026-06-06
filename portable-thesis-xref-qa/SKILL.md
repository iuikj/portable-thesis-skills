---
name: portable-thesis-xref-qa
description: Audit and safely repair a thesis DOCX copy for figure/table captions, Word REF/SEQ/PAGEREF fields, bibliography citation fields, citation superscript formatting, and render QA. Use after portable-thesis-docx-sync, when checking a finished thesis DOCX, or when the user asks about broken captions, static figure/table references, citation markers, or Word field integrity.
---

# Portable Thesis Xref QA

Use this skill on a DOCX copy, not on the official template or source document.

## Inputs

- Output DOCX copy to audit.
- Original source DOCX or template for source-protection comparison.
- Optional `.sync.json` sidecar from `portable-thesis-docx-sync`.
- Optional template analysis JSON for school-specific caption/reference rules.

Read `references/xref-contract.md` before applying repairs.

## Rules

- Never edit the source DOCX directly.
- Prefer ZIP-level OOXML patches for field-safe repairs.
- Do not flatten `SEQ`, `REF`, `PAGEREF`, `fldChar`, `instrText`, or bookmarks.
- Existing correct fields stay untouched.
- Treat caption insertion that changes numbering as manual-confirm, not automatic repair.
- Disable `officecli` resident/background behavior for read-only validation when supported.

## Audit Categories

Check:

- figure/table/equation/algorithm captions and numbering;
- body mentions such as `Figure 1-1`, `Fig. 1-1`, `图1-1`, or `表1-1` that should be REF fields;
- range references where each endpoint should be a field;
- bibliography citations such as `[1]` that should link to bibliography bookmarks;
- cached bibliography citation text superscript formatting;
- dangling `REF`/`PAGEREF` targets;
- bookmark id pairing and duplicate ids;
- render QA feasibility and visual page issues.

## Low-Risk Repairs

Apply only when the target is unambiguous:

- Replace a static figure/table label in body text with a `REF` field pointing to an existing caption bookmark.
- Replace each endpoint of a range reference with its own `REF` field while preserving ordinary separator text.
- Replace a static bibliography marker with a `REF` field pointing to an existing bibliography bookmark.
- Add superscript formatting to cached bibliography REF display text.

## Manual Confirmation Items

Ask before:

- inserting a missing caption;
- changing caption numbering;
- creating new bookmarks for ambiguous labels;
- editing paragraphs with mixed field structures beyond ordinary text replacement;
- accepting output when render QA could not run.

## Validation

Run structural checks:

- ZIP part list stable;
- `SEQ` and `PAGEREF` counts do not decrease;
- `fldChar begin/separate/end` counts are balanced;
- bookmark start/end ids are paired;
- every `REF` and `PAGEREF` target exists;
- no unresolved static body labels remain unless they are documented exceptions;
- no static body bibliography markers remain unless documented exceptions;
- bibliography REF cached text is superscript when required.

Run `officecli validate <copy.docx>` when available. Compare errors with the source DOCX and report inherited template noise separately.

Render QA requires external tools such as LibreOffice/`soffice`, `pdftoppm`, `pdf2image`, and `Pillow`. If missing, state that render QA was not completed.

## Final Report

Report output DOCX path, source hash/size/mtime status, repair list, skipped manual-confirm items, field/bookmark counts, bibliography superscript result, validation result, inherited errors, render QA status, and cleanup status.
