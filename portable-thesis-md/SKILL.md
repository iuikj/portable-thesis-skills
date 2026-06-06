---
name: portable-thesis-md
description: Create and maintain a git-backed Markdown workspace for a portable graduation thesis project. Use after a school DOCX template has been analyzed, when the user wants chapter Markdown files, figure/reference directories, a thesis-project.json update, or a draft structure based on template requirements and user preferences.
---

# Portable Thesis Markdown

Use this skill to create the thesis source workspace that later syncs into DOCX.

## Inputs

- Thesis project root.
- `thesis-project.json` if available.
- Template analysis JSON from `portable-thesis-template`.
- User preferences for chapter names, language, appendices, and bibliography style.

## Workspace Shape

Default structure:

```text
thesis-project/
|-- thesis-project.json
|-- thesis_md/
|   |-- 00_front_matter.md
|   |-- 01_introduction.md
|   |-- 02_related_work.md
|   |-- 03_requirements.md
|   |-- 04_design.md
|   |-- 05_implementation.md
|   |-- 06_testing.md
|   |-- 07_conclusion.md
|   |-- references.md
|   `-- appendices.md
|-- figures/
|-- docx/
`-- workflow/
```

Adapt chapter files to the template analysis and user domain. Do not force this exact list when the school template gives another structure.

## Workflow

1. Read template analysis:
   Use `workflowRecommendations.markdownChapters` when present. Otherwise infer a conservative chapter plan from protected/editable regions and user preference.

2. Create directories:
   Create Markdown, figures, DOCX, and workflow directories from `thesis-project.json.workspace`.

3. Initialize git:
   If the project root is not already a git repository, run `git init`. Do not commit automatically unless the user asks.

4. Write chapter files:
   Each file should start with a heading and a short drafting-notes block describing required content, word-count expectations, figure/table expectations, and template-specific formatting notes.

5. Update project profile:
   Set `workflow.currentPhase` to `drafting` and record workspace paths.

You may use the bundled scaffold helper:

```bash
python <skill-dir>/scripts/scaffold_md_workspace.py --root <project-root> --profile thesis-project.json --chapters "1 Introduction;2 Design;3 Testing"
```

## Do Not

- Do not overwrite existing Markdown files without user confirmation.
- Do not invent school requirements that were not found in the template or provided by the user.
- Do not create a DOCX in this skill; hand off to `portable-thesis-docx-sync`.
- Do not include generated build artifacts in git by default.

## Final Report

Report the project root, git status, created directories, created/skipped Markdown files, updated profile path, and next recommended skill.
