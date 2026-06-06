---
name: portable-thesis-template
description: Analyze a school graduation thesis DOCX template into portable requirements and workflow guidance. Use when the user provides a thesis/dissertation template, asks to create a template intake folder, wants JSON/Markdown requirements extracted from DOCX, or needs conflicts resolved between explicit template text and inferred styles. Prefer this portable skill for new projects, not repository-specific thesis template audits.
---

# Portable Thesis Template

Use this skill at the start of a portable thesis project. Its output drives Markdown scaffolding, DOCX sync boundaries, and QA checks.

## Inputs

- A school-provided `.docx` template, preferably placed under the project `template/` directory.
- Optional school written requirements from a PDF, website, handbook, or user notes.
- Optional `thesis-project.json` from `portable-thesis-workflow`.

If no template path is provided, create `template/` in the thesis project root and ask the user to place exactly one official DOCX template there. Do not infer a school's format from memory.

## Analysis Rules

- Treat explicit requirement text inside the template or official handbook as authoritative.
- Use style, OOXML, and visual/template structure as supporting evidence when explicit text is absent.
- If explicit text conflicts with inferred style, record the conflict and follow the explicit text.
- Preserve official front matter. Identify cover, declarations, authorization pages, TOC, headers, footers, and other pages that should be copied rather than rebuilt.
- Identify editable regions separately from protected regions.
- Do not modify the template file. Record SHA256, size, and mtime.

## Workflow

1. Locate the template:
   Use `thesis-project.json.template.sourceDocx` if present. Otherwise inspect `template/*.docx`. If multiple templates exist, ask the user which one is official.

2. Run read-only probes:
   Prefer `officecli` for high-level structure when available. Also run the bundled fallback probe:

   ```bash
   python <skill-dir>/scripts/docx_template_probe.py --docx <template.docx> --out <template-analysis.json>
   ```

3. Extract requirements:
   Read body paragraphs, tables, styles, headers/footers, captions, numbering examples, reference examples, and red/colored instruction text when available. Supplement with official written requirements if provided.

4. Produce JSON and Markdown:
   Follow `references/template-analysis-schema.md`. The JSON must include stable top-level keys: `sourceFiles`, `templateRequirements`, `templateScan`, `conflicts`, and `workflowRecommendations`.

5. Update project profile:
   If `thesis-project.json` exists, set `template.sourceDocx`, `template.analysisJson`, `template.analysisMarkdown`, and `workflow.currentPhase`.

## Output Expectations

The JSON report should capture:

- document structure and protected/editable regions;
- page setup, typography, heading numbering, paragraph rules;
- figure/table/equation/algorithm caption rules;
- reference count and bibliography formatting requirements;
- TOC/header/footer/field preservation notes;
- conflicts between explicit text and inferred style;
- recommendations for Markdown chapter scaffolding and DOCX sync.

The Markdown report should be readable by the user and list requirements, risks, and setup recommendations without requiring them to inspect JSON.

## Manual Confirmation Points

Ask the user before deciding:

- which of multiple DOCX files is the official template;
- whether non-template handbook text overrides template text;
- whether an ambiguous front-matter page is protected or editable;
- whether a detected example section should become actual chapter structure.

## Final Report

Report the template path, hash/size/mtime, JSON path, Markdown path, protected regions, editable regions, unresolved conflicts, and recommended next skill.
