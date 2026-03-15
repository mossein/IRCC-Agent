"""AcroForm filling via PyMuPDF."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import fitz  # PyMuPDF


def fill(
    pdf_path: str | Path,
    field_values: dict[str, Any],
    output_path: str | Path,
) -> dict[str, Any]:
    """Fill an AcroForm PDF using PyMuPDF widgets.

    Returns a result dict: {filled_count, skipped, output_path}.
    """
    pdf_path = Path(pdf_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    filled = 0
    skipped: list[str] = []

    with fitz.open(pdf_path) as doc:
        for page in doc:
            for widget in page.widgets():
                name = widget.field_name
                if not name or name not in field_values:
                    continue

                value = field_values[name]
                if value is None or str(value).strip() == "":
                    skipped.append(name)
                    continue

                try:
                    if widget.field_type == fitz.PDF_WIDGET_TYPE_CHECKBOX:
                        widget.field_value = bool(value)
                    elif widget.field_type == fitz.PDF_WIDGET_TYPE_RADIOBUTTON:
                        widget.field_value = str(value)
                    else:
                        widget.field_value = str(value)
                    widget.update()
                    filled += 1
                except Exception:
                    skipped.append(name)

        doc.save(str(output_path))

    return {
        "filled_count": filled,
        "skipped": skipped,
        "output_path": str(output_path),
    }
