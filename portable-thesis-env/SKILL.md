---
name: portable-thesis-env
description: Audit and prepare a portable thesis DOCX tooling environment, including Python, optional uv, virtual environments, Python packages, officecli, and the officecli skill. Use when starting a thesis project, checking whether the user's machine can analyze or edit DOCX files, or recording environment setup in thesis-project.json. Do not silently install global tools without user confirmation.
---

# Portable Thesis Env

Use this skill before template analysis or DOCX editing when the environment is unknown.

## Inputs

- Thesis project root.
- Optional `thesis-project.json`.
- User permission for installs when a tool is missing.

## Checks

Run read-only checks first:

```bash
python --version
python -m pip --version
uv --version
officecli --version
```

Also inspect available skills if the platform exposes them and verify an office document skill is installed or available.

## Environment Strategy

- Prefer `uv` when present because it is fast and reproducible.
- If `uv` is absent, use `python -m venv` and `python -m pip`.
- Do not require shell activation; record explicit interpreter paths in `thesis-project.json.tools.python`.
- Keep the virtual environment inside the thesis project by default: `.venv/`.
- Treat global `officecli` installation as a separate user-confirmed step.

## Suggested Packages

Install only what the workflow needs:

- `lxml` for robust OOXML parsing and patching.
- `python-docx` for read-only/simple copy operations on disposable copies only.
- `Pillow`, `pdf2image` for render QA when PDF conversion is available.

External tools such as LibreOffice/`soffice`, `pdftoppm`, Node.js, npm, and `officecli` are not Python packages. Record them as external dependencies.

## Workflow

1. Detect tools and write an environment report.
2. If Python is missing, stop and ask the user to install Python.
3. If no virtual environment exists, create one using `uv venv` or `python -m venv`.
4. Install Python packages with `uv pip install ...` or `<venv-python> -m pip install ...`.
5. Check `officecli`; if missing, explain the required install command for the user's platform and ask before running it.
6. Update `thesis-project.json.tools` with resolved command paths and versions.

## Do Not

- Do not install global npm packages or system packages without explicit confirmation.
- Do not assume Windows paths, PowerShell, or a fixed venv location.
- Do not make a DOCX edit just to test the environment.
- Do not claim render QA is available unless `soffice`/LibreOffice and PDF-to-image tooling are actually present.

## Final Report

Report Python, venv, `uv`, Python packages, `officecli`, office document skill availability, render QA dependencies, installed actions, skipped actions, and next recommended skill.
