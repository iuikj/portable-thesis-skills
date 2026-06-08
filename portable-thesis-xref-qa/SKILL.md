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

Use bundled scripts before writing custom code:

```bash
python <skill-dir>/scripts/xref_audit.py --docx <output.docx> --source-docx <pre-repair-output-or-template.docx>
python <skill-dir>/scripts/add_refs.py --docx <output.docx> --out <output_xref.docx> --apply
python <skill-dir>/scripts/xref_audit.py --docx <output_xref.docx> --source-docx <output.docx>
```

Do not create project-root scripts such as `xref_qa_audit.py` or `add_bidirectional_refs.py`. If the bundled audit or repair script is insufficient, patch the script in this skill and rerun it so the behavior remains reusable.

## Rules

- Never edit the source DOCX directly.
- Prefer ZIP-level OOXML patches for field-safe repairs.
- Do not flatten `SEQ`, `REF`, `PAGEREF`, `fldChar`, `instrText`, or bookmarks.
- Existing correct fields stay untouched.
- Treat caption insertion that changes numbering as manual-confirm, not automatic repair.
- Disable `officecli` resident/background behavior for read-only validation when supported.
- Audit first, repair second, audit again after repair. Do not repair from memory or from a prose-only issue list.
- For the post-repair audit, pass the pre-repair DOCX copy as `--source-docx`. This lets inherited source noise, such as existing orphan bookmarkEnd ids, be reported separately from new repair damage.
- The bundled `add_refs.py` is low-risk only. It may add bookmarks around existing unambiguous caption labels and bibliography markers, then replace matching static body labels and citation markers with `REF` fields. It must not convert chapter-style caption numbers into new `SEQ` fields automatically, and bookmarks must wrap only the label/marker text, not the whole caption or bibliography paragraph. Anything beyond that is a manual-confirm item or a reusable script enhancement.
- Do not stop after audit when the audit reports low-risk repairable issues. In the same invocation of this skill, continue to the repair phase with `add_refs.py --apply`, then run a post-repair audit. Only stop after audit when there are no repairable issues or when the remaining items require manual confirmation.

## Audit Categories

Check:

- figure/table/equation/algorithm captions and numbering;
- body mentions such as `Figure 1-1`, `Fig. 1-1`, `\u56fe1-1`, or `\u88681-1` that should be REF fields;
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

## Audit-to-Repair Flow

After `xref_audit.py`, inspect the JSON issues and counts:

- If issues include `static-body-reference`, `static-bibliography-citation`, or no `REF` fields while unambiguous captions/bibliography entries exist, immediately run `add_refs.py --apply` on a new output copy.
- Treat missing caption `SEQ` fields as manual-confirm unless the template-specific numbering rule is known; do not ask `add_refs.py` to synthesize chapter-style `SEQ` fields from plain text captions.
- Then rerun `xref_audit.py` on the repaired copy with `--source-docx <pre-repair-docx>`.
- Report both pre-repair and post-repair counts.
- Set `workflow/status.md` to `currentPhase: xref-qa` and `nextSkill: portable-thesis-xref-qa` while repairable issues remain. Set `qa-complete` only after the repair pass and post-repair audit.
- If using a shell where heredoc quoting conflicts with Markdown or XML snippets, write temporary helper input files under the project `workflow/` or OS temp directory, run them, then record and clean them. Do not leave large helper scripts in the thesis project root.

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

## Handoff

After QA, update `workflow/status.md` or the Trellis task with:

- `currentPhase: qa-complete` when no blocking issue remains, otherwise `currentPhase: xref-qa`;
- audit JSON/Markdown paths;
- repair sidecar path if repairs were applied;
- remaining `manualConfirm` items;
- `nextSkill: portable-thesis-xref-qa` when a repair pass is still required; otherwise omit `nextSkill` or set it to `None`.

## Final Report

Report output DOCX path, source hash/size/mtime status, repair list, skipped manual-confirm items, field/bookmark counts, bibliography superscript result, validation result, inherited errors, render QA status, and cleanup status.
