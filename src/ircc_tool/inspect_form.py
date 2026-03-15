"""Extract form field metadata from IRCC PDFs (AcroForm and XFA)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF

from ircc_tool.xfa import parse_xfa_fields


def detect_form_type(pdf_path: Path) -> str:
    """Return 'xfa', 'acroform', or 'none'."""
    import pikepdf

    with pikepdf.open(pdf_path) as pdf:
        try:
            acroform = pdf.Root.get("/AcroForm")
            if acroform and "/XFA" in acroform:
                return "xfa"
        except Exception:
            pass

    # Fall back to PyMuPDF widget check for AcroForm
    with fitz.open(pdf_path) as doc:
        for page in doc:
            if page.widgets():
                return "acroform"

    return "none"


def _extract_acroform_fields(pdf_path: Path) -> list[dict[str, Any]]:
    """Extract fields from an AcroForm PDF via PyMuPDF widgets."""
    type_map = {
        fitz.PDF_WIDGET_TYPE_TEXT: "text",
        fitz.PDF_WIDGET_TYPE_CHECKBOX: "checkbox",
        fitz.PDF_WIDGET_TYPE_RADIOBUTTON: "radio",
        fitz.PDF_WIDGET_TYPE_COMBOBOX: "dropdown",
        fitz.PDF_WIDGET_TYPE_LISTBOX: "dropdown",
        fitz.PDF_WIDGET_TYPE_SIGNATURE: "signature",
    }

    fields: list[dict[str, Any]] = []
    with fitz.open(pdf_path) as doc:
        for page_num, page in enumerate(doc, start=1):
            for widget in page.widgets():
                name = widget.field_name
                if not name:
                    continue
                fields.append({
                    "name": name,
                    "path": name,
                    "type": type_map.get(widget.field_type, "unknown"),
                    "page": page_num,
                    "value": widget.field_value or None,
                    "options": list(widget.choice_values) if widget.choice_values else [],
                    "tooltip": widget.field_type_string or "",
                    "required": False,
                })
    return fields


def inspect(pdf_path: str | Path) -> dict[str, Any]:
    """Inspect a PDF form and return structured field information.

    Returns a dict with keys: pdf_path, form_type, field_count, fields.
    """
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")

    form_type = detect_form_type(path)

    if form_type == "xfa":
        fields = parse_xfa_fields(path)
    elif form_type == "acroform":
        fields = _extract_acroform_fields(path)
    else:
        fields = []

    return {
        "pdf_path": str(path),
        "form_type": form_type,
        "field_count": len(fields),
        "fields": fields,
    }


def inspect_to_stdout(pdf_path: str | Path) -> None:
    """Run inspect and write JSON to stdout, diagnostics to stderr."""
    try:
        result = inspect(pdf_path)
        json.dump(result, sys.stdout, indent=2)
        sys.stdout.write("\n")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
