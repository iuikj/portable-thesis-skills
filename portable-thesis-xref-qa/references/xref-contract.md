# Portable Xref QA Contract

## Field Preservation

Word fields are split across multiple runs. A valid REF field commonly contains:

```xml
<w:fldChar w:fldCharType="begin"/>
<w:instrText xml:space="preserve"> REF _Ref123 \h </w:instrText>
<w:fldChar w:fldCharType="separate"/>
<w:t>Figure 1-1</w:t>
<w:fldChar w:fldCharType="end"/>
```

Do not replace the whole paragraph when it contains these field runs. Edit only ordinary text nodes around fields unless the repair is specifically building a new field.

## Caption and Body Label Rules

Captions can be language-specific. Detect labels from the template analysis first. If no rule exists, support common forms:

- `Figure 1-1`, `Table 1-1`
- `Fig. 1-1`, `Tbl. 1-1`
- `图1-1`, `表1-1`

Do not convert continuation captions, list labels, or examples inside template instruction text unless they are in the final body.

## Bibliography Rules

Only convert static citations when a matching bibliography bookmark exists or can be created without ambiguity. Repeated citations are allowed. Superscript requirements come from the school template or user preference.

## Repair Plan

Before patching, prepare a repair list:

```json
{
  "repairs": [
    {
      "type": "body-label-to-ref",
      "label": "Figure 2-1",
      "bookmark": "_Ref123",
      "risk": "low"
    }
  ],
  "manualConfirm": []
}
```

Apply low-risk repairs, rerun the audit, and stop if the same issue remains but the repair condition is no longer unambiguous.

## Completion Gate

The final audit must write a machine-readable `completionGate`.

- `qaComplete: true` only when there are no blocking errors, no low-risk repairable issues, and no manual-confirm issues.
- `orphan-ref-targets`, unbalanced fields, and new unpaired bookmarks are blocking.
- Static figure/table mentions are low-risk repairable only when an unambiguous caption target already exists or can be bookmarked without changing numbering.
- Static figure/table mentions with no caption target are manual-confirm issues. Do not run `add_refs.py` and claim completion for them; insert or confirm the missing caption/image first.
- A successful audit or repair script exit is not completion. Use `completionGate.qaComplete`.

When the audit is the closing gate for a DOCX sync, pass the sync sidecar to `xref_audit.py` with `--sidecar`. The audit must register its JSON/Markdown reports in `artifacts[]`, copy `completionGate` into `xrefQa.completionGate`, and update `workflow.currentPhase`, `workflow.nextSkill`, and `workflow.nextAction`. A parent sidecar that still says `workflow.nextSkill: portable-thesis-xref-qa` is not complete.
