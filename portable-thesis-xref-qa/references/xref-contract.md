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
