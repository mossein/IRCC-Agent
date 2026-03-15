"""CLI entry point for ircc-tool: inspect and fill IRCC PDF forms."""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="ircc-tool",
        description="Inspect and fill IRCC PDF forms (AcroForm & XFA)",
    )
    sub = parser.add_subparsers(dest="command")

    # --- inspect ---
    p_inspect = sub.add_parser("inspect", help="Extract form fields as JSON")
    p_inspect.add_argument("pdf", help="Path to PDF form")

    # --- fill ---
    p_fill = sub.add_parser("fill", help="Fill a PDF form from a JSON file")
    p_fill.add_argument("pdf", help="Path to PDF form")
    p_fill.add_argument("data", help="Path to JSON file with field values")
    p_fill.add_argument("-o", "--output", required=True, help="Output PDF path")

    args = parser.parse_args(argv)

    if args.command == "inspect":
        from ircc_tool.inspect_form import inspect_to_stdout

        inspect_to_stdout(args.pdf)

    elif args.command == "fill":
        from ircc_tool.fill_form import fill_to_stdout

        fill_to_stdout(args.pdf, args.data, args.output)

    else:
        parser.print_help()
        sys.exit(1)
