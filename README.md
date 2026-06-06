# Portable Thesis Skills

Portable Codex skills for graduation thesis workflows based on school DOCX templates, Markdown drafting, template-preserving DOCX sync, and cross-reference QA.

## Skills

- `portable-thesis-workflow`: Orchestrates a reusable thesis workflow from template intake through final DOCX QA.
- `portable-thesis-env`: Audits and prepares the local DOCX tooling environment.
- `portable-thesis-template`: Extracts portable requirements from a school DOCX template.
- `portable-thesis-md`: Creates and maintains the Markdown thesis workspace.
- `portable-thesis-docx-sync`: Syncs Markdown changes into a protected copy of the official DOCX template.
- `portable-thesis-xref-qa`: Audits and repairs captions, Word fields, citations, and cross-references in DOCX outputs.

## Install

Install all skills for Codex:

```powershell
npx skills add iuikj/portable-thesis-skills -a codex --all
```

Install one skill:

```powershell
npx skills add iuikj/portable-thesis-skills -a codex -s portable-thesis-workflow
```

List available skills without installing:

```powershell
npx skills add iuikj/portable-thesis-skills --list
```

## Usage

Start with:

```text
$portable-thesis-workflow
```

For focused tasks, call the specific skill directly:

```text
$portable-thesis-template
$portable-thesis-md
$portable-thesis-docx-sync
$portable-thesis-xref-qa
```

## Repository Layout

Each skill is published as a top-level directory containing `SKILL.md` plus optional `references/`, `scripts/`, and `agents/` assets.

## License

No license has been specified yet.

