# Template Analysis Schema

Use this schema as a stable contract. Fields can be extended, but the top-level keys should stay stable.

```json
{
  "generatedAt": "2026-01-01T00:00:00Z",
  "sourceFiles": {
    "template": {
      "path": "template/school-template.docx",
      "sha256": "...",
      "size": 0,
      "mtime": "..."
    },
    "writtenRequirements": []
  },
  "methodology": [
    "Read explicit requirement text first.",
    "Use OOXML/style evidence only as supporting evidence.",
    "Resolve conflicts in favor of explicit official text."
  ],
  "templateRequirements": {
    "sourcePriority": ["explicit-template-text", "official-handbook", "style-inference"],
    "documentStructure": [],
    "protectedRegions": [],
    "editableRegions": [],
    "pageSetup": {},
    "typography": {},
    "headingRules": {},
    "numberingAndElements": {},
    "referenceRequirements": {},
    "submissionRequirements": {}
  },
  "templateScan": {
    "paragraphCount": 0,
    "tableCount": 0,
    "imageCount": 0,
    "sectionCount": 0,
    "styles": [],
    "headers": [],
    "footers": [],
    "fieldCounts": {},
    "sampleParagraphs": []
  },
  "conflicts": [
    {
      "topic": "body font size",
      "explicitRequirement": "12pt",
      "inferredTemplateStyle": "10.5pt",
      "resolution": "follow explicitRequirement",
      "risk": "medium"
    }
  ],
  "workflowRecommendations": {
    "markdownChapters": [],
    "docxSync": {
      "copyTemplateFirst": true,
      "preserveRegions": [],
      "editableRegions": []
    },
    "qaChecklist": []
  }
}
```

## Requirement Priority

Use this order when sources disagree:

1. Explicit text in the official current template.
2. Explicit text in the current official handbook or school web page.
3. Style definitions and OOXML structure in the template.
4. Common thesis conventions.

Record every meaningful conflict instead of silently choosing.
