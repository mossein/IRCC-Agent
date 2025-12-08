"""XFA form parser for extracting fields from IRCC XFA-based PDFs."""

import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pypdf import PdfReader, PdfWriter

logger = logging.getLogger(__name__)

# XFA namespaces
XFA_NAMESPACES = {
    "xfa": "http://www.xfa.org/schema/xfa-data/1.0/",
    "xdp": "http://ns.adobe.com/xdp/",
    "template": "http://www.xfa.org/schema/xfa-template/2.8/",
    "form": "http://www.xfa.org/schema/xfa-form/2.8/",
}


@dataclass
class XFAField:
    """Represents a field from an XFA form."""
    name: str
    path: str  # Full path like "Page1.PersonalDetails.FamilyName"
    field_type: str  # "text", "checkbox", "dropdown", etc.
    value: Any = None
    options: list[str] | None = None  # For dropdowns
    tooltip: str | None = None


class XFAParser:
    """Parse XFA forms to extract field definitions and values."""

    def __init__(self, pdf_path: Path | str):
        """Initialize parser.
        
        Args:
            pdf_path: Path to the XFA PDF.
        """
        self.pdf_path = Path(pdf_path)
        self._reader: PdfReader | None = None
        self._xfa_streams: dict[str, bytes] = {}
        self._template_xml: ET.Element | None = None
        self._form_xml: ET.Element | None = None
        self._datasets_xml: ET.Element | None = None

    @property
    def reader(self) -> PdfReader:
        """Get PDF reader."""
        if self._reader is None:
            self._reader = PdfReader(str(self.pdf_path))
        return self._reader

    def is_xfa(self) -> bool:
        """Check if PDF contains XFA."""
        try:
            acro_form = self.reader.trailer["/Root"].get("/AcroForm")
            if acro_form and "/XFA" in acro_form:
                return True
        except Exception:
            pass
        return False

    def extract_xfa_streams(self) -> dict[str, bytes]:
        """Extract all XFA data streams from the PDF."""
        if self._xfa_streams:
            return self._xfa_streams

        try:
            xfa = self.reader.trailer["/Root"]["/AcroForm"]["/XFA"]
            
            # XFA is an array: [name1, stream1, name2, stream2, ...]
            current_name = None
            for item in xfa:
                if isinstance(item, str):
                    current_name = item
                elif hasattr(item, "get_data") or hasattr(item, "get_object"):
                    if hasattr(item, "get_object"):
                        item = item.get_object()
                    if hasattr(item, "get_data"):
                        data = item.get_data()
                        if current_name:
                            self._xfa_streams[current_name] = data
                            current_name = None

            logger.info(f"Extracted {len(self._xfa_streams)} XFA streams: {list(self._xfa_streams.keys())}")

        except Exception as e:
            logger.error(f"Failed to extract XFA: {e}")

        return self._xfa_streams

    def get_template_xml(self) -> ET.Element | None:
        """Get the XFA template (field definitions)."""
        if self._template_xml is not None:
            return self._template_xml

        streams = self.extract_xfa_streams()
        if "template" in streams:
            try:
                xml_str = streams["template"].decode("utf-8", errors="ignore")
                # Clean up XML
                xml_str = re.sub(r'<\?[^>]+\?>', '', xml_str)  # Remove processing instructions
                self._template_xml = ET.fromstring(xml_str)
                return self._template_xml
            except ET.ParseError as e:
                logger.error(f"Failed to parse template XML: {e}")

        return None

    def get_form_xml(self) -> ET.Element | None:
        """Get the XFA form (current values)."""
        if self._form_xml is not None:
            return self._form_xml

        streams = self.extract_xfa_streams()
        if "form" in streams:
            try:
                xml_str = streams["form"].decode("utf-8", errors="ignore")
                self._form_xml = ET.fromstring(xml_str)
                return self._form_xml
            except ET.ParseError as e:
                logger.error(f"Failed to parse form XML: {e}")

        return None

    def extract_fields(self) -> list[XFAField]:
        """Extract all fields from the XFA form.
        
        Returns:
            List of XFAField objects.
        """
        fields = []
        template = self.get_template_xml()

        if template is None:
            logger.warning("No template XML found")
            return fields

        # Find all field elements in template
        self._extract_fields_recursive(template, "", fields)

        logger.info(f"Extracted {len(fields)} XFA fields")
        return fields

    def _extract_fields_recursive(
        self,
        element: ET.Element,
        path_prefix: str,
        fields: list[XFAField],
    ):
        """Recursively extract fields from XML element."""
        # Get element name (without namespace)
        tag = element.tag.split("}")[-1] if "}" in element.tag else element.tag
        name = element.get("name", "")

        # Build path
        current_path = f"{path_prefix}.{name}" if path_prefix and name else (path_prefix or name)

        # Check if this is a field element
        if tag == "field":
            field_type = self._determine_field_type(element)
            tooltip = self._get_tooltip(element)
            options = self._get_dropdown_options(element)
            value = self._get_field_value(element)

            fields.append(XFAField(
                name=name,
                path=current_path,
                field_type=field_type,
                value=value,
                options=options,
                tooltip=tooltip,
            ))

        # Recurse into children
        for child in element:
            self._extract_fields_recursive(child, current_path, fields)

    def _determine_field_type(self, element: ET.Element) -> str:
        """Determine field type from XFA element."""
        # Look for ui child
        for child in element:
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if tag == "ui":
                for ui_child in child:
                    ui_tag = ui_child.tag.split("}")[-1] if "}" in ui_child.tag else ui_child.tag
                    if ui_tag == "textEdit":
                        return "text"
                    elif ui_tag == "checkButton":
                        return "checkbox"
                    elif ui_tag == "choiceList":
                        return "dropdown"
                    elif ui_tag == "dateTimeEdit":
                        return "date"
                    elif ui_tag == "numericEdit":
                        return "number"
                    elif ui_tag == "signature":
                        return "signature"
        return "text"  # Default

    def _get_tooltip(self, element: ET.Element) -> str | None:
        """Get tooltip/description from field."""
        for child in element:
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if tag == "assist":
                for assist_child in child:
                    assist_tag = assist_child.tag.split("}")[-1] if "}" in assist_child.tag else assist_child.tag
                    if assist_tag == "toolTip":
                        return assist_child.text
        return None

    def _get_dropdown_options(self, element: ET.Element) -> list[str] | None:
        """Get dropdown options for choice fields."""
        options = []
        for child in element:
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if tag == "items":
                for item in child:
                    item_tag = item.tag.split("}")[-1] if "}" in item.tag else item.tag
                    if item_tag == "text" and item.text:
                        options.append(item.text)
        return options if options else None

    def _get_field_value(self, element: ET.Element) -> Any:
        """Get current value from field."""
        for child in element:
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if tag == "value":
                for value_child in child:
                    if value_child.text:
                        return value_child.text
        return None

    def get_field_summary(self) -> dict[str, int]:
        """Get summary of field types."""
        fields = self.extract_fields()
        summary = {}
        for field in fields:
            summary[field.field_type] = summary.get(field.field_type, 0) + 1
        return summary


def test_xfa_parser(pdf_path: str):
    """Test the XFA parser on a PDF."""
    parser = XFAParser(pdf_path)
    
    print(f"Is XFA: {parser.is_xfa()}")
    print(f"XFA Streams: {list(parser.extract_xfa_streams().keys())}")
    
    fields = parser.extract_fields()
    print(f"\nTotal fields: {len(fields)}")
    print(f"Field types: {parser.get_field_summary()}")
    
    print("\nFirst 20 fields:")
    for field in fields[:20]:
        value_str = f" = '{field.value}'" if field.value else ""
        print(f"  {field.path}: {field.field_type}{value_str}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        test_xfa_parser(sys.argv[1])
