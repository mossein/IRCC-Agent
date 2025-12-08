"""PDF form field extractor for analyzing IRCC form structure."""

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF
from pypdf import PdfReader

logger = logging.getLogger(__name__)


class FormType(Enum):
    """Type of PDF form."""

    ACROFORM = "acroform"
    XFA = "xfa"
    NONE = "none"


class FieldType(Enum):
    """Type of form field."""

    TEXT = "text"
    CHECKBOX = "checkbox"
    RADIO = "radio"
    DROPDOWN = "dropdown"
    SIGNATURE = "signature"
    UNKNOWN = "unknown"


@dataclass
class FormField:
    """Represents a form field in a PDF."""

    name: str
    field_type: FieldType
    page: int = 0
    value: Any = None
    default_value: Any = None
    options: list[str] = field(default_factory=list)  # For dropdowns/radios
    required: bool = False
    max_length: int | None = None
    tooltip: str = ""
    rect: tuple[float, float, float, float] | None = None  # x0, y0, x1, y1

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "type": self.field_type.value,
            "page": self.page,
            "value": self.value,
            "options": self.options,
            "required": self.required,
            "tooltip": self.tooltip,
        }


class FormFieldExtractor:
    """Extract form fields from PDF files."""

    def __init__(self, pdf_path: Path | str):
        """Initialize extractor with a PDF file.

        Args:
            pdf_path: Path to the PDF file.
        """
        self.pdf_path = Path(pdf_path)
        if not self.pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        self._form_type: FormType | None = None
        self._fields: list[FormField] | None = None

    @property
    def form_type(self) -> FormType:
        """Detect and return the form type."""
        if self._form_type is None:
            self._form_type = self._detect_form_type()
        return self._form_type

    def _detect_form_type(self) -> FormType:
        """Detect if PDF uses XFA or AcroForm."""
        try:
            reader = PdfReader(self.pdf_path)

            # Check for XFA
            if "/XFA" in reader.trailer.get("/Root", {}):
                return FormType.XFA

            # Check catalog for XFA
            if reader.xfa:
                return FormType.XFA

            # Check for AcroForm
            if reader.get_form_text_fields() or reader.get_fields():
                return FormType.ACROFORM

            return FormType.NONE
        except Exception as e:
            logger.warning(f"Error detecting form type: {e}")
            # Try alternative detection with PyMuPDF
            try:
                with fitz.open(self.pdf_path) as doc:
                    for page in doc:
                        if page.widgets():
                            return FormType.ACROFORM
                return FormType.NONE
            except Exception:
                return FormType.NONE

    def extract_fields(self) -> list[FormField]:
        """Extract all form fields from the PDF.

        Returns:
            List of FormField objects.
        """
        if self._fields is not None:
            return self._fields

        if self.form_type == FormType.XFA:
            logger.warning(
                "XFA form detected. XFA forms have limited support. "
                "Consider converting to AcroForm for better compatibility."
            )
            self._fields = self._extract_xfa_fields()
        elif self.form_type == FormType.ACROFORM:
            self._fields = self._extract_acroform_fields()
        else:
            self._fields = []
            logger.warning("No form fields detected in PDF")

        return self._fields

    def _extract_acroform_fields(self) -> list[FormField]:
        """Extract fields from AcroForm PDF using PyMuPDF."""
        fields = []

        with fitz.open(self.pdf_path) as doc:
            for page_num, page in enumerate(doc, start=1):
                for widget in page.widgets():
                    field = self._widget_to_field(widget, page_num)
                    if field:
                        fields.append(field)

        logger.info(f"Extracted {len(fields)} fields from AcroForm")
        return fields

    def _widget_to_field(self, widget: fitz.Widget, page_num: int) -> FormField | None:
        """Convert PyMuPDF widget to FormField."""
        try:
            # Map widget field types
            type_map = {
                fitz.PDF_WIDGET_TYPE_TEXT: FieldType.TEXT,
                fitz.PDF_WIDGET_TYPE_CHECKBOX: FieldType.CHECKBOX,
                fitz.PDF_WIDGET_TYPE_RADIOBUTTON: FieldType.RADIO,
                fitz.PDF_WIDGET_TYPE_COMBOBOX: FieldType.DROPDOWN,
                fitz.PDF_WIDGET_TYPE_LISTBOX: FieldType.DROPDOWN,
                fitz.PDF_WIDGET_TYPE_SIGNATURE: FieldType.SIGNATURE,
            }

            field_type = type_map.get(widget.field_type, FieldType.UNKNOWN)
            rect = widget.rect

            return FormField(
                name=widget.field_name or f"field_{page_num}_{id(widget)}",
                field_type=field_type,
                page=page_num,
                value=widget.field_value,
                options=list(widget.choice_values) if widget.choice_values else [],
                tooltip=widget.field_type_string or "",
                rect=(rect.x0, rect.y0, rect.x1, rect.y1) if rect else None,
            )
        except Exception as e:
            logger.warning(f"Error extracting widget: {e}")
            return None

    def _extract_xfa_fields(self) -> list[FormField]:
        """Extract fields from XFA PDF using the XFA XML parser."""
        fields = []

        try:
            from ircc_agent.pdf.xfa_parser import XFAParser

            parser = XFAParser(self.pdf_path)
            xfa_fields = parser.extract_fields()

            if xfa_fields:
                logger.info(f"Extracted {len(xfa_fields)} fields from XFA template")

                # Map XFA field type to FieldType enum
                type_map = {
                    "text": FieldType.TEXT,
                    "number": FieldType.TEXT,  # Treat as text for now
                    "checkbox": FieldType.CHECKBOX,
                    "dropdown": FieldType.DROPDOWN,
                    "date": FieldType.TEXT,  # Treat as text for now
                    "signature": FieldType.SIGNATURE,
                }

                for xfa_field in xfa_fields:
                    field_type = type_map.get(xfa_field.field_type, FieldType.UNKNOWN)
                    fields.append(
                        FormField(
                            name=xfa_field.path,  # Use full path as name
                            field_type=field_type,
                            value=xfa_field.value,
                            options=xfa_field.options or [],
                            tooltip=xfa_field.tooltip or "",
                        )
                    )
                return fields

            # Fallback to basic pypdf extraction
            logger.warning("XFA parser returned no fields, falling back to basic extraction")
            reader = PdfReader(self.pdf_path)
            if reader.get_fields():
                for name, field_data in reader.get_fields().items():
                    field_type = self._map_pypdf_field_type(field_data)
                    fields.append(
                        FormField(
                            name=name,
                            field_type=field_type,
                            value=field_data.get("/V"),
                            default_value=field_data.get("/DV"),
                        )
                    )

        except Exception as e:
            logger.error(f"Error extracting XFA fields: {e}")

        return fields

    def _map_pypdf_field_type(self, field_data: dict) -> FieldType:
        """Map pypdf field type to FieldType enum."""
        ft = str(field_data.get("/FT", ""))
        if ft == "/Tx":
            return FieldType.TEXT
        elif ft == "/Btn":
            # Could be checkbox or radio
            ff = field_data.get("/Ff", 0)
            if isinstance(ff, int) and ff & (1 << 15):  # Radio button flag
                return FieldType.RADIO
            return FieldType.CHECKBOX
        elif ft == "/Ch":
            return FieldType.DROPDOWN
        elif ft == "/Sig":
            return FieldType.SIGNATURE
        return FieldType.UNKNOWN

    def get_field_names(self) -> list[str]:
        """Get list of all field names."""
        return [f.name for f in self.extract_fields()]

    def get_fields_by_type(self, field_type: FieldType) -> list[FormField]:
        """Get fields of a specific type."""
        return [f for f in self.extract_fields() if f.field_type == field_type]

    def to_dict(self) -> dict:
        """Export extracted fields as dictionary."""
        return {
            "pdf_path": str(self.pdf_path),
            "form_type": self.form_type.value,
            "field_count": len(self.extract_fields()),
            "fields": [f.to_dict() for f in self.extract_fields()],
        }
