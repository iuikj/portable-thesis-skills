# Project Profile Contract

Use `thesis-project.json` as the portable source of truth for paths and workflow state.

## Required Principles

- Store it in the thesis project root.
- Prefer relative paths from the project root.
- Do not store machine-specific absolute paths unless no relative path can represent the resource.
- Keep official template files immutable; generated copies and reports go elsewhere.
- Update `workflow.currentPhase` after completing each major phase.

## Minimal Schema

```json
{
  "schemaVersion": 1,
  "projectName": "my-thesis",
  "template": {
    "directory": "template",
    "sourceDocx": "template/school-template.docx",
    "analysisJson": "template/template-analysis.json",
    "analysisMarkdown": "template/template-analysis.md"
  },
  "workspace": {
    "markdownDir": "thesis_md",
    "figuresDir": "figures",
    "docxDir": "docx",
    "venvDir": ".venv"
  },
  "tools": {
    "python": null,
    "uv": null,
    "officecli": null
  },
  "workflow": {
    "baselineTagPrefix": "to-docx-",
    "currentPhase": "template",
    "lastSyncedCommit": null
  }
}
```

## Phase Values

- `template`: template folder exists; waiting for analysis or user input.
- `environment`: tooling is being checked or installed.
- `drafting`: Markdown workspace exists and writing is underway.
- `initial-docx`: first template-based DOCX is being prepared.
- `syncing`: post-draft Markdown changes are being synced to DOCX.
- `qa`: DOCX is undergoing xref/format/render checks.
- `accepted`: user accepted the current output.

## Artifact Naming

Use stable, descriptive filenames:

- `template/template-analysis.json`
- `template/template-analysis.md`
- `docx/<template-stem>_draft_<shortsha>.docx`
- `docx/<template-stem>_sync_<shortsha>.docx`
- `docx/<output-stem>.sync.json`
- `docx/<output-stem>.xref_audit.json`

Generated JSON reports should include source file SHA256, size, and mtime. Mark source template and final DOCX as non-cleanable in sidecars.
