"""PDF form filler for populating IRCC forms with extracted data."""

import logging
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF
from pypdf import PdfReader, PdfWriter

from ircc_agent.pdf.extractor import FormFieldExtractor, FormType

logger = logging.getLogger(__name__)


class PDFFiller:
    """Fill PDF forms with provided data."""

    def __init__(self, pdf_path: Path | str):
        """Initialize filler with a PDF form.

        Args:
            pdf_path: Path to the PDF form to fill.
        """
        self.pdf_path = Path(pdf_path)
        if not self.pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        self.extractor = FormFieldExtractor(pdf_path)

    @property
    def form_type(self) -> FormType:
        """Get the form type."""
        return self.extractor.form_type

    def fill(
        self,
        data: dict[str, Any],
        output_path: Path | str,
        flatten: bool = False,
    ) -> Path:
        """Fill the PDF form with provided data.

        Args:
            data: Dictionary mapping field names to values.
            output_path: Path for the filled PDF output.
            flatten: Whether to flatten the form (make fields non-editable).

        Returns:
            Path to the filled PDF.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if self.form_type == FormType.XFA:
            logger.warning(
                "XFA form detected. Form filling may be limited. "
                "Consider converting to AcroForm for reliable filling."
            )
            return self._fill_with_pymupdf(data, output_path, flatten)
        elif self.form_type == FormType.ACROFORM:
            return self._fill_with_pymupdf(data, output_path, flatten)
        else:
            raise ValueError("PDF does not contain fillable form fields")

    def _fill_with_pymupdf(
        self,
        data: dict[str, Any],
        output_path: Path,
        flatten: bool = False,
    ) -> Path:
        """Fill form using PyMuPDF (fitz)."""
        filled_count = 0

        with fitz.open(self.pdf_path) as doc:
            for page in doc:
                for widget in page.widgets():
                    field_name = widget.field_name
                    if field_name and field_name in data:
                        value = data[field_name]

                        try:
                            if widget.field_type == fitz.PDF_WIDGET_TYPE_CHECKBOX:
                                # Handle checkbox - set to checked if truthy
                                widget.field_value = bool(value)
                            elif widget.field_type == fitz.PDF_WIDGET_TYPE_RADIOBUTTON:
                                # Handle radio button
                                widget.field_value = str(value)
                            else:
                                # Text and other fields
                                widget.field_value = str(value) if value is not None else ""

                            widget.update()
                            filled_count += 1
                        except Exception as e:
                            logger.warning(f"Error filling field '{field_name}': {e}")

            # Optionally flatten the form
            if flatten:
                for page in doc:
                    for widget in page.widgets():
                        # Remove widget interactivity
                        widget.field_flags = 1  # ReadOnly flag
                        widget.update()

            doc.save(str(output_path))

        logger.info(f"Filled {filled_count} fields, saved to {output_path}")
        return output_path

    def _fill_with_pypdf(
        self,
        data: dict[str, Any],
        output_path: Path,
        flatten: bool = False,
    ) -> Path:
        """Fill form using pypdf (alternative method)."""
        reader = PdfReader(self.pdf_path)
        writer = PdfWriter()

        # Copy pages
        for page in reader.pages:
            writer.add_page(page)

        # Update form fields
        writer.update_page_form_field_values(writer.pages[0], data)

        # Write output
        with open(output_path, "wb") as f:
            writer.write(f)

        logger.info(f"Filled form saved to {output_path}")
        return output_path

    def preview_fill(self, data: dict[str, Any]) -> dict[str, Any]:
        """Preview what fields would be filled.

        Args:
            data: Dictionary mapping field names to values.

        Returns:
            Dictionary showing which fields will be filled and which are missing.
        """
        fields = self.extractor.extract_fields()
        field_names = {f.name for f in fields}

        filled = {}
        missing = {}
        extra = {}

        for name, value in data.items():
            if name in field_names:
                filled[name] = value
            else:
                extra[name] = value

        for field in fields:
            if field.name not in data:
                missing[field.name] = {
                    "type": field.field_type.value,
                    "options": field.options,
                }

        return {
            "will_fill": filled,
            "missing_in_form": extra,
            "unfilled_fields": missing,
        }

    def get_field_names(self) -> list[str]:
        """Get list of all field names in the form."""
        return self.extractor.get_field_names()
