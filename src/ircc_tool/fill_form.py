"""Orchestrator: detect form type and route to the right filler."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from ircc_tool import acroform, xfa
from ircc_tool.inspect_form import detect_form_type


def fill(
    pdf_path: str | Path,
    field_values: dict[str, Any],
    output_path: str | Path,
) -> dict[str, Any]:
    """Fill a PDF form, auto-detecting AcroForm vs XFA.

    Returns a result dict with filled_count, skipped, output_path, form_type.
    """
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")

    form_type = detect_form_type(path)

    if form_type == "xfa":
        result = xfa.fill(path, field_values, output_path)
    elif form_type == "acroform":
        result = acroform.fill(path, field_values, output_path)
    else:
        raise ValueError("PDF does not contain fillable form fields")

    result["form_type"] = form_type
    return result


def fill_to_stdout(
    pdf_path: str | Path,
    data_json_path: str | Path,
    output_path: str | Path,
) -> None:
    """Load data JSON, fill, and write result JSON to stdout."""
    try:
        with open(data_json_path) as f:
            field_values = json.load(f)

        result = fill(pdf_path, field_values, output_path)
        json.dump(result, sys.stdout, indent=2)
        sys.stdout.write("\n")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
