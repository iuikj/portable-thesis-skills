# Toolchain Notes

Use this reference when deciding what to install or record.

## Python

Use an explicit interpreter path for every script. Avoid requiring environment activation.

Preferred command shape:

```bash
<venv-python> -m pip install lxml python-docx Pillow pdf2image
<venv-python> <skill-dir>/scripts/some_script.py --help
```

## uv

If `uv` is available:

```bash
uv venv .venv
uv pip install --python .venv/bin/python lxml python-docx Pillow pdf2image
```

On Windows, the interpreter is usually `.venv\Scripts\python.exe`; on Unix-like systems it is `.venv/bin/python`.

## officecli

`officecli` is an external CLI. Check it with:

```bash
officecli --version
officecli validate <copy.docx>
```

For read-only checks, disable resident/background behavior when the tool supports it:

```bash
OFFICECLI_NO_AUTO_RESIDENT=1 officecli validate <copy.docx>
```

## Render QA

Render QA requires external conversion, not just Python packages:

- LibreOffice or `soffice` for DOCX to PDF.
- `pdftoppm` or equivalent for PDF to images.
- `pdf2image` and `Pillow` for Python image inspection.

If any dependency is missing, report render QA as not completed.
