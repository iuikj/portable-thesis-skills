---
name: portable-thesis-docx-sync
description: Sync a Markdown thesis draft or later Markdown changes into a protected copy of a school-template-based DOCX without rebuilding the document from scratch. Use when creating the initial DOCX from a template, incrementally syncing thesis_md changes, preserving official front matter, or preparing a DOCX for xref QA in a portable thesis project.
---

# Portable Thesis DOCX Sync

Use this skill to create or update DOCX outputs while preserving the official template.

## Inputs

- `thesis-project.json`.
- Template analysis JSON from `portable-thesis-template`.
- Markdown source directory.
- Official template DOCX or previous finished DOCX.
- Optional git base/target commits for incremental sync.

Read `references/sync-contract.md` before editing any DOCX.

Use bundled scripts before writing custom code:

```bash
python <skill-dir>/scripts/sync_markdown_docx.py --root <project-root> --profile thesis-project.json --plan-out <docx-output>.sync.json
python <skill-dir>/scripts/sync_markdown_docx.py --root <project-root> --profile thesis-project.json --out <output.docx> --apply --insert-mode replace-template-body
python <portable-thesis-xref-qa>/scripts/xref_audit.py --docx <output.docx> --source-docx <template-or-pre-xref.docx> --sidecar <output.docx>.sync.json --out-json <output.docx>.xref_audit.json
```

The helper defaults to plan-only mode. Treat the plan as the review gate. If the helper lacks a needed reusable behavior, patch the helper in this skill and rerun it. Do not create a project-root `sync_to_docx.py` or another one-off large sync script.

The helper must convert common inline Markdown before writing DOCX: `**bold**` and `__bold__` become bold runs, `*italic*`/`_italic_` become italic runs, inline code becomes a code-font run, links become visible link text, and image syntax becomes a visible image placeholder unless a real image insertion path is implemented. Body paragraphs must use a two-character first-line indent (`w:firstLineChars=200`) unless the paragraph is a heading, list item, table row, caption, or other non-body block.

For initial DOCX generation, `replace-template-body` is the default and expected mode. Do not use `append-before-sectpr` for an initial school-template draft unless the user explicitly approves an append-only diagnostic file; that mode preserves stale template sample content and is not deliverable.

## Core Rules

- Never edit the source template or source DOCX directly.
- Always copy the source to a clearly named output DOCX and work only on the copy.
- Do not rebuild the whole document if a template exists.
- Preserve official cover pages, declarations, authorization pages, TOC SDT, headers, footers, styles, fields, bookmarks, and numbering unless the user explicitly approves a change.
- Use field-safe editing for paragraphs containing Word fields. Never flatten `SEQ`, `REF`, `PAGEREF`, `fldChar`, `instrText`, or bookmarks.
- Prefer ZIP-level OOXML patches for targeted text/field changes. Use `officecli` mainly for discovery, validation, and supported document operations.

## Initial DOCX Workflow

1. Confirm source template and output name.
2. Run the bundled sync helper in plan-only mode and review `manualConfirm`.
3. Copy the template to `docx/<template-stem>_draft_<shortsha-or-date>.docx`.
4. Use template analysis to identify protected and editable regions.
5. Fill cover metadata using existing tables/content controls where possible.
6. Replace template sample/instruction text only inside editable regions.
7. Insert Markdown content conservatively, preserving template styles, inline formatting, Markdown tables as Word tables, readable code/math blocks, fixed 20 pt line spacing, and two-character first-line indentation for body paragraphs.
8. Validate the output and record a `.sync.json` sidecar. Check `qualityGate.status`, `sourceProtection.unchanged`, `markdownInlineFormatting.residueAfterConversion`, and `manualConfirm`. Do not report DOCX sync as complete if `qualityGate.status` is `blocked`.
9. Load and run `portable-thesis-xref-qa` as the closing gate. Pass the sync sidecar via `--sidecar` so the xref audit registers its reports and updates the parent workflow state.

The sidecar is the authority for completion. It must show:

- official authorization/declaration pages still present;
- Chinese abstract body and `关键词` present;
- no stale template text/tables such as `正文要求`, `Corpus表`, `首页模块`, `课程模块`, or `购物商城模块`;
- no visible raw Markdown residue outside code blocks;
- source template hash/size unchanged;
- `workflow.currentPhase: xref-qa` and `workflow.nextSkill: portable-thesis-xref-qa` until the xref post-audit gate is clean;
- after xref audit, `xrefQa.completionGate.qaComplete: true` before reporting QA complete.

## Incremental Sync Workflow

1. Identify base and target:
   Prefer the latest configured `baselineTagPrefix`, such as `to-docx-*`, unless the user specifies another base.

2. Inspect diff:
   Review only Markdown and figure changes relevant to the thesis source. Ignore unrelated dirty files.

3. Prepare sidecar:
   Record source DOCX hash/size/mtime, target commit, output DOCX, and cleanable intermediate artifacts.

4. Build a patch plan:
   Locate changes by chapter/section range, then by local paragraph/table/image context. Do not use the first global keyword match.

5. Apply only reviewed targeted patches:
   Automatically apply exact old-to-new replacements when the old text is uniquely found in the expected section. Treat ambiguous/missing matches as blockers or manual-confirm items.

6. Verify:
   Check source unchanged, ZIP part list stability, old/new text assertions, field/bookmark counts, and `officecli validate` if available.

7. Tag:
   After user acceptance and a clean target commit, create or confirm a `to-docx-<shortsha>`-style baseline tag.

8. Run xref QA:
   Load `portable-thesis-xref-qa` and invoke its audit before final report.

## Manual Confirmation Points

Ask before:

- changing official front matter;
- replacing an ambiguous paragraph;
- adding missing captions that may renumber existing captions;
- flattening, updating, or deleting Word fields;
- deleting intermediate artifacts.

## Markdown Conversion Checks

Before reporting DOCX sync as complete:

- Verify no visible `**...**`, `__...__`, backtick inline-code markers, Markdown links, image syntax, or table separator rows remain in body text unless deliberately documented.
- Verify body paragraphs use two-character first-line indentation; headings, captions, lists, tables, code blocks, references, and front matter may use template-specific indentation instead.
- If a Markdown construct is unsupported, preserve the meaning in readable DOCX text and list it in `manualConfirm` rather than leaving raw Markdown markup in the final document.
- Verify Markdown tables became real `w:tbl` tables or are listed as manual-confirm blockers.
- Verify code identifiers such as `__init__` inside code-font paragraphs are not treated as Markdown residue.

## Handoff

After generating or updating a DOCX, update `workflow/status.md` or the Trellis task with:

- `currentPhase: xref-qa`;
- `nextSkill: portable-thesis-xref-qa`;
- source DOCX path/hash, output DOCX path, sidecar path, and manual-confirm items.

When continuing in the same session, immediately load `portable-thesis-xref-qa/SKILL.md` before auditing or repairing fields.

The sync sidecar is not complete while top-level `nextSkill` or `workflow.nextSkill` is `portable-thesis-xref-qa`. Follow the sidecar's `workflow.xrefAudit.commandArgs` or latest `xrefQa.completionGate.nextAction` rather than relying on a successful script exit.

## Final Report

Report source DOCX hash/size/mtime status, output DOCX path, diff range, applied patches, skipped/manual-confirm items, field/bookmark integrity, validation result, xref QA result, render QA status, tag status, and cleanup status.
