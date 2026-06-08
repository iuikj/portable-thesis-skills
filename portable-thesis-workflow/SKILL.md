---
name: portable-thesis-workflow
description: Orchestrate a reusable Trellis-backed graduation thesis workflow from school DOCX template intake through Markdown drafting, template-based DOCX delivery, and cross-reference QA. Use when starting a new thesis project for another user, designing a portable thesis-writing workflow, creating thesis project structure, or coordinating the portable-thesis-* subskills. Do not use for repository-specific local DOCX sync tasks unless the user explicitly asks for the portable/generalized workflow.
---

# Portable Thesis Workflow

Use this as the main entry skill for a new, reusable thesis project. It coordinates the portable subskills and keeps project-specific paths in a config file instead of hard-coding local directories.

## Skill Routing

- Before doing phase-specific work, explicitly load and follow the matching child skill's `SKILL.md`. Do not merely mention the next child skill in prose.
- Use `portable-thesis-template` when the task is to collect or analyze the school's DOCX template.
- Use `portable-thesis-env` when the task is to check Python, `uv`, virtualenv, packages, `officecli`, or the officecli skill.
- Use `portable-thesis-md` when the task is to create the Markdown thesis workspace and chapter files.
- Use `portable-thesis-docx-sync` when Markdown content must be inserted or incrementally synced into a protected DOCX copy.
- Use `portable-thesis-xref-qa` when the task is caption, REF/SEQ/PAGEREF, bibliography citation, superscript, or render QA.
- Prefer this `portable-thesis-*` suite for general/new projects. Prefer project-local skills, such as `thesis-docx-sync`, for already-customized local workflows.

If a child skill is not installed in the current runtime, locate it from the project skill roots (`.agents/skills`, `.codex/skills`, `.claude/skills`, or the installed skill directory) and read its `SKILL.md` by path. If it still cannot be found, stop and report the missing skill; do not continue by inventing a fresh workflow.

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
   Load `portable-thesis-template`. Create `template/` and ask the user to place the school DOCX template there if no path was provided. Run the bundled template probe from that skill and write both JSON and Markdown analysis outputs.

2. Environment bootstrap:
   Load `portable-thesis-env`. Prefer `uv` if available, but allow `python -m venv` fallback. Do not silently install system tools.

3. Markdown workspace:
   Load `portable-thesis-md` after template requirements are known. Use its scaffold helper when creating a new workspace, then adjust chapter files from template structure plus user preferences.

4. Initial DOCX:
   Load `portable-thesis-docx-sync`. Generate a sync plan first, then copy the template and fill/replace only the content regions that the template analysis marks as editable. Preserve cover pages, declarations, authorization pages, headers, footers, styles, fields, and TOC structures unless the user explicitly changes them.
   Before handing off, verify the sync sidecar and output DOCX for converted inline Markdown, no visible Markdown residue, and two-character first-line indentation in body paragraphs.

5. Iteration:
   Track Markdown changes in git. Sync only targeted changes into a protected DOCX copy and tag synced commits with the configured `baselineTagPrefix`.

6. Closing QA:
   Load `portable-thesis-xref-qa` on the output DOCX. Run its bundled audit script before any repair, then continue in that same child skill invocation through low-risk repair and post-repair audit when repairable issues exist. Do not stop after a prose audit unless there are no repairable issues or the next change needs user confirmation. Report pre/post counts, field integrity, caption/reference status, bibliography citation status, validation results, and render QA status.

## Non-Negotiable Rules

- Never edit the original school template or source DOCX directly.
- Do not rebuild a thesis DOCX from scratch when a school template exists; work on a copy of the template.
- Treat explicit template text requirements as higher priority than inferred style/OOXML evidence.
- Keep project paths, interpreter paths, and filenames configurable.
- Preserve Word fields and bookmarks: never flatten `SEQ`, `REF`, `PAGEREF`, `fldChar`, `instrText`, or bookmarks during sync or QA.
- Ask for user confirmation before any repair that changes numbering, inserts missing captions, or may alter official front matter.
- Do not write large one-off scripts such as `analyze_template.py`, `sync_to_docx.py`, `xref_qa_audit.py`, or `add_bidirectional_refs.py` into the thesis project root. Use bundled child-skill scripts. If a bundled script is insufficient, patch or extend the child skill resource and rerun it, so the fix remains reusable.
- If shell heredoc syntax conflicts with Markdown, XML, or Windows quoting, write only small temporary helper input files under `workflow/` or the OS temp directory, execute them, record the reason, and clean them. Do not leave reusable logic as project-local temporary scripts.
- At every phase transition, write `workflow/status.md` with `currentPhase`, completed artifacts, and `nextSkill`. The next action must name the child skill to load, not just describe the task.

## Final Report

Report the project root, `thesis-project.json` path, template analysis outputs, environment status, Markdown workspace path, DOCX output path, QA status, and any manual-confirm items.
