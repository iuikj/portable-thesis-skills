---
name: portable-thesis-workflow
description: Orchestrate a reusable Trellis-backed graduation thesis workflow from school DOCX template intake through Markdown drafting, template-based DOCX delivery, and cross-reference QA. Use when starting a new thesis project for another user, designing a portable thesis-writing workflow, creating thesis project structure, or coordinating the portable-thesis-* subskills. Do not use for repository-specific local DOCX sync tasks unless the user explicitly asks for the portable/generalized workflow.
---

# Portable Thesis Workflow

Use this as the main entry skill for a new, reusable thesis project. It coordinates the portable subskills and keeps project-specific paths in a config file instead of hard-coding local directories.

## Skill Routing

- Use `portable-thesis-template` when the task is to collect or analyze the school's DOCX template.
- Use `portable-thesis-env` when the task is to check Python, `uv`, virtualenv, packages, `officecli`, or the officecli skill.
- Use `portable-thesis-md` when the task is to create the Markdown thesis workspace and chapter files.
- Use `portable-thesis-docx-sync` when Markdown content must be inserted or incrementally synced into a protected DOCX copy.
- Use `portable-thesis-xref-qa` when the task is caption, REF/SEQ/PAGEREF, bibliography citation, superscript, or render QA.
- Prefer this `portable-thesis-*` suite for general/new projects. Prefer project-local skills, such as `thesis-docx-sync`, for already-customized local workflows.

## Project Profile

Create or update `thesis-project.json` in the thesis project root. Use relative paths from that root where possible:

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
  "workflow": {
    "baselineTagPrefix": "to-docx-",
    "currentPhase": "template"
  }
}
```

Read `references/project-profile.md` before creating or changing this file.

## Trellis Task Flow

If the target project has `.trellis/`, use it:

1. Check the active task with `.trellis/scripts/task.py current --source`.
2. If no relevant task exists, create one for the thesis workflow.
3. Write or update `prd.md` with the user's school, template path, expected deliverables, and acceptance criteria.
4. Start the task only after the template/input requirements are clear enough.
5. Store template analysis, environment reports, and sync reports under the task directory or the thesis project root, not in chat memory.

If the target project has no Trellis, create `workflow/` under the thesis root and write `workflow/status.md` with current phase, decisions, and next action.

## End-to-End Workflow

1. Template intake:
   Create `template/` and ask the user to place the school DOCX template there if no path was provided. Run `portable-thesis-template`.

2. Environment bootstrap:
   Run `portable-thesis-env`. Prefer `uv` if available, but allow `python -m venv` fallback. Do not silently install system tools.

3. Markdown workspace:
   Run `portable-thesis-md` after template requirements are known. Create chapter files from template structure plus user preferences.

4. Initial DOCX:
   Use `portable-thesis-docx-sync` to copy the template and fill/replace only the content regions that the template analysis marks as editable. Preserve cover pages, declarations, authorization pages, headers, footers, styles, fields, and TOC structures unless the user explicitly changes them.

5. Iteration:
   Track Markdown changes in git. Sync only targeted changes into a protected DOCX copy and tag synced commits with the configured `baselineTagPrefix`.

6. Closing QA:
   Run `portable-thesis-xref-qa` on the output DOCX. Report field integrity, caption/reference status, bibliography citation status, validation results, and render QA status.

## Non-Negotiable Rules

- Never edit the original school template or source DOCX directly.
- Do not rebuild a thesis DOCX from scratch when a school template exists; work on a copy of the template.
- Treat explicit template text requirements as higher priority than inferred style/OOXML evidence.
- Keep project paths, interpreter paths, and filenames configurable.
- Preserve Word fields and bookmarks: never flatten `SEQ`, `REF`, `PAGEREF`, `fldChar`, `instrText`, or bookmarks during sync or QA.
- Ask for user confirmation before any repair that changes numbering, inserts missing captions, or may alter official front matter.

## Final Report

Report the project root, `thesis-project.json` path, template analysis outputs, environment status, Markdown workspace path, DOCX output path, QA status, and any manual-confirm items.
