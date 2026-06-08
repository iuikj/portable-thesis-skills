# Portable DOCX Sync Contract

This contract generalizes a project-specific incremental DOCX sync workflow.

## Source Protection

Before editing:

- Record source SHA256, size, and mtime.
- Copy the source to a new output DOCX.
- Write a sidecar JSON next to the output.
- Mark the official template/source DOCX and final output DOCX as non-cleanable.

## Sidecar Shape

```json
{
  "schemaVersion": 1,
  "sourceDocx": {
    "path": "docx/source.docx",
    "sha256": "...",
    "size": 0,
    "mtime": "..."
  },
  "outputDocx": {
    "path": "docx/source_sync_abc1234.docx"
  },
  "git": {
    "base": "to-docx-old",
    "target": "abc1234",
    "baselineTagPrefix": "to-docx-"
  },
  "artifacts": [
    {"path": "docx/output.sync.json", "role": "sidecar", "cleanup": true},
    {"path": "docx/output.docx", "role": "deliverable", "cleanup": false}
  ]
}
```

## Patch Safety

Safe automatic edits:

- exact old-to-new text replacement in the expected section;
- replacing ordinary `w:t` text around existing fields;
- updating a copied output file, never the source.

Manual-confirm edits:

- ambiguous old text;
- baseline drift where old text is absent and new text is absent;
- any edit to a paragraph with complex fields if the operation is more than ordinary text around fields;
- caption insertion or renumbering;
- front matter, declarations, authorization pages, TOC, headers, or footers.

## Verification

Required checks:

- source hash/size/mtime unchanged;
- output DOCX opens as a ZIP and has expected Word parts;
- ZIP part list did not unexpectedly shrink;
- `SEQ`, `REF`, `PAGEREF`, `fldChar`, `instrText`, and bookmark counts did not decrease unexpectedly;
- `bookmarkStart` and `bookmarkEnd` ids are paired after replacing any template region;
- official declaration/authorization pages still exist after initial draft generation;
- Chinese abstract body and `关键词` exist; English abstract exists when provided;
- stale template instruction/sample terms and tables are absent from the output;
- Markdown tables are real Word tables or are explicit manual-confirm blockers;
- visible Markdown residue is absent outside code-font paragraphs;
- expected old text is gone and new text is present;
- `officecli validate` run when available;
- xref QA run or explicitly deferred.

## Initial Template Replacement

For an initial draft, prefer `replace-template-body`. It preserves front matter and replaces the editable abstract/body/reference/acknowledgement region as one audited operation. `append-before-sectpr` is diagnostic-only for school templates that contain sample body text; it must not be treated as a deliverable because it leaves the sample thesis content and stale TOC entries in place.

After replacing a template region, remove stale bookmark endpoints that became unpaired because a template TOC/bookmark span crossed the replaced region boundary. Record those removed endpoints in the sidecar and verify bookmark pairing again before handoff.
